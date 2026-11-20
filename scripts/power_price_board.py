# SPDX-License-Identifier: MIT
# power_price_board.py - noknok Power Price Board  v1.0.0
#
# "Is electricity cheap right now?" The day-ahead wholesale price of a European market zone (default
# Switzerland) on a noknok Display, so you can start the washing machine or charge the car when power is cheap.
# Data: Energy-Charts (Fraunhofer ISE, CC BY 4.0) through the brain library noknok_feeds; the product
# itself does no network I/O. Needs the home WiFi and internet.
#
#   Page 1   the price now (cents per kWh), the word CHEAP / OK / PRICEY, and the cheapest 2-hour window ahead.
#   Page 2   one bar per hour for the hours we know (green cheap, amber ok, red pricey, white = now).
#   LED Button  short press = next page. The button LED shows the level (green / amber / red).
#   Cheap and pricey are relative: the cheapest / dearest quarter (percentages in the app) of the hours we know.
#
# IMPORTANT: this is the EXCHANGE price (EUR/MWh / 10), NOT your tariff. Your bill has grid fees, taxes
# and a fixed price or a different tariff. Use it as a hint for WHEN, not for how much.
# Tomorrow's prices appear around 13:00; before that the board shows what is known. Needs the brain library
# noknok_feeds (DEV-?). Nothing is written to files. Factory reset = the brain's own gesture.

from noknok import Conductor
import noknok_feeds as nf
import time

GREY, WHITE = 0x707070, 0xFFFFFF
LEVELS = (("CHEAP", 0x30FF60, (0, 255, 60)), ("OK", 0xFFD000, (255, 180, 0)), ("PRICEY", 0xFF3030, (255, 0, 0)))
STD = {"cet": 1, "gmt": 0, "eet": 2}

c = Conductor()
c.enumerate()
if not (c.display and c.ledbutton):
    raise SystemExit("Power Price Board needs a Display and an LED Button - check wiring.")
d, btn = c.display[0], c.ledbutton[0]

