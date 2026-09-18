# smart_lamp.py — noknok Smart Lamp Midi (Setup 3: USB LEDs + I2C controls)  v2.0.0
#
# The middle lamp of the Smart Lamp family: a USB LEDs module for light, an LED
# Button for brightness and mode, a Knob for colour, a Buzzer for confirmation.
#
#   Button
#     - short press      -> next brightness level: off -> 1 -> 2 -> 3 -> 4 -> 5 -> off
#                           (buzzer clicks per step, a lower tone for off)
#     - hold (1 s)       -> toggle the MODE: light <-> sundown (buzzer confirms)
#     - its RGB LED is the STATUS LIGHT: glows the lamp's colour when on, dark when off.
#       For 5 s after a mode toggle it shows the mode instead:
#         sundown -> breathes full -> off three times
#         light   -> stays constant on
#   Knob
#     - turn             -> step through 64 colours (4 whites + 60 hues), wraps around
#     - tap (quick press)-> jump to warm white
#   Buzzer
#     - confirmation sounds for brightness steps, off, and the mode toggle
#
#   Modes
#     light   -> constant light at the chosen level
#     sundown -> whenever the lamp is on, it fades from the current level to off
#                over sundown_minutes (the LEDs module runs the fade itself,
#                eased). A brightness step or colour change during the fade
#                restarts it from the new level/colour. When the fade ends the
#                lamp is off; the next short press starts a fresh one at level 1.
#
# Factory reset is not this script's job: hold the button (or the knob) while
# plugging in the power (code.py 0.18 boot-hold).
#
# Settings (c.settings, shared with the noknok app's settings page): on,
# brightness (0-255), color (#RRGGBB), mode (light / sundown), sundown_minutes.
# The app may set any value; the controls snap to the next grid step above it.
# Persistence is the Conductor's (runtime Store, never a file: DEV-18).
#
# v2.0.0: the two-knob 1.x layout (brightness knob + colour knob) is gone —
# brightness moved to the button, Sundown became a mode instead of a one-shot.
#
# The lamp drives EVERY connected USB LEDs module (c.leds), so a second module
# for a brighter lamp works with no code change.

from noknok import Conductor
import time

# ── Brightness levels: 5 steps, roughly perceptual (each ~1.5-2x the previous) ─
LEVELS = [20, 64, 120, 180, 255]

# ── Colour palette: 4 whites + 60 hues = 64 ────────────────────────────────────
# Whites first (indices 0-3) so a knob "tap" can jump straight to warm white.
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

def next_level(current):
    """The next of the 5 levels above `current`, or None when the next step is
    'off' (current is at or above the top level)."""
    for lv in LEVELS:
        if lv > current:
            return lv
    return None


# ── Behaviour tuning ───────────────────────────────────────────────────────────
LONG_PRESS_S   = 1.0     # button hold -> mode toggle
TAP_MAX_S      = 0.8     # knob press shorter than this = a "tap" shortcut
MODE_SHOW_S    = 5.0     # how long the status LED shows the mode after a toggle
MODE_BREATHS   = 3       # sundown indication: full -> off this many times in MODE_SHOW_S
LOOP_SLEEP_S   = 0.03

MODE_LIGHT   = "light"
MODE_SUNDOWN = "sundown"

# Defaults — same ids and values as the manifest's config_schema.
DEFAULTS = {
    "on": True,
    "brightness": LEVELS[2],
    "color": rgb_to_hex(WHITES[WARM_WHITE_INDEX]),
    "mode": MODE_LIGHT,
    "sundown_minutes": 30,
}


# ── Setup ──────────────────────────────────────────────────────────────────────
c = Conductor()
c.enumerate_all()      # both buses: I2C controls + USB LEDs
c.load_roles()         # no roles in this product (every module is a singleton)

button = c.ledbutton[0] if c.ledbutton else None
knob   = c.knob[0]      if c.knob      else None
buzzer = c.buzzer[0]    if c.buzzer    else None
lamps  = c.leds        # ALL connected USB LEDs modules

if not lamps:
    print("[smart_lamp] FAILED: no USB LEDs module found")
    raise SystemExit("No USB LEDs module found - check wiring.")
if button is None or knob is None:
    print("[smart_lamp] WARNING missing control(s): button=%s knob=%s"
          % (button is not None, knob is not None))

s = c.settings
s.defaults(DEFAULTS)

# Accessors that clamp — the app validates, the brain stores verbatim.
def lamp_on():         return bool(s.get("on"))
def brightness():      return max(0, min(255, int(s.get("brightness", LEVELS[2]))))
def color_rgb():       return hex_to_rgb(s.get("color"), WHITES[WARM_WHITE_INDEX])
def sundown_mode():    return str(s.get("mode", MODE_LIGHT)) == MODE_SUNDOWN
def sundown_minutes(): return max(1, min(120, int(s.get("sundown_minutes", 30))))

print("[smart_lamp] up: %d lamp module(s), button=%s knob=%s buzzer=%s, settings=%s"
      % (len(lamps), button is not None, knob is not None, buzzer is not None, s.all()))


# ── Output (drive EVERY connected USB LEDs module + the status LED) ────────────
fade_end  = None    # monotonic time the running Sundown fade reaches off, or None
mode_show = None    # (start time, mode) while the status LED shows the mode

