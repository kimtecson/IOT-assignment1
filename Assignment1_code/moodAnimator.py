#!/usr/bin/env python3
"""
moodAnimator.py
Displays 5 original animated emoji faces on the Raspberry Pi Sense HAT
8×8 LED matrix with full joystick navigation.

Controls
--------
  Joystick RIGHT  : advance to next emoji
  Joystick LEFT   : go back to previous emoji
  Joystick MIDDLE : pause / resume animation
  Any direction   : wake from sleep mode

Rate-limiting : only one navigation/pause action per 3 seconds.
Idle timeout  : after 15 s of no input, dims LEDs and shows a neutral
                sleep face.  Any joystick press wakes the display.
"""

import time
import threading

try:
    from sense_hat import SenseHat
except ImportError:
    from sense_emu import SenseHat
from emojis import (
    HappyEmoji, SadEmoji, AngryEmoji, SurprisedEmoji, CoolEmoji,
    SLEEP_FACE,
)


# ═══════════════════════════ Constants ════════════════════════════════

FRAME_DELAY  = 0.5   # seconds each animation frame is displayed
RATE_LIMIT   = 3.0   # minimum seconds between accepted joystick presses
IDLE_TIMEOUT = 15.0  # seconds of no input before entering sleep mode


# ═══════════════════════════ EmojiAnimator ════════════════════════════

class EmojiAnimator:
    """
    Manages the animation loop and joystick interaction for the five
    mood emojis.  All state mutations are protected by a threading.Lock
    because the Sense HAT joystick callbacks fire in a background thread.
    """

    def __init__(self):
        self._sense = SenseHat()
        self._sense.set_rotation(0)
        self._sense.low_light = False

        # Ordered list of emojis (indices 0-4 map to MoodEmo1-5)
        self._emojis = [
            HappyEmoji(),       # MoodEmo1
            SadEmoji(),         # MoodEmo2
            AngryEmoji(),       # MoodEmo3
            SurprisedEmoji(),   # MoodEmo4
            CoolEmoji(),        # MoodEmo5
        ]

        # Mutable state (all access via self._lock)
        self._emoji_idx  : int   = 0
        self._frame_idx  : int   = 0
        self._paused     : bool  = False
        self._sleeping   : bool  = False
        self._running    : bool  = True

        # Timing
        self._last_press : float = 0.0          # last accepted press timestamp
        self._last_input : float = time.time()  # last any joystick event timestamp

        self._lock = threading.Lock()

        # Register non-blocking joystick event handlers
        self._sense.stick.direction_right  = self._handle_right
        self._sense.stick.direction_left   = self._handle_left
        self._sense.stick.direction_middle = self._handle_middle
        self._sense.stick.direction_up     = self._handle_any
        self._sense.stick.direction_down   = self._handle_any

    # ── Private helpers ───────────────────────────────────────────────

    def _record_input(self) -> None:
        """Update the idle timer whenever any joystick event occurs."""
        self._last_input = time.time()

    def _check_rate_limit(self) -> bool:
        """
        Return True (and update timestamp) if enough time has passed since
        the last accepted press; return False if still within the 3 s window.
        """
        now = time.time()
        if now - self._last_press < RATE_LIMIT:
            return False        # still rate-limited → ignore
        self._last_press = now
        return True             # accepted

    def _enter_sleep(self) -> None:
        """Dim the display and show the neutral sleep face."""
        with self._lock:
            self._sleeping = True
        self._sense.low_light = True
        self._sense.set_pixels(SLEEP_FACE)
        print("[Sleep] Idle timeout reached – entering sleep mode.")

    def _wake(self) -> None:
        """Restore full brightness and resume the current emoji."""
        with self._lock:
            self._sleeping = False
        self._sense.low_light = False
        print("[Wake] Joystick pressed – waking display.")

    # ── Joystick event handlers (called from SenseHat background thread) ──

    def _handle_right(self, event) -> None:
        if event.action != "pressed":
            return
        self._record_input()
        with self._lock:
            if self._sleeping:
                self._sleeping = False          # flag; full wake handled in loop
                return
        if not self._check_rate_limit():
            return
        with self._lock:
            self._emoji_idx = (self._emoji_idx + 1) % len(self._emojis)
            self._frame_idx = 0
        print(f"[Nav] → Next emoji: {self._emojis[self._emoji_idx].name}")

    def _handle_left(self, event) -> None:
        if event.action != "pressed":
            return
        self._record_input()
        with self._lock:
            if self._sleeping:
                self._sleeping = False
                return
        if not self._check_rate_limit():
            return
        with self._lock:
            self._emoji_idx = (self._emoji_idx - 1) % len(self._emojis)
            self._frame_idx = 0
        print(f"[Nav] ← Prev emoji: {self._emojis[self._emoji_idx].name}")

    def _handle_middle(self, event) -> None:
        if event.action != "pressed":
            return
        self._record_input()
        with self._lock:
            if self._sleeping:
                self._sleeping = False
                return
        if not self._check_rate_limit():
            return
        with self._lock:
            self._paused = not self._paused
        state = "paused" if self._paused else "resumed"
        print(f"[Control] Animation {state}.")

    def _handle_any(self, event) -> None:
        """Handle UP / DOWN – used only to wake from sleep."""
        if event.action != "pressed":
            return
        self._record_input()
        with self._lock:
            if self._sleeping:
                self._sleeping = False

    # ── Main animation loop ───────────────────────────────────────────

    def run(self) -> None:
        """
        Blocking main loop.  Advances frames, checks idle timeout, and
        delegates joystick events to background handlers.
        Press Ctrl+C to exit cleanly.
        """
        print("=== moodAnimator started ===")
        print("RIGHT / LEFT : navigate emojis | MIDDLE : pause/resume")
        print(f"Idle timeout : {IDLE_TIMEOUT} s | Rate limit : {RATE_LIMIT} s")
        print("Press Ctrl+C to exit.\n")

        try:
            while self._running:
                # ── Snapshot state under lock ──────────────────────────
                with self._lock:
                    sleeping  = self._sleeping
                    paused    = self._paused
                    emoji_idx = self._emoji_idx
                    frame_idx = self._frame_idx

                # ── Idle-timeout check ────────────────────────────────
                if not sleeping and (time.time() - self._last_input) > IDLE_TIMEOUT:
                    self._enter_sleep()
                    time.sleep(0.1)
                    continue

                # ── Sleep mode active: apply wake if flag cleared ──────
                if sleeping:
                    # _sleeping may have been cleared by a handler; call wake()
                    with self._lock:
                        still_sleeping = self._sleeping
                    if not still_sleeping:
                        self._wake()
                    else:
                        time.sleep(0.1)
                        continue

                # ── Normal display ────────────────────────────────────
                if not paused:
                    emoji  = self._emojis[emoji_idx]
                    pixels = emoji.get_flat_frame(frame_idx)
                    self._sense.set_pixels(pixels)

                    # Advance to the next frame
                    with self._lock:
                        # Guard: emoji_idx may have changed during set_pixels
                        if self._emoji_idx == emoji_idx:
                            self._frame_idx = (frame_idx + 1) % emoji.frame_count

                time.sleep(FRAME_DELAY)

        except KeyboardInterrupt:
            print("\n[Exit] Keyboard interrupt – shutting down.")
        finally:
            self._sense.clear()
            print("[Exit] Display cleared. Goodbye!")


# ═══════════════════════════ Entry Point ══════════════════════════════

if __name__ == "__main__":
    animator = EmojiAnimator()
    animator.run()
