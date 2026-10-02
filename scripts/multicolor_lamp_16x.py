# multicolor_lamp_16x.py — noknok Multicolor Lamp 16x (USB LEDs 16x, RGBW)  v1.0.0
#
# The first product for the noknok LEDs 16x: a lamp controlled from the noknok
# app, using the ring's dedicated WHITE LEDs (a neutral-white die in every LED).
#
#   Light mode (app)
#     - White           -> white LEDs only: clean, efficient neutral white
#     - Colour          -> any colour from the RGB LEDs
#     - Colour + white  -> the colour, softened with an adjustable amount of white
#
#   Read-only on the app's settings page (config_schema type "info"):
#     - Temperature -> the module's chip temperature, live
#     - Light       -> Normal / Dimmed (warm) / Off (too hot) / Off (weak USB power):
#                      the module protects itself and dims when hot or on a weak
#                      USB supply; this line says why the lamp looks dimmer.
#
# Settings live in c.settings (runtime Store, never a file: DEV-18). The lamp
# drives EVERY connected LEDs 16x, so a second ring works with no code change.
# Factory reset: the app's factory reset (no button on this product).
# Needs LEDs 16x firmware 2.2.0+ (older firmware reports itself as the 8x board).

from noknok import Conductor
import time

# ── Settings (same ids and defaults as the manifest's config_schema) ──────────
DEFAULTS = {
    "on": True,
    "brightness": 120,
    "mode": "white",          # white | color | mix
    "color": "#FFAF5F",       # warm white from the RGB LEDs
    "white": 160,             # white amount in "mix" mode
}

LOOP_SLEEP_S   = 0.25         # nothing to poll; c.sleep() keeps the app answered
STATUS_CACHE_S = 0.5          # both info rows share one status read per app poll


def hex_to_rgb(s, fallback=(255, 175, 95)):
    """'#RRGGBB' -> (r, g, b); anything malformed -> fallback (the app validates,
    the brain stores verbatim, the product is the last line of defence)."""
    try:
        s = str(s).lstrip("#")
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return fallback

def clamp255(v, fallback):
    try:
        return max(0, min(255, int(v)))
    except Exception:
        return fallback


# ── Setup ──────────────────────────────────────────────────────────────────────
c = Conductor()
c.enumerate_all()
rings = c.leds16              # ALL connected LEDs 16x modules

if not rings:
    if c.leds:
        print("[lamp16] FAILED: found an LEDs module that reports itself as the 8x - "
              "a LEDs 16x needs firmware 2.2.0+")
    else:
        print("[lamp16] FAILED: no LEDs 16x found")
    raise SystemExit("No LEDs 16x found - check wiring.")

s = c.settings
s.defaults(DEFAULTS)

def lamp_on():    return bool(s.get("on"))
def brightness(): return clamp255(s.get("brightness"), DEFAULTS["brightness"])
def white_amt():  return clamp255(s.get("white"), DEFAULTS["white"])
def mode():
    m = s.get("mode")
    return m if m in ("white", "color", "mix") else DEFAULTS["mode"]

print("[lamp16] up: %d ring(s), settings=%s" % (len(rings), s.all()))


# ── Output ─────────────────────────────────────────────────────────────────────
def apply_output(changed=None):
    """Paint every ring from the current settings. Also the on_change target:
    the app changed something -> repaint."""
    r, g, b = hex_to_rgb(s.get("color"))
    m = mode()
    for ring in rings:
        if not lamp_on():
            ring.off()                       # LED power rail off: ~0.03 W standby
            continue
        ring.set_brightness(brightness())
        if m == "white":
            ring.white(255)
        elif m == "color":
            ring.set_all(r, g, b)
        else:
            ring.set_all(r, g, b, w=white_amt())


# ── Read-only info for the app (the first ring speaks for the lamp) ──────────
_status = {"t": -1.0, "v": None}

def ring_status():
    """One GET_STATUS per app poll, shared by both info rows."""
    now = time.monotonic()
    if now - _status["t"] > STATUS_CACHE_S:
        _status["v"] = rings[0].status()
        _status["t"] = now
    return _status["v"]

def temperature():
    st = ring_status()
    return st["temp_c"] if st else None      # None -> the app shows "—"

def light_state():
    st = ring_status()
    if st is None:
        return None
    if st["thermal_cut"]:
        return "Off - too hot, cooling down"
    if st["vbus_cut"]:
        return "Off - USB power too weak"
    if not lamp_on():
        return "Off"
    if st["thermal_pct"] < 100:
        return "Dimmed - warm (%d %%)" % st["thermal_pct"]
    if st["vbus_pct"] < 100:
        return "Dimmed - weak USB power (%d %%)" % st["vbus_pct"]
    return "Normal"

s.info("temperature", temperature)
s.info("light", light_state)


# ── Main loop ──────────────────────────────────────────────────────────────────
s.on_change(apply_output)
apply_output()

while True:
    c.sleep(LOOP_SLEEP_S)     # services the app channel; settings changes arrive here
