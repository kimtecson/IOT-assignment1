#!/usr/bin/env python3
"""
SensorMonitor.py
RMIT COSC2674/2755 – Programming Internet of Things
Individual Assignment 1 – Task 3
Student Name : [Your Name]
Student ID   : [Your Student ID]

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

Fixes applied:
  1. Improved pitch/roll normalisation (handles both >180 and <-180)
  2. Yaw wrap-around logic for circular ranges
  3. Yaw smoothing via moving average (deque of last 5 readings)
  4. Separate DB connect method for reliability
  5. Display renders once per interval, not every tick
  6. Sensor error handling – skips failed reads gracefully
  7. Pause/resume LED feedback (PAUSED / RESUME message)
  8. Resource cleanup on exit (joystick handler removed)
  9. Config label validation for all sections
"""

import json
import os
import sqlite3
import sys
import time
import threading
from collections import deque
from datetime import datetime

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
        if not os.path.exists(self._path):
            self._abort(f"Config file not found: {self._path}")

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

        # Numeric range validation
        for section in ["temperature", "humidity", "pressure"]:
            mn = data[section]["min"]
            mx = data[section]["max"]
            if not isinstance(mn, (int, float)) or not isinstance(mx, (int, float)):
                self._abort(f"'{section}' min/max must be numeric.")
            if mn >= mx:
                self._abort(f"'{section}' min ({mn}) must be less than max ({mx}).")

        # Fix 10: validate label keys for each section
        for section in ["temperature", "humidity", "pressure"]:
            for label in ["low", "ok", "high"]:
                if label not in data[section]["labels"]:
                    self._abort(f"Missing label '{label}' in config section '{section}'.")
        for label in ["aligned", "tilted"]:
            if label not in data["orientation"]["labels"]:
                self._abort(f"Missing label '{label}' in config section 'orientation'.")

        ori = data["orientation"]
        for key in ["pitch_limit", "roll_limit"]:
            if not (0 < ori[key] <= 90):
                self._abort(f"orientation.{key} must be between 0 and 90 degrees.")

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
        self._connect()  # Fix 4: separate connect method

    def _connect(self):
        """Create database connection and ensure table exists."""
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
        mn  = self._cfg[section]["min"]
        mx  = self._cfg[section]["max"]
        lbl = self._cfg[section]["labels"]
        if value < mn:
            return lbl["low"],  BLUE
        elif value > mx:
            return lbl["high"], RED
        else:
            return lbl["ok"],   GREEN

    @staticmethod
    def _normalise(angle: float) -> float:
        """Fix 1: normalise any angle to -180..+180 range."""
        if angle > 180:
            angle -= 360
        elif angle < -180:
            angle += 360
        return angle

    def classify_orientation(self, pitch: float, roll: float, yaw: float) -> tuple:
        ori         = self._cfg["orientation"]
        lbl         = ori["labels"]
        pitch_limit = ori["pitch_limit"]
        roll_limit  = ori["roll_limit"]
        yaw_min     = ori["yaw_min"]
        yaw_max     = ori["yaw_max"]

        # Fix 1: improved normalisation
        norm_pitch = self._normalise(pitch)
        norm_roll  = self._normalise(roll)

        # Fix 2: yaw wrap-around logic
        if yaw_min <= yaw_max:
            yaw_ok = yaw_min <= yaw <= yaw_max
        else:
            # handles wrap-around e.g. 350° to 10°
            yaw_ok = yaw >= yaw_min or yaw <= yaw_max

        tilted = (
            abs(norm_pitch) > pitch_limit
            or abs(norm_roll) > roll_limit
            or not yaw_ok
        )

        if tilted:
            return lbl["tilted"], AMBER
        return lbl["aligned"], GREEN


# ═══════════════════════════ DisplayManager ═══════════════════════════

class DisplayManager:
    """
    Cycles through 4 LED screens every DISPLAY_INTERVAL seconds.
    Fix 5: renders only once per interval, not on every tick.
    """

    SCREENS = ["temperature", "humidity", "pressure", "orientation"]

    def __init__(self, sense: SenseHat):
        self._sense        = sense
        self._screen_idx   = 0
        self._last_switch  = time.time()
        self._reading      = None
        self._paused       = False
        self._needs_render = True   # render immediately on first reading
        self._lock         = threading.Lock()

    def update_reading(self, reading: dict):
        with self._lock:
            self._reading      = reading
            self._needs_render = True

    def set_paused(self, paused: bool):
        with self._lock:
            self._paused = paused

    def tick(self):
        """Advances screen every DISPLAY_INTERVAL; renders once per switch."""
        with self._lock:
            paused       = self._paused
            reading      = self._reading
            needs_render = self._needs_render

        if paused or reading is None:
            return

        now = time.time()
        # Fix 5: only switch + render once per interval
        if now - self._last_switch >= DISPLAY_INTERVAL:
            self._screen_idx  = (self._screen_idx + 1) % len(self.SCREENS)
            self._last_switch = now
            with self._lock:
                self._needs_render = True
            needs_render = True

        if needs_render:
            screen = self.SCREENS[self._screen_idx]
            self._render(screen, reading)
            with self._lock:
                self._needs_render = False

    def _render(self, screen: str, reading: dict):
        if screen == "temperature":
            text   = f"T:{reading['temperature_cal']:.0f}"
            colour = reading["temperature_colour"]
        elif screen == "humidity":
            text   = f"H:{reading['humidity']:.0f}"
            colour = reading["humidity_colour"]
        elif screen == "pressure":
            text   = f"P:{reading['pressure']:.0f}"
            colour = reading["pressure_colour"]
        else:
            p = reading["pitch"]
            r = reading["roll"]
            y = reading["yaw"]
            text   = f"P:{p:.0f} R:{r:.0f} Y:{y:.0f}"
            colour = reading["orientation_colour"]

        self._sense.show_message(
            text,
            scroll_speed = SCROLL_SPEED,
            text_colour  = colour,
        )


