# SPDX-License-Identifier: MIT
# morse_tapper.py - noknok Morse Tapper  v1.0.0
#
# Tap Morse code on the LED Button and read your message on the display.
#
#   Tap (short)     dot        Press longer (about 3x)   dash
#   Pause           a short pause finishes a letter, a longer one adds a space
#   Feedback        the button lights white while you press; the buzzer beeps while you press;
#                   a finished letter flashes the button green (unknown pattern: red)
#   Display         top: the dots and dashes you are tapping; below: the last 20 letters
#   Hold 1.5 s      clear the text
#
# Speed is set in the app in words per minute (one dot = 1200 / wpm ms; 10 wpm = 120 ms). The
# dot / dash limit is 2 dots, a letter ends after 2.5 dots of silence, a word after 6.
# Letters, digits and . , ? are known. Nothing is stored; the text lives in RAM.
# Factory reset = the brain's own gesture (hold the button while plugging in).

from noknok import Conductor
import time

CODE = {
    ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E", "..-.": "F", "--.": "G", "....": "H",
    "..": "I", ".---": "J", "-.-": "K", ".-..": "L", "--": "M", "-.": "N", "---": "O", ".--.": "P",
    "--.-": "Q", ".-.": "R", "...": "S", "-": "T", "..-": "U", "...-": "V", ".--": "W", "-..-": "X",
    "-.--": "Y", "--..": "Z", "-----": "0", ".----": "1", "..---": "2", "...--": "3", "....-": "4",
    ".....": "5", "-....": "6", "--...": "7", "---..": "8", "----.": "9", ".-.-.-": ".", "--..--": ",",
    "..--..": "?",
}
CLEAR_S = 1.5
MAX_CODE = 6

c = Conductor()
c.enumerate()

if not (c.ledbutton and c.display and c.buzzer):
    raise SystemExit("Morse Tapper needs an LED Button, a Display and a Buzzer - check wiring.")
btn, d, buzzer = c.ledbutton[0], c.display[0], c.buzzer[0]

s = c.settings
s.defaults({"wpm": 10, "tone": 700, "show_code": True, "volume": 40, "brightness": 120})
text = [""]
s.info("message", lambda: text[0][-24:])


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def unit():   return 1.2 / clamp(s.get("wpm"), 5, 25, 10)         # one dot in seconds
def vol():    return clamp(s.get("volume"), 0, 100, 40)
def bright(): return clamp(s.get("brightness"), 5, 255, 120)


def lamp(r, g, b):
    k = bright() / 255
    btn.set_color(int(r * k), int(g * k), int(b * k))


d.clear(0)
d.region("code", 0, 2, 160, 16, size=16, align="center", color=0xFFFF00)
d.region("text", 0, 24, 160, 32, size=16, align="left")
d.region("help", 0, 66, 160, 8, size=8, align="center", color=0x808080)
d.set("help", text="tap . -  hold=clear")


def draw_text():
    t = text[0][-20:]
    d.set("text", text=(t[:10] + "\n" + t[10:]) if len(t) > 10 else t)


def draw_code(pattern):
    if s.get("show_code"):
        d.set("code", text=pattern)


def finish_letter(pattern):
    ch = CODE.get(pattern)
    if ch is None:
        lamp(255, 0, 0)
        buzzer.tune(buzzer.BEEP_ERROR)
    else:
        text[0] += ch
        lamp(0, 255, 0)
    draw_text()
    draw_code("")


lamp(40, 40, 40)
buzzer.tune(buzzer.STARTUP)
print("[morse] up, settings=%s" % s.all())
pattern = ""
down_at = None
up_at = None
spaced = True                         # no space after a space / at the start
last_beep = 0.0
flash_until = 0.0
while True:
    now = time.monotonic()
    b = btn.read()
    if b is not None:
        if b.press_event and down_at is None:
            down_at = now
            last_beep = 0.0
            lamp(255, 255, 255)
        if down_at is not None and b.pressed:
            if now - last_beep >= 0.09:                  # keep the tone going while pressed
                last_beep = now
                buzzer.play(clamp(s.get("tone"), 300, 1500, 700), 100, vol())
            if now - down_at >= CLEAR_S:
                text[0] = ""
                pattern = ""
                spaced = True
                draw_text()
                draw_code("")
                buzzer.tune(buzzer.BEEP_OK)
                down_at = None
                while True:                              # wait for release
                    r = btn.read()
                    if r is None or not r.pressed:
                        break
                    c.sleep(0.03)
                lamp(40, 40, 40)
        if down_at is not None and (b.release_event or not b.pressed):
            dur = now - down_at
            down_at = None
            up_at = now
            buzzer.stop()
            if len(pattern) < MAX_CODE:
                pattern += "." if dur < 2 * unit() else "-"
            draw_code(pattern)
            lamp(40, 40, 40)
            spaced = False
    if down_at is None and up_at is not None:
        gap = now - up_at
        if pattern and gap > 2.5 * unit():
            finish_letter(pattern)
            pattern = ""
            flash_until = now + 0.25
        elif not pattern and not spaced and gap > 6 * unit():
            text[0] += " "
            spaced = True
            draw_text()
    if flash_until and now >= flash_until:
        flash_until = 0.0
        lamp(40, 40, 40)
    c.sleep(0.01)
