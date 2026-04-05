#!/usr/bin/env python3
"""
Defines all Emoji classes used by moodAnimator.py and tiltEmotions.py.
Each emoji provides a multi-frame animation (≥3 frames, ≥4 colours/frame).

Emoji roster
------------
  HappyEmoji     – MoodEmo1  (smiling, rosy cheeks, wink cycle)
  SadEmoji       – MoodEmo2  (frown, falling tears)
  AngryEmoji     – MoodEmo3  (red face, furrowed brows, flush)
  SurprisedEmoji – MoodEmo4  (wide eyes, O-mouth, raised brows)
  CoolEmoji      – MoodEmo5  (sunglasses, smirk, lens shine)
  DizzyEmoji     – MoodEmo6  (spiral eyes, star-burst – tiltEmotions only)
  SleepFace      – module-level flat pixel list for idle/sleep mode
"""

B   = (0,   0,   0)    # Black
W   = (255, 255, 255)  # White
Y   = (255, 220,   0)  # Yellow
R   = (210,   0,   0)  # Red
O   = (255, 140,   0)  # Orange
BL  = (0,   80,  220)  # Blue
LB  = (130, 190, 255)  # Light Blue
CY  = (0,   200, 200)  # Cyan
DK  = (20,  10,   0)   # Dark (nearly black)
P   = (180,   0,  200) # Purple
G   = (0,   180,   0)  # Green
SL  = (0,   50,   0)   # Sleep glow


class Emoji:
    """
    Abstract base class for an animated 8×8 LED emoji.

    Subclasses implement _build_frames(), returning a list of frames.
    Each frame is an 8-element list of 8-element rows of (r, g, b) tuples.
    """

    def __init__(self, name: str):
        self.name = name
        self.frames: list = self._build_frames()

    # ── Public API ────────────────────────────────────────────────────

    def get_flat_frame(self, frame_idx: int) -> list:
        """Return frame as a flat list of 64 (r, g, b) tuples for set_pixels()."""
        grid = self.frames[frame_idx % len(self.frames)]
        return [pixel for row in grid for pixel in row]

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    # ── Abstract ──────────────────────────────────────────────────────

    def _build_frames(self) -> list:
        raise NotImplementedError(f"{self.__class__.__name__} must implement _build_frames()")


# ═══════════════════════════ Concrete Emojis ══════════════════════════

class HappyEmoji(Emoji):
    """
    MoodEmo1 – Happy 😊
    Colours per frame: Yellow (face), Black (outline/eyes), White (highlights), Red (cheeks)
    3 frames: normal smile → open smile with teeth → wink
    """

    def __init__(self):
        super().__init__("Happy")

    def _build_frames(self) -> list:
        # Frame 1: closed-mouth smile with eye shine + rosy cheeks
        f1 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, B, W, Y, Y, W, B, Y],   # eyes with white highlight
            [Y, B, Y, Y, Y, Y, B, Y],   # eye lower half
            [R, Y, Y, Y, Y, Y, Y, R],   # rosy cheeks
            [Y, B, Y, Y, Y, Y, B, Y],   # mouth corners up
            [Y, Y, B, B, B, B, Y, Y],   # smile arc
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        # Frame 2: open mouth smile – teeth showing (W)
        f2 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, B, W, Y, Y, W, B, Y],
            [Y, B, Y, Y, Y, Y, B, Y],
            [R, Y, Y, Y, Y, Y, Y, R],
            [Y, B, Y, Y, Y, Y, B, Y],
            [Y, Y, W, W, W, W, Y, Y],   # teeth
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        # Frame 3: wink – left eye closed (line), right eye normal
        f3 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, B, B, B, Y, W, B, Y],   # left = dash, right = highlight
            [Y, Y, Y, Y, Y, B, Y, Y],   # right eye lower
            [R, Y, Y, Y, Y, Y, Y, R],
            [Y, B, Y, Y, Y, Y, B, Y],
            [Y, Y, B, B, B, B, Y, Y],
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        return [f1, f2, f3]


