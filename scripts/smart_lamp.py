# smart_lamp.py — noknok Smart Lamp (Setup 3: USB LEDs + I2C controls)  v1.1.0
#
# A configurable lamp assembled from a USB LEDs module plus I2C controls:
#
#   Power button (LED button)
#     - short press      -> toggle the lamp on / off (buzzer confirms)
#     - long press (1 s) -> Sundown: an eased fade to off (buzzer confirms)
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
# v1.1.0 (DEV-34): the lamp's settings — on, brightness, color, sundown_minutes —
# live in c.settings. The knobs and the noknok app change the SAME values: the
# app's settings page (rendered from the manifest's config_schema) calls
# settings.set on the brain, the Conductor hands the change to on_change()
# below between two of our module reads, and we repaint. Persistence is the
# Conductor's job (runtime Store, written after 5 s of quiet — never a file,
# never from this loop: DEV-18). The old smart_lamp_settings.json is gone.
#
# The lamp drives EVERY connected USB LEDs module (c.leds), so plugging in a second
# module for a brighter lamp works with no code change.

from noknok import Conductor
import time

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

def rgb_to_hex(rgb):
    return "#%02X%02X%02X" % rgb

def hex_to_rgb(s, fallback=WHITES[0]):
    """'#RRGGBB' -> (r, g, b); anything malformed -> fallback (the app validates,
    the brain stores verbatim, we are the last line of defence)."""
    try:
        s = str(s).lstrip("#")
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return fallback

def palette_index(rgb):
    """Index of rgb in the palette, or None if the app picked a free colour."""
    try:
        return PALETTE.index(tuple(rgb))
    except ValueError:
        return None


# ── Behaviour tuning ──────────────────────────────────────────────────────────
LONG_PRESS_S    = 1.0     # power-button hold -> Sundown
TAP_MAX_S       = 0.8     # knob press shorter than this = a "tap" shortcut
BRIGHTNESS_STEP = 8       # brightness change per knob detent (~32 detents = full range)
LOOP_SLEEP_S    = 0.03

# Defaults — same ids and values as the manifest's config_schema.
DEFAULTS = {
    "on": True,
    "brightness": 180,
    "color": rgb_to_hex(WHITES[WARM_WHITE_INDEX]),
    "sundown_minutes": 30,
}


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
    print("[smart_lamp] FAILED: no USB LEDs module found")
    raise SystemExit("No USB LEDs module found - check wiring.")
if power_button is None or bright_knob is None or color_knob is None:
    print("[smart_lamp] WARNING missing control(s): power=%s bright=%s color=%s"
          % (power_button is not None, bright_knob is not None, color_knob is not None))

s = c.settings
s.defaults(DEFAULTS)

# Accessors that clamp — the app validates, the brain stores verbatim.
def lamp_on():        return bool(s.get("on"))
def brightness():     return max(0, min(255, int(s.get("brightness", 180))))
def color_rgb():      return hex_to_rgb(s.get("color"), WHITES[WARM_WHITE_INDEX])
def sundown_minutes():return max(1, min(120, int(s.get("sundown_minutes", 30))))

print("[smart_lamp] up: %d lamp module(s), controls power=%s bright=%s color=%s buzzer=%s, settings=%s"
      % (len(lamps), power_button is not None, bright_knob is not None,
         color_knob is not None, buzzer is not None, s.all()))


# ── Output helpers (drive EVERY connected USB LEDs module) ─────────────────────
def apply_output(changed=None):
    """Push the current settings to the lamp(s) and mirror them on the status
    LED. Also the on_change target: the app changed something -> repaint."""
    r, g, b = color_rgb()
    for lamp in lamps:
        if lamp_on():
            lamp.set_brightness(brightness())
            lamp.set_all(r, g, b)
        else:
            lamp.off()
    if power_button is not None:
        if lamp_on():
            power_button.set_color(r, g, b)   # status light glows the lamp colour
        else:
            power_button.led_off()

def start_sundown():
    """Long-press action: hand the lamp(s) a self-running Sundown fade of the
    CURRENT colour over sundown_minutes. The module runs the fade autonomously."""
    r, g, b = color_rgb()
    for lamp in lamps:
        lamp.play_preset(lamp.PRESET_SUNDOWN, sundown_minutes(), r, g, b)
    s.set("on", True)
    if power_button is not None:
        power_button.set_color(r, g, b)
    print("[smart_lamp] sundown started (%d min, %s)" % (sundown_minutes(), s.get("color")))

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
s.on_change(apply_output)   # app-side changes: repaint (called between our reads)
apply_output()              # reflect the restored settings immediately

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
                s.set("on", not lamp_on())
                (beep_on if lamp_on() else beep_off)()
                apply_output()
                print("[smart_lamp] toggled %s" % ("ON" if lamp_on() else "OFF"))
            pb_press_start = None

    # ── Brightness knob: turn = dim/brighten, tap = full brightness ──────────
    if bk is not None:
        if lamp_on() and bk.delta != 0:                # ignore turns while off
            s.set("brightness", max(0, min(255, brightness() + bk.delta * BRIGHTNESS_STEP)))
            apply_output()
        if bk.pressed and not bk_was_pressed:
            bk_press_start = now
        elif (not bk.pressed) and bk_was_pressed:      # release -> was it a tap?
            if (now - (bk_press_start or now)) < TAP_MAX_S:
                s.set("brightness", 255)
                if lamp_on():
                    apply_output()
                print("[smart_lamp] brightness tap -> full")
        bk_was_pressed = bk.pressed

    # ── Colour knob: turn = step colour, tap = warm white ────────────────────
    if ck is not None:
        if lamp_on() and ck.delta != 0:                # ignore turns while off
            idx = palette_index(color_rgb())
            # A free colour from the app is not in the palette: the first detent
            # steps from warm white instead of from an undefined position.
            idx = WARM_WHITE_INDEX if idx is None else (idx + ck.delta) % len(PALETTE)
            s.set("color", rgb_to_hex(PALETTE[idx]))
            apply_output()
        if ck.pressed and not ck_was_pressed:
            ck_press_start = now
        elif (not ck.pressed) and ck_was_pressed:      # release -> was it a tap?
            if (now - (ck_press_start or now)) < TAP_MAX_S:
                s.set("color", rgb_to_hex(WHITES[WARM_WHITE_INDEX]))
                if lamp_on():
                    apply_output()
                print("[smart_lamp] colour tap -> warm white")
        ck_was_pressed = ck.pressed

    c.sleep(LOOP_SLEEP_S)   # also services the app channel (settings changes arrive here)
