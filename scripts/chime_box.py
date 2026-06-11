# chime_box.py — noknok Chime Box
#
# A simple melody player built from the I2C trio:
#
#   Knob CW / CCW    → select a melody (LED colour shows which one)
#   LED button press → play the selected melody on the buzzer
#   Hold Knob 5 s    → factory reset (wipe product, back to noknok-setup)
#
# Run from Thonny. Ctrl-C to stop.

from noknok import Conductor
import time

# ── Setup ─────────────────────────────────────────────────────────────────────
c = Conductor()
c.enumerate()

if not c.knob:
    raise SystemExit("No knob found — check wiring.")
if not c.buzzer:
    raise SystemExit("No buzzer found — check wiring.")
if not c.ledbutton:
    raise SystemExit("No LED button found — check wiring.")

knb = c.knob[0]
buz = c.buzzer[0]
kbd = c.ledbutton[0]

# ── Melodies ──────────────────────────────────────────────────────────────────
# Each entry: (tune id from the buzzer firmware, display name, LED colour).
# The melodies themselves live in the buzzer module's firmware — we just pick one.
TUNES = [
    (buz.NOKIA,          "Nokia",          (  0,   0, 180)),  # blue
    (buz.HAPPY_BIRTHDAY, "Happy Birthday", (200,   0, 120)),  # pink
    (buz.BEEP_OK,        "Beep OK",        (  0, 180,   0)),  # green
    (buz.BEEP_ERROR,     "Beep Error",     (200,   0,   0)),  # red
    (buz.STARTUP,        "Startup",        (200, 140,   0)),  # amber
]

sel = 0  # index of the currently selected melody
kbd_was_pressed = False  # for detecting the button-press edge ourselves


def show_selection():
    tune_id, name, (r, g, b) = TUNES[sel]
    kbd.set_color(r, g, b)
    print(f"  ♫  selected: {name}")


print("\n noknok Chime Box")
print(" ─────────────────")
print("  Knob CW / CCW    →  choose a melody (LED colour = selection)")
print("  LED button press →  play it")
print("  Hold knob 5 s    →  factory reset")
print()
show_selection()

# ── Main loop ─────────────────────────────────────────────────────────────────
while True:
    ks    = knb.read()
    kbd_s = kbd.read()

    if ks is None or kbd_s is None:
        time.sleep(0.03)
        continue

    # Factory reset: hold the Knob button ~5 s to wipe this product and return
    # to the noknok-setup AP, so the app can install a different product.
    # Pass the knob status we just read (a second read would eat the rotation).
    c.check_factory_reset(ks)

    # ── Knob rotation: change selection ───────────────────────────────────────
    if ks.delta != 0:
        step = 1 if ks.delta > 0 else -1
        sel  = (sel + step) % len(TUNES)   # wraps around the list
        show_selection()

    # ── LED button press: play the selected melody ────────────────────────────
    # Detect the press edge ourselves from the level (.pressed), the same way
    # trio_demo does — the firmware's press_event edge flag isn't reliable.
    if kbd_s.pressed and not kbd_was_pressed:
        tune_id, name, _ = TUNES[sel]
        print(f"  ▶  playing: {name}")
        buz.tune(tune_id)
    kbd_was_pressed = kbd_s.pressed

    time.sleep(0.03)
