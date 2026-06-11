# two_button_box.py — noknok Two-Button Box
#
# Two LED Buttons — OK and Cancel — with sound and light feedback. Which
# physical button is OK and which is Cancel is chosen in the app during setup
# (role assignment), so the two identical buttons are told apart by the UID the
# customer pressed.
#
#   OK button press     → green + "OK" beep
#   Cancel button press  → red + error beep
#   Hold the Knob 5 s    → factory reset (back to noknok-setup)
#
# Run from Thonny. Ctrl-C to stop.

from noknok import Conductor
import time

# ── Setup ─────────────────────────────────────────────────────────────────────
c = Conductor()
c.enumerate()
c.load_roles()   # reads noknok_roles.json written during app role assignment

if not c.buzzer:
    raise SystemExit("No buzzer found — check wiring.")
if not c.knob:
    raise SystemExit("No knob found — check wiring.")

ok     = c.role.get("ok_button")
cancel = c.role.get("cancel_button")
if ok is None or cancel is None:
    raise SystemExit("Buttons not assigned — re-run setup in the noknok app.")

buz = c.buzzer[0]
knb = c.knob[0]

# Idle colours so the customer can see which button is which.
OK_IDLE, OK_ON         = (0, 60, 0), (0, 255, 0)     # green
CANCEL_IDLE, CANCEL_ON = (60, 0, 0), (255, 0, 0)     # red
ok.set_color(*OK_IDLE)
cancel.set_color(*CANCEL_IDLE)

print("\n noknok Two-Button Box")
print(" ──────────────────────")
print("  OK button     → green + OK beep")
print("  Cancel button → red + error beep")
print("  Hold knob 5 s → factory reset\n")

ok_was = False
cancel_was = False

# Product is fully initialized (modules found, roles loaded, LEDs set) — play a
# "ready" chime so the customer knows setup is done and they can start using it.
buz.tune(buz.STARTUP)

# ── Main loop ─────────────────────────────────────────────────────────────────
while True:
    # Factory reset: hold the Knob button ~5 s (pass the status we read).
    c.check_factory_reset(knb.read())

    s_ok     = ok.read()
    s_cancel = cancel.read()
    if s_ok is None or s_cancel is None:
        time.sleep(0.03)
        continue

    # OK button — rising edge
    if s_ok.pressed and not ok_was:
        ok.set_color(*OK_ON)
        buz.tune(buz.BEEP_OK)
        print("  OK pressed")
    if not s_ok.pressed and ok_was:
        ok.set_color(*OK_IDLE)
    ok_was = s_ok.pressed

    # Cancel button — rising edge
    if s_cancel.pressed and not cancel_was:
        cancel.set_color(*CANCEL_ON)
        buz.tune(buz.BEEP_ERROR)
        print("  Cancel pressed")
    if not s_cancel.pressed and cancel_was:
        cancel.set_color(*CANCEL_IDLE)
    cancel_was = s_cancel.pressed

    time.sleep(0.03)
