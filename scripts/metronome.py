# SPDX-License-Identifier: MIT
# metronome.py - noknok Metronome  v1.0.0
#
# A practice metronome for music: steady click, accented first beat, big BPM on the display.
#
#   Knob turn    tempo (30 - 240 BPM, 1 per click; the app slider is the same setting)
#   Knob press   TAP TEMPO: tap the beat 3 or more times, the tempo follows (average of the last 4 taps)
#   LED Button   start / stop. The button LED blinks on every beat (accent = white, others = blue).
#   Display      BPM in big digits and one square per beat of the bar; the current beat is filled.
#
# Beats are scheduled on the brain's clock from the previous beat, not from "now", so the
# tempo does not drift when the loop is busy. The click is a short buzzer note.
# Settings (c.settings): bpm, beats per bar, accent on/off, volume, brightness.
# Factory reset = the brain's own gesture.

from noknok import Conductor
import time

c = Conductor()
c.enumerate()

if not (c.knob and c.ledbutton and c.display and c.buzzer):
    raise SystemExit("Metronome needs a Knob, an LED Button, a Display and a Buzzer - check wiring.")
knob, btn, d, buzzer = c.knob[0], c.ledbutton[0], c.display[0], c.buzzer[0]

s = c.settings
s.defaults({"bpm": 100, "beats": 4, "accent": True, "volume": 40, "brightness": 120})


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return fallback


def bpm():    return clamp(s.get("bpm"), 30, 240, 100)
def beats():  return clamp(s.get("beats"), 1, 8, 4)
def vol():    return clamp(s.get("volume"), 0, 100, 40)
def bright(): return clamp(s.get("brightness"), 5, 255, 120)


def lamp(rgb):
    k = bright() / 255
    btn.set_color(int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


running = [False]
s.info("running", lambda: "yes" if running[0] else "no")

d.clear(0)
d.region("bpm", 0, 6, 160, 48, size=48, align="center")
d.region("label", 0, 54, 160, 8, size=8, align="center", color=0x808080)
SQ, GAP, SQY = 12, 4, 66


def draw_bpm():
    d.set("bpm", text=str(bpm()), color=0xFFFFFF if running[0] else 0x808080)
    d.set("label", text="BPM  " + ("running" if running[0] else "stopped"))


def draw_beats(current):
    n = beats()
    total = n * SQ + (n - 1) * GAP
    x0 = (160 - total) // 2
    for i in range(n):
        on = (i == current)
        col = (0xFFFFFF if i == 0 else 0x3070FF) if on else 0x303030
        d.fill_rect(x0 + i * (SQ + GAP), SQY, SQ, 12, col)


def tap_tempo(taps, now):
    """Keep the last 4 taps (a pause over 2 s starts a new count); return a new BPM or None."""
    if taps and now - taps[-1] > 2.0:
        del taps[:]
    taps.append(now)
    del taps[:-4]
    if len(taps) >= 3:
        avg = (taps[-1] - taps[0]) / (len(taps) - 1)
        if avg > 0:
            return clamp(60.0 / avg, 30, 240, 100)
    return None


def click(first):
    if first and s.get("accent"):
        buzzer.play(1500, 100, vol())
        lamp((255, 255, 255))
    else:
        buzzer.play(1000, 100, vol())
        lamp((0, 60, 255))


draw_bpm()
draw_beats(-1)
lamp((60, 60, 60))
buzzer.tune(buzzer.STARTUP)
print("[metro] up, settings=%s" % s.all())

taps = []
beat = 0
next_t = 0.0
led_off_at = 0.0
knob_was = False
while True:
    now = time.monotonic()
    k = knob.read()
    if k is not None:
        if k.delta:
            s.set("bpm", clamp(bpm() + k.delta, 30, 240, 100))
            draw_bpm()
        if k.pressed and not knob_was:
            t = tap_tempo(taps, now)
            buzzer.play(2000, 100, vol() // 2)
            if t is not None:
                s.set("bpm", t)
                draw_bpm()
        knob_was = k.pressed
    b = btn.read()
    if b is not None and b.press_event:
        running[0] = not running[0]
        beat = 0
        next_t = now + 0.05
        draw_bpm()
        draw_beats(-1)
        if not running[0]:
            lamp((60, 60, 60))
    if running[0] and now >= next_t:
        cur = beat % beats()
        click(cur == 0)
        draw_beats(cur)
        beat += 1
        led_off_at = now + 0.08
        next_t += 60.0 / bpm()
        if next_t < now:                      # fell behind (a long pause): restart the grid
            next_t = now + 60.0 / bpm()
    if led_off_at and now >= led_off_at:
        led_off_at = 0.0
        lamp((20, 20, 20) if running[0] else (60, 60, 60))
    c.sleep(0.004)
