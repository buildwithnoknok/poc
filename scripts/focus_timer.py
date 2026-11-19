# SPDX-License-Identifier: MIT
# focus_timer.py - noknok Focus Timer  v1.0.0
#
# A Pomodoro desk timer: work in focused blocks, rest in short breaks.
#
#   Ready      Turn the knob to set the focus minutes (5 - 90, steps of 5).
#              LED Button = start.
#   Focus      Big countdown + progress bar. Button LED red.
#              Knob press = pause / resume. Hold the LED Button 1 s = stop (back to ready).
#   Break      After a focus block: short break; after every `sessions_before_long`
#              blocks a long break. Button LED green. Chime at every change.
#   The next block starts by itself (`auto_next` on) or waits for the LED Button.
#
# The minutes you set with the knob are the same setting the app shows (c.settings), so
# they survive a power cut. Counting is done on the brain's clock: no WiFi needed.
# Factory reset = the brain's own gesture (hold a button or the knob while plugging in).

from noknok import Conductor
import time

RED, GREEN, AMBER, WHITE = (255, 0, 0), (0, 255, 0), (255, 150, 0), (200, 220, 255)
HOLD_STOP_S = 1.0
STEP = 5

c = Conductor()
c.enumerate()

if not (c.knob and c.ledbutton and c.display and c.buzzer):
    raise SystemExit("Focus Timer needs a Knob, an LED Button, a Display and a Buzzer - check wiring.")
knob, btn, d, buzzer = c.knob[0], c.ledbutton[0], c.display[0], c.buzzer[0]

s = c.settings
s.defaults({"focus_min": 25, "break_min": 5, "long_break_min": 15, "sessions_before_long": 4,
            "auto_next": True, "volume": 40, "brightness": 120})


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


def mmss(sec):
    sec = max(0, int(sec + 0.999))
    return "%02d:%02d" % (sec // 60, sec % 60)


state_name = ["Ready"]
s.info("phase", lambda: state_name[0])

d.clear(0)
d.region("title", 0, 0, 160, 16, size=16, align="center")
d.region("time", 0, 20, 160, 32, size=32, align="center")
d.region("round", 0, 68, 160, 8, size=8, align="center", color=0x808080)
BAR_X, BAR_Y, BAR_W, BAR_H = 8, 56, 144, 6


def bar(frac, color):
    done = int(BAR_W * max(0.0, min(1.0, frac)))
    d.fill_rect(BAR_X, BAR_Y, BAR_W, BAR_H, 0x202020)
    if done:
        d.fill_rect(BAR_X, BAR_Y, done, BAR_H, color)


def chime(kind):
    v = vol()
    notes = {"focus_end": (784, 988, 1175), "break_end": (1175, 988, 784), "stop": (440,)}[kind]
    for f in notes:
        buzzer.note(f, 120, v)


def screen(title, color, remaining, total, rounds):
    state_name[0] = title
    d.set("title", text=title, color=color)
    d.set("time", text=mmss(remaining), color=color)
    bar(1 - remaining / total if total else 0, color)
    d.set("round", text=rounds)


def idle():
    """Ready screen: the knob sets the focus minutes. Returns when the LED Button starts."""
    lamp(WHITE, 0.4)
    shown = None
    btn.read()
    while True:
        k = knob.read()
        if k is not None and k.delta:
            m = clamp(s.get("focus_min"), 5, 90, 25) + k.delta * STEP
            s.set("focus_min", clamp(m, 5, 90, 25))
        m = clamp(s.get("focus_min"), 5, 90, 25)
        if m != shown:
            shown = m
            screen("Ready", 0xFFFFFF, m * 60, m * 60, "turn knob = minutes")
            d.set("time", text="%02d:00" % m)
        b = btn.read()
        if b is not None and b.press_event:
            return
        c.sleep(0.03)


def run_phase(title, minutes, color, rgb, rounds):
    """Counts down. Returns "done" or "stop"."""
    total = minutes * 60
    end = time.monotonic() + total
    paused_left = None
    last_shown = -1
    held = None
    btn.read()
    lamp(rgb)
    screen(title, color, total, total, rounds)
    while True:
        now = time.monotonic()
        k = knob.read()
        if k is not None and k.pressed and not knob_down[0]:
            knob_down[0] = True
            if paused_left is None:
                paused_left = max(0.0, end - now)
                screen("Paused", 0xFF9600, paused_left, total, rounds)
                lamp(AMBER)
            else:
                end = now + paused_left
                paused_left = None
                screen(title, color, end - now, total, rounds)
                lamp(rgb)
        elif k is not None and not k.pressed:
            knob_down[0] = False
        b = btn.read()
        if b is not None:
            if b.press_event:
                held = now
            if b.pressed and held is not None and now - held >= HOLD_STOP_S:
                return "stop"
            if not b.pressed:
                held = None
        if paused_left is None:
            left = end - now
            if left <= 0:
                return "done"
            if int(left + 0.999) != last_shown:
                last_shown = int(left + 0.999)
                d.set("time", text=mmss(left))
                bar(1 - left / total, color)
        c.sleep(0.05)


knob_down = [False]


def wait_for_start():
    lamp(WHITE, 0.4)
    btn.read()
    while True:
        b = btn.read()
        if b is not None and b.press_event:
            return
        c.sleep(0.05)


def session():
    idle()
    done = 0
    while True:
        focus = clamp(s.get("focus_min"), 5, 90, 25)
        every = clamp(s.get("sessions_before_long"), 2, 8, 4)
        r = run_phase("FOCUS", focus, 0xFF3030, RED, "block %d of %d" % (done % every + 1, every))
        if r == "stop":
            chime("stop")
            return
        done += 1
        chime("focus_end")
        if done % every == 0:
            brk, name = clamp(s.get("long_break_min"), 1, 60, 15), "LONG BREAK"
        else:
            brk, name = clamp(s.get("break_min"), 1, 30, 5), "BREAK"
        r = run_phase(name, brk, 0x30FF60, GREEN, "%d blocks done" % done)
        if r == "stop":
            chime("stop")
            return
        chime("break_end")
        if not s.get("auto_next"):
            screen("Next?", 0xFFFFFF, focus * 60, focus * 60, "LED Button = start")
            wait_for_start()


buzzer.tune(buzzer.STARTUP)
print("[focus] up, settings=%s" % s.all())
while True:
    session()