s = c.settings
s.defaults({"zone": "CH", "cheap_pct": 25, "pricey_pct": 75, "timezone": "cet", "brightness": 80})


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def lamp(rgb, f=1.0):
    k = clamp(s.get("brightness"), 5, 255, 80) * f / 255
    btn.set_color(int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


def zone():
    z = str(s.get("zone"))
    return z if z in nf.ZONES else "CH"


def std():
    return STD.get(str(s.get("timezone")), 1)


feeds = nf.attach(c)
feeds.add("price", nf.power_price, every=1800, zone=zone(), std_hours=std())
shown = {}


def settings_changed(changed=None):
    feeds.update("price", zone=zone(), std_hours=std())
    shown.clear()


s.on_change(settings_changed)
status = ["starting"]
state = {"level": None, "now": None}
s.info("price_now", lambda: state["now"])
s.info("level", lambda: LEVELS[state["level"]][0] if state["level"] is not None else None)
s.info("status", lambda: status[0])
s.info("source", lambda: nf.SRC_POWER)

d.clear(0)
d.region("head", 0, 0, 160, 14, size=12, align="left")
d.region("big", 0, 16, 128, 32, size=32, align="left")
d.region("unit", 128, 20, 32, 16, size=16, align="left")
d.region("level", 0, 50, 160, 14, size=12, align="left")
d.region("foot", 0, 68, 160, 10, size=8, align="left", color=GREY)
page = [0]
BAR_Y0, BAR_H = 18, 44


def put(name, text, color=WHITE):
    if shown.get(name) != (text, color):
        shown[name] = (text, color)
        d.set(name, text=text, color=color)


def percentile(vals, pct):
    v = sorted(vals)
    return v[min(len(v) - 1, max(0, int(round((len(v) - 1) * pct / 100.0))))]


def analyse(data, now):
    """-> dict: current hour index, per-hour levels, price now, best 2-hour start (UTC epoch) or None."""
    p = data["p"]
    h0 = data["h0"]
    known = [x for x in p if x is not None]
    lo = percentile(known, clamp(s.get("cheap_pct"), 5, 50, 25))
    hi = percentile(known, clamp(s.get("pricey_pct"), 50, 95, 75))
    levels = [None if x is None else (0 if x <= lo else 2 if x >= hi else 1) for x in p]
    cur = (now - h0) // 3600
    best, best_i = None, None
    for i in range(max(0, cur), len(p) - 1):
        if p[i] is None or p[i + 1] is None:
            continue
        v = p[i] + p[i + 1]
        if best is None or v < best:
            best, best_i = v, i
    price_now = data["cur"] if data["cur"] is not None else (p[cur] if 0 <= cur < len(p) else None)
    return {"cur": cur, "levels": levels, "now": price_now, "best": None if best_i is None else h0 + best_i * 3600,
            "min": min(known), "max": max(known)}


def draw_bars(data, a, grey):
    p, lv = data["p"], a["levels"]
    start = max(0, a["cur"])
    idx = list(range(start, min(len(p), start + 24)))
    key = ("bars", tuple(p[i] for i in idx), a["cur"], grey)
    if shown.get("bars") == key or not idx:
        return
    shown["bars"] = key
    d.fill_rect(0, BAR_Y0, 160, BAR_H + 2, 0)
    vals = [p[i] for i in idx if p[i] is not None]
    lo, hi = min(vals), max(vals)
    span = max(0.5, hi - lo)
    w = max(2, min(12, 156 // len(idx) - 1))
    for k, i in enumerate(idx):
        if p[i] is None:
            continue
        bh = 3 + int((p[i] - lo) / span * (BAR_H - 3))
        col = 0x404040 if grey else (WHITE if i == a["cur"] else LEVELS[lv[i]][1])
        d.fill_rect(2 + k * (w + 1), BAR_Y0 + BAR_H - bh, w, bh, col)


def render():
    data = feeds.get("price")
    err = feeds.error("price")
    age = feeds.age("price")
    if data is None:
        put("head", "%s power price" % zone(), GREY)
        put("big", "--", GREY)
        put("unit", "")
        put("level", "loading..." if err is None else "no data: " + str(err)[:16], GREY if err is None else 0xFF3030)
        put("foot", "")
        status[0] = "no data yet" if err is None else "error: %s" % err
        lamp((60, 60, 60), 0.5)
        return
    now = int(time.time())
    stale = err is not None and (age is None or age > 4 * 3600)
    a = analyse(data, now)
    col = GREY if stale else WHITE
    lvl = None if (a["cur"] < 0 or a["cur"] >= len(data["p"]) or a["levels"][a["cur"]] is None) else a["levels"][a["cur"]]
    state["level"], state["now"] = lvl, a["now"]
    if page[0] == 0:
        put("head", "%s wholesale ct/kWh" % zone(), col)
        put("big", "--" if a["now"] is None else "%.1f" % a["now"], col)
        put("unit", "ct", GREY)
        if lvl is None:
            put("level", "no price for this hour", GREY)
        else:
            best = ""
            if a["best"] is not None:
                h, m = nf.local_hm(a["best"], std())
                best = "  best 2h: %02d:%02d" % (h, m)
            put("level", (LEVELS[lvl][0] + best)[:26], GREY if stale else LEVELS[lvl][1])
    else:
        put("head", "next: %.1f to %.1f ct" % (a["min"], a["max"]), col)
        draw_bars(data, a, stale)
        put("level", "white = now, not a tariff", GREY)
    put("foot", "energy-charts.info", GREY)
    status[0] = ("stale: %s" % err) if stale else "ok, %ds old" % (age or 0)
    if lvl is None or stale:
        lamp((60, 60, 60), 0.5)
    else:
        lamp(LEVELS[lvl][2])


print("[power] up, settings=%s" % s.all())
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
