# SPDX-License-Identifier: MIT
# quiz_buzzers.py - noknok Quiz Buzzers  v1.0.0
#
# A game-show buzzer set for family quiz night: one LED Button per team.
#
#   Get ready      3-2-1 beeps. Pressing early is a FALSE START: that team is red and
#                  out for this question.
#   Buzz           The first team to press lights up in its colour, everyone else goes dark.
#   Quizmaster     taps the winning team's button   = WRONG: that team is out for this
#                                                     question, the others can buzz again
#                  holds it for 1 s                 = RIGHT: the team scores a point
#   No answer      after `answer_s` seconds the buzz counts as wrong.
#   First to `points_to_win` points wins the game; then a new game starts by itself.
#
# Two to four teams (the first four LED Buttons). If two teams press within the same
# ~30 ms poll, the lower-numbered button wins: the Buttons give no time stamp.
# Settings live in c.settings (never a file). Factory reset = the brain's own gesture.

from noknok import Conductor
import time

TEAM_COLORS = ((255, 0, 0), (0, 255, 0), (0, 90, 255), (255, 150, 0))
HOLD_S = 1.0                    # hold the winner's button this long = answer was right

c = Conductor()
c.enumerate()

btns = c.ledbutton[:4]
if len(btns) < 2:
    raise SystemExit("Quiz Buzzers needs 2 to 4 LED Buttons - check wiring.")
if not c.buzzer:
    raise SystemExit("No Buzzer found - check wiring.")
if not c.display:
    raise SystemExit("No Display found - check wiring.")
buzzer, d = c.buzzer[0], c.display[0]
n = len(btns)

s = c.settings
s.defaults({"points_to_win": 3, "countdown": True, "answer_s": 10, "volume": 40, "brightness": 120})

score = [0] * n
out = [False] * n               # locked out for the current question


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def vol():    return clamp(s.get("volume"), 0, 100, 40)
def bright(): return clamp(s.get("brightness"), 5, 255, 120)


def lamp(i, rgb, f=1.0):
    k = bright() * f / 255
    btns[i].set_color(int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


def tone(freq, ms):
    buzzer.play(freq, ms, vol())


def scores_text():
    return " ".join(str(x) for x in score)


s.info("scores", lambda: " : ".join(str(x) for x in score))

d.clear(0)
d.region("title", 0, 2, 160, 16, size=16, align="center")
d.region("scores", 0, 24, 160, 16, size=16, align="center")
d.region("status", 0, 46, 160, 16, size=16, align="center")
d.region("help", 0, 68, 160, 8, size=8, align="center", color=0x808080)


def show(title, status, color=0xFFFFFF, help_text=""):
    d.set("title", text=title, color=color)
    d.set("scores", text=scores_text())
    d.set("status", text=status)
    d.set("help", text=help_text)


def paint_open():
    """Everyone who is still in the game: lit white-ish. Locked-out teams: red."""
    for i in range(n):
        if out[i]:
            lamp(i, (255, 0, 0), 0.25)
        else:
            lamp(i, (200, 220, 255), 0.5)


def countdown():
    """3-2-1. Returns when it is time to buzz. Early presses = false start."""
    show("QUIZ", "Get ready", 0xFFFF00)
    for i in range(n):
        lamp(i, (255, 150, 0), 0.15) if not out[i] else lamp(i, (255, 0, 0), 0.25)
    t0 = time.monotonic()
    beeped = -1
    while True:
        el = time.monotonic() - t0
        if el >= 3.0:
            return
        if int(el) != beeped:
            beeped = int(el)
            tone(440, 100)
        for i in range(n):
            st = btns[i].read()
            if st is not None and st.press_event and not out[i]:
                out[i] = True
                lamp(i, (255, 0, 0))
                tone(200, 300)
                show("QUIZ", "T%d early!" % (i + 1), 0xFF0000)
        c.sleep(0.03)


def wait_buzz():
    """Armed: returns the index of the first team that presses."""
    paint_open()
    show("BUZZ NOW!", "", 0x00FF00)
    tone(880, 150)
    for b in btns:
        b.read()                          # drop presses that happened before GO
    while True:
        for i in range(n):
            st = btns[i].read()
            if st is not None and st.press_event and not out[i]:
                return i
        c.sleep(0.02)


def answer(w):
    """Team w buzzed. Returns True = right, False = wrong / no answer."""
    for i in range(n):
        if i == w:
            lamp(i, TEAM_COLORS[i])
        else:
            btns[i].led_off()
    tone(1200, 150)
    show("Team %d" % (w + 1), "Answer?", ((TEAM_COLORS[w][0] << 16) | (TEAM_COLORS[w][1] << 8) | TEAM_COLORS[w][2]),
         "hold=right tap=wrong")
    limit = clamp(s.get("answer_s"), 0, 60, 10)
    t0 = time.monotonic()
    held = None
    while True:
        now = time.monotonic()
        st = btns[w].read()
        if st is not None:
            if st.press_event:
                held = now
            if held is not None and st.pressed and now - held >= HOLD_S:
                return True
            if held is not None and st.release_event and now - held < HOLD_S:
                return False
            if not st.pressed and not st.release_event:
                held = None
        if limit and now - t0 > limit:
            return False
        c.sleep(0.03)


def victory(w):
    show("T%d WINS!" % (w + 1), "", 0x00FF00)
    for f in (523, 659, 784, 1047):
        buzzer.note(f, 140, vol())
    t0 = time.monotonic()
    while time.monotonic() - t0 < 6:
        k = int((time.monotonic() - t0) * 4)
        for i in range(n):
            lamp(i, TEAM_COLORS[(i + k) % 4])
        c.sleep(0.1)


def play_game():
    for i in range(n):
        score[i] = 0
    first = True
    while True:
        for i in range(n):
            out[i] = False
        if s.get("countdown"):
            countdown()
        while True:                        # one question, several buzzes possible
            if all(out):
                break
            w = wait_buzz()
            if answer(w):
                score[w] += 1
                buzzer.tune(buzzer.BEEP_OK)
                for i in range(n):
                    lamp(i, (0, 255, 0) if i == w else (0, 0, 0), 1.0)
                show("Team %d" % (w + 1), "Correct!", 0x00FF00)
                c.sleep(1.5)
                if score[w] >= clamp(s.get("points_to_win"), 1, 9, 3):
                    victory(w)
                    return
                break
            out[w] = True
            buzzer.tune(buzzer.BEEP_ERROR)
            show("Team %d" % (w + 1), "Wrong", 0xFF0000)
            c.sleep(1.2)
        if all(out):
            show("QUIZ", "No winner", 0xFF8000)
            c.sleep(1.5)


buzzer.tune(buzzer.STARTUP)
print("[quiz] up: %d teams, settings=%s" % (n, s.all()))
while True:
    play_game()
