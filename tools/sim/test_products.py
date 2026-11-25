# SPDX-License-Identifier: MIT
# Copyright 2026 noknok (Christopher Houben)
"""Logic tests for the exploration products (20-25 Nov 2026), run on the PC with fakebrain.

    python tools/sim/test_products.py [path to poc repo]      (default: this repo)
    NK_BRAIN=<brain-Pico clone> ...     for the 3 data products (they need noknok_feeds.py)

Each test drives the product with scripted button / knob / sensor events on a fake clock and
checks what it showed, played and lit. Not a bench test: no I2C, no real timing.
"""
import os, sys, random
sys.path.insert(0, os.path.dirname(__file__))
from fakebrain import Sim

POC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
FAILS = []


def script(name):
    return os.path.join(POC, "scripts", name)


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAILS.append(msg)


def shown(sim, region):
    return [d[1] for (t, d) in sim.where("disp.set") if d[0] == region]


def seen(sim, region, text):
    return text in shown(sim, region)


# ----------------------------------------------------------------------------------------------
def test_quiz():
    print("quiz_buzzers")
    sim = Sim(buttons=4, display=True, buzzer=True)
    sim.settings.v.update(points_to_win=2)
    # question 1: team 3 (index 2) jumps the gun at 1 s, team 2 buzzes first at 5 s,
    # quizmaster holds the button 1.3 s = right
    sim.tap(2, t=1.0)
    sim.tap(1, t=5.0)
    sim.tap(0, t=5.5)                       # a later press must not steal the buzz
    sim.press(1, t=7.0, hold=1.3)
    # question 2 (countdown 3 s after 1.5 s of "Correct!"): team 1 buzzes, tap = wrong,
    # team 4 buzzes and is right -> still 1:0 ... then team 2 wins question 3 -> game over
    sim.run(script("quiz_buzzers.py"), seconds=12.5)
    check(seen(sim, "status", "T3 early!"), "false start is shown")
    check(any(d == (255 * 120 // 255 * 0 + int(255 * 0.25 * 120 / 255), 0, 0) or d[0] > 0 and d[1] == 0 and d[2] == 0
              for (t, d) in sim.where("btn2.color", 1.0, 1.5)), "false-start team lit red")
    check(seen(sim, "title", "Team 2"), "first buzz wins: Team 2")
    check(not seen(sim, "title", "Team 1"), "a later press does not steal the buzz")
    check(seen(sim, "status", "Correct!"), "hold = correct")
    check(seen(sim, "scores", "0 1 0 0"), "score 0 1 0 0")
    # round 2 on a fresh sim: wrong answer locks the team out, another team can answer
    sim = Sim(buttons=4, display=True, buzzer=True)
    sim.settings.v.update(points_to_win=1, countdown=False)
    sim.tap(0, t=1.0)                       # team 1 buzzes
    sim.tap(0, t=2.0)                       # quizmaster taps = wrong
    sim.tap(0, t=4.0)                       # team 1 is locked out: must be ignored
    sim.tap(3, t=5.0)                       # team 4 buzzes
    sim.press(3, t=6.5, hold=1.3)           # right -> points_to_win 1 -> victory
    sim.run(script("quiz_buzzers.py"), seconds=9.5)
    check(seen(sim, "status", "Wrong"), "tap = wrong")
    check(shown(sim, "status").count("Answer?") == 2, "locked-out team cannot buzz again (2 answers: team 1, then team 4)")
    check(seen(sim, "title", "Team 4"), "second team gets its chance")
    check(seen(sim, "title", "T4 WINS!"), "first to points_to_win wins")
    # timeout counts as wrong
    sim = Sim(buttons=2, display=True, buzzer=True)
    sim.settings.v.update(countdown=False, answer_s=3)
    sim.tap(1, t=1.0)
    sim.run(script("quiz_buzzers.py"), seconds=6)
    check(seen(sim, "status", "Wrong"), "no answer in time = wrong")


def test_duel():
    print("reaction_duel")
    random.seed(1)
    sim = Sim(buttons=2, display=True, buzzer=True)
    sim.settings.v.update(rounds_to_win=2, min_wait_s=2, max_wait_s=3)
    # round 1: player 1 presses early at 1 s -> player 2 gets the point
    sim.tap(0, t=3.0)
    # then wait; we do not know the GO time (random) so press from a log-driven hook
    state = {"go": None}

    def watcher():
        pass
    sim.run(script("reaction_duel.py"), seconds=20)
    check(seen(sim, "title", "P2 scores"), "false start gives the round to the other player")
    check(seen(sim, "info", "P1 early"), "false start named")
    # reaction round: press button 1 shortly after green
    random.seed(2)
    sim = Sim(buttons=2, display=True, buzzer=True)
    sim.settings.v.update(rounds_to_win=1, min_wait_s=2, max_wait_s=3)
    seq = {"go": None}
    orig_log = sim.log

    class L(list):
        def append(self, x):
            list.append(self, x)
            if x[1] == "disp.set" and x[2] == ("title", "GO!") and seq["go"] is None:
                seq["go"] = x[0]
                sim.tap(1, t=x[0] + 0.250)
    sim.log = L()
    sim.run(script("reaction_duel.py"), seconds=15)
    check(seq["go"] is not None, "GO shown")
    check(any(i.startswith("P2 2") and i.endswith(" ms") for i in shown(sim, "info")), "P2 reaction time ~250 ms shown: %s" % shown(sim, "info"))
    check(seen(sim, "title", "P2 WINS!"), "P2 wins the duel")
    check(sim.settings.infos["best_ms"]() is not None, "best time is exposed as info")


def test_focus():
    print("focus_timer")
    sim = Sim(buttons=1, knob=True, display=True, buzzer=True)
    sim.settings.v.update(focus_min=5, break_min=1, long_break_min=2, sessions_before_long=2)
    sim.turn(1.0, 2)                        # 5 -> 15 min
    sim.turn(1.5, -1)                       # -> 10
    sim.tap(0, t=3.0)                       # start
    sim.knob_tap(60.0)                      # pause at 57 s into focus
    sim.knob_tap(120.0)                     # resume
    sim.run(script("focus_timer.py"), seconds=60 * 25)
    check(sim.settings.v["focus_min"] == 10, "knob sets focus minutes (10)")
    check(seen(sim, "title", "FOCUS") and seen(sim, "title", "Paused"), "focus + pause shown")
    check(seen(sim, "title", "BREAK"), "short break after focus")
    check("09:59" in shown(sim, "time") or "10:00" in shown(sim, "time"), "countdown starts at 10:00")
    t_break = [t for (t, d) in sim.where("disp.set") if d == ("title", "BREAK")][0]
    # focus started at 3 s, paused 60 -> 120 (60 s lost): break at 3 + 600 + 60 = 663 s
    check(abs(t_break - 663) < 2, "pause stops the clock (break at %.0f s, expected ~663)" % t_break)
    check(seen(sim, "title", "LONG BREAK"), "long break after sessions_before_long blocks")


def test_focus_stop():
    print("focus_timer (stop by hold)")
    sim = Sim(buttons=1, knob=True, display=True, buzzer=True)
    sim.settings.v.update(focus_min=5)
    sim.tap(0, t=1.0)
    sim.press(0, t=10.0, hold=1.3)
    sim.run(script("focus_timer.py"), seconds=20)
    check(shown(sim, "title")[-1] == "Ready", "hold 1 s stops: back to Ready")


def test_box():
    print("puzzle_box")
    sim = Sim(buttons=1, knob=True, display=True, buzzer=True)
    sim.settings.v.update(code="7-21-33", open_s=5, lockout_after=2, lockout_s=10)

    def dial(t, n):
        sim.turn(t, n)

    # wrong: 7, 21, 30 -> 2/3
    dial(1, 7); sim.tap(0, t=2)
    dial(3, 14); sim.tap(0, t=4)
    dial(5, 9); sim.tap(0, t=6)            # 30
    # wrong again: 1,2,3 -> locked out
    dial(10, -29)                          # position 1
    sim.tap(0, t=11)
    dial(12, 1); sim.tap(0, t=13)
    dial(14, 1); sim.tap(0, t=15)
    # (locked 10 s) then right: 7, 21, 33 -> dial from 3
    dial(30, 7); sim.tap(0, t=31)          # 7 (the dial restarts at 0 for every attempt)
    dial(32, 14); sim.tap(0, t=33)         # 21
    dial(34, 12); sim.tap(0, t=35)         # 33
    sim.run(script("puzzle_box.py"), seconds=45)
    check(seen(sim, "dial", "2/3"), "hint shows 2/3 right")
    check(seen(sim, "title", "WRONG"), "wrong code is shown")
    check(seen(sim, "title", "LOCKED"), "lockout after 2 wrong codes")
    check(seen(sim, "title", "OPEN!"), "right code opens")
    t_open = [t for (t, d) in sim.where("disp.set") if d == ("title", "OPEN!")][0]
    check(30 < t_open < 40, "opened at %.1f s" % t_open)
    check(sim.settings.infos["state"]() in ("Locked", "Open"), "state info works")
    # hint off hides the count
    sim = Sim(buttons=1, knob=True, display=True, buzzer=True)
    sim.settings.v.update(code="5", show_hint=False)
    sim.turn(1, 6); sim.tap(0, t=2)
    sim.run(script("puzzle_box.py"), seconds=6)
    check(not seen(sim, "dial", "0/1"), "show_hint off hides the count")
    # broken code falls back to a usable default
    sim = Sim(buttons=1, knob=True, display=True, buzzer=True)
    sim.settings.v.update(code="abc")
    sim.run(script("puzzle_box.py"), seconds=3)
    check(seen(sim, "title", "Number 1/3"), "broken code falls back to 3 numbers")


def test_breath():
    print("breathing_guide")
    sim = Sim(knob=True, buzzer=True, leds16=True)
    sim.settings.v.update(pattern="box", session_min=1, sound=True, brightness=255, color="#FFFFFF")
    sim.turn(1.0, 1)                        # pattern -> relax
    sim.knob_tap(5.0)                       # start
    sim.run(script("breathing_guide.py"), seconds=100)
    check(sim.settings.v["pattern"] == "relax", "knob turn changes the pattern")
    frames = sim.where("leds16")
    lit = [sum(1 for px in f if px[0] >= 250) for (t, f) in frames]
    check(max(lit) == 16, "ring fills completely at the top of the breath")
    # sample at box? pattern is relax: inhale 4 s from t~6.2 -> full at ~10.2
    check(any(16 == n for n in lit), "full ring reached")
    full_t = [t for (t, f), n in zip(frames, lit) if n == 16][0]
    check(9.0 < full_t < 10.5, "full at the end of the 4 s inhale (%.1f s)" % full_t)
    # session ends: frames dark-ish at the end, chime played
    check(sim.where("buzz")[-1][1][2] == 20, "chime is quiet (volume 20)")
    check(sum(1 for px in frames[-1][1] if px[0] > 20) <= 1, "ring faded at the end")
    # stop by press mid-session
    sim = Sim(knob=True, buzzer=True, leds16=True)
    sim.settings.v.update(session_min=5)
    sim.knob_tap(1.0); sim.knob_tap(10.0)
    sim.run(script("breathing_guide.py"), seconds=20)
    last_full = max(t for (t, f) in sim.where("leds16"))
    check(sum(1 for px in sim.where("leds16")[-1][1] if px[0] > 20) == 0, "stopped session returns to dim glow")


class Obj:
    pass


def test_plant():
    print("plant_climate_monitor")
    light, therm = Obj(), Obj()
    light.lux, therm.temperature = 3000.0, 22.0
    sim = Sim(buttons=1, display=True, thirdparty={"veml7700": [light], "tmp102": [therm]})
    sim.settings.v.update(plant="leafy")
    sim.at(5, lambda: setattr(light, "lux", 300.0))       # too dark
    sim.at(10, lambda: setattr(therm, "temperature", 31.0))   # too hot
    sim.at(15, lambda: setattr(therm, "temperature", 12.0))   # too cold
    sim.at(20, lambda: (setattr(therm, "temperature", 21.0), setattr(light, "lux", 0.5)))  # night
    sim.at(25, lambda: setattr(light, "lux", 50000.0))    # too bright
    sim.at(30, lambda: setattr(light, "lux", None))       # hiccup
    sim.tap(0, t=34)                                      # page 2
    sim.tap(0, t=36)                                      # page 3
    sim.run(script("plant_climate_monitor.py"), seconds=40)
    r3 = shown(sim, "r3")
    for want in ("Happy!", "Too dark", "Too hot", "Too cold", "Sleeping", "Too bright"):
        check(want in r3, "verdict %r shown" % want)
    check(("min 12.0 C" in shown(sim, "r1")) and ("max 31.0 C" in shown(sim, "r2")), "min / max kept")
    check(any(x.endswith("hours") for x in shown(sim, "r1")), "good-light page shown")
    bl = [d for (t, d) in sim.where("disp.backlight")]
    check(0.1 in bl and bl[-1] == 1.0 or 0.1 in bl, "backlight dims at night: %s" % bl)
    check(sim.settings.infos["lux"]() is None, "info lux survives None")
    check(any(x == (0, 255, 0) or (x[1] > 0 and x[0] == 0 and x[2] == 0) for (t, x) in sim.where("btn0.color")), "green LED when happy")


def test_guard():
    print("desk_guard")
    pir, acc = Obj(), Obj()
    pir.motion, acc.acceleration = False, (0.0, 0.0, 9.8)
    sim = Sim(buttons=1, buzzer=True, thirdparty={"soldered_pir": [pir], "msa311": [acc]})
    sim.settings.v.update(exit_s=3, entry_s=4, alarm_s=6, bump_limit=1.0)
    sim.tap(0, t=1)                                          # arm
    sim.at(10, lambda: setattr(acc, "acceleration", (0.0, 0.1, 9.85)))    # tiny drift: ignored
    sim.at(12, lambda: setattr(acc, "acceleration", (1.5, 0.0, 9.8)))     # bump
    sim.tap(0, t=14)                                         # disarm during entry
    sim.tap(0, t=20)                                         # arm again
    sim.at(30, lambda: setattr(pir, "motion", True))         # motion -> entry -> alarm
    sim.at(31, lambda: setattr(pir, "motion", False))
    sim.run(script("desk_guard.py"), seconds=50)
    st = sim.settings.infos["state"]()
    trig = sim.settings.infos["triggers"]()
    check(trig == 2, "two triggers (bump, motion); got %s" % trig)
    check(sim.settings.infos["last_trigger"]() == "motion", "last trigger = motion")
    sirens = [d for (t, d) in sim.where("buzz") if d[0] in (900, 1400)]
    check(len(sirens) > 5, "siren played after the entry delay (%d notes)" % len(sirens))
    check(not any(900 <= d[0] <= 1400 and t < 14 and d[1] == 300 for (t, d) in sim.where("buzz")), "no siren when disarmed in time")
    check(st in ("Armed", "ALARM", "Entry"), "state afterwards: %s" % st)
    # sensors switched off
    sim = Sim(buttons=1, buzzer=True, thirdparty={"soldered_pir": [pir], "msa311": [acc]})
    pir.motion, acc.acceleration = False, (0.0, 0.0, 9.8)
    sim.settings.v.update(exit_s=1, pir_on=False, bump_on=False)
    sim.tap(0, t=1)
    sim.at(6, lambda: setattr(pir, "motion", True))
    sim.run(script("desk_guard.py"), seconds=20)
    check(sim.settings.infos["triggers"]() == 0, "sensors off = no trigger")


def test_metronome():
    print("metronome")
    sim = Sim(buttons=1, knob=True, display=True, buzzer=True)
    sim.settings.v.update(bpm=120, beats=4)
    sim.tap(0, t=1.0)                                    # start
    sim.turn(7.0, 20)                                    # 140 BPM
    for tt in (10.0, 10.6, 11.2):                        # tap tempo: 0.6 s = 100 BPM
        sim.knob_tap(tt)
    sim.tap(0, t=14.0)                                   # stop
    sim.run(script("metronome.py"), seconds=16)
    clicks = [(t, d[0]) for (t, d) in sim.where("buzz") if d[0] in (1500, 1000)]
    first = [t for t, f in clicks if t < 6.5]
    gaps = [round(b - a, 2) for a, b in zip(first, first[1:])]
    check(len(first) >= 9 and all(abs(g - 0.5) < 0.02 for g in gaps), "120 BPM: steady 0.5 s clicks %s" % gaps[:6])
    check([f for t, f in clicks[:5]] == [1500, 1000, 1000, 1000, 1500], "accent on every 4th beat")
    check(sim.settings.v["bpm"] == 100, "tap tempo sets 100 BPM (got %s)" % sim.settings.v["bpm"])
    check(seen(sim, "bpm", "140"), "knob turn gives 140")
    check(sim.settings.infos["running"]() == "no", "stop works")
    late = [t for t, f in clicks if t > 14.1]
    check(not late, "no clicks after stop")


def test_dice():
    print("dice_roller")
    random.seed(3)
    sim = Sim(buttons=1, display=True, buzzer=True)
    sim.tap(0, t=1.0)
    sim.press(0, t=6.0, hold=1.3)                         # next kind: 2d6
    sim.tap(0, t=9.0)
    sim.press(0, t=14.0, hold=1.3)                        # d20
    sim.press(0, t=18.0, hold=1.3)                        # d100
    sim.press(0, t=22.0, hold=1.3)                        # coin
    sim.tap(0, t=25.0)
    sim.run(script("dice_roller.py"), seconds=30)
    check(sim.settings.v["dice"] == "coin", "hold cycles d6 > 2d6 > d20 > d100 > coin")
    check(sim.settings.infos["rolls"]() == 3, "3 rolls counted (holds do not roll): %s" % sim.settings.infos["rolls"]())
    last = sim.settings.infos["last"]()
    check(last in ("HEADS", "TAILS"), "coin result: %s" % last)
    bigs = shown(sim, "big")
    check(any(b.isdigit() and 1 <= int(b) <= 6 for b in bigs), "d6 shows 1-6")
    sm = [x for x in shown(sim, "small") if "+" in x]
    ok = True
    for x in sm:
        a, b = [int(v) for v in x.split("+")]
        ok = ok and 1 <= a <= 6 and 1 <= b <= 6
    check(sm and ok, "2d6 shows both dice: %s" % sm[-1:])
    # many d20 rolls: every natural 20 plays the fanfare, every 1 the sad tone
    random.seed(11)
    sim = Sim(buttons=1, display=True, buzzer=True)
    sim.settings.v.update(dice="d20")
    for i in range(70):
        sim.tap(0, t=1.0 + i * 4)
    sim.run(script("dice_roller.py"), seconds=1.0 + 70 * 4 + 3)
    results = [int(x) for x in shown(sim, "big") if x.isdigit()]
    check(sim.settings.infos["rolls"]() == 70, "70 rolls")
    check(20 in results and 1 in results, "both extremes occurred")
    check(any(d == 1568 for (t, d) in [(t, d[0]) for (t, d) in sim.where("buzz")]), "nat 20 fanfare played")
    check(len(sim.where("tune")) >= 2, "sad tone for a 1 (and startup)")


def test_stopwatch():
    print("stopwatch")
    sim = Sim(buttons=1, knob=True, display=True, buzzer=True)
    sim.tap(0, t=1.0)                                     # start
    sim.knob_tap(3.5)                                     # lap 1 (2.5 s)
    sim.knob_tap(6.0)                                     # lap 2 (2.5 s)
    sim.tap(0, t=8.0)                                     # stop at 7.0 s
    sim.turn(9.0, -1)                                     # look at lap 1
    sim.knob_tap(11.0)                                    # reset
    sim.run(script("stopwatch.py"), seconds=13)
    times = shown(sim, "time")
    check("07.00" in times or "07.05" in times or "06.95" in times, "stop shows ~7.00 s: %s" % times[-12:-8])
    check(sim.settings.infos["laps"]() == 0, "reset clears the laps")
    laps = [x for x in shown(sim, "lap") if x]
    check(any(x.startswith("L1 2.5") for x in laps) and any(x.startswith("L2 2.5") for x in laps), "two laps of 2.5 s shown: %s" % laps)
    check(sum(1 for x in laps if x.startswith("L1 ")) >= 2, "knob turn looks back at lap 1")
    check(times[-1] == "00.00", "reset shows 00.00")
    # formats over time
    sim = Sim(buttons=1, knob=True, display=True, buzzer=True)
    sim.tap(0, t=0.5)
    sim.run(script("stopwatch.py"), seconds=3700)
    tt = shown(sim, "time")
    check(any(x[:2] in ("58", "59") and x[2] == "." and len(x) == 5 for x in tt), "seconds format below a minute")
    check(any(x.startswith("1:0") and "." in x for x in tt), "m:ss.t format (a minute and more)")
    check(any(x == "11:40" for x in tt), "mm:ss format from 10 min")
    check(any(x.startswith("1:01:") for x in tt), "h:mm:ss format from 1 h")


def test_morse():
    print("morse_tapper")
    sim = Sim(buttons=1, display=True, buzzer=True)
    sim.settings.v.update(wpm=10)                         # unit 0.12 s
    t = 1.0
    for hold, gap in ((0.08, 0.1), (0.08, 0.1), (0.08, 0.7),       # S
                      (0.4, 0.1), (0.4, 0.1), (0.4, 0.7),          # O
                      (0.08, 0.1), (0.08, 0.1), (0.08, 0.9)):      # S
        sim.press(0, t=t, hold=hold)
        t += hold + gap
    t += 1.0
    for i in range(6):                                    # ...... = unknown
        sim.press(0, t=t + i * 0.2, hold=0.08)
    sim.press(0, t=t + 4.0, hold=1.7)                     # clear
    sim.run(script("morse_tapper.py"), seconds=t + 7)
    msgs = shown(sim, "text")
    check("SOS" in msgs, "SOS decoded: %s" % msgs[:6])
    check(any(x == "SOS " for x in msgs), "long pause adds a space")
    check(seen(sim, "code", "...") and seen(sim, "code", "......"), "dots shown while tapping")
    check(len(sim.where("tune")) >= 3, "unknown pattern = error tune, clear = ok tune")
    check(msgs[-1] == "", "hold 1.5 s clears the text")
    check(any(d[0] == 700 for (t2, d) in sim.where("buzz")), "sidetone plays")


def test_level():
    print("spirit_level")
    import math
    acc = Obj()
    acc.acceleration = (0.0, 0.0, 9.8)
    sim = Sim(buttons=1, display=True, thirdparty={"msa311": [acc]})
    tilt = math.radians(5)
    sim.at(3, lambda: setattr(acc, "acceleration", (9.8 * math.sin(tilt), 0.0, 9.8 * math.cos(tilt))))
    sim.tap(0, t=8)                                       # zero here
    sim.press(0, t=12, hold=1.3)                          # back to the board's own zero
    sim.run(script("spirit_level.py"), seconds=16)
    reads = shown(sim, "read")
    check(reads[0] == "+0.0 +0.0", "flat = +0.0 +0.0 (%s)" % reads[0])
    check("+5.0 +0.0" in reads, "5 degrees tilt shown (%s)" % sorted(set(reads))[:6])
    check(reads[reads.index("+5.0 +0.0"):].count("+0.0 +0.0") > 0, "zero button levels the reading")
    check(reads[-1] == "+5.0 +0.0", "hold goes back to the board's own zero (%s)" % reads[-1])
    cols = [d[4] for (t, d) in sim.where("disp.rect")]
    check(0x00FF00 in cols and 0xFF8000 in cols, "bubble green when level, orange when tilted")
    check(sim.settings.infos["tilt_x"]() == 5.0, "tilt info row")
    leds = [x for (t, x) in sim.where("btn0.color")]
    check(any(x[1] > 0 and x[0] == 0 for x in leds) and any(x[0] > 0 and x[1] > 0 and x[2] == 0 for x in leds), "LED green / orange")


def test_meter():
    print("light_meter")
    light = Obj()
    light.lux = 1000.0
    sim = Sim(buttons=1, knob=True, display=True, thirdparty={"veml7700": [light]})
    sim.turn(2.0, 1)                                      # aperture 5.6 -> 8
    sim.knob_tap(3.0)                                     # now ISO
    sim.turn(4.0, 1); sim.turn(4.5, 1)                    # ISO 100 -> 200 -> 400
    sim.tap(0, t=6.0)                                     # freeze
    sim.at(7.0, lambda: setattr(light, "lux", 10.0))
    sim.tap(0, t=9.0)                                     # release
    sim.at(11.0, lambda: setattr(light, "lux", None))
    sim.run(script("light_meter.py"), seconds=13)
    sh = shown(sim, "shutter")
    check(sh[0] == "1/15", "1000 lx, f/5.6, ISO 100 -> 1/15 (got %s)" % sh[0])
    check("1/8" in sh, "f/8 -> 1/8")
    check("1/30" in sh, "f/8 ISO 400 -> 1/30")
    lx = shown(sim, "lux")
    check(lx.count("1000 lx") > 5 and "10 lx" in lx, "freeze holds 1000 lx, release shows 10 lx")
    check(lx[-1] == "--", "None reading shows --")
    check(shown(sim, "ap")[-1] == "f/8" and shown(sim, "iso")[-1] == "ISO 400", "aperture and ISO shown")
    check(sim.settings.v["aperture"] == "8" and sim.settings.v["iso"] == "400", "values kept as settings")
    check(sim.settings.infos["lux"]() is None, "info survives None")



# ---------------------------------------------------------------------------------------------
# data products (brain library noknok_feeds with RECORDED real API answers, 20 Nov 2026)
# ---------------------------------------------------------------------------------------------
BRAIN = os.environ.get("NK_BRAIN") or os.path.join(POC, "..", "brain-Pico")


class Net:
    """Serves the fixtures of brain-Pico/tools/fixtures/feeds instead of the internet."""

    def __init__(self):
        self.urls, self.fail = [], None

    def __call__(self, url, timeout, max_bytes):
        self.urls.append(url)
        if self.fail:
            raise self.fail
        name = ("departures_bern" if "stationboard" in url else "geocode_bern" if "geocoding" in url
                else "weather_bern" if "open-meteo.com/v1/forecast" in url else "power_ch" if "energy-charts" in url else None)
        if name is None:
            raise OSError("no route " + url)
        with open(os.path.join(BRAIN, "tools", "fixtures", "feeds", name + ".json"), "rb") as f:
            return f.read()


def feeds_lib():
    sys.path.insert(0, os.path.join(BRAIN, "software"))
    import noknok_feeds as nf
    net = Net()
    nf._http[0] = net
    nf._geo_cache.clear()
    return nf, net


def test_bus():
    print("bus_stop_board")
    nf, net = feeds_lib()
    sim = Sim(buttons=1, display=True, epoch0=1795159500 - 300)           # first departure in 5 minutes
    sim.settings.v.update(walk_min=3, refresh_s=20)
    sim.at(10, lambda: sim.settings.app_sets(walk_min=4))
    sim.run(script("bus_stop_board.py"), seconds=14)
    r0 = [x for x in shown(sim, "r0") if x]
    check(r0[0] == "loading...", "first screen before the (slow) first fetch: loading...")
    r0 = [x for x in r0 if x != "loading..."]
    check(r0 and r0[0].startswith("9") and r0[0].endswith("5'"), "first row: line 9 in 5 minutes: %r" % (r0[:1],))
    check(sim.display.colors["r0"] == 0xFFD000, "walk 4 min: 5 minutes is 'hurry' (yellow)")
    check(shown(sim, "head")[-1] == "Bern, Bahnhof" and shown(sim, "clock")[-1] == "08:20", "stop name and local clock %s" % shown(sim, "clock")[-1:])
    check(all(len(x) <= 26 for r in ("r0", "r1", "r2", "r3") for x in shown(sim, r)), "every row fits 26 characters")
    check(sim.settings.infos["stop_found"]() == "Bern, Bahnhof" and sim.settings.infos["next_min"]() is not None, "info rows")
    check(sim.settings.infos["source"]().startswith("transport.opendata.ch"), "attribution info row")
    check(any("limit=15" in u for u in net.urls) and len(net.urls) <= 2, "one request per refresh (%d in 14 s)" % len(net.urls))
    # green with time to spare
    nf, net = feeds_lib()
    sim = Sim(buttons=1, display=True, epoch0=1795159500 - 300)
    sim.settings.v.update(walk_min=2)
    sim.run(script("bus_stop_board.py"), seconds=4)
    check(sim.display.colors["r0"] == 0x30FF60, "walk 2 min: 5 minutes is green")
    # line filter
    nf, net = feeds_lib()
    sim = Sim(buttons=1, display=True, epoch0=1795159500 - 300)
    sim.settings.v.update(line="9")
    sim.run(script("bus_stop_board.py"), seconds=4)
    rows = [x for r in ("r0", "r1", "r2", "r3") for x in shown(sim, r) if x and x != "loading..."]
    check(rows and all(x.split()[0] == "9" for x in rows), "line filter 9: %s" % rows[:3])
    # two stops: the button switches
    nf, net = feeds_lib()
    sim = Sim(buttons=1, display=True, epoch0=1795159500 - 300)
    sim.settings.v.update(stop2="Zürich, Bellevue")
    sim.tap(0, t=5)
    sim.run(script("bus_stop_board.py"), seconds=9)
    check(any("Z%C3%BCrich%2C%20Bellevue" in u for u in net.urls), "button switches to the second stop (request for it)")
    # offline: the last board stays, greyed, with a stale status
    nf, net = feeds_lib()
    sim = Sim(buttons=1, display=True, epoch0=1795159500 - 300)
    sim.settings.v.update(refresh_s=20)
    sim.at(10, lambda: setattr(net, "fail", OSError(110)))
    sim.run(script("bus_stop_board.py"), seconds=50)
    check(sim.display.colors["head"] == 0x707070 and sim.display.colors["r0"] == 0x707070, "offline: board kept, greyed")
    check(sim.settings.infos["status"]().startswith("stale"), "status says stale: %s" % sim.settings.infos["status"]())
    # clock not set
    nf, net = feeds_lib()
    sim = Sim(buttons=1, display=True, epoch0=100)
    sim.run(script("bus_stop_board.py"), seconds=4)
    check(shown(sim, "clock")[-1] == "--:--" and "--" in shown(sim, "r0")[-1], "no clock (NTP missing): minutes shown as --")
    # nothing yet + error
    nf, net = feeds_lib()
    net.fail = OSError(101)
    sim = Sim(buttons=1, display=True, epoch0=1795159500)
    sim.run(script("bus_stop_board.py"), seconds=5)
    check(shown(sim, "r0")[-1].startswith("no data"), "first fetch fails: 'no data' line, no crash")


def test_weather():
    print("weather_board")
    nf, net = feeds_lib()
    sim = Sim(buttons=1, display=True, epoch0=1795159500)
    sim.tap(0, t=5)
    sim.at(12, lambda: sim.settings.app_sets(place="Lugano"))
    sim.run(script("weather_board.py"), seconds=16)
    check("7" in shown(sim, "temp") and "C" in shown(sim, "unit"), "temperature 7 C (real answer 7.4)")
    check(any(x.startswith("Light rain") for x in shown(sim, "sky")), "weather in words: %s" % [x for x in shown(sim, "sky")][:2])
    check(any(x.startswith("next 12 h") for x in shown(sim, "head")), "page 2 header %s" % shown(sim, "head")[-1:])
    bars = [d for (t, d) in sim.where("disp.rect", 5, 11.9) if d[2] == 11]
    check(len(bars) == 12, "12 hourly bars drawn (%d)" % len(bars))
    check(any("name=Lugano" in u for u in net.urls) and any("latitude=" in u for u in net.urls), "new place is looked up and fetched")
    cols = [x for (t, x) in sim.where("btn0.color")]
    check(any(x[0] == 0 and x[2] > x[1] > 0 for x in cols), "LED blue for rain")
    check(sim.settings.infos["source"]() == "Weather data by Open-Meteo.com", "attribution info row")
    check(all(len(x) <= 26 for r in ("head", "sky") for x in shown(sim, r)), "text fits")
    nf, net = feeds_lib()
    net.fail = OSError(101)
    sim = Sim(buttons=1, display=True, epoch0=1795159500)
    sim.run(script("weather_board.py"), seconds=5)
    check(shown(sim, "sky")[-1].startswith("no data"), "offline at start: 'no data', no crash")


def test_power():
    print("power_price_board")
    import datetime
    t0 = int(datetime.datetime(2026, 11, 20, 7, 25, tzinfo=datetime.timezone.utc).timestamp())
    nf, net = feeds_lib()
    sim = Sim(buttons=1, display=True, epoch0=t0)
    sim.tap(0, t=5)
    sim.at(12, lambda: sim.settings.app_sets(zone="DE-LU"))
    sim.run(script("power_price_board.py"), seconds=16)
    big = [x for x in shown(sim, "big") if x not in ("--", "")]
    check(big and big[0] == "25.9", "price now 25.9 ct/kWh (real answer): %s" % big[:1])
    lv = [x for x in shown(sim, "level") if x.split()[0] in ("CHEAP", "OK", "PRICEY")]
    check(lv and "best 2h:" in lv[0], "level word and cheapest 2 h window: %s" % lv[:1])
    check(sim.settings.infos["level"]() in ("CHEAP", "OK", "PRICEY") and sim.settings.infos["price_now"]() == 25.93, "info rows")
    bars = [d for (t, d) in sim.where("disp.rect", 5, 11.9) if d[2] <= 12 and d[3] >= 3]
    check(len(bars) == 16, "16 hourly bars from now to the end of the known prices (%d)" % len(bars))
    check(any(d[4] == 0xFFFFFF for (t, d) in sim.where("disp.rect", 5)), "current hour bar is white")
    check(any("bzn=DE-LU" in u for u in net.urls) and any("start=2026-11-20&end=2026-11-21" in u for u in net.urls), "zone change refetches; request uses local dates")
    check(all(len(x) <= 26 for r in ("head", "level") for x in shown(sim, r)), "text fits")
    check(sim.settings.infos["source"]() == "energy-charts.info (CC BY 4.0)", "attribution info row")
    # no clock: the product says so instead of guessing
    nf, net = feeds_lib()
    sim = Sim(buttons=1, display=True, epoch0=100)
    sim.run(script("power_price_board.py"), seconds=5)
    check(shown(sim, "level")[-1].startswith("no data: no clock"), "no clock: 'no data: no clock'")



def data_products_available():
    """The three data products need their scripts in POC and noknok_feeds.py in brain-Pico."""
    return (all(os.path.isfile(os.path.join(POC, "scripts", n)) for n in
                ("bus_stop_board.py", "weather_board.py", "power_price_board.py"))
            and os.path.isfile(os.path.join(BRAIN, "software", "noknok_feeds.py")))


if __name__ == "__main__":
    tests = [test_quiz, test_duel, test_focus, test_focus_stop, test_box, test_breath, test_plant, test_guard,
             test_metronome, test_dice, test_stopwatch, test_morse, test_level, test_meter]
    if data_products_available():
        tests += [test_bus, test_weather, test_power]
    else:
        print("SKIPPED the 3 data products (need scripts/bus_stop_board.py, weather_board.py, power_price_board.py "
              "and brain-Pico software/noknok_feeds.py; set NK_BRAIN to a brain-Pico clone)")
    for t in tests:
        try:
            t()
        except Exception as e:
            import traceback
            traceback.print_exc()
            FAILS.append("%s raised %r" % (t.__name__, e))
    print("\nFAILED: %d" % len(FAILS) if FAILS else "\nALL OK")
    for f in FAILS:
        print(" -", f)
    sys.exit(1 if FAILS else 0)
