# SPDX-License-Identifier: MIT
# spirit_level.py - noknok Spirit Level  v1.0.0
#
# A digital spirit level for shelves, tables, 3D-printer beds and picture frames.
# A third-party MSA311 accelerometer (Adafruit 5309 or a compatible Qwiic / Stemma QT copy)
# feels which way is down; a noknok Display shows a bubble and the tilt in degrees.
# Plug third-party boards in with the brain OFF.
#
#   Lay the board flat on the surface. The bubble moves towards the HIGH side, like a real
#   bubble level; the cross is "level". Bottom line: tilt left-right / front-back in degrees.
#   LED Button   short press = call this surface "zero" (ZERO), hold 1 s = back to the board's own zero
#                The button LED is green when both tilts are inside the tolerance, orange when not.
#   Tolerance and the scale of the bubble field are settings in the app.
#
# Angles come from the direction of gravity, so the board must stand still while you read it
# (a bump shows as a wobble). The zero is kept in RAM only. Readings can be None on an I2C hiccup:
# that turn is skipped. Factory reset = the brain's own gesture.

from noknok import Conductor
import noknok_thirdparty as tp
import math
import time

FIELD_W, FIELD_H = 160, 56
CX, CY = FIELD_W // 2, FIELD_H // 2
BUBBLE = 10

c = Conductor()
c.enumerate()
tp.attach(c)

if not c.display or not c.ledbutton:
    raise SystemExit("Spirit Level needs a Display and an LED Button - check wiring.")
if not c.msa311:
    raise SystemExit("No accelerometer (MSA311) found - check wiring.")
d, btn, acc = c.display[0], c.ledbutton[0], c.msa311[0]

s = c.settings
s.defaults({"tolerance": 0.5, "range_deg": 15, "brightness": 80})

tilt = [0.0, 0.0]                  # smoothed raw tilt (deg): x = right side down, y = front down
zero = [0.0, 0.0]
level_now = [None]
s.info("tilt_x", lambda: round(tilt[0] - zero[0], 1))
s.info("tilt_y", lambda: round(tilt[1] - zero[1], 1))


def num(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, float(v)))
    except Exception:
        return fallback


def lamp(rgb):
    b = int(num(s.get("brightness"), 5, 255, 80))
    k = b / 255
    btn.set_color(int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


def angles(a):
    """Tilt from gravity, degrees: (about the long axis, about the short axis)."""
    ax, ay, az = a
    return (math.degrees(math.atan2(ax, math.sqrt(ay * ay + az * az))),
            math.degrees(math.atan2(ay, math.sqrt(ax * ax + az * az))))


d.clear(0)
d.region("read", 0, 62, 160, 16, size=16, align="center")
prev = [None]


def cross():
    d.fill_rect(0, CY, FIELD_W, 1, 0x404040)
    d.fill_rect(CX, 0, 1, FIELD_H, 0x404040)
    d.fill_rect(CX - 8, CY - 8, 16, 1, 0x808080)
    d.fill_rect(CX - 8, CY + 7, 16, 1, 0x808080)
    d.fill_rect(CX - 8, CY - 8, 1, 16, 0x808080)
    d.fill_rect(CX + 7, CY - 8, 1, 16, 0x808080)


def draw(x, y, ok):
    rng = num(s.get("range_deg"), 5, 45, 15)
    px = CX + int(max(-1.0, min(1.0, x / rng)) * (CX - BUBBLE))
    py = CY + int(max(-1.0, min(1.0, y / rng)) * (CY - BUBBLE))
    if prev[0] is not None:
        d.fill_rect(prev[0][0] - BUBBLE // 2, prev[0][1] - BUBBLE // 2, BUBBLE, BUBBLE, 0)
    cross()
    d.fill_rect(px - BUBBLE // 2, py - BUBBLE // 2, BUBBLE, BUBBLE, 0x00FF00 if ok else 0xFF8000)
    prev[0] = (px, py)
    d.set("read", text="%+.1f %+.1f" % (x, y), color=0x00FF00 if ok else 0xFFFFFF)


def take_zero():
    zero[0], zero[1] = tilt[0], tilt[1]
    lamp((255, 255, 255))
    c.sleep(0.2)


print("[level] up, settings=%s" % s.all())
first = True
held = None
while True:
    now = time.monotonic()
    b = btn.read()
    if b is not None:
        if b.press_event:
            held = now
        if held is not None and b.pressed and now - held >= 1.0:
            held = None
            zero[0] = zero[1] = 0.0
            lamp((255, 255, 255))
        elif held is not None and b.release_event and now - held < 1.0:
            held = None
            take_zero()
        elif not b.pressed and not b.release_event:
            held = None
    a = acc.acceleration
    if a is not None:
        x, y = angles(a)
        if first:
            tilt[0], tilt[1], first = x, y, False
        else:
            tilt[0] += 0.4 * (x - tilt[0])               # smooth the jitter
            tilt[1] += 0.4 * (y - tilt[1])
        rx, ry = tilt[0] - zero[0], tilt[1] - zero[1]
        tol = num(s.get("tolerance"), 0.1, 5.0, 0.5)
        ok = abs(rx) <= tol and abs(ry) <= tol
        if ok != level_now[0]:
            level_now[0] = ok
            lamp((0, 255, 0) if ok else (255, 100, 0))
        draw(rx, ry, ok)
    c.sleep(0.1)
