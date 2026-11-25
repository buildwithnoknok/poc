# SPDX-License-Identifier: MIT
# desk_guard.py - noknok Desk Guard  v1.0.0
#
# A little alarm for your desk, your bag or your room. It watches two things:
#   - movement in the room   (Soldered easyC PIR motion sensor, 3rd-party, I2C address 0x30)
#   - a bump on the desk     (MSA311 accelerometer, 3rd-party, Adafruit 5309 or a compatible copy)
# Plug third-party boards in with the brain OFF. The PIR has no ID: this product names it for
# you at address 0x30 on bus A (change its address jumper to 0x30, or name it in the app).
#
#   LED Button  short press: arm (when disarmed) or disarm (any time).
#   Exit delay  `exit_s` seconds of quiet beeps to leave the room, then it is ARMED
#               (the button LED glows faint red). The desk's position is learned then.
#   Entry       movement or a bump starts the entry delay: fast beeps, button flashes. Press
#               the button within `entry_s` seconds to disarm.
#   Alarm       siren for `alarm_s` seconds, then it arms again by itself.
#
# Each sensor can be switched off in the app, the bump limit is adjustable (m/s^2, gravity is
# 9.8): 1.0 notices a knock on the table, 3.0 only a real shove. Nothing is stored in files; a
# power cut disarms the guard. This is a toy for peace of mind, NOT a security system.

from noknok import Conductor
import noknok_thirdparty as tp
import time

DISARMED, EXIT, ARMED, ENTRY, ALARM = "Disarmed", "Arming", "Armed", "Entry", "ALARM"
PIR_ADDRESS = 0x30

c = Conductor()
c.enumerate()
tp.attach(c)
if not c.soldered_pir:
    tp.assign(c, "soldered_pir", "A", PIR_ADDRESS)     # the PIR cannot be identified, so we name it

if not c.buzzer or not c.ledbutton:
    raise SystemExit("Desk Guard needs a Buzzer and an LED Button - check wiring.")
if not c.soldered_pir:
    raise SystemExit("No PIR motion sensor found at 0x30 - check wiring / address.")
if not c.msa311:
    raise SystemExit("No accelerometer (MSA311) found - check wiring.")
buzzer, btn = c.buzzer[0], c.ledbutton[0]
pir, acc = c.soldered_pir[0], c.msa311[0]

s = c.settings
s.defaults({"pir_on": True, "bump_on": True, "bump_limit": 1.0, "exit_s": 10, "entry_s": 10,
            "alarm_s": 20, "volume": 60})

state = [DISARMED]
trigger_count = [0]
last_reason = ["-"]
s.info("state", lambda: state[0])
s.info("triggers", lambda: trigger_count[0])
s.info("last_trigger", lambda: last_reason[0])


def clamp(v, lo, hi, fallback):
    try:
        return max(lo, min(hi, float(v)))
    except Exception:
        return fallback


def vol(): return int(clamp(s.get("volume"), 0, 100, 60))


def lamp(rgb):
    btn.set_color(*rgb)


def beep(freq, ms):
    buzzer.play(freq, ms, vol())


def pressed():
    b = btn.read()
    return b is not None and b.press_event


def learn_baseline():
    """Average a few readings: where the desk is now (gravity + tilt)."""
    sx = sy = sz = 0.0
    n = 0
    t0 = time.monotonic()
    while n < 5 and time.monotonic() - t0 < 2.0:
        a = acc.acceleration
        if a is not None:
            sx, sy, sz, n = sx + a[0], sy + a[1], sz + a[2], n + 1
        c.sleep(0.05)
    return [sx / n, sy / n, sz / n] if n else None


def bumped(base):
    """True if the desk moved more than the limit away from the learned position.
    The baseline follows very slow tilts, so a slowly sagging shelf does not alarm."""
    a = acc.acceleration
    if a is None or base is None:
        return False
    dx, dy, dz = a[0] - base[0], a[1] - base[1], a[2] - base[2]
    dev = (dx * dx + dy * dy + dz * dz) ** 0.5
    if dev <= clamp(s.get("bump_limit"), 0.1, 10.0, 1.0):
        for i in range(3):
            base[i] += 0.01 * (a[i] - base[i])
        return False
    return True


def disarmed():
    state[0] = DISARMED
    lamp((0, 60, 0))
    while not pressed():
        c.sleep(0.05)
    return EXIT


def arming():
    state[0] = EXIT
    n = int(clamp(s.get("exit_s"), 0, 60, 10))
    t0 = time.monotonic()
    last = -1
    while time.monotonic() - t0 < n:
        sec = int(time.monotonic() - t0)
        if sec != last:
            last = sec
            beep(600, 60)
            lamp((255, 120, 0))
        elif time.monotonic() - t0 - sec > 0.2:
            lamp((60, 30, 0))
        if pressed():
            return DISARMED
        c.sleep(0.05)
    return ARMED


def armed():
    state[0] = ARMED
    lamp((40, 0, 0))
    base = learn_baseline()
    buzzer.tune(buzzer.BEEP_OK)
    pir.motion                                        # flush a stale reading
    c.sleep(1.0)
    while True:
        if pressed():
            return DISARMED
        if s.get("pir_on") and pir.motion:
            last_reason[0] = "motion"
            return ENTRY
        if s.get("bump_on") and bumped(base):
            last_reason[0] = "bump"
            return ENTRY
        c.sleep(0.05)


def entry():
    state[0] = ENTRY
    trigger_count[0] += 1
    n = clamp(s.get("entry_s"), 0, 30, 10)
    t0 = time.monotonic()
    on = False
    while time.monotonic() - t0 < n:
        if pressed():
            return DISARMED
        step = int((time.monotonic() - t0) * 4)
        if (step % 2 == 0) != on:
            on = step % 2 == 0
            lamp((255, 0, 0) if on else (0, 0, 0))
            if on:
                beep(1000, 80)
        c.sleep(0.05)
    return ALARM


def alarm():
    state[0] = ALARM
    t0 = time.monotonic()
    limit = clamp(s.get("alarm_s"), 5, 120, 20)
    k = 0
    while time.monotonic() - t0 < limit:
        beep(900 if k % 2 == 0 else 1400, 300)
        lamp((255, 0, 0) if k % 2 == 0 else (0, 0, 255))
        k += 1
        for _ in range(6):
            if pressed():
                buzzer.stop()
                return DISARMED
            c.sleep(0.05)
    buzzer.stop()
    return ARMED


STEPS = {DISARMED: disarmed, EXIT: arming, ARMED: armed, ENTRY: entry, ALARM: alarm}

buzzer.tune(buzzer.STARTUP)
print("[guard] up, settings=%s" % s.all())
nxt = DISARMED
while True:
    nxt = STEPS[nxt]()
