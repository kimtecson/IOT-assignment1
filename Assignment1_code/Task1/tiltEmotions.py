#!/usr/bin/env python3
"""
tiltEmotions.py

Reads Sense HAT orientation (pitch / roll / yaw) and maps the physical
tilt of the device to one of six mood emotions displayed as animated
sequences on the 8×8 LED matrix.

Orientation → Mood mapping
--------------------------
  Tilt right   (roll  >  TILT_THRESH)  → MoodEmo1 : Happy
  Tilt left    (roll  < -TILT_THRESH)  → MoodEmo2 : Sad
  Tilt forward (pitch >  TILT_THRESH)  → MoodEmo3 : Angry
  Tilt back    (pitch < -TILT_THRESH)  → MoodEmo4 : Surprised
  Flat         (all within threshold)  → MoodEmo5 : Cool
  Rapid flip   (|Δroll| > 60° in 0.5s) → MoodEmo6 : Dizzy  ← special!

Additional controls
-------------------
  Joystick MIDDLE : pause / resume display updates
  Joystick any    : wake from sleep mode (if implemented)

The display updates ONLY when the orientation zone changes, preventing
LED flickering at zone boundaries.
"""

import time
import threading

try:
    from sense_hat import SenseHat
except ImportError:
    from sense_emu import SenseHat

from emojis import (
    HappyEmoji, SadEmoji, AngryEmoji, SurprisedEmoji, CoolEmoji,
    DizzyEmoji,
)


# ═══════════════════════════ Constants ════════════════════════════════

POLL_INTERVAL   = 0.1    # seconds between orientation polls
FRAME_DELAY     = 0.5    # seconds each animation frame is shown
TILT_THRESH     = 30.0   # degrees from flat to register a tilt zone
FLIP_DELTA      = 60.0   # minimum roll change (°) for "rapid flip"
FLIP_WINDOW     = 0.5    # seconds within which flip must occur
DIZZY_DURATION  = 3.0    # seconds the dizzy animation plays before resuming


# ═══════════════════════════ Helpers ══════════════════════════════════

def normalise(angle: float) -> float:
    """
    Convert a Sense HAT angle (0–360 °) to a signed value (-180 … +180 °).
    This makes threshold comparisons straightforward (e.g. roll > 30°).
    """
    return angle - 360.0 if angle > 180.0 else angle


# ═══════════════════════════ OrientationClassifier ════════════════════

class OrientationClassifier:
    """
    Classifies the current orientation zone from pitch and roll readings.
    Supports hysteresis via enter/exit thresholds to reduce zone flapping.
    Also detects rapid-flip events.
    """

    ENTER_THRESH = TILT_THRESH          # |angle| must exceed this to enter zone
    EXIT_THRESH  = TILT_THRESH - 8.0    # |angle| must drop below this to exit zone

    # Zone identifiers (used as dict keys / printable labels)
    FLAT      = "flat"
    TILT_R    = "right"
    TILT_L    = "left"
    TILT_FWD  = "forward"
    TILT_BACK = "back"
    DIZZY     = "dizzy"

    def __init__(self):
        self._current_zone: str   = self.FLAT
        self._prev_roll   : float = 0.0
        self._prev_roll_t : float = time.time()

    @property
    def current_zone(self) -> str:
        return self._current_zone

    def update(self, pitch_raw: float, roll_raw: float) -> tuple:
        """
        Call with raw Sense HAT angles.  Returns (zone, changed) where
        `zone` is the current zone string and `changed` is True only when
        the zone is different from the previous call.
        """
        pitch = normalise(pitch_raw)
        roll  = normalise(roll_raw)
        now   = time.time()

        # ── Rapid-flip detection (takes priority) ─────────────────────
        delta_roll = abs(roll - self._prev_roll)
        dt         = now - self._prev_roll_t
        if delta_roll > FLIP_DELTA and dt <= FLIP_WINDOW:
            new_zone = self.DIZZY
        else:
            new_zone = self._classify(pitch, roll)

        self._prev_roll   = roll
        self._prev_roll_t = now

        changed = (new_zone != self._current_zone)
        self._current_zone = new_zone
        return self._current_zone, changed

    def _classify(self, pitch: float, roll: float) -> str:
        """Apply hysteresis-based classification for the five tilt zones."""
        current = self._current_zone

        # Determine entry/exit threshold for the current zone
        def exceeds(val, thresh):
            return abs(val) > thresh

        # Priority: if already in a zone, require drop below EXIT_THRESH to leave
        if current == self.TILT_R:
            if roll > self.EXIT_THRESH:   return self.TILT_R
        elif current == self.TILT_L:
            if roll < -self.EXIT_THRESH:  return self.TILT_L
        elif current == self.TILT_FWD:
            if pitch > self.EXIT_THRESH:  return self.TILT_FWD
        elif current == self.TILT_BACK:
            if pitch < -self.EXIT_THRESH: return self.TILT_BACK

        # Check entry into a new zone
        if roll > self.ENTER_THRESH:           return self.TILT_R
        if roll < -self.ENTER_THRESH:          return self.TILT_L
        if pitch > self.ENTER_THRESH:          return self.TILT_FWD
        if pitch < -self.ENTER_THRESH:         return self.TILT_BACK
        return self.FLAT


