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
  • Repeated rapid presses handled gracefully (non-blocking event model)
"""

import math
import time
import threading

try:
    from sense_hat import SenseHat   # physical Sense HAT
except ImportError:
    from sense_emu import SenseHat   # emulator fallback


# ═══════════════════════════ Constants ════════════════════════════════

DEFAULT_X     = 16
TEXT_COLOUR   = (255, 255, 255)   # white
ERROR_COLOUR  = (255,   0,   0)   # red  – used for "ERR" message
RESET_COLOUR  = (0,   200,   0)   # green – used for reset flash
SCROLL_SPEED  = 0.08              # seconds per character scroll


# ═══════════════════════════ Calculator ═══════════════════════════════

class Calculator:
    """
    Manages the current value of x and all arithmetic operations.
    Thread-safe: display and joystick run concurrently.
    """

    def __init__(self):
        self._sense   = SenseHat()
        self._sense.set_rotation(0)

        self._x       : float = DEFAULT_X
        self._lock    = threading.Lock()
        self._running : bool  = True

        # Register non-blocking joystick handlers
        self._sense.stick.direction_up     = self._handle_up
        self._sense.stick.direction_down   = self._handle_down
        self._sense.stick.direction_left   = self._handle_left
        self._sense.stick.direction_right  = self._handle_right
        self._sense.stick.direction_middle = self._handle_middle

        # Show the default value immediately on start
        self._display_value()

    # ── Value helpers ─────────────────────────────────────────────────

    def _format(self, value: float) -> str:
        """
        Format value for display:
          • If it is a whole number → show as int  (e.g. 4.0 → "4")
          • Otherwise → round to 2 decimal places  (e.g. 1.41)
        """
        if value == int(value):
            return str(int(value))
        return str(round(value, 2))

    def _display_value(self, colour: tuple = TEXT_COLOUR) -> None:
        """Scroll the current value of x across the LED matrix."""
        with self._lock:
            text = self._format(self._x)
        print(f"[Display] x = {text}")
        self._sense.show_message(
            text,
            scroll_speed = SCROLL_SPEED,
            text_colour  = colour,
        )

    def _display_error(self, msg: str) -> None:
        """Show a short error message in red."""
        print(f"[Error] {msg}")
        self._sense.show_message(
            "ERR",
            scroll_speed = SCROLL_SPEED,
            text_colour  = ERROR_COLOUR,
        )

    # ── Joystick event handlers ───────────────────────────────────────

    def _handle_up(self, event) -> None:
        """UP → x = x + 1"""
        if event.action != "pressed":
            return
        with self._lock:
            self._x += 1
        print(f"[UP] x + 1 → {self._format(self._x)}")
        self._display_value()

    def _handle_down(self, event) -> None:
        """DOWN → x = x - 1"""
        if event.action != "pressed":
            return
        with self._lock:
            self._x -= 1
        print(f"[DOWN] x - 1 → {self._format(self._x)}")
        self._display_value()

    def _handle_left(self, event) -> None:
        """LEFT → x = x²"""
        if event.action != "pressed":
            return
        with self._lock:
            self._x = self._x ** 2
        print(f"[LEFT] x² → {self._format(self._x)}")
        self._display_value()

    def _handle_right(self, event) -> None:
        """RIGHT → x = √x  (error if x < 0)"""
        if event.action != "pressed":
            return
        with self._lock:
            current = self._x
        if current < 0:
            self._display_error(f"Cannot √ of negative ({self._format(current)})")
            return
        with self._lock:
            self._x = math.sqrt(current)
        print(f"[RIGHT] √x → {self._format(self._x)}")
        self._display_value()

    def _handle_middle(self, event) -> None:
        """MIDDLE → reset x to default (16)"""
        if event.action != "pressed":
            return
        with self._lock:
            self._x = DEFAULT_X
        print(f"[MIDDLE] Reset → {DEFAULT_X}")
        self._display_value(colour=RESET_COLOUR)

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Keep the program alive while joystick events are handled in the
        background.  Press Ctrl+C to exit.
        """
        print("=== Calculator started ===")
        print(f"Default x = {DEFAULT_X}")
        print("UP: x+1 | DOWN: x-1 | LEFT: x² | RIGHT: √x | MIDDLE: reset")
        print("Press Ctrl+C to exit.\n")

        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[Exit] Keyboard interrupt – shutting down.")
        finally:
            self._sense.clear()
            print("[Exit] Display cleared. Goodbye!")


# ═══════════════════════════ Entry Point ══════════════════════════════

if __name__ == "__main__":
    calc = Calculator()
    calc.run()
