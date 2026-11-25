# SPDX-License-Identifier: MIT
# light_meter.py - noknok Light Meter  v1.0.0
#
# A light meter for photography and for plants. A third-party Adafruit VEML7700 light sensor
# (Qwiic / Stemma QT) measures the light; a noknok Display shows lux and, for photographers,
# the shutter speed that fits your aperture and ISO (incident-light reading, the usual
# calibration constant 250: EV = log2(lux / 2.5) at ISO 100). Plug third-party boards in with the brain OFF.
#
#   Knob turn    change the highlighted value: aperture (f/1.4 ... f/22) or ISO (50 ... 1600)
#   Knob press   switch which of the two the knob changes (the highlighted one is yellow)
#   LED Button   HOLD: freeze the reading / release it (button LED amber while frozen)
#   Display      top: lux; middle: the shutter speed; bottom: aperture and ISO
#
# Aim the sensor at the light that falls ON the subject (an incident reading), not at the subject.
# It is a helpful estimate, not a lab instrument. Aperture and ISO are settings (the app shows the
# same values, they survive a power cut). Readings can be None on an I2C hiccup: shown as --.
# Factory reset = the brain's own gesture.

from noknok import Conductor
import noknok_thirdparty as tp
import math
import time

APERTURES = ("1.4", "2", "2.8", "4", "5.6", "8", "11", "16", "22")
ISOS = ("50", "100", "200", "400", "800", "1600")
SHUTTERS = (30, 15, 8, 4, 2, 1, 1 / 2, 1 / 4, 1 / 8, 1 / 15, 1 / 30, 1 / 60, 1 / 125, 1 / 250, 1 / 500,
            1 / 1000, 1 / 2000, 1 / 4000, 1 / 8000)
CAL = 2.5                      # lux per EV 0 at ISO 100 (incident, constant 250)

c = Conductor()
c.enumerate()
tp.attach(c)

if not (c.display and c.knob and c.ledbutton):
    raise SystemExit("Light Meter needs a Display, a Knob and an LED Button - check wiring.")
if not c.veml7700:
    raise SystemExit("No light sensor (Adafruit VEML7700) found - check wiring.")
d, knob, btn, light = c.display[0], c.knob[0], c.ledbutton[0], c.veml7700[0]

s = c.settings
s.defaults({"aperture": "5.6", "iso": "100", "brightness": 80})
ev_now = [None]
s.info("lux", lambda: None if light.lux is None else int(light.lux))
s.info("ev", lambda: None if ev_now[0] is None else round(ev_now[0], 1))


def pick(key, options, fallback):
    v = str(s.get(key))
    return v if v in options else fallback


def lamp(r, g, b):
    try:
        k = max(0, min(255, int(s.get("brightness")))) / 255
    except Exception:
        k = 0.3
    btn.set_color(int(r * k), int(g * k), int(b * k))


def shutter_text(t):
    """Nearest standard shutter speed as text that fits: 1/125, 1/4000, 0.5s, 2s, 15s."""
    best = min(SHUTTERS, key=lambda x: abs(math.log(x) - math.log(t)))
    if best >= 1:
        return "%ds" % best
    if best >= 0.5:
        return "0.5s"
    return "1/%d" % round(1 / best)


def exposure(lux, aperture, iso):
    """-> (EV at ISO 100, shutter seconds) for the given aperture (f-number) and ISO."""
    ev = math.log(lux / CAL) / math.log(2)
    t = (aperture * aperture) / (2 ** ev) * (100.0 / iso)
    return ev, t


d.clear(0)
d.region("lux", 0, 0, 160, 16, size=16, align="center")
d.region("shutter", 0, 18, 160, 32, size=32, align="center")
d.region("ap", 0, 58, 76, 14, size=12, align="right")
d.region("iso", 84, 58, 76, 14, size=12, align="left")

sel = [0]                     # 0 = knob changes aperture, 1 = ISO
frozen = [False]
held_lux = [None]


def draw(lux, t, ev):
    d.set("lux", text="--" if lux is None else "%d lx" % int(lux), color=0xFFFFFF)
    if t is None:
        d.set("shutter", text="--", size=32, color=0x808080)
    else:
        txt = shutter_text(t)
        d.set("shutter", text=txt, size=32 if len(txt) <= 5 else 24, color=0xFFB000 if frozen[0] else 0x00FF00)
    ap, iso = pick("aperture", APERTURES, "5.6"), pick("iso", ISOS, "100")
    d.set("ap", text="f/" + ap, color=0xFFFF00 if sel[0] == 0 else 0xA0A0A0)
    d.set("iso", text="ISO " + iso, color=0xFFFF00 if sel[0] == 1 else 0xA0A0A0)


def step(key, options, fallback, delta):
    i = options.index(pick(key, options, fallback)) + (1 if delta > 0 else -1)
    s.set(key, options[max(0, min(len(options) - 1, i))])


print("[meter] up, settings=%s" % s.all())
lamp(0, 255, 0)
knob_was = False
next_draw = 0.0
while True:
    now = time.monotonic()
    k = knob.read()
    if k is not None:
        if k.pressed and not knob_was:
            sel[0] = 1 - sel[0]
            next_draw = 0.0
        knob_was = k.pressed
        if k.delta:
            if sel[0] == 0:
                step("aperture", APERTURES, "5.6", k.delta)
            else:
                step("iso", ISOS, "100", k.delta)
            next_draw = 0.0
    b = btn.read()
    if b is not None and b.press_event:
        frozen[0] = not frozen[0]
        held_lux[0] = light.lux if frozen[0] else None
        lamp(255, 150, 0) if frozen[0] else lamp(0, 255, 0)
        next_draw = 0.0
    if now >= next_draw:
        next_draw = now + 0.3
        lux = held_lux[0] if frozen[0] else light.lux
        if lux is not None and lux > 0.01:
            ev, t = exposure(lux, float(pick("aperture", APERTURES, "5.6")), float(pick("iso", ISOS, "100")))
            ev_now[0] = ev
        else:
            ev, t = None, None
        draw(lux, t, ev)
    c.sleep(0.03)