# ═══════════════════════════ TiltEmotionController ════════════════════

class TiltEmotionController:
    """
    Main controller: polls orientation, maps zone → emoji, drives LED
    animation, handles joystick pause/resume, and manages the dizzy timer.
    """

    # Map zone → (Emoji instance, display label)
    _ZONE_MAP: dict = {
        OrientationClassifier.TILT_R    : (HappyEmoji(),     "MoodEmo1 – Happy"),
        OrientationClassifier.TILT_L    : (SadEmoji(),       "MoodEmo2 – Sad"),
        OrientationClassifier.TILT_FWD  : (AngryEmoji(),     "MoodEmo3 – Angry"),
        OrientationClassifier.TILT_BACK : (SurprisedEmoji(), "MoodEmo4 – Surprised"),
        OrientationClassifier.FLAT      : (CoolEmoji(),      "MoodEmo5 – Cool"),
        OrientationClassifier.DIZZY     : (DizzyEmoji(),     "MoodEmo6 – Dizzy"),
    }

    def __init__(self):
        self._sense      = SenseHat()
        self._sense.set_rotation(0)
        self._sense.low_light = False

        self._classifier = OrientationClassifier()
        self._classifier._current_zone = OrientationClassifier.FLAT  # start flat

        # Mutable state
        self._current_emoji    = CoolEmoji()   # initial emoji (Flat = Cool)
        self._frame_idx  : int = 0
        self._paused     : bool = False
        self._running    : bool = True
        self._dizzy_until: float = 0.0         # epoch time until dizzy ends

        self._lock = threading.Lock()

        # Joystick: only middle to pause/resume
        self._sense.stick.direction_middle = self._handle_middle

        # Animation frame timer
        self._frame_timer: float = time.time()

    # ── Joystick handler ─────────────────────────────────────────────

    def _handle_middle(self, event) -> None:
        if event.action != "pressed":
            return
        with self._lock:
            self._paused = not self._paused
        state = "paused" if self._paused else "resumed"
        print(f"[Control] Display {state}.")

    # ── Internal helpers ─────────────────────────────────────────────

    def _switch_emoji(self, zone: str) -> None:
        """Update the current emoji to the one mapped from zone."""
        emoji, label = self._ZONE_MAP[zone]
        with self._lock:
            self._current_emoji = emoji
            self._frame_idx     = 0
        print(f"[Zone] {zone.upper():8s} → {label}")

    # ── Main loop ─────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Blocking main loop.
        - Polls orientation every POLL_INTERVAL seconds.
        - Advances animation frames every FRAME_DELAY seconds.
        - Switches emoji only when the orientation zone changes.
        """
        print("=== tiltEmotions started ===")
        print("Tilt the Sense HAT to change mood | MIDDLE : pause/resume")
        print(f"Tilt threshold: ±{TILT_THRESH}° | Flip: Δroll>{FLIP_DELTA}° in {FLIP_WINDOW}s")
        print("Press Ctrl+C to exit.\n")

        last_poll = time.time()

        try:
            while self._running:
                now = time.time()

                # ── Orientation poll ───────────────────────────────────
                if now - last_poll >= POLL_INTERVAL:
                    last_poll = now
                    orientation = self._sense.get_orientation()
                    pitch_raw   = orientation["pitch"]
                    roll_raw    = orientation["roll"]
                    yaw_raw     = orientation["yaw"]

                    zone, changed = self._classifier.update(pitch_raw, roll_raw)

                    # If dizzy, hold it for DIZZY_DURATION regardless of tilt
                    with self._lock:
                        paused = self._paused
                        dizzy_until = self._dizzy_until

                    if zone == OrientationClassifier.DIZZY and changed:
                        self._dizzy_until = now + DIZZY_DURATION
                        self._switch_emoji(zone)
                    elif now < self._dizzy_until:
                        # Still in dizzy hold; do not update zone yet
                        pass
                    elif changed:
                        self._switch_emoji(zone)

                # ── Animation frame advance ────────────────────────────
                if now - self._frame_timer >= FRAME_DELAY:
                    self._frame_timer = now
                    with self._lock:
                        paused    = self._paused
                        emoji     = self._current_emoji
                        frame_idx = self._frame_idx

                    if not paused:
                        pixels = emoji.get_flat_frame(frame_idx)
                        self._sense.set_pixels(pixels)
                        with self._lock:
                            self._frame_idx = (frame_idx + 1) % emoji.frame_count

                time.sleep(0.01)  # tight loop; real delays handled by timers

        except KeyboardInterrupt:
            print("\n[Exit] Keyboard interrupt – shutting down.")
        finally:
            self._sense.clear()
            print("[Exit] Display cleared. Goodbye!")


# ═══════════════════════════ Entry Point ══════════════════════════════

if __name__ == "__main__":
    controller = TiltEmotionController()
    controller.run()
