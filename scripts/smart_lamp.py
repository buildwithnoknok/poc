# smart_lamp.py — noknok Smart Lamp (Setup 3: USB LEDs + I2C controls)
#
# A configurable lamp assembled from a USB LEDs module plus I2C controls:
#
#   Power button (LED button)
#     - short press      -> toggle the lamp on / off (buzzer confirms)
#     - long press (1 s) -> Sundown: a 30-minute eased fade to off (buzzer confirms)
#     - its own RGB LED is the STATUS LIGHT: glows the lamp's colour when on, dark when off
#   Brightness knob
#     - turn             -> dim / brighten
#     - tap (quick press)-> jump to full brightness
#     - hold 5 s         -> factory reset (wipe + back to the noknok-setup AP)
#   Colour knob
#     - turn             -> step through 64 colours (4 whites + 60 hues), wraps around
#     - tap (quick press)-> jump to warm white
#   Buzzer
#     - distinct confirmation sounds for on / off / sundown
#
# State (on / brightness / colour) is saved to smart_lamp_settings.json so the
# lamp restores itself after a power cut. That file is ALSO the intended hook for
# future app configuration: a /settings endpoint on the Pico would write the same
# JSON, and this script would pick it up on the next boot. Writes are debounced
# (a couple of seconds after the last change) so a knob sweep doesn't hammer the
# Pico's flash.
#
# The lamp drives EVERY connected USB LEDs module (c.leds), so plugging in a second
# module for a brighter lamp works with no code change.

from noknok import Conductor
import time
import json

# One GENERIC settings file per device (a Pico runs one product at a time), so the
# filename is product-agnostic — matches noknok's other on-device files (wifi.json,
# noknok_roles.json, noknok_state.json) and lets a future /settings app endpoint
# read/write it without knowing which product is installed. The product id is tagged
# INSIDE the file so a product can ignore stale settings left by a previous product.
SETTINGS_FILE = "product_settings.json"
PRODUCT_ID    = "smart-lamp-v1"


def _log(msg):
    """Append to log.txt (code.py doesn't capture product.py's own output)."""
    try:
        with open("log.txt", "a") as f:
            f.write("[smart_lamp] " + str(msg) + "\n")
    except Exception:
        pass


# ── Colour palette: 4 whites + 60 hues = 64 ───────────────────────────────────
# Whites first (indices 0-3) so a colour-knob "tap" can jump straight to warm white.
WHITES = [
    (255, 175,  95),   # 0  warm white   (~2700 K)
    (255, 205, 150),   # 1  soft white
    (255, 240, 225),   # 2  neutral white
    (200, 220, 255),   # 3  cool white   (~6500 K)
]
WARM_WHITE_INDEX = 0

def _hsv_hue(h):
    """Hue 0-360 at full saturation/brightness -> (r, g, b) 0-255. Integer maths,
    no libraries (keeps it light for CircuitPython)."""
    c = 255
    x = int(255 * (1 - abs((h / 60.0) % 2 - 1)))
    if   h < 60:  return (c, x, 0)
    elif h < 120: return (x, c, 0)
    elif h < 180: return (0, c, x)
    elif h < 240: return (0, x, c)
    elif h < 300: return (x, 0, c)
    else:         return (c, 0, x)

PALETTE = WHITES + [_hsv_hue(i * 6) for i in range(60)]   # 60 hues, 6 deg apart -> 64 total


# ── Behaviour tuning ──────────────────────────────────────────────────────────
LONG_PRESS_S    = 1.0     # power-button hold -> Sundown
TAP_MAX_S       = 0.8     # knob press shorter than this = a "tap" shortcut
BRIGHTNESS_STEP = 8       # brightness change per knob detent (~32 detents = full range)
SUNDOWN_MINUTES = 30      # Sundown fade duration
SAVE_DEBOUNCE_S = 2.0     # save settings this long after the last change
LOOP_SLEEP_S    = 0.03


# ── State + persistence ───────────────────────────────────────────────────────
state = {"on": True, "brightness": 180, "color_index": WARM_WHITE_INDEX}

def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            saved = json.load(f)
        # Ignore settings left behind by a different product (stale after a switch).
        if saved.get("product") not in (None, PRODUCT_ID):
            _log("settings file belongs to %s, not %s - ignoring"
                 % (saved.get("product"), PRODUCT_ID))
            return
        for k in ("on", "brightness", "color_index"):
            if k in saved:
                state[k] = saved[k]
        state["on"]          = bool(state["on"])
        state["brightness"]  = max(0, min(255, int(state["brightness"])))
        state["color_index"] = int(state["color_index"]) % len(PALETTE)
        _log("settings loaded: %s" % state)
    except Exception as e:
        _log("no saved settings (%s) - using defaults" % e)

_dirty = False
_last_change = 0.0
def mark_dirty():
    global _dirty, _last_change
    _dirty = True
    _last_change = time.monotonic()

def maybe_save():
    global _dirty
    if _dirty and (time.monotonic() - _last_change) >= SAVE_DEBOUNCE_S:
        try:
            record = {"product": PRODUCT_ID}
            record.update(state)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(record, f)
            _log("settings saved: %s" % record)
        except Exception as e:
            _log("settings save failed: %s" % e)
        _dirty = False


# ── Setup ─────────────────────────────────────────────────────────────────────
c = Conductor()
c.enumerate_all()      # both buses: I2C controls + USB LEDs
c.load_roles()         # noknok_roles.json (created by the app during setup)

