#!/usr/bin/env python3
"""
analytics.py
RMIT COSC2674/2755 – Programming Internet of Things
Individual Assignment 1 – Task 4
Student Name : [Your Name]
Student ID   : [Your Student ID]

Reads sensor data from envirotrack.db (Task 3) and produces 2 visualisation
images using two different Python libraries:

  Image 1 – matplotlib : Line chart of temperature, humidity, and pressure
                         over time (multi-axis to handle different scales).
  Image 2 – seaborn    : Bar chart showing the count of each classification
                         status (Low / Comfortable / High / Aligned / Tilted)
                         across all sensor readings.

Output files
------------
  chart_matplotlib.png  – time-series line chart
  chart_seaborn.png     – status distribution bar chart
"""

import os
import sqlite3
import sys
from datetime import datetime

import matplotlib
matplotlib.use("Agg")   # non-interactive backend – no display required
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import pandas as pd


# ═══════════════════════════ Config ═══════════════════════════════════

DB_FILE   = os.path.join(os.path.dirname(__file__), "..", "Task 3", "envirotrack.db")
OUT_DIR   = os.path.dirname(__file__)

IMG1 = os.path.join(OUT_DIR, "chart_matplotlib.png")
IMG2 = os.path.join(OUT_DIR, "chart_seaborn.png")


# ═══════════════════════════ Data Loader ══════════════════════════════

class DataLoader:
    """Loads sensor readings from envirotrack.db into a Pandas DataFrame."""

    QUERY = """
        SELECT
            timestamp,
            temperature_cal,   temperature_status,
            humidity,          humidity_status,
            pressure,          pressure_status,
            pitch, roll, yaw,  orientation_status
        FROM sensor_readings
        ORDER BY timestamp ASC;
    """

    def __init__(self, db_path: str):
        if not os.path.exists(db_path):
            print(f"[ERROR] Database not found: {db_path}")
            print("  → Run SensorMonitor.py first to generate data.")
            sys.exit(1)

        conn = sqlite3.connect(db_path)
        self.df = pd.read_sql_query(self.QUERY, conn, parse_dates=["timestamp"])
        conn.close()

        if self.df.empty:
            print("[ERROR] Database contains no rows.")
            print("  → Let SensorMonitor.py run for at least one poll cycle.")
            sys.exit(1)

        print(f"[Data] Loaded {len(self.df)} rows from {db_path}")


# ═══════════════════════════ Chart 1 – matplotlib ═════════════════════

class MatplotlibChart:
    """
    Line chart: temperature_cal, humidity, and pressure over time.
    Uses twin y-axes so temperature/humidity (small range) and pressure
    (large range ~980-1030) are readable on the same plot.
    """

    def __init__(self, df: pd.DataFrame):
        self._df = df

    def save(self, path: str):
        df   = self._df
        time = df["timestamp"]

        fig, ax1 = plt.subplots(figsize=(12, 5))
        fig.suptitle("Sensor Readings Over Time", fontsize=14, fontweight="bold")

        # ── Left axis: temperature & humidity ─────────────────────────
        ax1.set_xlabel("Time")
        ax1.set_ylabel("Temperature (°C) / Humidity (%)", color="black")
        ax1.tick_params(axis="y", labelcolor="black")

        l1, = ax1.plot(time, df["temperature_cal"], color="#e74c3c",
                       linewidth=2, marker="o", markersize=4, label="Temp (°C)")
        l2, = ax1.plot(time, df["humidity"], color="#3498db",
                       linewidth=2, marker="s", markersize=4, label="Humidity (%)")

        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        fig.autofmt_xdate(rotation=30)

        # ── Right axis: pressure ───────────────────────────────────────
        ax2 = ax1.twinx()
        ax2.set_ylabel("Pressure (hPa)", color="#27ae60")
        ax2.tick_params(axis="y", labelcolor="#27ae60")

        l3, = ax2.plot(time, df["pressure"], color="#27ae60",
                       linewidth=2, linestyle="--", marker="^",
                       markersize=4, label="Pressure (hPa)")

        # ── Threshold reference lines ──────────────────────────────────
        ax1.axhline(y=24, color="#e74c3c", linestyle=":", alpha=0.5, label="Temp max (24°C)")
        ax1.axhline(y=15, color="#e74c3c", linestyle=":", alpha=0.3, label="Temp min (15°C)")

        # ── Legend ────────────────────────────────────────────────────
        lines  = [l1, l2, l3]
        labels = [l.get_label() for l in lines]
        ax1.legend(lines, labels, loc="upper left", fontsize=9)

        ax1.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"[Chart 1] Saved → {path}")


# ═══════════════════════════ Chart 2 – seaborn ════════════════════════

class SeabornChart:
    """
    Bar chart: count of each status label across all sensor columns.
    Shows how often each classification (Low / Comfortable / High /
    Aligned / Tilted) was recorded for each sensor type.
    """

    # Colour map matching the LED scheme
    STATUS_COLOURS = {
        "Low":         "#3498db",   # blue
        "Comfortable": "#2ecc71",   # green
        "Normal":      "#2ecc71",   # green
        "High":        "#e74c3c",   # red
        "Aligned":     "#2ecc71",   # green
        "Tilted":      "#f39c12",   # amber
    }

    def __init__(self, df: pd.DataFrame):
        self._df = df

    def _build_status_df(self) -> pd.DataFrame:
        """Melt status columns into a long-form DataFrame for seaborn."""
        status_cols = {
            "temperature_status": "Temperature",
            "humidity_status":    "Humidity",
            "pressure_status":    "Pressure",
            "orientation_status": "Orientation",
        }
        rows = []
        for col, label in status_cols.items():
            counts = self._df[col].value_counts()
            for status, count in counts.items():
                rows.append({
                    "Sensor":  label,
                    "Status":  status,
                    "Count":   count,
                })
        return pd.DataFrame(rows)

    def save(self, path: str):
        status_df = self._build_status_df()

        # Build per-status colour list in the order seaborn will plot them
        all_statuses = status_df["Status"].unique().tolist()
        palette      = {s: self.STATUS_COLOURS.get(s, "#95a5a6") for s in all_statuses}

        fig, ax = plt.subplots(figsize=(10, 6))
        sns.barplot(
            data    = status_df,
            x       = "Sensor",
            y       = "Count",
            hue     = "Status",
            palette = palette,
            ax      = ax,
        )

        ax.set_title("Sensor Status Distribution", fontsize=14, fontweight="bold")
        ax.set_xlabel("Sensor", fontsize=11)
        ax.set_ylabel("Number of Readings", fontsize=11)
        ax.legend(title="Status", bbox_to_anchor=(1.01, 1), loc="upper left")
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        sns.despine()

        plt.tight_layout()
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"[Chart 2] Saved → {path}")


# ═══════════════════════════ Main ═════════════════════════════════════

class Analytics:
    """Orchestrates data loading and chart generation."""

    def __init__(self):
        self._loader = DataLoader(DB_FILE)

    def run(self):
        df = self._loader.df

        MatplotlibChart(df).save(IMG1)
        SeabornChart(df).save(IMG2)

        print("\nDone! Output files:")
        print(f"  {IMG1}")
        print(f"  {IMG2}")


if __name__ == "__main__":
    Analytics().run()
