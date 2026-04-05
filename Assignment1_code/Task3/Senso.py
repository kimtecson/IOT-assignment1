#!/usr/bin/env python3
"""
Continuously monitors Sense HAT environmental sensors and orientation.
Classifies readings against user-defined thresholds in enviro_config.json.
Logs all readings to a local SQLite database (envirotrack.db).
Provides colour-coded real-time LED matrix feedback.
Joystick middle press pauses / resumes sensing and display.

LED display cycle (every 5 seconds)
-------------------------------------
  Screen 1 : T:<temp>   – green=Comfortable, blue=Low, red=High
  Screen 2 : H:<humid>  – green=Comfortable, blue=Low, red=High
  Screen 3 : P:<press>  – green=Normal,      blue=Low, red=High
  Screen 4 : orientation – green=Aligned, amber=Tilted
"""

import json
import math
import os
import sqlite3
import sys
import time
import threading
from datetime import datetime
from collections import deque

try:
    from sense_hat import SenseHat
except ImportError:
    from sense_emu import SenseHat


# ═══════════════════════════ Constants ════════════════════════════════

CONFIG_FILE      = os.path.join(os.path.dirname(__file__), "enviro_config.json")
DB_FILE          = os.path.join(os.path.dirname(__file__), "envirotrack.db")
POLL_INTERVAL    = 10.0   # seconds between sensor reads
DISPLAY_INTERVAL = 5.0    # seconds each LED screen is shown
TEMP_OFFSET      = 2.0    # °C subtracted to correct for Pi internal heat
SCROLL_SPEED     = 0.06

# LED colours
GREEN  = (0,   200,   0)
RED    = (200,   0,   0)
BLUE   = (0,    80, 220)
AMBER  = (255, 140,   0)
WHITE  = (255, 255, 255)


# ═══════════════════════════ Config Loader ════════════════════════════