# ═══════════════════════════ SensorMonitor ════════════════════════════

class SensorMonitor:
    """
    Main controller: polls sensors, classifies, logs, and drives display.
    Joystick middle press toggles pause/resume.
    """

    def __init__(self):
        loader      = ConfigLoader(CONFIG_FILE)
        self._cfg   = loader.config

        self._sense = SenseHat()
        self._sense.set_rotation(0)
        # Use all 3 sensors for best orientation accuracy
        self._sense.set_imu_config(True, True, True)

        self._db      = DatabaseManager(DB_FILE)
        self._clf     = Classifier(self._cfg)
        self._display = DisplayManager(self._sense)

        # Fix 3: yaw smoothing via moving average
        self._yaw_history = deque(maxlen=5)

        self._paused    : bool  = False
        self._running   : bool  = True
        self._last_poll : float = 0.0
        self._lock      = threading.Lock()

        self._sense.stick.direction_middle = self._handle_middle

    # ── Joystick ─────────────────────────────────────────────────────

    def _handle_middle(self, event):
        if event.action != "pressed":
            return
        with self._lock:
            self._paused = not self._paused
        paused = self._paused
        self._display.set_paused(paused)
        # Fix 7: visual feedback on pause/resume
        if paused:
            self._sense.show_message("PAUSED", text_colour=AMBER, scroll_speed=0.05)
        else:
            self._sense.show_message("RESUME", text_colour=GREEN, scroll_speed=0.05)
        print(f"[Joystick] {'PAUSED' if paused else 'RESUMED'}")

    # ── Yaw smoothing ─────────────────────────────────────────────────

    def _smooth_yaw(self, yaw: float) -> float:
        """Fix 3: moving average over last 5 yaw readings."""
        self._yaw_history.append(yaw)
        return round(sum(self._yaw_history) / len(self._yaw_history), 2)

    # ── Sensor poll ───────────────────────────────────────────────────

    def _poll(self):
        """Fix 6: wrapped in try/except – returns None on sensor failure."""
        try:
            temp_raw = self._sense.get_temperature()
            temp_cal = round(temp_raw - TEMP_OFFSET, 2)
            humidity = round(self._sense.get_humidity(), 2)
            pressure = round(self._sense.get_pressure(), 2)

            # Accelerometer for pitch/roll (no drift)
            accel = self._sense.get_accelerometer()
            pitch = round(accel["pitch"], 2)
            roll  = round(accel["roll"],  2)

            # Fix 3: smoothed yaw
            raw_yaw = self._sense.get_orientation()["yaw"]
            yaw     = self._smooth_yaw(raw_yaw)

        except Exception as e:
            print(f"[Error] Sensor read failed: {e}")
            return None  # Fix 6: skip this reading

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
            f"Ori:({pitch},{roll},{yaw}) {ori_status}"
        )
        return reading

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self):
        print("=== SensorMonitor started ===")
        print(f"Config : {CONFIG_FILE}")
        print(f"DB     : {DB_FILE}")
        print(f"Poll every {POLL_INTERVAL}s | Display cycles every {DISPLAY_INTERVAL}s")
        print("MIDDLE joystick : pause / resume  |  Ctrl+C : exit\n")

        try:
            while self._running:
                now = time.time()

                with self._lock:
                    paused = self._paused

                if not paused and (now - self._last_poll) >= POLL_INTERVAL:
                    self._last_poll = now
                    reading = self._poll()
                    if reading:  # Fix 6: only log successful reads
                        self._db.log(reading)
                        self._display.update_reading(reading)

                self._display.tick()
                time.sleep(0.1)  # Fix 9: prevent CPU hogging

        except KeyboardInterrupt:
            print("\n[Exit] Shutting down.")
        finally:
            self._sense.clear()
            self._sense.stick.direction_middle = None  # Fix 8: cleanup handler
            self._db.close()
            print("[Exit] Display cleared. Database closed. Goodbye!")


# ═══════════════════════════ Entry Point ══════════════════════════════

if __name__ == "__main__":
    SensorMonitor().run()
