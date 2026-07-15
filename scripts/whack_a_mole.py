# SPDX-FileCopyrightText: 2026 noknok (Christopher Houben)
# SPDX-License-Identifier: MIT
#
# whack_a_mole.py — noknok Whack-a-Mole (Setup: I2C only)
#
# A screen-free arcade game built from many identical LED Buttons plus a Knob
# and a Buzzer. Every LED Button is a "mole hole": one lights up at random and
# you have to whack it (press it) before it disappears. The game speeds up as
# your score climbs.
#
#   Menu:  turn the Knob → pick a difficulty (1-5, shown as one colour-coded LED)
#          press the Knob → start a 30-second round
#   Play:  a random button lights amber → press it before it goes dark
#          hit  → green flash + OK beep, +1 point, moles get faster
#          miss → red flash (the mole got away)
#   End:   the buzzer counts up your score with a rising tune + light chase
#   Any time: hold the Knob button ~5 s → factory reset (back to noknok-setup)
#
# The buttons are treated *symmetrically* — the game just uses c.ledbutton (the
# whole list), so there is NO per-button role assignment. Plug in any number of
# LED Buttons (2 minimum, 10 is the flagship layout) and the game adapts.
#
# Run from Thonny. Ctrl-C to stop.

from noknok import Conductor
import time
import random

# ── Setup ─────────────────────────────────────────────────────────────────────
c = Conductor()
c.enumerate()

moles = c.ledbutton                       # every LED Button = one mole hole
buz   = c.buzzer[0] if c.buzzer else None  # optional, but makes the game sing
knob  = c.knob[0]   if c.knob   else None  # optional controller (menu + start)

if len(moles) < 2:
    raise SystemExit("Whack-a-Mole needs at least 2 LED Buttons — check wiring.")

print("\n noknok Whack-a-Mole")
print(" ────────────────────")
print(f"  {len(moles)} mole hole(s) found"
      + ("  |  knob: yes" if knob else "  |  knob: NO (press any button to start)")
      + ("  |  buzzer: yes" if buz else "  |  buzzer: NO"))

# ── Tunable game feel ─────────────────────────────────────────────────────────
GAME_SECONDS = 30                # length of one round
UP_MS = {1: 1500, 2: 1150, 3: 850, 4: 650, 5: 500}   # mole "up" time per level
GAP_MS      = 220                # pause between moles
RAMP_MS     = 25                 # each point shaves this much off the up-time…
RAMP_FLOOR  = 0.45               # …but never below 45% of the level's base time

# Colours (R, G, B — 0-255 each). To keep power draw low we NEVER light more than
# ONE LED at a time (no idle glow, no lit bar), so a single lit LED is the worst
# case — the game runs fine on plain USB power without a PowerHub.
MOLE  = (255, 90, 0)     # amber — a mole is up, whack it!
HIT   = (0, 255, 0)      # green flash — you got it
MISS  = (120, 0, 0)      # red flash — it got away

# Difficulty 1-5 shown as the colour of ONE indicator LED in the menu (green→red).
LEVEL_COLORS = {
    1: (0, 90, 0),     # green  — easy
    2: (0, 70, 70),    # cyan
    3: (0, 0, 110),    # blue
    4: (110, 60, 0),   # amber
    5: (150, 0, 0),    # red    — hard
}


# ── Small helpers ─────────────────────────────────────────────────────────────
def all_off():
    for m in moles:
        m.led_off()

def all_color(rgb):
    for m in moles:
        m.set_color(*rgb)

def drain_events():
    """Read every button once to clear stale press_event flags before a round."""
    for m in moles:
        m.read()

def beep(tune_id):
    if buz:
        buz.tune(tune_id)


# ── Menu: pick difficulty, then start ─────────────────────────────────────────
# Power note: the menu lights only ONE LED — a single indicator hole (moles[0])
# whose COLOUR encodes the difficulty. No lit bar, no idle glow.
def choose_level():
    """Return a difficulty 1-5. Knob turns to choose, knob press starts.
    With no knob, start on any button press at the default level."""
    level = 2
    indicator = moles[0]
    all_off()
    indicator.set_color(*LEVEL_COLORS[level])
    if buz:
        buz.tune(buz.STARTUP)   # "ready" chime

    while True:
        # Factory reset (hold knob ~5 s) works from the menu too.
        if knob:
            ks = knob.read()
            if ks is not None:
                c.check_factory_reset(ks)
                if ks.delta:
                    level = max(1, min(5, level + ks.delta))
                    indicator.set_color(*LEVEL_COLORS[level])
                    beep(buz.BEEP_OK) if buz else None
                if ks.pressed:
                    # wait for release so the press doesn't leak into the game
                    while knob.is_pressed:
                        time.sleep(0.02)
                    indicator.led_off()
                    return level
        else:
            # No knob → any button press starts at the default level.
            for m in moles:
                s = m.read()
                if s is not None and s.press_event:
                    indicator.led_off()
                    return level
        time.sleep(0.03)


# ── One round ─────────────────────────────────────────────────────────────────
def play_round(level):
    base_ms = UP_MS[level]
    floor_ms = base_ms * RAMP_FLOOR
    score = 0
    misses = 0

    all_off()
    drain_events()
    if buz:
        buz.tune(buz.STARTUP)
    time.sleep(0.4)

    round_end = time.monotonic() + GAME_SECONDS

    while time.monotonic() < round_end:
        active = random.choice(moles)
        active.set_color(*MOLE)
        drain_events()   # ignore any presses that happened before the mole rose

        # Mole stays up for a window that shrinks as the score grows.
        up_ms = max(floor_ms, base_ms - score * RAMP_MS)
        up_deadline = min(round_end, time.monotonic() + up_ms / 1000)

        whacked = False
        while time.monotonic() < up_deadline:
            s = active.read()
            if s is not None and s.press_event:
                whacked = True
                break
            time.sleep(0.008)   # ~8 ms poll → snappy response

        if whacked:
            score += 1
            active.set_color(*HIT)
            beep(buz.BEEP_OK) if buz else None
        else:
            misses += 1
            active.set_color(*MISS)
        time.sleep(0.09)
        active.led_off()
        time.sleep(GAP_MS / 1000)

    return score, misses


# ── Score reveal (screen-free) ────────────────────────────────────────────────
def reveal(score):
    """Count the score up around the ring of holes with a rising blip per point."""
    all_off()
    time.sleep(0.3)
    for i in range(score):
        m = moles[i % len(moles)]
        m.set_color(*HIT)
        if buz:
            buz.play(400 + min(i, 30) * 40, 80)   # pitch rises, then plateaus
        time.sleep(0.09)
        m.led_off()
    if buz:
        buz.tune(buz.STARTUP)
    time.sleep(0.6)
    all_off()


# ── Main loop ─────────────────────────────────────────────────────────────────
while True:
    level = choose_level()
    print(f"\n  Round start — level {level}")
    score, misses = play_round(level)
    print(f"  Time! Score: {score}   Missed: {misses}")
    reveal(score)
