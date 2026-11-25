# SPDX-License-Identifier: MIT
# breathing_guide.py - noknok Breathing Guide  v1.0.0
#
# A calm light you breathe with. The LEDs 16x ring fills from the middle outwards while you
# breathe in, holds, and fades back while you breathe out. No screen, no numbers.
#
#   Knob turn    choose a pattern (the ring shows 1, 2 or 3 lit LEDs for a moment):
#                  1 = Box 4-4-4-4     2 = Relax 4-7-8     3 = Calm 5-5
#   Knob press   start / stop a session
#   Session      runs `session_min` minutes and ends with a soft fade; a quiet chime if
#                `sound` is on (it is off by default: the light does the work).
#
# Needs a noknok LEDs 16x (firmware 2.2.0+, USB), a Knob and a Buzzer. The same settings are in
# the app: pattern, minutes, colour, brightness, sound.
# LED order on the 16x: 0-11 outer ring clockwise, 12-15 inner. Factory reset = the app.

from noknok import Conductor
import time

# (name, inhale s, hold s, exhale s, hold s)
PATTERNS = {"box": (4, 4, 4, 4), "relax": (4, 7, 8, 0), "calm": (5, 0, 5, 0)}
ORDER = ("box", "relax", "calm")
FILL_ORDER = (12, 13, 14, 15, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)   # middle first, then ring
FRAME_S = 0.1

c = Conductor()
c.enumerate_all()

if not c.leds16:
    raise SystemExit("Breathing Guide needs a noknok LEDs 16x - check wiring.")
if not c.knob:
    raise SystemExit("Breathing Guide needs a Knob - check wiring.")
ring, knob = c.leds16[0], c.knob[0]
buzzer = c.buzzer[0] if c.buzzer else None

s = c.settings
s.defaults({"pattern": "box", "session_min": 5, "color": "#5090FF", "brightness": 120, "sound": False})


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def rgb():
    try:
        h = str(s.get("color")).lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return (80, 144, 255)


def pattern_name():
    p = s.get("pattern")
    return p if p in PATTERNS else "box"


def paint(level, floor=0.03):
    """level 0..1 = how much of the ring is lit (middle first, the last LED fades in)."""
    level = max(0.0, min(1.0, level))
    r, g, b = rgb()
    k = clamp(s.get("brightness"), 5, 255, 120) / 255
    lit = level * 16
    px = [(0, 0, 0)] * 16
    for rank, led in enumerate(FILL_ORDER):
        f = max(floor, min(1.0, lit - rank))
        px[led] = (int(r * k * f), int(g * k * f), int(b * k * f))
    ring.set_all_pixels(px)


def ease(x):
    """smooth start and end (smoothstep)"""
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def chime(freqs):
    if buzzer and s.get("sound"):
        for f in freqs:
            buzzer.note(f, 150, 20)


def knob_wait_release():
    while True:
        k = knob.read()
        if k is None or not k.pressed:
            return
        c.sleep(0.03)


def show_pattern():
    idx = ORDER.index(pattern_name())
    r, g, b = rgb()
    px = [(0, 0, 0)] * 16
    for i in range(idx + 1):
        px[12 + i] = (r, g, b)
    ring.set_all_pixels(px)
    c.sleep(1.2)               # turns during this time add up in the knob; the main loop applies them


def phase(seconds, start, end):
    """Move the ring level from start to end in `seconds`. Returns False if stopped."""
    t0 = time.monotonic()
    while True:
        x = (time.monotonic() - t0) / seconds if seconds else 1.0
        paint(start + (end - start) * ease(x))
        if x >= 1.0:
            return True
        k = knob.read()
        if k is not None and k.pressed:
            return False
        c.sleep(FRAME_S)


def session():
    end = time.monotonic() + clamp(s.get("session_min"), 1, 60, 5) * 60
    pat = PATTERNS[pattern_name()]
    chime((659, 784))
    while time.monotonic() < end:
        inh, h1, exh, h2 = pat
        if not phase(inh, 0.0, 1.0):
            break
        if h1 and not phase(h1, 1.0, 1.0):
            break
        if not phase(exh, 1.0, 0.0):
            break
        if h2 and not phase(h2, 0.0, 0.0):
            break
    chime((784, 659, 523))
    knob_wait_release()


print("[breath] up, settings=%s" % s.all())
if buzzer:
    buzzer.tune(buzzer.STARTUP)
paint(0.0)
while True:
    k = knob.read()
    if k is not None and k.delta:
        idx = (ORDER.index(pattern_name()) + (1 if k.delta > 0 else -1)) % 3
        s.set("pattern", ORDER[idx])
        show_pattern()
        paint(0.0)
    elif k is not None and k.pressed:
        knob_wait_release()
        session()
        paint(0.0)
    c.sleep(0.05)