class SadEmoji(Emoji):
    """
    MoodEmo2 – Sad 😢
    Colours per frame: Yellow (face), Black (eyes/frown), Light Blue + Blue (tears)
    3 frames: tear forms → tear streams → tears from both eyes
    """

    def __init__(self):
        super().__init__("Sad")

    def _build_frames(self) -> list:
        # Frame 1: tear forming below right eye
        f1 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, B, B, Y, Y, B, B, Y],   # sad dot-eyes (no shine)
            [Y, Y, LB, Y, Y, LB, Y, Y], # tiny tear bead
            [Y, Y, BL, Y, Y, BL, Y, Y], # tear starting to fall
            [Y, Y, B, B, B, B, Y, Y],   # frown arc
            [Y, B, Y, Y, Y, Y, B, Y],   # frown corners down
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        # Frame 2: tear streams down the face
        f2 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, B, LB, Y, Y, B, LB, Y], # tear at eye level
            [Y, Y, BL, Y, Y, BL, Y, Y],
            [Y, Y, LB, Y, Y, LB, Y, Y],
            [Y, Y, B, B, B, B, Y, Y],
            [Y, B, Y, Y, Y, Y, B, Y],
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        # Frame 3: tears dripping from chin
        f3 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, B, B, Y, Y, B, B, Y],
            [Y, LB, Y, Y, Y, LB, Y, Y], # tear on cheek
            [Y, BL, Y, Y, Y, BL, Y, Y],
            [Y, Y, B, B, B, B, Y, Y],
            [Y, B, Y, Y, Y, Y, B, Y],
            [B, LB, Y, Y, Y, LB, Y, B], # drip at chin
        ]
        return [f1, f2, f3]


class AngryEmoji(Emoji):
    """
    MoodEmo3 – Angry 😠
    Colours per frame: Red (face), Black (brows/mouth), Orange (flush), White (narrow eyes)
    3 frames: mild → strong → rage (brows joined)
    """

    def __init__(self):
        super().__init__("Angry")

    def _build_frames(self) -> list:
        # Frame 1: angled brows, narrow eyes, mild flush
        f1 = [
            [B, R, R, R, R, R, R, B],
            [R, B, R, R, R, R, B, R],   # outer brow edges angled in
            [R, R, B, R, R, B, R, R],   # inner brow points
            [R, R, R, W, W, R, R, R],   # narrow white eyes
            [O, R, R, R, R, R, R, O],   # cheek flush (orange)
            [R, R, B, R, R, B, R, R],   # frown corners up (anger)
            [R, B, R, R, R, R, B, R],   # frown arc
            [B, R, R, R, R, R, R, B],
        ]
        # Frame 2: stronger brows, wider flush
        f2 = [
            [B, R, R, R, R, R, R, B],
            [B, R, B, R, R, B, R, B],   # brows more angular
            [R, R, R, B, B, R, R, R],   # brow tips nearly meet
            [R, R, R, W, W, R, R, R],
            [O, O, R, R, R, R, O, O],   # flush wider
            [R, R, B, R, R, B, R, R],
            [R, B, R, R, R, R, B, R],
            [B, R, R, R, R, R, R, B],
        ]
        # Frame 3: brows fully joined = RAGE
        f3 = [
            [B, R, R, R, R, R, R, B],
            [R, B, R, R, R, R, B, R],
            [R, R, B, B, B, B, R, R],   # brows joined in one line
            [R, R, R, W, W, R, R, R],
            [O, R, O, R, R, O, R, O],   # pulsing flush pattern
            [R, R, B, R, R, B, R, R],
            [R, B, R, R, R, R, B, R],
            [B, R, R, R, R, R, R, B],
        ]
        return [f1, f2, f3]


class SurprisedEmoji(Emoji):
    """
    MoodEmo4 – Surprised 😮
    Colours per frame: Yellow (face), Black (outline), White (wide eyes), Orange (O-mouth)
    3 frames: initial surprise → brows raised → eyes at widest
    """

    def __init__(self):
        super().__init__("Surprised")

    def _build_frames(self) -> list:
        # Frame 1: wide eyes + open O-mouth
        f1 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, W, B, Y, Y, B, W, Y],   # big round eyes (white surround, black pupil)
            [Y, B, Y, Y, Y, Y, B, Y],   # eye lower arc
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, Y, O, O, O, O, Y, Y],   # top of O-mouth
            [Y, Y, O, Y, Y, O, Y, Y],   # sides of O-mouth
            [B, Y, Y, B, B, Y, Y, B],   # bottom of O-mouth
        ]
        # Frame 2: eyebrows raised (B pixels on row 0)
        f2 = [
            [B, Y, B, Y, Y, B, Y, B],   # raised brow arches
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, W, B, Y, Y, B, W, Y],
            [Y, B, Y, Y, Y, Y, B, Y],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, Y, O, O, O, O, Y, Y],
            [Y, Y, O, Y, Y, O, Y, Y],
            [B, Y, Y, B, B, Y, Y, B],
        ]
        # Frame 3: maximum surprise – entire eyes white (no pupil yet)
        f3 = [
            [B, Y, B, Y, Y, B, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, W, W, Y, Y, W, W, Y],   # fully white eyes (shock)
            [Y, W, B, Y, Y, B, W, Y],   # pupils appear below centre
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, Y, O, O, O, O, Y, Y],
            [Y, Y, O, Y, Y, O, Y, Y],
            [B, Y, Y, B, B, Y, Y, B],
        ]
        return [f1, f2, f3]


