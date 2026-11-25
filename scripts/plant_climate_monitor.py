# SPDX-License-Identifier: MIT
# plant_climate_monitor.py - noknok Plant Climate Monitor  v1.0.0
#
# Is the spot good for your plant? A light sensor and a temperature sensor next to a
# noknok Display and an LED Button. Two third-party Qwiic / Stemma QT boards:
#   Adafruit VEML7700 (light, lux)   and   SparkFun TMP102 (temperature)
# (plug third-party boards in with the brain OFF - see the authoring guide).
#
#   Display page 1 "Now"    light, temperature, verdict (Happy! / Too dark / Too hot ...)
#   Display page 2 "Range"  coldest and warmest temperature since power-on
#   Display page 3 "Light"  hours of good light since power-on
#   LED Button  short press = next page. The button LED is the plant's mood:
#               green = happy, amber = light problem, blue = too cold, red = too hot,
#               off at night (the display dims too, `night_dim`).
#   Pick the plant in the app (Succulent / Leafy / Herb / Orchid). The ranges are a ROUGH
#   guide for typical houseplants, not plant science: your plant may disagree.
#
# Totals live in RAM only (nothing is written to files): a power cut starts them again.
# Readings can be None on an I2C hiccup: that turn is skipped. Factory reset = the brain's gesture.

from noknok import Conductor
import noknok_thirdparty as tp
import time

# key: (name, min C, max C, min lux, max lux)
PLANTS = {
    "succulent": ("Succulent", 15, 30, 5000, 40000),
    "leafy": ("Leafy", 16, 27, 1000, 10000),
    "herb": ("Herb", 15, 25, 5000, 25000),
    "orchid": ("Orchid", 16, 28, 1500, 6000),
}
NIGHT_LUX = 2.0
GREEN, AMBER, BLUE, RED = (0, 255, 0), (255, 150, 0), (0, 90, 255), (255, 0, 0)

c = Conductor()
c.enumerate()
tp.attach(c)

if not c.display or not c.ledbutton:
    raise SystemExit("Plant Climate Monitor needs a Display and an LED Button - check wiring.")
if not c.veml7700:
    raise SystemExit("No light sensor (Adafruit VEML7700) found - check wiring.")
if not c.tmp102:
    raise SystemExit("No temperature sensor (SparkFun TMP102) found - check wiring.")
d, btn = c.display[0], c.ledbutton[0]
light, thermo = c.veml7700[0], c.tmp102[0]

s = c.settings
s.defaults({"plant": "leafy", "night_dim": True, "brightness": 80})
s.info("lux", lambda: None if light.lux is None else int(light.lux))
s.info("temperature", lambda: None if thermo.temperature is None else round(thermo.temperature, 1))

t_min = [None]
t_max = [None]
good_light_s = [0.0]
page = [0]
last_lux = [None]
last_temp = [None]


def plant():
    p = s.get("plant")
    return PLANTS.get(p, PLANTS["leafy"])


def lamp(rgb, f=1.0):
    try:
        b = max(0, min(255, int(s.get("brightness"))))
    except Exception:
        b = 80
    k = b * f / 255
    btn.set_color(int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


d.clear(0)
d.region("title", 0, 0, 160, 16, size=16, align="center")
d.region("r1", 0, 22, 160, 16, size=16, align="center")
d.region("r2", 0, 42, 160, 16, size=16, align="center")
d.region("r3", 0, 62, 160, 16, size=16, align="center")


def verdict(lux, temp):
    """-> (text, led colour or None, display colour). Night = no verdict, LED off."""
    name, tmin, tmax, lmin, lmax = plant()
    if lux is not None and lux < NIGHT_LUX:
        return "Sleeping", None, 0x6070A0
    if temp is not None and temp > tmax:
        return "Too hot", RED, 0xFF3030
    if temp is not None and temp < tmin:
        return "Too cold", BLUE, 0x3070FF
    if lux is not None and lux < lmin:
        return "Too dark", AMBER, 0xFF9600
    if lux is not None and lux > lmax:
        return "Too bright", AMBER, 0xFF9600
    if lux is None or temp is None:
        return "...", None, 0x808080
    return "Happy!", GREEN, 0x00FF00


def draw():
    name, tmin, tmax, lmin, lmax = plant()
    lux, temp = last_lux[0], last_temp[0]
    p = page[0]
    if p == 0:
        text, led, col = verdict(lux, temp)
        d.set("title", text=name, color=0xFFFFFF)
        d.set("r1", text="--" if lux is None else "%d lx" % int(lux),
              color=0xFF9600 if lux is not None and (lux < lmin or lux > lmax) and lux >= NIGHT_LUX else 0xFFFFFF)
        d.set("r2", text="--" if temp is None else "%.1f C" % temp,
              color=0xFF3030 if temp is not None and temp > tmax else (0x3070FF if temp is not None and temp < tmin else 0xFFFFFF))
        d.set("r3", text=text, color=col)
        if led is None:
            btn.led_off()
        else:
            lamp(led)
    elif p == 1:
        d.set("title", text="Temp range", color=0xFFFFFF)
        d.set("r1", text="--" if t_min[0] is None else "min %.1f C" % t_min[0])
        d.set("r2", text="--" if t_max[0] is None else "max %.1f C" % t_max[0])
        d.set("r3", text="since boot", color=0x808080)
    else:
        hours = min(99.9, good_light_s[0] / 3600)
        d.set("title", text="Good light", color=0xFFFFFF)
        d.set("r1", text="%.1f hours" % hours)
        d.set("r2", text="lx > %d" % lmin, color=0x808080)
        d.set("r3", text="since boot", color=0x808080)


dim_state = [None]


def update_backlight():
    lux = last_lux[0]
    if lux is None or not s.get("night_dim"):
        want = 1.0
    else:
        night = lux < NIGHT_LUX
        want = 0.1 if night else 1.0
    if want != dim_state[0]:
        dim_state[0] = want
        d.backlight(want)


print("[plant] up, settings=%s" % s.all())
draw()
last_tick = time.monotonic()
next_draw = 0.0
while True:
    now = time.monotonic()
    b = btn.read()
    if b is not None and b.press_event:
        page[0] = (page[0] + 1) % 3
        next_draw = 0.0
    lx = light.lux
    tc = thermo.temperature
    if lx is not None:
        last_lux[0] = lx
        if lx >= plant()[3]:
            good_light_s[0] += now - last_tick
    if tc is not None:
        last_temp[0] = tc
        t_min[0] = tc if t_min[0] is None else min(t_min[0], tc)
        t_max[0] = tc if t_max[0] is None else max(t_max[0], tc)
    last_tick = now
    if now >= next_draw:
        next_draw = now + 1.0
        update_backlight()
        draw()
    c.sleep(0.1)
