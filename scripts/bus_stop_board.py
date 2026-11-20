# SPDX-License-Identifier: MIT
# bus_stop_board.py - noknok Bus Stop Board  v1.0.0
#
# The next departures of a Swiss bus / tram / train stop on a noknok Display.
# Data: transport.opendata.ch (built on opentransportdata.swiss) through the brain library
# noknok_feeds (the product itself does no network I/O). Needs the home WiFi and internet.
#
#   Stop        type the stop name in the app (any spelling the timetable knows, e.g. "Zuerich, Bellevue").
#   Line        optional filter, e.g. "9,11" = only lines 9 and 11 (empty = all).
#   Walk time   minutes you need to reach the stop. Green = you can make it with time to spare,
#               yellow = hurry, grey = too late. The button LED shows the same for the first
#               departure you can still reach (green / yellow / red = none soon).
#   LED Button  short press = switch to the second stop (if set) or refresh now.
#
# Times are minutes until the real departure (scheduled time + delay). If the data cannot be fetched
# the last board stays on screen, greyed, with its age. Nothing is written to files.
# Needs the brain library noknok_feeds (DEV-?). Factory reset = the brain's own gesture.

from noknok import Conductor
import noknok_feeds as nf
import time

GREEN, YELLOW, GREY, RED, WHITE = 0x30FF60, 0xFFD000, 0x707070, 0xFF3030, 0xFFFFFF     # display colours

c = Conductor()
c.enumerate()
if not (c.display and c.ledbutton):
    raise SystemExit("Bus Stop Board needs a Display and an LED Button - check wiring.")
d, btn = c.display[0], c.ledbutton[0]

s = c.settings
s.defaults({"stop": "Bern, Bahnhof", "stop2": "", "line": "", "walk_min": 3, "rows": 4,
            "refresh_s": 30, "timezone": "cet", "brightness": 80})
STD = {"cet": 1, "gmt": 0, "eet": 2}


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def lamp(rgb, f=1.0):
    k = clamp(s.get("brightness"), 5, 255, 80) * f / 255
    btn.set_color(int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


def stop_name(i):
    return (str(s.get("stop2") if i else s.get("stop")) or "").strip()


which = [0]
feeds = nf.attach(c)
feeds.add("deps", nf.departures, every=clamp(s.get("refresh_s"), 20, 300, 30), station=stop_name(0) or "Bern, Bahnhof", limit=15)


def settings_changed(changed=None):
    i = which[0] if stop_name(which[0]) else 0
    which[0] = i
    feeds.update("deps", station=stop_name(i) or "Bern, Bahnhof")
    feeds.feeds["deps"].every = clamp(s.get("refresh_s"), 20, 300, 30)
    shown.clear()


s.on_change(settings_changed)
status = ["starting"]
nxt = [None]
s.info("stop_found", lambda: (feeds.get("deps") or {}).get("stop", stop_name(which[0])))
s.info("next_min", lambda: nxt[0])
s.info("status", lambda: status[0])
s.info("source", lambda: nf.SRC_DEPARTURES)

d.clear(0)
d.region("head", 0, 0, 112, 14, size=12, align="left")
d.region("clock", 112, 0, 48, 14, size=12, align="right")
for i in range(4):
    d.region("r%d" % i, 0, 16 + i * 16, 160, 14, size=12, align="left")
shown = {}


def put(name, text, color=WHITE):
    """Redraw a region only when its text or colour changed (every draw is an I2C command)."""
    if shown.get(name) != (text, color):
        shown[name] = (text, color)
        d.set(name, text=text, color=color)


def line_filter():
    raw = str(s.get("line") or "")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def render():
    data = feeds.get("deps")
    err = feeds.error("deps")
    age = feeds.age("deps")
    have_clock = nf.clock_ok()
    now = time.time()
    std = STD.get(str(s.get("timezone")), 1)
    stale = data is not None and (err is not None or (age is not None and age > 150))
    if data is None:
        put("head", (stop_name(which[0]) or "?")[:18], GREY)
        put("clock", "", GREY)
        put("r0", "loading..." if err is None else "no data: " + str(err)[:15], GREY if err is None else RED)
        for i in range(1, 4):
            put("r%d" % i, "")
        status[0] = "no data yet" if err is None else "error: %s" % err
        lamp((255, 0, 0), 0.3)
        nxt[0] = None
        return
    if have_clock:
        h, m = nf.local_hm(now, std)
        put("clock", "%02d:%02d" % (h, m), GREY if stale else WHITE)
    else:
        put("clock", "--:--", GREY)
    put("head", data["stop"][:18], GREY if stale else WHITE)
    walk = clamp(s.get("walk_min"), 0, 30, 3)
    flt = line_filter()
    nrows = clamp(s.get("rows"), 2, 4, 4)
    lines = []
    first_ok = None
    for r in data["rows"]:
        if flt and r["line"].lower() not in flt:
            continue
        mins = int((r["ts"] + r["delay"] * 60 - now + 30) // 60) if have_clock else None
        if mins is not None and mins < 0:
            continue
        lines.append((r, mins))
        if first_ok is None and mins is not None and mins >= walk:
            first_ok = mins
        if len(lines) >= nrows:
            break
    for i in range(4):
        if i >= nrows:
            put("r%d" % i, "")
        elif i < len(lines):
            r, mins = lines[i]
            if mins is None:
                t, col = "--", GREY
            else:
                t = "now" if mins <= 0 else "%d'" % mins if mins < 60 else "%02d:%02d" % nf.local_hm(r["ts"] + r["delay"] * 60, std)
                col = GREY if (stale or mins < walk) else YELLOW if mins < walk + 2 else GREEN
            put("r%d" % i, "%-3s %-16.16s %4s" % (r["line"][:3], r["to"], t), col)
        elif i == 0:
            put("r0", "no matching departures", GREY)
        else:
            put("r%d" % i, "")
    nxt[0] = first_ok
    if stale:
        status[0] = "stale: %s (%ds old)" % (err or "slow", age or 0)
        lamp((255, 0, 0), 0.3)
    else:
        status[0] = "ok, %ds old" % (age or 0)
        if first_ok is None:
            lamp((255, 0, 0), 0.6)
        elif first_ok < walk + 2:
            lamp((255, 180, 0))
        else:
            lamp((0, 255, 60))


print("[bus] up, settings=%s" % s.all())
lamp((60, 60, 60))
last_render = 0.0
while True:
    b = btn.read()
    if b is not None and b.press_event:
        if stop_name(1):
            which[0] = 1 - which[0]
            settings_changed()
        else:
            feeds.refresh("deps")
    if feeds.poll() is not None:
        last_render = 0.0
    t = time.monotonic()
    if t - last_render >= 1.0:
        last_render = t
        render()
    c.sleep(0.05)