class CoolEmoji(Emoji):
    """
    MoodEmo5 – Cool 😎
    Colours per frame: Yellow (face), Black (outline), Cyan (glasses frame), Dark (lenses)
    3 frames: glasses on → lens shine → glasses lifted (eyes peek out)
    """

    def __init__(self):
        super().__init__("Cool")

    def _build_frames(self) -> list:
        # Frame 1: standard cool – glasses + right-side smirk
        f1 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, CY, CY, CY, CY, CY, CY, Y],  # glasses frame row
            [Y, CY, DK,  DK, CY,  DK, DK, Y],  # dark lenses
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, Y, Y, Y, Y, B, Y, Y],   # smirk right corner
            [Y, Y, Y, B, B, Y, Y, Y],   # smirk arc
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        # Frame 2: lens shine (white glint on left lens)
        f2 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, CY, CY, CY, CY, CY, CY, Y],
            [Y, CY, W,   DK, CY,  DK, DK, Y],  # W = glint
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, Y, Y, Y, Y, B, Y, Y],
            [Y, Y, Y, B, B, Y, Y, Y],
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        # Frame 3: glasses slid up – eyes visible beneath
        f3 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, CY, CY, CY, CY, CY, CY, Y],  # glasses shifted up
            [Y, CY, DK,  DK, CY,  DK, DK, Y],
            [Y, B, Y, Y, Y, B, Y, Y],   # eyes peeking from under glasses
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, Y, Y, Y, Y, B, Y, Y],
            [Y, Y, Y, B, B, Y, Y, Y],
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        return [f1, f2, f3]


class DizzyEmoji(Emoji):
    """
    MoodEmo6 – Dizzy 😵  (tiltEmotions only – triggered by rapid flip)
    Colours per frame: Yellow (face), Black (outline), Purple + Green (spiral eyes)
    3 frames: spiral phase A → spiral phase B → star-burst
    """

    def __init__(self):
        super().__init__("Dizzy")

    def _build_frames(self) -> list:
        # Frame 1: spiral eyes phase A + wavy mouth
        f1 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, P, G, Y, Y, G, P, Y],   # outer ring: P G
            [Y, G, P, Y, Y, P, G, Y],   # inner ring: G P  (spiral illusion)
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, Y, B, Y, B, Y, B, Y],   # wavy mouth
            [Y, Y, Y, B, Y, B, Y, Y],
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        # Frame 2: spiral rotated (P↔G swap = rotation illusion)
        f2 = [
            [B, Y, Y, Y, Y, Y, Y, B],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, G, P, Y, Y, P, G, Y],
            [Y, P, G, Y, Y, G, P, Y],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, Y, Y, B, Y, B, Y, Y],   # wavy mouth shifted
            [Y, Y, B, Y, B, Y, B, Y],
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        # Frame 3: star burst – stars above head, dizzy mouth
        f3 = [
            [B, Y, P, Y, Y, P, Y, B],   # stars
            [Y, Y, Y, G, G, Y, Y, Y],
            [Y, P, Y, Y, Y, Y, P, Y],
            [Y, Y, G, Y, Y, G, Y, Y],
            [Y, Y, Y, Y, Y, Y, Y, Y],
            [Y, Y, B, Y, B, Y, B, Y],
            [Y, Y, Y, B, Y, B, Y, Y],
            [B, Y, Y, Y, Y, Y, Y, B],
        ]
        return [f1, f2, f3]


# ═══════════════════════ Sleep / Idle Face ════════════════════════════

def build_sleep_face() -> list:
    """
    Return a flat 64-pixel list for the idle sleep-mode display.
    Uses dim SL (green glow) so it looks like a low-power standby screen.
    """
    grid = [
        [B,  SL, SL, SL, SL, SL, SL, B],
        [SL, SL, SL, SL, SL, SL, SL, SL],
        [SL, B,  B,  SL, SL, B,  B,  SL],  # closed dot-eyes
        [SL, SL, SL, SL, SL, SL, SL, SL],
        [SL, SL, SL, SL, SL, SL, SL, SL],
        [SL, SL, B,  B,  B,  B,  SL, SL],  # neutral flat mouth
        [SL, SL, SL, SL, SL, SL, SL, SL],
        [B,  SL, SL, SL, SL, SL, SL, B],
    ]
    return [pixel for row in grid for pixel in row]


SLEEP_FACE: list = build_sleep_face()
