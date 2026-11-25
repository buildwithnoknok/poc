# SPDX-License-Identifier: MIT
# dice_roller.py - noknok Dice Roller  v1.0.0
#
# One LED Button rolls the dice for board games, role-play or "who goes first".
#
#   Press        roll (a short tumble on the display, slowing down, then the result)
#   Hold 1 s     next kind of dice: d6 > 2d6 > d20 > d100 > coin
#   Kinds        d6 = one die, 2d6 = two dice (sum and both dice), d20, d100 (1-100), coin (heads / tails)
#   Fun          a natural 20 on the d20 (or a 12 on 2d6, 100 on d100) plays a fanfare, a 1 a sad tone.
#
# The kind of dice is the same setting the app shows (c.settings), so it survives a power cut.
# Random numbers come from CircuitPython's `random` (good enough for games, not for gambling).
# Factory reset = the brain's own gesture (hold the button while plugging in).

from noknok import Conductor
import time
import random

KINDS = ("d6", "2d6", "d20", "d100", "coin")
NAMES = {"d6": "One die", "2d6": "Two dice", "d20": "d20", "d100": "d100", "coin": "Coin"}
HOLD_S = 1.0

c = Conductor()
c.enumerate()

if not (c.ledbutton and c.display and c.buzzer):
    raise SystemExit("Dice Roller needs an LED Button, a Display and a Buzzer - check wiring.")
btn, d, buzzer = c.ledbutton[0], c.display[0], c.buzzer[0]

s = c.settings
s.defaults({"dice": "d6", "volume": 40, "brightness": 120})
rolls = [0]
last = ["-"]
s.info("rolls", lambda: rolls[0])
s.info("last", lambda: last[0])


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def vol():    return clamp(s.get("volume"), 0, 100, 40)
def bright(): return clamp(s.get("brightness"), 5, 255, 120)


def kind():
    k = s.get("dice")
    return k if k in KINDS else "d6"


def lamp(r, g, b):
    k = bright() / 255
    btn.set_color(int(r * k), int(g * k), int(b * k))


d.clear(0)
d.region("title", 0, 0, 160, 16, size=16, align="center")
d.region("big", 0, 18, 160, 48, size=48, align="center")
d.region("small", 0, 66, 160, 12, size=12, align="center", color=0x808080)


def roll_once(k):
    """-> (big text, small text, 'high' / 'low' / None)"""
    if k == "d6":
        v = random.randint(1, 6)
        return str(v), "", ("high" if v == 6 else "low" if v == 1 else None)
    if k == "2d6":
        a, b = random.randint(1, 6), random.randint(1, 6)
        return str(a + b), "%d + %d" % (a, b), ("high" if a + b == 12 else "low" if a + b == 2 else None)
    if k == "d20":
        v = random.randint(1, 20)
        return str(v), "", ("high" if v == 20 else "low" if v == 1 else None)
    if k == "d100":
        v = random.randint(1, 100)
        return str(v), "", ("high" if v == 100 else "low" if v == 1 else None)
    return ("HEADS" if random.randint(0, 1) else "TAILS"), "", None


def show(big, small, k, color=0xFFFFFF):
    size = 32 if k == "coin" else 48
    d.set("title", text=NAMES[k], color=0x8CA0FF)
    d.set("big", text=big, size=size, color=color)
    d.set("small", text=small)


def tumble(k):
    delay = 0.04
    while delay < 0.4:
        big, small, _ = roll_once(k)
        show(big, "", k, 0x808080)
        if delay > 0.15:
            buzzer.play(900, 100, vol() // 2)
        lamp(random.randint(60, 255), random.randint(60, 255), random.randint(60, 255))
        c.sleep(delay)
        delay *= 1.28


def do_roll():
    k = kind()
    tumble(k)
    big, small, flag = roll_once(k)
    rolls[0] += 1
    last[0] = big + ((" (" + small + ")") if small else "")
    if flag == "high":
        show(big, small, k, 0x00FF00)
        lamp(0, 255, 0)
        for f in (784, 988, 1175, 1568):
            buzzer.note(f, 100, vol())
    elif flag == "low":
        show(big, small, k, 0xFF3030)
        lamp(255, 0, 0)
        buzzer.tune(buzzer.BEEP_ERROR)
    else:
        show(big, small, k)
        lamp(0, 80, 255)
        buzzer.play(1200, 100, vol())


def next_kind():
    k = KINDS[(KINDS.index(kind()) + 1) % len(KINDS)]
    s.set("dice", k)
    show("?", "press = roll", k, 0x808080)
    lamp(255, 150, 0)
    buzzer.play(600, 100, vol())


show("?", "press = roll, hold = next", kind(), 0x808080)
lamp(255, 255, 255)
buzzer.tune(buzzer.STARTUP)
print("[dice] up, settings=%s" % s.all())
held = None
while True:
    now = time.monotonic()
    b = btn.read()
    if b is not None:
        if b.press_event:
            held = now
        if held is not None and b.pressed and now - held >= HOLD_S:
            held = None
            next_kind()
            while True:                       # wait for release so the hold does not roll
                r = btn.read()
                if r is None or not r.pressed:
                    break
                c.sleep(0.03)
        elif held is not None and b.release_event and now - held < HOLD_S:
            held = None
            do_roll()
        elif not b.pressed and not b.release_event:
            held = None
    c.sleep(0.03)
