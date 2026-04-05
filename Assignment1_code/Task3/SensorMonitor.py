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
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._create_table()
        print(f"[DB] Connected to {db_path}")

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

    # def classify_orientation(self, pitch: float, roll: float, yaw: float) -> tuple:
    #     """
    #     Returns (label, colour) for orientation.
    #     Pitch/roll are normalised to ±180 before comparing.
    #     """
    #     ori         = self._cfg["orientation"]
    #     lbl         = ori["labels"]
    #     pitch_limit = ori["pitch_limit"]
    #     roll_limit  = ori["roll_limit"]
    #     yaw_min     = ori["yaw_min"]
    #     yaw_max     = ori["yaw_max"]

    #     norm_pitch = pitch - 360 if pitch > 180 else pitch
    #     norm_roll  = roll  - 360 if roll  > 180 else roll

    #     tilted = (
    #         abs(norm_pitch) > pitch_limit
    #         or abs(norm_roll) > roll_limit
    #         or not (yaw_min <= yaw <= yaw_max)
    #     )

    #     if tilted:
    #         return lbl["tilted"],  AMBER
    #     return lbl["aligned"], GREEN

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

        # Normalise pitch and roll to -180..+180
        norm_pitch = self._normalise(pitch)
        norm_roll  = self._normalise(roll)

        # Only check pitch and roll — yaw is optional per assignment spec
        tilted = (
            abs(norm_pitch) > pitch_limit
            or abs(norm_roll) > roll_limit
        )

        if tilted:
            return lbl["tilted"], AMBER
        return lbl["aligned"], GREEN


# ═══════════════════════════ DisplayManager ═══════════════════════════

class DisplayManager:
    """
    Cycles through 4 LED screens every DISPLAY_INTERVAL seconds.
    All sense.show_message calls happen here on a dedicated thread.
    """

    SCREENS = ["temperature", "humidity", "pressure", "orientation"]

    def __init__(self, sense: SenseHat):
        self._sense       = sense
        self._screen_idx  = 0
        self._last_switch = time.time()
        self._reading     = None          # latest reading dict
        self._paused      = False
        self._lock        = threading.Lock()

    def update_reading(self, reading: dict):
        with self._lock:
            self._reading = reading

    def set_paused(self, paused: bool):
        with self._lock:
            self._paused = paused

    def tick(self):
        """Call from main loop – advances screen and renders if due."""
        with self._lock:
            paused  = self._paused
            reading = self._reading

        if paused or reading is None:
            return

        now = time.time()
        if now - self._last_switch >= DISPLAY_INTERVAL:
            self._screen_idx  = (self._screen_idx + 1) % len(self.SCREENS)
            self._last_switch = now

        screen = self.SCREENS[self._screen_idx]
        self._render(screen, reading)

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
        else:  # orientation
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
        # Load and validate config
        loader      = ConfigLoader(CONFIG_FILE)
        self._cfg   = loader.config

        # Initialise subsystems
        self._sense   = SenseHat()
        self._sense.set_rotation(0)
        self._sense.set_imu_config(True, True, False) #gyro + accel for accurate yaw
        self._db      = DatabaseManager(DB_FILE)
        self._clf     = Classifier(self._cfg)
        self._display = DisplayManager(self._sense)

        self._paused      : bool  = False
        self._running     : bool  = True
        self._last_poll   : float = 0.0   # force immediate first poll
        self._lock        = threading.Lock()

        # Joystick: middle to pause/resume
        self._sense.stick.direction_middle = self._handle_middle

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

    # ── Sensor read & classify ────────────────────────────────────────

    def _poll(self) -> dict:
        """Read all sensors, calibrate, classify, return a reading dict."""
        temp_raw  = self._sense.get_temperature()
        temp_cal  = round(temp_raw - TEMP_OFFSET, 2)
        humidity  = round(self._sense.get_humidity(), 2)
        pressure  = round(self._sense.get_pressure(), 2)
        ori       = self._sense.get_orientation()
        pitch     = round(ori["pitch"], 2)
        roll      = round(ori["roll"],  2)
        yaw       = round(self._sense.get_orientation()["yaw"],   2)

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

                # ── Sensor poll (every POLL_INTERVAL seconds) ──────────
                if not paused and (now - self._last_poll) >= POLL_INTERVAL:
                    self._last_poll = now
                    reading = self._poll()
                    self._db.log(reading)
                    self._display.update_reading(reading)

                # ── Display tick ───────────────────────────────────────
                self._display.tick()

        except KeyboardInterrupt:
            print("\n[Exit] Shutting down.")
        finally:
            self._sense.clear()
            self._db.close()
            print("[Exit] Display cleared. Database closed. Goodbye!")


# ═══════════════════════════ Entry Point ══════════════════════════════

if __name__ == "__main__":
    SensorMonitor().run()
