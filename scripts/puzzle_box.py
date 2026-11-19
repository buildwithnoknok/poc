# SPDX-License-Identifier: MIT
# puzzle_box.py - noknok Puzzle Box  v1.0.0
#
# A combination lock for an escape-room puzzle or a treasure box: turn the Knob like a
# safe dial, press the LED Button to enter each number.
#
#   Dial        0 - 39 (like a padlock). Turn the knob, the number shows on the display.
#   Enter       LED Button (or knob press = clear the numbers you entered so far).
#   Code        3 numbers by default, set in the app as text, e.g. "7-21-33".
#               Wrong code: red flash. With `show_hint` on, the display says how many of
#               the numbers were right (in the right place).
#   Lockout     After `lockout_after` wrong codes the box is locked for `lockout_s` seconds.
#   Open        Green light + fanfare for `open_s` seconds, then it locks again.
#
# The numbers are a setting (c.settings), so the host changes the code from the app
# without touching the box. Nothing is written to files. Hardware: Knob, LED Button, Buzzer,
# Display. Factory reset = the brain's own gesture.

from noknok import Conductor
import time

DIAL = 40                      # numbers 0..39
PURPLE, RED, GREEN, WHITE = (140, 40, 255), (255, 0, 0), (0, 255, 0), (200, 220, 255)

c = Conductor()
c.enumerate()

if not (c.knob and c.ledbutton and c.display and c.buzzer):
    raise SystemExit("Puzzle Box needs a Knob, an LED Button, a Display and a Buzzer - check wiring.")
knob, btn, d, buzzer = c.knob[0], c.ledbutton[0], c.display[0], c.buzzer[0]

s = c.settings
s.defaults({"code": "7-21-33", "show_hint": True, "lockout_after": 3, "lockout_s": 30,
            "open_s": 10, "volume": 40, "brightness": 120})


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def vol():    return clamp(s.get("volume"), 0, 100, 40)
def bright(): return clamp(s.get("brightness"), 5, 255, 120)


def lamp(rgb, f=1.0):
    k = bright() * f / 255
    btn.set_color(int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


def parse_code():
    """'7-21-33' -> [7, 21, 33]. Anything that is not digits separates numbers.
    A broken code falls back to the default, so the box can never be un-openable."""
    nums, cur = [], ""
    for ch in str(s.get("code")) + " ":
        if ch.isdigit():
            cur += ch
        elif cur:
            nums.append(max(0, min(DIAL - 1, int(cur))))
            cur = ""
    if not 1 <= len(nums) <= 6:
        return [7, 21, 33]
    return nums


state = ["Locked"]
s.info("state", lambda: state[0])

d.clear(0)
d.region("title", 0, 0, 160, 16, size=16, align="center")
d.region("dial", 0, 18, 160, 48, size=48, align="center")
d.region("entered", 0, 68, 160, 8, size=8, align="center", color=0x808080)


def entered_text(entered, total):
    parts = ["%d" % v for v in entered] + ["_"] * (total - len(entered))
    return " - ".join(parts)


def fail_feedback(right, total):
    lamp(RED)
    buzzer.tune(buzzer.BEEP_ERROR)
    d.set("title", text="WRONG", color=0xFF0000)
    if s.get("show_hint"):
        d.set("dial", text="%d/%d" % (right, total), size=32, color=0xFF8000)
    c.sleep(1.8)


def locked_out(seconds):
    t0 = time.monotonic()
    last = -1
    state[0] = "Locked out"
    lamp(RED, 0.3)
    d.set("title", text="LOCKED", color=0xFF0000)
    while time.monotonic() - t0 < seconds:
        left = int(seconds - (time.monotonic() - t0)) + 1
        if left != last:
            last = left
            d.set("dial", text=str(left), size=48, color=0xFF0000)
        knob.read()
        btn.read()
        c.sleep(0.1)
    knob.read()
    btn.read()


def opened():
    state[0] = "Open"
    lamp(GREEN)
    d.set("title", text="OPEN!", color=0x00FF00)
    d.set("dial", text="OK", size=48, color=0x00FF00)
    d.set("entered", text="")
    for f in (523, 659, 784, 1047, 1319):
        buzzer.note(f, 120, vol())
    t0 = time.monotonic()
    limit = clamp(s.get("open_s"), 3, 120, 10)
    while time.monotonic() - t0 < limit:
        knob.read()
        btn.read()
        c.sleep(0.1)
    buzzer.tune(buzzer.BEEP_OK)


def attempt():
    """One try at the whole code. Returns True if it was right."""
    code = parse_code()
    total = len(code)
    entered = []
    state[0] = "Locked"
    lamp(PURPLE, 0.6)
    knob.set_position(0)
    knob.read()
    btn.read()
    shown = None
    while len(entered) < total:
        k = knob.read()
        b = btn.read()
        value = (k.position if k is not None else 0) % DIAL
        if (value, len(entered)) != shown:
            shown = (value, len(entered))
            d.set("title", text="Number %d/%d" % (len(entered) + 1, total), color=0xFFFFFF)
            d.set("dial", text="%d" % value, size=48, color=0x8C28FF)
            d.set("entered", text=entered_text(entered, total))
        if k is not None and k.pressed and entered:
            entered = []                        # knob press = start the code again
            buzzer.play(300, 100, vol())
            c.sleep(0.4)
            shown = None
            continue
        if b is not None and b.press_event:
            entered.append(value)
            buzzer.play(1000 + 150 * len(entered), 100, vol())
            shown = None
        c.sleep(0.03)
    right = sum(1 for a, b2 in zip(entered, code) if a == b2)
    if right == total:
        return True
    fail_feedback(right, total)
    return False


buzzer.tune(buzzer.STARTUP)
print("[box] up, %d numbers" % len(parse_code()))
fails = 0
while True:
    if attempt():
        fails = 0
        opened()
    else:
        fails += 1
        if fails >= clamp(s.get("lockout_after"), 1, 10, 3):
            fails = 0
            locked_out(clamp(s.get("lockout_s"), 5, 600, 30))
