# smart_lamp_mini.py — noknok Smart Lamp Mini (Setup 3: USB LEDs + one LED Button)  v1.0.0
#
# The smallest lamp in the Smart Lamp family: a USB LEDs module for light and a
# single LED Button for everything else.
#
#   Button
#     - short press      -> next brightness level: off -> 1 -> 2 -> 3 -> 4 -> 5 -> off
#     - hold (1 s)       -> next colour, ONE step per hold (release and hold again
#                           for the next one; the step happens at the 1-s mark so
#                           you see it while still holding)
#     - its RGB LED is the STATUS LIGHT: glows the lamp's colour when on, dark when off
#
# Factory reset is not this script's job: hold the button while plugging in the
# power (code.py 0.18 boot-hold). Both of the button's gestures are ours.
#
# Settings (c.settings, shared with the noknok app's settings page): on,
# brightness (0-255), color (#RRGGBB). The app may set any value; the button
# snaps to the next grid step above it — an off-grid brightness steps up to the
# next of the 5 levels, an off-palette colour steps to warm white first.
# Persistence is the Conductor's (runtime Store, never a file: DEV-18).
#
# The lamp drives EVERY connected USB LEDs module (c.leds), so a second module
# for a brighter lamp works with no code change.

from noknok import Conductor
import time

# ── Brightness levels: 5 steps, roughly perceptual (each ~1.5-2x the previous) ─
LEVELS = [20, 64, 120, 180, 255]

# ── Colour palette: 3 whites + 9 hues = 12 (one step per hold, so keep it short) ─
WHITES = [
    (255, 175,  95),   # 0  warm white   (~2700 K)
    (255, 240, 225),   # 1  neutral white
    (200, 220, 255),   # 2  cool white   (~6500 K)
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

PALETTE = WHITES + [_hsv_hue(i * 40) for i in range(9)]   # 9 hues, 40 deg apart -> 12 total

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

def next_level(current):
    """The next of the 5 levels above `current`, or None when the next step is
    'off' (current is at or above the top level)."""
    for lv in LEVELS:
        if lv > current:
            return lv
    return None


# ── Behaviour tuning ───────────────────────────────────────────────────────────
LONG_PRESS_S = 1.0     # button hold -> colour step
LOOP_SLEEP_S = 0.03

# Defaults — same ids and values as the manifest's config_schema.
DEFAULTS = {
    "on": True,
    "brightness": LEVELS[2],
    "color": rgb_to_hex(WHITES[WARM_WHITE_INDEX]),
}


# ── Setup ──────────────────────────────────────────────────────────────────────
c = Conductor()
c.enumerate_all()      # both buses: the I2C button + the USB LEDs
c.load_roles()         # no roles in this product; harmless if the file is missing

button = c.ledbutton[0] if c.ledbutton else None
lamps  = c.leds        # ALL connected USB LEDs modules

if not lamps:
    print("[smart_lamp_mini] FAILED: no USB LEDs module found")
    raise SystemExit("No USB LEDs module found - check wiring.")
if button is None:
    print("[smart_lamp_mini] WARNING: no LED Button found - app control only")

s = c.settings
s.defaults(DEFAULTS)

# Accessors that clamp — the app validates, the brain stores verbatim.
def lamp_on():    return bool(s.get("on"))
def brightness(): return max(0, min(255, int(s.get("brightness", LEVELS[2]))))
def color_rgb():  return hex_to_rgb(s.get("color"), WHITES[WARM_WHITE_INDEX])

print("[smart_lamp_mini] up: %d lamp module(s), button=%s, settings=%s"
      % (len(lamps), button is not None, s.all()))


# ── Output (drive EVERY connected USB LEDs module + the status LED) ────────────
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
    if button is not None:
        if lamp_on():
            button.set_color(r, g, b)      # status light glows the lamp colour
        else:
            button.led_off()

def step_brightness():
    """Short press: off -> level 1 ... level 5 -> off."""
    if not lamp_on():
        s.set("on", True)
        s.set("brightness", LEVELS[0])
    else:
        nxt = next_level(brightness())
        if nxt is None:
            s.set("on", False)
        else:
            s.set("brightness", nxt)
    apply_output()
    print("[smart_lamp_mini] brightness -> %s" % (brightness() if lamp_on() else "off"))

def step_color():
    """Hold: one palette step. A free colour from the app is not in the palette:
    the first step goes to warm white instead of from an undefined position."""
    idx = palette_index(color_rgb())
    idx = WARM_WHITE_INDEX if idx is None else (idx + 1) % len(PALETTE)
    s.set("color", rgb_to_hex(PALETTE[idx]))
    apply_output()
    print("[smart_lamp_mini] colour -> %s" % s.get("color"))


# ── Main loop ──────────────────────────────────────────────────────────────────
s.on_change(apply_output)   # app-side changes: repaint (called between our reads)
apply_output()              # reflect the restored settings immediately

press_start = None
long_fired  = False

while True:
    now = time.monotonic()
    st = button.read() if button else None   # edges auto-clear on read

    if st is not None:
        if st.press_event:
            press_start = now
            long_fired  = False
        # Long hold: fire ONCE at the 1-s mark, then wait for the release.
        if (st.pressed and press_start is not None and not long_fired
                and (now - press_start) >= LONG_PRESS_S):
            long_fired = True
            if lamp_on():                     # nothing to see while off
                step_color()
        if st.release_event:
            if not long_fired:                # a short press -> next brightness
                step_brightness()
            press_start = None

    c.sleep(LOOP_SLEEP_S)   # also services the app channel (settings changes arrive here)