def apply_output(changed=None):
    """Push the current settings to the lamp(s) and mirror them on the status
    LED. Also the on_change target: the app changed something -> repaint.
    In sundown mode every repaint (re)starts the fade from the current
    level — the module stops its animation on any other LED command anyway."""
    global fade_end
    r, g, b = color_rgb()
    if not lamp_on():
        fade_end = None
        for lamp in lamps:
            lamp.off()
    elif sundown_mode():
        for lamp in lamps:
            lamp.set_brightness(brightness())              # the fade starts here
            lamp.play_preset(lamp.PRESET_SUNDOWN, sundown_minutes(), r, g, b)
        fade_end = time.monotonic() + sundown_minutes() * 60
    else:
        fade_end = None
        for lamp in lamps:
            lamp.set_brightness(brightness())
            lamp.set_all(r, g, b)
    paint_status()

def paint_status(level=1.0):
    """Status LED: the lamp colour (scaled by `level`, for the breathing
    indication) when on, dark when off."""
    if button is None:
        return
    if lamp_on() and level > 0:
        r, g, b = color_rgb()
        button.set_color(int(r * level), int(g * level), int(b * level))
    else:
        button.led_off()

def service_mode_show(now):
    """Drive the 5-s mode indication on the status LED, non-blocking."""
    global mode_show
    if mode_show is None:
        return
    start, mode = mode_show
    t = now - start
    if t >= MODE_SHOW_S:
        mode_show = None
        paint_status()                                     # back to the status light
        return
    if mode == MODE_SUNDOWN:
        period = MODE_SHOW_S / MODE_BREATHS
        level  = 1.0 - (t % period) / period               # full -> off, three times
        if button is not None:
            r, g, b = color_rgb()
            button.set_color(int(r * level), int(g * level), int(b * level))
    # light mode: constant on — nothing to animate. If the lamp is off the LED
    # still shows the mode, so force it on for the 5 s.
    elif button is not None:
        r, g, b = color_rgb()
        button.set_color(r, g, b)


# ── Buzzer confirmations (fire-and-forget single notes; distinct pitches) ──────
def beep_step():
    if buzzer: buzzer.play(1000, 40, 60)          # short click per level
def beep_off():
    if buzzer: buzzer.play(440, 120, 70)          # lower: lamp off
def beep_light():
    if buzzer: buzzer.play(880, 120, 70)          # single note: light mode
def beep_sundown():
    # Gentle descending "good night" motif. Blocking ~0.5 s is fine on a
    # deliberate long-press.
    if buzzer:
        for f in (660, 523, 392):
            buzzer.note(f, 150, 55, gap_ms=30)


# ── Actions ────────────────────────────────────────────────────────────────────
def step_brightness():
    """Short press: off -> level 1 ... level 5 -> off."""
    if not lamp_on():
        s.set("on", True)
        s.set("brightness", LEVELS[0])
        beep_step()
    else:
        nxt = next_level(brightness())
        if nxt is None:
            s.set("on", False)
            beep_off()
        else:
            s.set("brightness", nxt)
            beep_step()
    apply_output()
    print("[smart_lamp] brightness -> %s" % (brightness() if lamp_on() else "off"))

def toggle_mode():
    """Hold: light <-> sundown, confirm by sound, show it on the LED for 5 s."""
    global mode_show
    new_mode = MODE_LIGHT if sundown_mode() else MODE_SUNDOWN
    s.set("mode", new_mode)
    (beep_sundown if new_mode == MODE_SUNDOWN else beep_light)()
    apply_output()                                         # starts / stops the fade
    mode_show = (time.monotonic(), new_mode)
    print("[smart_lamp] mode -> %s" % new_mode)

def end_of_fade():
    """The Sundown fade reached off on the module: mirror that in the settings
    so the app agrees and the next press starts from off."""
    global fade_end
    fade_end = None
    s.set("on", False)
    apply_output()
    print("[smart_lamp] sundown finished -> off")


# ── Main loop ──────────────────────────────────────────────────────────────────
s.on_change(apply_output)   # app-side changes: repaint (called between our reads)
apply_output()              # reflect the restored settings immediately

pb_press_start = None    # button
pb_long_fired  = False
kn_was_pressed = False   # knob
kn_press_start = None

while True:
    now = time.monotonic()

    # One read per control per loop (knob delta + button edges auto-clear on read).
    pb = button.read() if button else None
    kn = knob.read()   if knob   else None

    # ── Button: short press = brightness step, hold = mode toggle ───────────
    if pb is not None:
        if pb.press_event:
            pb_press_start = now
            pb_long_fired  = False
        if (pb.pressed and pb_press_start is not None and not pb_long_fired
                and (now - pb_press_start) >= LONG_PRESS_S):
            pb_long_fired = True
            toggle_mode()
        if pb.release_event:
            if not pb_long_fired:                       # a short press
                step_brightness()
            pb_press_start = None

    # ── Knob: turn = step colour, tap = warm white ───────────────────────────
    if kn is not None:
        if lamp_on() and kn.delta != 0:                # ignore turns while off
            idx = palette_index(color_rgb())
            # A free colour from the app is not in the palette: the first detent
            # steps from warm white instead of from an undefined position.
            idx = WARM_WHITE_INDEX if idx is None else (idx + kn.delta) % len(PALETTE)
            s.set("color", rgb_to_hex(PALETTE[idx]))
            apply_output()
        if kn.pressed and not kn_was_pressed:
            kn_press_start = now
        elif (not kn.pressed) and kn_was_pressed:      # release -> was it a tap?
            if (now - (kn_press_start or now)) < TAP_MAX_S:
                s.set("color", rgb_to_hex(WHITES[WARM_WHITE_INDEX]))
                if lamp_on():
                    apply_output()
                print("[smart_lamp] colour tap -> warm white")
        kn_was_pressed = kn.pressed

    # ── Housekeeping: mode indication, end of a Sundown fade ────────────────
    service_mode_show(now)
    if fade_end is not None and now >= fade_end:
        end_of_fade()

    c.sleep(LOOP_SLEEP_S)   # also services the app channel (settings changes arrive here)
