# SPDX-License-Identifier: MIT
# reaction_duel.py - noknok Reaction Duel  v1.0.0
#
# Two players, two LED Buttons (the first two found: left = player 1, blue; right = player 2,
# orange). Both buttons wait, dark. After a random pause both light GREEN with a beep: the
# first to press wins the round and the display shows the reaction time.
#
#   Press before GREEN  = false start: the other player gets the round.
#   First to `rounds_to_win` rounds wins the duel; a new duel starts by itself.
#   Fastest time of this session (since power-on) is kept on the display / in the app.
#
# Reaction times are measured on the brain: they include the polling delay (a few ms),
# so compare players, not stopwatches. If both press inside the same poll the round is a draw.
# Settings: c.settings (never a file). Factory reset = the brain's own gesture.

from noknok import Conductor
import time
import random

P_COLORS = ((0, 80, 255), (255, 130, 0))
P_HEX = (0x3070FF, 0xFF8000)
POLL_S = 0.004

c = Conductor()
c.enumerate()

if len(c.ledbutton) < 2:
    raise SystemExit("Reaction Duel needs 2 LED Buttons - check wiring.")
if not c.buzzer:
    raise SystemExit("No Buzzer found - check wiring.")
if not c.display:
    raise SystemExit("No Display found - check wiring.")
btn = c.ledbutton[:2]
buzzer, d = c.buzzer[0], c.display[0]

s = c.settings
s.defaults({"rounds_to_win": 3, "min_wait_s": 2, "max_wait_s": 6, "volume": 40, "brightness": 140})

best_ms = [None]
wins = [0, 0]


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def vol():    return clamp(s.get("volume"), 0, 100, 40)
def bright(): return clamp(s.get("brightness"), 5, 255, 140)


def lamp(i, rgb, f=1.0):
    k = bright() * f / 255
    btn[i].set_color(int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


s.info("best_ms", lambda: best_ms[0])

d.clear(0)
d.region("title", 0, 2, 160, 16, size=16, align="center")
d.region("p1", 0, 22, 64, 32, size=32, color=P_HEX[0], align="center")
d.region("colon", 64, 22, 32, 32, size=32, align="center")
d.region("p2", 96, 22, 64, 32, size=32, color=P_HEX[1], align="center")
d.region("info", 0, 62, 160, 16, size=16, align="center")
d.set("colon", text=":")


def show(title, info="", color=0xFFFFFF):
    d.set("title", text=title, color=color)
    d.set("p1", text=str(wins[0]))
    d.set("p2", text=str(wins[1]))
    d.set("info", text=info)


def tone(freq, ms):
    buzzer.play(freq, ms, vol())


def flush():
    for b in btn:
        b.read()


def one_round():
    """Returns (winner 0/1 or None for a draw, reaction ms or None, text)."""
    lo = clamp(s.get("min_wait_s"), 1, 10, 2)
    hi = max(lo + 1, clamp(s.get("max_wait_s"), 2, 20, 6))
    for i in range(2):
        lamp(i, P_COLORS[i], 0.25)
    show("Wait...", "", 0xFFFF00)
    flush()
    wait = lo + random.random() * (hi - lo)
    t0 = time.monotonic()
    while time.monotonic() - t0 < wait:
        for i in range(2):
            st = btn[i].read()
            if st is not None and st.press_event:
                lamp(i, (255, 0, 0))
                tone(200, 400)
                return 1 - i, None, "P%d early" % (i + 1)
        c.sleep(POLL_S)
    for i in range(2):
        lamp(i, (0, 255, 0))
    tone(1000, 150)
    show("GO!", "", 0x00FF00)
    flush()
    go = time.monotonic()
    while time.monotonic() - go < 3.0:
        pressed = [False, False]
        for i in range(2):
            st = btn[i].read()
            pressed[i] = bool(st is not None and st.press_event)
        now = time.monotonic()
        if pressed[0] and pressed[1]:
            return None, None, "Draw!"
        for i in range(2):
            if pressed[i]:
                ms = int((now - go) * 1000)
                return i, ms, "P%d %d ms" % (i + 1, ms)
        c.sleep(POLL_S)
    return None, None, "Too slow"


def duel():
    wins[0] = wins[1] = 0
    target = clamp(s.get("rounds_to_win"), 1, 9, 3)
    show("Reaction", "Get ready", 0xFFFFFF)
    c.sleep(1.5)
    while max(wins) < target:
        w, ms, text = one_round()
        if w is None:
            for i in range(2):
                btn[i].led_off()
            buzzer.tune(buzzer.BEEP_ERROR)
        else:
            wins[w] += 1
            lamp(w, (0, 255, 0))
            lamp(1 - w, (0, 0, 0))
            buzzer.tune(buzzer.BEEP_OK)
            if ms is not None and (best_ms[0] is None or ms < best_ms[0]):
                best_ms[0] = ms
        show("P%d scores" % (w + 1) if w is not None else "No point", text,
             P_HEX[w] if w is not None else 0xFF8000)
        c.sleep(2.0)
    w = 0 if wins[0] > wins[1] else 1
    show("P%d WINS!" % (w + 1), "best %sms" % best_ms[0] if best_ms[0] else "", P_HEX[w])
    for f in (523, 659, 784, 1047):
        buzzer.note(f, 140, vol())
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5:
        k = int((time.monotonic() - t0) * 4) % 2
        lamp(w, P_COLORS[w], 1.0 if k else 0.2)
        lamp(1 - w, (0, 0, 0))
        c.sleep(0.1)


buzzer.tune(buzzer.STARTUP)
print("[duel] up, settings=%s" % s.all())
while True:
    duel()