class ConfigLoader:
    """Loads and validates enviro_config.json."""

    REQUIRED = {
        "temperature": ["min", "max", "labels"],
        "humidity":    ["min", "max", "labels"],
        "pressure":    ["min", "max", "labels"],
        "orientation": ["pitch_limit", "roll_limit", "yaw_min", "yaw_max", "labels"],
    }

    def __init__(self, path: str):
        self._path = path
        self.config = self._load()

    def _load(self) -> dict:
        # File existence check
        if not os.path.exists(self._path):
            self._abort(f"Config file not found: {self._path}")

        # JSON parse check
        try:
            with open(self._path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            self._abort(f"Config file is malformed JSON: {e}")

        # Structure validation
        for section, keys in self.REQUIRED.items():
            if section not in data:
                self._abort(f"Missing section '{section}' in config.")
            for key in keys:
                if key not in data[section]:
                    self._abort(f"Missing key '{key}' in config section '{section}'.")

            # Check label structure
            if "labels" in data[section]:
                if section == "orientation":
                    required_labels = ["aligned", "tilted"]
                else:
                    required_labels = ["low", "ok", "high"]

                for label in required_labels:
                    if label not in data[section]["labels"]:
                        self._abort(f"Missing label '{label}' in config section '{section}'.")

        # Numeric range validation
        for section in ["temperature", "humidity", "pressure"]:
            mn = data[section]["min"]
            mx = data[section]["max"]
            if not isinstance(mn, (int, float)) or not isinstance(mx, (int, float)):
                self._abort(f"'{section}' min/max must be numeric.")
            if mn >= mx:
                self._abort(f"'{section}' min ({mn}) must be less than max ({mx}).")

        ori = data["orientation"]
        for key in ["pitch_limit", "roll_limit"]:
            if not (0 < ori[key] <= 90):
                self._abort(f"orientation.{key} must be between 0 and 90 degrees.")
        if not (0 <= ori["yaw_min"] < ori["yaw_max"] <= 360):
            self._abort("orientation yaw_min/yaw_max must be within 0-360 and min < max.")

        print("[Config] Loaded and validated successfully.")
        return data

    @staticmethod
    def _abort(msg: str):
        print(f"[Config ERROR] {msg}")
        sys.exit(1)


# ═══════════════════════════ Database Manager ═════════════════════════

class DatabaseManager:
    """Handles SQLite connection, table creation, and parameterised inserts."""

    CREATE_SQL = """
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp           TEXT    NOT NULL,
            temperature_raw     REAL    NOT NULL,
            temperature_cal     REAL    NOT NULL,
            temperature_status  TEXT    NOT NULL,
            humidity            REAL    NOT NULL,
            humidity_status     TEXT    NOT NULL,
            pressure            REAL    NOT NULL,
            pressure_status     TEXT    NOT NULL,
            pitch               REAL    NOT NULL,
            roll                REAL    NOT NULL,
            yaw                 REAL    NOT NULL,
            orientation_status  TEXT    NOT NULL
        );
    """

    INSERT_SQL = """
        INSERT INTO sensor_readings (
            timestamp,
            temperature_raw, temperature_cal, temperature_status,
            humidity,        humidity_status,
            pressure,        pressure_status,
            pitch, roll, yaw, orientation_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    def __init__(self, db_path: str):
        self._path = db_path
        self._conn = None
        self._lock = threading.Lock()
        self._connect()

    def _connect(self):
        """Create database connection"""
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._create_table()
        print(f"[DB] Connected to {self._path}")

    def _create_table(self):
        with self._lock:
            self._conn.execute(self.CREATE_SQL)
            self._conn.commit()
        print("[DB] Table ready.")

    def log(self, reading: dict):
        """Insert one sensor reading using parameterised query."""
        params = (
            reading["timestamp"],
            reading["temperature_raw"],
            reading["temperature_cal"],
            reading["temperature_status"],
            reading["humidity"],
            reading["humidity_status"],
            reading["pressure"],
            reading["pressure_status"],
            reading["pitch"],
            reading["roll"],
            reading["yaw"],
            reading["orientation_status"],
        )
        with self._lock:
            self._conn.execute(self.INSERT_SQL, params)
            self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()


# ═══════════════════════════ Classifier ═══════════════════════════════

class Classifier:
    """Classifies sensor readings against config thresholds."""

    def __init__(self, config: dict):
        self._cfg = config

    def classify_env(self, value: float, section: str) -> tuple:
        """
        Returns (label, colour) for temperature / humidity / pressure.
        """
        mn  = self._cfg[section]["min"]
        mx  = self._cfg[section]["max"]
        lbl = self._cfg[section]["labels"]

        if value < mn:
            return lbl["low"],  BLUE
        elif value > mx:
            return lbl["high"], RED
        else:
            return lbl["ok"],   GREEN

    def classify_orientation(self, pitch: float, roll: float, yaw: float) -> tuple:
        """
        Returns (label, colour) for orientation.
        Normalises pitch/roll to -180..180 range and handles circular yaw.
        """
        ori         = self._cfg["orientation"]
        lbl         = ori["labels"]
        pitch_limit = ori["pitch_limit"]
        roll_limit  = ori["roll_limit"]
        yaw_min     = ori["yaw_min"]
        yaw_max     = ori["yaw_max"]

        # Normalise pitch and roll to -180..180 range
        norm_pitch = pitch
        norm_roll = roll

        if norm_pitch > 180:
            norm_pitch -= 360
        elif norm_pitch < -180:
            norm_pitch += 360

        if norm_roll > 180:
            norm_roll -= 360
        elif norm_roll < -180:
            norm_roll += 360

        # Check if within limits
        pitch_ok = abs(norm_pitch) <= pitch_limit
        roll_ok = abs(norm_roll) <= roll_limit

        # Handle yaw (circular)
        if yaw_min <= yaw_max:
            yaw_ok = yaw_min <= yaw <= yaw_max
        else:
            # Handle wrap-around case (e.g., 350° to 10°)
            yaw_ok = yaw >= yaw_min or yaw <= yaw_max

        tilted = not (pitch_ok and roll_ok and yaw_ok)

        if tilted:
            return lbl["tilted"],  AMBER
        return lbl["aligned"], GREEN


# ═══════════════════════════ DisplayManager ═══════════════════════════

class DisplayManager:
    """
    Cycles through 4 LED screens every DISPLAY_INTERVAL seconds.
    All sense.show_message calls happen here.
    """

    SCREENS = ["temperature", "humidity", "pressure", "orientation"]

    def __init__(self, sense: SenseHat):
        self._sense       = sense
        self._screen_idx  = 0
        self._last_switch = time.time()
        self._last_display_time = time.time()  # Track when display started
        self._reading     = None          # latest reading dict
        self._paused      = False
        self._lock        = threading.Lock()
        self._current_text = ""
        self._displaying = False

    def update_reading(self, reading: dict):
        with self._lock:
            self._reading = reading

    def set_paused(self, paused: bool):
        with self._lock:
            self._paused = paused
            if paused:
                self._sense.clear()  # Clear display when paused

    def tick(self):
        """Call from main loop – advances screen and renders if due."""
        with self._lock:
            paused  = self._paused
            reading = self._reading

        if paused or reading is None:
            return

        now = time.time()

        # Only switch screens every DISPLAY_INTERVAL seconds
        if now - self._last_switch >= DISPLAY_INTERVAL:
            self._screen_idx = (self._screen_idx + 1) % len(self.SCREENS)
            self._last_switch = now
            self._render_current_screen(reading)

    def _render_current_screen(self, reading: dict):
        """Render the current screen based on index"""
        screen = self.SCREENS[self._screen_idx]

        if screen == "temperature":
            text = f"T:{reading['temperature_cal']:.0f}"
            colour = reading.get('temperature_colour', GREEN)
        elif screen == "humidity":
            text = f"H:{reading['humidity']:.0f}"
            colour = reading.get('humidity_colour', GREEN)
        elif screen == "pressure":
            text = f"P:{reading['pressure']:.0f}"
            colour = reading.get('pressure_colour', GREEN)
        else:  # orientation
            p = reading["pitch"]
            r = reading["roll"]
            text = f"P:{p:.0f} R:{r:.0f}"
            colour = reading.get('orientation_colour', GREEN)

        # Display the message (non-blocking approach)
        self._sense.show_message(
            text,
            scroll_speed=SCROLL_SPEED,
            text_colour=colour,
            back_colour=(0, 0, 0)
        )


# ═══════════════════════════ SensorMonitor ════════════════════════════

class SensorMonitor:
    """
    Main controller: polls sensors, classifies, logs, and drives display.
    Joystick middle press toggles pause/resume.
    """

    def __init__(self):
        # Load and validate config
        loader      = ConfigLoader(CONFIG_FILE)
        self._cfg   = loader.config

        # Initialise subsystems
        self._sense   = SenseHat()
        self._sense.set_rotation(0)
        self._db      = DatabaseManager(DB_FILE)
        self._clf     = Classifier(self._cfg)
        self._display = DisplayManager(self._sense)

        self._paused      = False
        self._running     = True
        self._last_poll   = 0.0   # force immediate first poll
        self._lock        = threading.Lock()

        # Yaw smoothing
        self._yaw_history = deque(maxlen=5)

        # Joystick: middle to pause/resume
        self._sense.stick.direction_middle = self._handle_middle

        # Clear display on startup
        self._sense.clear()

    # ── Joystick ─────────────────────────────────────────────────────

    def _handle_middle(self, event):
        if event.action != "pressed":
            return
        with self._lock:
            self._paused = not self._paused
        paused = self._paused
        self._display.set_paused(paused)
        state = "PAUSED" if paused else "RESUMED"
        print(f"[Joystick] {state}")

        # Show status on LED
        if paused:
            self._sense.show_message("PAUSED", text_colour=AMBER, scroll_speed=0.05)
        else:
            self._sense.show_message("RESUME", text_colour=GREEN, scroll_speed=0.05)

    # ── Yaw smoothing ────────────────────────────────────────────────

    def _smooth_yaw(self, yaw: float) -> float:
        """Apply moving average to yaw readings to reduce noise"""
        self._yaw_history.append(yaw)
        return sum(self._yaw_history) / len(self._yaw_history)

    # ── Sensor read & classify ────────────────────────────────────────

    def _poll(self) -> dict:
        """Read all sensors, calibrate, classify, return a reading dict."""
        # Read sensors with error handling
        try:
            temp_raw = self._sense.get_temperature()
            humidity = self._sense.get_humidity()
            pressure = self._sense.get_pressure()
            ori = self._sense.get_orientation()
        except Exception as e:
            print(f"[Error] Sensor read failed: {e}")
            return None

        # Apply calibration
        temp_cal = round(temp_raw - TEMP_OFFSET, 2)
        humidity = round(humidity, 2)
        pressure = round(pressure, 2)

        # Get orientation with yaw smoothing
        pitch = round(ori["pitch"], 2)
        roll = round(ori["roll"], 2)
        raw_yaw = ori["yaw"]
        smoothed_yaw = self._smooth_yaw(raw_yaw)
        yaw = round(smoothed_yaw, 2)

        # Classify readings
        temp_status,  temp_colour  = self._clf.classify_env(temp_cal,  "temperature")
        humid_status, humid_colour = self._clf.classify_env(humidity,  "humidity")
        press_status, press_colour = self._clf.classify_env(pressure,  "pressure")
        ori_status,   ori_colour   = self._clf.classify_orientation(pitch, roll, yaw)

        reading = {
            "timestamp":           datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "temperature_raw":     round(temp_raw, 2),
            "temperature_cal":     temp_cal,
            "temperature_status":  temp_status,
            "temperature_colour":  temp_colour,
            "humidity":            humidity,
            "humidity_status":     humid_status,
            "humidity_colour":     humid_colour,
            "pressure":            pressure,
            "pressure_status":     press_status,
            "pressure_colour":     press_colour,
            "pitch":               pitch,
            "roll":                roll,
            "yaw":                 yaw,
            "orientation_status":  ori_status,
            "orientation_colour":  ori_colour,
        }

        print(
            f"[Poll] {reading['timestamp']} | "
            f"T:{temp_cal}°C ({temp_status}) | "
            f"H:{humidity}% ({humid_status}) | "
            f"P:{pressure}hPa ({press_status}) | "
            f"Ori:({pitch:.1f},{roll:.1f},{yaw:.1f}) {ori_status}"
        )
        return reading

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self):
        print("=== SensorMonitor started ===")
        print(f"Config : {CONFIG_FILE}")
        print(f"DB     : {DB_FILE}")
        print(f"Poll every {POLL_INTERVAL}s | Display cycles every {DISPLAY_INTERVAL}s")
        print("MIDDLE joystick : pause / resume  |  Ctrl+C : exit\n")

        # Force immediate first poll
        self._last_poll = time.time() - POLL_INTERVAL

        try:
            while self._running:
                now = time.time()

                with self._lock:
                    paused = self._paused

                # ── Sensor poll (every POLL_INTERVAL seconds) ──────────
                if not paused and (now - self._last_poll) >= POLL_INTERVAL:
                    self._last_poll = now
                    reading = self._poll()
                    if reading:  # Only log if read was successful
                        self._db.log(reading)
                        self._display.update_reading(reading)

                # ── Display tick ───────────────────────────────────────
                self._display.tick()

                # Small sleep to prevent CPU hogging
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n[Exit] Shutting down.")
        finally:
            self._sense.clear()
            self._sense.stick.direction_middle = None  # Remove event handler
            self._db.close()
            print("[Exit] Display cleared. Database closed. Goodbye!")


# ═══════════════════════════ Entry Point ══════════════════════════════

if __name__ == "__main__":
    SensorMonitor().run()