# The two knobs are the same module type, so they MUST come from roles. The button
# and buzzer are singletons; fall back to index if a roles file is missing (bench).
power_button = c.role.get("power_button")    or (c.ledbutton[0] if c.ledbutton else None)
bright_knob  = c.role.get("brightness_knob") or (c.knob[0] if c.knob else None)
color_knob   = c.role.get("color_knob")      or (c.knob[1] if len(c.knob) > 1 else None)
buzzer       = c.buzzer[0] if c.buzzer else None
lamps        = c.leds      # ALL connected USB LEDs modules

if not lamps:
    _log("FAILED: no USB LEDs module found")
    raise SystemExit("No USB LEDs module found - check wiring.")
if power_button is None or bright_knob is None or color_knob is None:
    _log("WARNING missing control(s): power=%s bright=%s color=%s"
         % (power_button is not None, bright_knob is not None, color_knob is not None))

load_settings()
_log("smart lamp up: %d lamp module(s), controls power=%s bright=%s color=%s buzzer=%s"
     % (len(lamps), power_button is not None, bright_knob is not None,
        color_knob is not None, buzzer is not None))


# ── Output helpers (drive EVERY connected USB LEDs module) ─────────────────────
def apply_output():
    """Push the current state to the lamp(s) and mirror it on the status LED."""
    r, g, b = PALETTE[state["color_index"]]
    for lamp in lamps:
        if state["on"]:
            lamp.set_brightness(state["brightness"])
            lamp.set_all(r, g, b)
        else:
            lamp.off()
    if power_button is not None:
        if state["on"]:
            power_button.set_color(r, g, b)   # status light glows the lamp colour
        else:
            power_button.led_off()

def start_sundown():
    """Long-press action: hand the lamp(s) a self-running Sundown fade of the
    CURRENT colour, over SUNDOWN_MINUTES. The module runs the fade autonomously."""
    r, g, b = PALETTE[state["color_index"]]
    for lamp in lamps:
        lamp.play_preset(lamp.PRESET_SUNDOWN, SUNDOWN_MINUTES, r, g, b)
    state["on"] = True
    if power_button is not None:
        power_button.set_color(r, g, b)
    mark_dirty()
    _log("sundown started (%d min, colour idx %d)" % (SUNDOWN_MINUTES, state["color_index"]))

# Buzzer confirmations (fire-and-forget single notes; distinct pitches).
def beep_on():
    if buzzer: buzzer.play(880, 120, 70)          # bright, rising feel
def beep_off():
    if buzzer: buzzer.play(440, 120, 70)          # lower
def beep_sundown():
    # Gentle descending "good night" motif. Blocking ~0.5 s is fine on a
    # deliberate long-press.
    if buzzer:
        for f in (660, 523, 392):
            buzzer.note(f, 150, 55, gap_ms=30)


# ── Main loop ─────────────────────────────────────────────────────────────────
apply_output()   # reflect the restored state immediately

pb_press_start = None    # power button
pb_long_fired  = False
bk_was_pressed = False    # brightness knob
bk_press_start = None
ck_was_pressed = False    # colour knob
ck_press_start = None

while True:
    now = time.monotonic()

    # One read per control per loop (knob delta + button edges auto-clear on read).
    pb = power_button.read() if power_button else None
    bk = bright_knob.read()  if bright_knob  else None
    ck = color_knob.read()   if color_knob   else None

    # Factory-reset watchdog lives on the brightness knob (hold 5 s).
    c.check_factory_reset(bk)

    # ── Power button: short press = on/off, long press = Sundown ──────────────
    if pb is not None:
        if pb.press_event:
            pb_press_start = now
            pb_long_fired  = False
        if (pb.pressed and pb_press_start is not None and not pb_long_fired
                and (now - pb_press_start) >= LONG_PRESS_S):
            pb_long_fired = True
            beep_sundown()
            start_sundown()
        if pb.release_event:
            if not pb_long_fired:                       # a short press -> toggle
                state["on"] = not state["on"]
                (beep_on if state["on"] else beep_off)()
                apply_output()
                mark_dirty()
                _log("toggled %s" % ("ON" if state["on"] else "OFF"))
            pb_press_start = None

    # ── Brightness knob: turn = dim/brighten, tap = full brightness ──────────
    if bk is not None:
        if state["on"] and bk.delta != 0:              # ignore turns while off
            state["brightness"] = max(0, min(255, state["brightness"] + bk.delta * BRIGHTNESS_STEP))
            apply_output()
            mark_dirty()
        if bk.pressed and not bk_was_pressed:
            bk_press_start = now
        elif (not bk.pressed) and bk_was_pressed:      # release -> was it a tap?
            if (now - (bk_press_start or now)) < TAP_MAX_S:
                state["brightness"] = 255
                if state["on"]:
                    apply_output()
                mark_dirty()
                _log("brightness tap -> full")
        bk_was_pressed = bk.pressed

    # ── Colour knob: turn = step colour, tap = warm white ────────────────────
    if ck is not None:
        if state["on"] and ck.delta != 0:              # ignore turns while off
            state["color_index"] = (state["color_index"] + ck.delta) % len(PALETTE)
            apply_output()
            mark_dirty()
        if ck.pressed and not ck_was_pressed:
            ck_press_start = now
        elif (not ck.pressed) and ck_was_pressed:      # release -> was it a tap?
            if (now - (ck_press_start or now)) < TAP_MAX_S:
                state["color_index"] = WARM_WHITE_INDEX
                if state["on"]:
                    apply_output()
                mark_dirty()
                _log("colour tap -> warm white")
        ck_was_pressed = ck.pressed

    maybe_save()
    time.sleep(LOOP_SLEEP_S)
