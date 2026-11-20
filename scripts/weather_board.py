# SPDX-License-Identifier: MIT
# weather_board.py - noknok Weather Board  v1.0.0
#
# Weather for a place you type in the app, on a noknok Display. Data: Open-Meteo.com (free, CC BY 4.0
# attribution) through the brain library noknok_feeds; the product itself does no network I/O.
# Needs the home WiFi and internet.
#
#   Page 1   temperature, the weather in words, wind and rain.
#   Page 2   the next 12 hours: one bar per hour (height = temperature, blue = chance of rain).
#   LED Button  short press = next page. The button LED colour follows the weather
#               (yellow clear, white cloudy, blue rain, cyan snow, purple thunderstorm).
#   Place    any town name ("Bern", "Lugano", "Zermatt"); it is looked up once with Open-Meteo's geocoder.
#
# If the data cannot be fetched the last weather stays on screen, greyed, with its age.
# Please check Open-Meteo's terms before selling a product that uses it (see data-sources/README.md).
# Needs the brain library noknok_feeds (DEV-?). Nothing is written to files. Factory reset = the brain's gesture.

from noknok import Conductor
import noknok_feeds as nf
import time

# WMO weather code -> (short text, LED colour)
SKY = {0: ("Clear", (255, 200, 0)), 1: ("Mostly clear", (255, 200, 0)), 2: ("Partly cloudy", (200, 220, 255)),
       3: ("Overcast", (150, 170, 200)), 45: ("Fog", (120, 120, 140)), 48: ("Rime fog", (120, 120, 140)),
       51: ("Light drizzle", (0, 90, 255)), 53: ("Drizzle", (0, 90, 255)), 55: ("Heavy drizzle", (0, 90, 255)),
       56: ("Freezing drizzle", (0, 150, 255)), 57: ("Freezing drizzle", (0, 150, 255)),
       61: ("Light rain", (0, 90, 255)), 63: ("Rain", (0, 60, 255)), 65: ("Heavy rain", (0, 30, 255)),
       66: ("Freezing rain", (0, 150, 255)), 67: ("Freezing rain", (0, 150, 255)),
       71: ("Light snow", (120, 255, 255)), 73: ("Snow", (120, 255, 255)), 75: ("Heavy snow", (120, 255, 255)),
       77: ("Snow grains", (120, 255, 255)), 80: ("Showers", (0, 90, 255)), 81: ("Showers", (0, 60, 255)),
       82: ("Heavy showers", (0, 30, 255)), 85: ("Snow showers", (120, 255, 255)), 86: ("Snow showers", (120, 255, 255)),
       95: ("Thunderstorm", (170, 0, 255)), 96: ("Thunder + hail", (170, 0, 255)), 99: ("Thunder + hail", (170, 0, 255))}
GREY, WHITE = 0x707070, 0xFFFFFF

c = Conductor()
c.enumerate()
if not (c.display and c.ledbutton):
    raise SystemExit("Weather Board needs a Display and an LED Button - check wiring.")
d, btn = c.display[0], c.ledbutton[0]

s = c.settings
s.defaults({"place": "Bern", "refresh_min": 15, "brightness": 80})


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def lamp(rgb, f=1.0):
    k = clamp(s.get("brightness"), 5, 255, 80) * f / 255
    btn.set_color(int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


def place():
    return (str(s.get("place") or "").strip() or "Bern")


feeds = nf.attach(c)
feeds.add("wx", nf.weather, every=clamp(s.get("refresh_min"), 5, 60, 15) * 60, place=place(), hours=12)
shown = {}


def settings_changed(changed=None):
    feeds.update("wx", place=place())
    feeds.feeds["wx"].every = clamp(s.get("refresh_min"), 5, 60, 15) * 60
    shown.clear()


s.on_change(settings_changed)
status = ["starting"]
s.info("place_found", lambda: (feeds.get("wx") or {}).get("place", place()))
s.info("temperature", lambda: (feeds.get("wx") or {}).get("temp"))
s.info("status", lambda: status[0])
s.info("source", lambda: nf.SRC_WEATHER)

d.clear(0)
d.region("head", 0, 0, 160, 14, size=12, align="left")
d.region("temp", 0, 16, 112, 32, size=32, align="left")
d.region("unit", 112, 20, 48, 16, size=16, align="left")
d.region("sky", 0, 50, 160, 14, size=12, align="left")
d.region("foot", 0, 68, 160, 10, size=8, align="left", color=GREY)
page = [0]
BAR_Y0, BAR_H = 20, 40


def put(name, text, color=WHITE):
    if shown.get(name) != (text, color):
        shown[name] = (text, color)
        d.set(name, text=text, color=color)


def draw_bars(data, grey):
    h = data["h"]
    if not h:
        return
    ts = [x["t"] for x in h]
    lo, hi = min(ts), max(ts)
    span = max(1.0, hi - lo)
    key = ("bars", tuple((x["t"], x["p"]) for x in h), grey)
    if shown.get("bars") == key:
        return
    shown["bars"] = key
    d.fill_rect(0, BAR_Y0, 160, BAR_H + 2, 0)
    w, gap = 11, 2
    for i, x in enumerate(h[:12]):
        bh = 3 + int((x["t"] - lo) / span * (BAR_H - 3))
        f = min(1.0, x["p"] / 100.0)            # chance of rain: grey -> blue
        col = 0x404040 if grey else (int(150 * (1 - f)) << 16) | (int(150 * (1 - f) + 120 * f) << 8) | int(150 * (1 - f) + 255 * f)
        d.fill_rect(2 + i * (w + gap), BAR_Y0 + BAR_H - bh, w, bh, col)


def render():
    data = feeds.get("wx")
    err = feeds.error("wx")
    age = feeds.age("wx")
    if data is None:
        put("head", place()[:26], GREY)
        put("temp", "--", GREY)
        put("unit", "")
        put("sky", "loading..." if err is None else "no data: " + str(err)[:16], GREY if err is None else 0xFF3030)
        put("foot", "")
        status[0] = "no data yet" if err is None else "error: %s" % err
        lamp((60, 60, 60), 0.5)
        return
    stale = err is not None or (age is not None and age > 3 * clamp(s.get("refresh_min"), 5, 60, 15) * 60)
    sky, rgb = SKY.get(data["code"], ("Weather %d" % data["code"], (200, 200, 200)))
    col = GREY if stale else WHITE
    if page[0] == 0:
        put("head", data["place"][:26], col)
        put("temp", "%d" % round(data["temp"]), col)
        put("unit", "C", col)
        put("sky", "%s %dkm/h %.1fmm" % (sky[:11], round(data["wind"]), data["rain"]), col)
    else:
        h = data["h"]
        put("head", "next %d h  %d to %d C" % (len(h), round(min(x["t"] for x in h)), round(max(x["t"] for x in h))), col)
        draw_bars(data, stale)
        put("sky", "blue = rain chance", GREY)
    put("foot", "open-meteo.com" + (" (old)" if stale else ""), GREY)
    status[0] = ("stale: %s" % err) if stale else "ok, %ds old" % (age or 0)
    lamp(rgb, 0.3 if stale else 1.0)


print("[weather] up, settings=%s" % s.all())
lamp((60, 60, 60), 0.5)
last_render = 0.0
while True:
    b = btn.read()
    if b is not None and b.press_event:
        page[0] = 1 - page[0]
        last_render = 0.0
        shown.clear()
        d.fill_rect(0, 16, 160, 62, 0)
    if feeds.poll() is not None:
        last_render = 0.0
    t = time.monotonic()
    if t - last_render >= 1.0:
        last_render = t
        render()
    c.sleep(0.05)
