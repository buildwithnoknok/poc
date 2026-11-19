# SPDX-License-Identifier: MIT
# stopwatch.py - noknok Stopwatch  v1.0.0
#
# A stopwatch with laps for sports, cooking, board games or "how long does the print take".
#
#   LED Button   start / stop (green while running, red while stopped with a time on it)
#   Knob press   LAP while running (lap time and split are shown, a short beep)
#                RESET while stopped (and clears the laps)
#   Knob turn    while stopped: look through the last 10 laps
#   Display      big time (seconds.hundredths up to a minute, then minutes:seconds), and the
#                last lap on the bottom line.
#
# Time comes from the brain's monotonic clock. Laps live in RAM only (nothing is written
# to files): a power cut clears them. Best lap is shown in the app as an info row.
# Factory reset = the brain's own gesture.

from noknok import Conductor
import time

MAX_LAPS = 10

c = Conductor()
c.enumerate()

if not (c.knob and c.ledbutton and c.display and c.buzzer):
    raise SystemExit("Stopwatch needs a Knob, an LED Button, a Display and a Buzzer - check wiring.")
knob, btn, d, buzzer = c.knob[0], c.ledbutton[0], c.display[0], c.buzzer[0]

s = c.settings
s.defaults({"beep": True, "volume": 40, "brightness": 120})


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def vol():    return clamp(s.get("volume"), 0, 100, 40)
def bright(): return clamp(s.get("brightness"), 5, 255, 120)


def lamp(r, g, b):
    k = bright() / 255
    btn.set_color(int(r * k), int(g * k), int(b * k))


def beep(freq, ms=100):
    if s.get("beep"):
        buzzer.play(freq, ms, vol())


def fmt(sec):
    """-> (text, size) that always fits the 160 px wide panel."""
    if sec < 60:
        return "%05.2f" % sec, 32
    if sec < 600:
        return "%d:%04.1f" % (int(sec // 60), sec % 60), 24
    if sec < 3600:
        return "%02d:%02d" % (int(sec // 60), int(sec % 60)), 32
    return "%d:%02d:%02d" % (int(sec // 3600), int((sec % 3600) // 60), int(sec % 60)), 16


def short(sec):
    """Compact lap time for the bottom line: 12.34 / 2:03.4 / 45:12"""
    if sec < 60:
        return "%.2f" % sec
    if sec < 600:
        return "%d:%04.1f" % (int(sec // 60), sec % 60)
    return "%d:%02d" % (int(sec // 60), int(sec % 60))


laps = []                    # list of (split since start, lap time)
state = {"run": False, "t0": 0.0, "elapsed": 0.0, "lap_start": 0.0, "view": -1}
s.info("best_lap", lambda: None if not laps else round(min(x[1] for x in laps), 2))
s.info("laps", lambda: len(laps))

d.clear(0)
d.region("time", 0, 8, 160, 32, size=32, align="center")
d.region("lap", 0, 52, 160, 16, size=16, align="center", color=0x80C0FF)
d.region("state", 0, 70, 160, 8, size=8, align="center", color=0x808080)


def elapsed(now):
    return state["elapsed"] + ((now - state["t0"]) if state["run"] else 0.0)


def draw_time(sec, color=0xFFFFFF):
    text, size = fmt(sec)
    d.set("time", text=text, size=size, color=color)


def draw_lap(view):
    if not laps:
        d.set("lap", text="")
        return
    i = len(laps) + view if view < 0 else view
    i = max(0, min(len(laps) - 1, i))
    d.set("lap", text="L%d %s" % (i + 1 + lap_offset[0], short(laps[i][1])))


lap_offset = [0]                 # laps dropped from the front once there are more than MAX_LAPS


def draw_state():
    if state["run"]:
        d.set("state", text="knob press = lap")
    elif elapsed(time.monotonic()) > 0:
        d.set("state", text="knob press = reset")
    else:
        d.set("state", text="button = start")


def start(now):
    state["run"] = True
    state["t0"] = now
    lamp(0, 255, 0)
    beep(1200)
    draw_state()


def stop(now):
    state["elapsed"] = elapsed(now)
    state["run"] = False
    lamp(255, 0, 0)
    beep(700)
    draw_time(state["elapsed"], 0xFF8000)
    draw_state()


def lap(now):
    e = elapsed(now)
    laps.append((e, e - state["lap_start"]))
    state["lap_start"] = e
    if len(laps) > MAX_LAPS:
        del laps[0]
        lap_offset[0] += 1
    state["view"] = -1
    beep(1800, 60)
    draw_lap(-1)


def reset():
    state["elapsed"] = 0.0
    state["lap_start"] = 0.0
    state["view"] = -1
    del laps[:]
    lap_offset[0] = 0
    lamp(255, 255, 255)
    beep(500)
    draw_time(0.0, 0x808080)
    draw_lap(-1)
    draw_state()


reset()
buzzer.tune(buzzer.STARTUP)
print("[stopwatch] up, settings=%s" % s.all())
last_draw = 0.0
knob_was = False
while True:
    now = time.monotonic()
    b = btn.read()
    if b is not None and b.press_event:
        stop(now) if state["run"] else start(now)
    k = knob.read()
    if k is not None:
        if k.pressed and not knob_was:
            lap(now) if state["run"] else reset()
        knob_was = k.pressed
        if k.delta and not state["run"] and laps:
            state["view"] = max(-len(laps), min(-1, state["view"] + (1 if k.delta > 0 else -1)))
            draw_lap(state["view"])
    if state["run"] and now - last_draw >= 0.05:
        last_draw = now
        draw_time(elapsed(now))
    c.sleep(0.01)
