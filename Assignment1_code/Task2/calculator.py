#!/usr/bin/env python3
"""
calculator.py
RMIT COSC2674/2755 – Programming Internet of Things
Individual Assignment 1 – Task 2
Student Name : [Your Name]
Student ID   : [Your Student ID]

Displays a running value of x on the Sense HAT LED matrix.
Joystick controls update x with different mathematical operations.

Controls
--------
  UP     : x = x + 1
  DOWN   : x = x - 1
  LEFT   : x = x²  (square)
  RIGHT  : x = √x  (square root – rounded to 2 dp)
  MIDDLE : x = 16  (reset to default)

Edge cases handled
------------------
  • Square root of a negative number → shows "ERR" and keeps x unchanged
  • Square root result is whole → displayed as int (e.g. 4.0 → 4)
  • Very large / very small numbers → scrolled as string on LED matrix
  • All display calls run on the main thread to avoid Sense HAT conflicts
"""

import math
import time
import threading

try:
    from sense_hat import SenseHat   # physical Sense HAT
except ImportError:
    from sense_emu import SenseHat   # emulator fallback


# ═══════════════════════════ Constants ════════════════════════════════

DEFAULT_X    = 16
TEXT_COLOUR  = (255, 255, 255)   # white  – normal value
ERROR_COLOUR = (255,   0,   0)   # red    – error message
RESET_COLOUR = (0,   200,   0)   # green  – reset confirmation
SCROLL_SPEED = 0.08              # seconds per character


# ═══════════════════════════ Calculator ═══════════════════════════════

class Calculator:
    """
    Manages x and joystick operations.
    Joystick handlers ONLY update state — the main loop owns the display.
    """

    def __init__(self):
        self._sense = SenseHat()
        self._sense.set_rotation(0)

        self._x             : float = float(DEFAULT_X)
        self._display_text  : str   = str(DEFAULT_X)
        self._text_colour   : tuple = TEXT_COLOUR
        self._needs_display : bool  = True   # show initial value on start
        self._lock          = threading.Lock()
        self._running       : bool  = True

        # Register joystick handlers (run in background thread)
        self._sense.stick.direction_up     = self._handle_up
        self._sense.stick.direction_down   = self._handle_down
        self._sense.stick.direction_left   = self._handle_left
        self._sense.stick.direction_right  = self._handle_right
        self._sense.stick.direction_middle = self._handle_middle

    # ── Formatting ────────────────────────────────────────────────────

    def _format(self, value: float) -> str:
        """Whole numbers → int string; floats → 2 dp."""
        if value == int(value):
            return str(int(value))
        return str(round(value, 2))

    # ── Joystick handlers (background thread – NO display calls here) ─

    def _handle_up(self, event) -> None:
        if event.action != "pressed":
            return
        with self._lock:
            self._x += 1
            self._display_text  = self._format(self._x)
            self._text_colour   = TEXT_COLOUR
            self._needs_display = True
        print(f"[UP]     x + 1  →  {self._display_text}")

    def _handle_down(self, event) -> None:
        if event.action != "pressed":
            return
        with self._lock:
            self._x -= 1
            self._display_text  = self._format(self._x)
            self._text_colour   = TEXT_COLOUR
            self._needs_display = True
        print(f"[DOWN]   x - 1  →  {self._display_text}")

    def _handle_left(self, event) -> None:
        if event.action != "pressed":
            return
        with self._lock:
            self._x             = self._x ** 2
            self._display_text  = self._format(self._x)
            self._text_colour   = TEXT_COLOUR
            self._needs_display = True
        print(f"[LEFT]   x²     →  {self._display_text}")

    def _handle_right(self, event) -> None:
        if event.action != "pressed":
            return
        with self._lock:
            current = self._x
        if current < 0:
            with self._lock:
                self._display_text  = "ERR"
                self._text_colour   = ERROR_COLOUR
                self._needs_display = True
            print(f"[RIGHT]  ERROR: cannot √ negative ({self._format(current)})")
            return
        with self._lock:
            self._x             = math.sqrt(current)
            self._display_text  = self._format(self._x)
            self._text_colour   = TEXT_COLOUR
            self._needs_display = True
        print(f"[RIGHT]  √x     →  {self._display_text}")

    def _handle_middle(self, event) -> None:
        if event.action != "pressed":
            return
        with self._lock:
            self._x             = float(DEFAULT_X)
            self._display_text  = str(DEFAULT_X)
            self._text_colour   = RESET_COLOUR
            self._needs_display = True
        print(f"[MIDDLE] Reset  →  {DEFAULT_X}")

    # ── Main loop (owns all display calls) ───────────────────────────

    def run(self) -> None:
        """
        Main loop: checks for pending display updates and scrolls the
        value on the LED matrix from the main thread only.
        """
        print("=== Calculator started ===")
        print(f"Default x = {DEFAULT_X}")
        print("UP:x+1 | DOWN:x-1 | LEFT:x² | RIGHT:√x | MIDDLE:reset")
        print("Press Ctrl+C to exit.\n")

        try:
            while True:
                with self._lock:
                    needs_display = self._needs_display
                    if needs_display:
                        text   = self._display_text
                        colour = self._text_colour
                        self._needs_display = False

                if needs_display:
                    # show_message blocks until scroll is done – safe on main thread
                    self._sense.show_message(
                        text,
                        scroll_speed = SCROLL_SPEED,
                        text_colour  = colour,
                    )
                else:
                    time.sleep(0.05)

        except KeyboardInterrupt:
            print("\n[Exit] Keyboard interrupt – shutting down.")
        finally:
            self._sense.clear()
            print("[Exit] Display cleared. Goodbye!")


# ═══════════════════════════ Entry Point ══════════════════════════════

if __name__ == "__main__":
    calc = Calculator()
    calc.run()
