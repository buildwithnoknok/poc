# SPDX-License-Identifier: MIT
# smart_lamp_maxi.py — noknok Smart Lamp Maxi (Setup 3: USB LEDs + I2C controls + Display)  v1.1.0
#
# The top lamp of the Smart Lamp family: lamp + clock + kitchen timer + wake-up
# light. Modules: LEDs 16x (or 8x), LED Button, Knob, Buzzer, Display.
#
#   Home screen (160x80): big clock, info line (timer / sundown / alarm),
#   bell when the alarm is armed, colour swatch + brightness bar. The one the
#   knob is currently changing has a white frame. Backlight: 60 % with the
#   lamp on, 15 % off, its lowest level after a Sundown (night) until the
#   lamp is switched on again.
#
#   Button
#     - short press      -> lamp on / off
#     - hold (1 s)       -> Sundown: fade from the current brightness to off
#                           over sundown_minutes (eased, stepped from here)
#     - its RGB LED      -> dark; shows a new colour for 3 s after a change
#     - while ringing    -> timer: stop. Alarm: short = snooze 5 min, hold = stop
#   Knob (home screen)
#     - turn             -> brightness (or colour, after a tap)
#     - tap              -> switch the knob between brightness and colour;
#                           back to brightness after 5 s without turning
#     - hold (2 s)       -> menu
#   Knob (menu)  Timer · Alarm · Sundown · Reset lamp · Back
#     - turn = choose / adjust, tap = confirm, hold 2 s = leave the menu
#   Timer   1-120 min kitchen timer; at zero the buzzer rings and the lamp
#           pulses until any press (stops by itself after 5 min).
#   Alarm   wake-up light: the lamp fades UP from dark to the set brightness
#           over sunrise_minutes before the alarm time (driven from here with
#           set_brightness, no module firmware involved), then the buzzer rings.
#           Needs the clock, i.e. WiFi at power-on.
#
# Time: the brain syncs UTC over NTP at boot (code.py). The local time comes
# from the `timezone` setting; summer time (EU / US rules) is computed here, so
# the clock is right all year without the phone. No WiFi -> "--:--", the timer
# still works, the alarm waits for the clock.
#
# Factory reset is not this script's job: hold the button (or the knob) while
# plugging in the power (code.py 0.18 boot-hold). "Reset lamp" in the menu only
# puts the lamp's own settings back to defaults (the timezone is kept).
#
# Settings (c.settings, shared with the app): on, brightness, color,
# sundown_minutes, alarm_on, alarm_time, sunrise_minutes, timezone, and the
# read-only info field `clock` (the lamp's local time, to check the timezone).
# Persistence is the Conductor's (runtime Store, never a file: DEV-18).
#
# Display: there is no frame buffer, so everything is repainted only when its
# value changes — a full home screen is ~20 I2C commands, a clock tick ~8.

from noknok import Conductor, BLACK, WHITE, GREY, DARK_GREY, LANDSCAPE
import time

# ── Palette: 4 whites + 60 hues = 64 (same as Smart Lamp Midi) ─────────────────
WHITES = [
    (255, 175,  95),   # 0  warm white   (~2700 K)
    (255, 205, 150),   # 1  soft white
    (255, 240, 225),   # 2  neutral white
    (200, 220, 255),   # 3  cool white   (~6500 K)
]
WARM_WHITE_INDEX = 0

def _hsv_hue(h):
    """Hue 0-360 at full saturation/brightness -> (r, g, b) 0-255."""
    c = 255
    x = int(255 * (1 - abs((h / 60.0) % 2 - 1)))
    if   h < 60:  return (c, x, 0)
    elif h < 120: return (x, c, 0)
    elif h < 180: return (0, c, x)
    elif h < 240: return (0, x, c)
    elif h < 300: return (x, 0, c)
    else:         return (c, 0, x)

PALETTE = WHITES + [_hsv_hue(i * 6) for i in range(60)]

def rgb_to_hex(rgb):
    return "#%02X%02X%02X" % rgb

def hex_to_rgb(s, fallback=WHITES[0]):
    try:
        s = str(s).lstrip("#")
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return fallback

def palette_index(rgb):
    try:
        return PALETTE.index(tuple(rgb))
    except ValueError:
        return None

def parse_hhmm(s, fallback=7 * 60):
    """'HH:MM' -> minutes after midnight."""
    try:
        h, m = str(s).split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return h * 60 + m
    except Exception:
        pass
    return fallback

def fmt_hhmm(minutes):
    minutes %= 1440
    return "%02d:%02d" % (minutes // 60, minutes % 60)

def fmt_mmss(seconds):
    seconds = max(0, int(seconds + 0.999))      # round up: never show 0:00 early
    return "%d:%02d" % (seconds // 60, seconds % 60)


# ── Time zones: id -> (standard offset in hours, summer-time rule) ─────────────
# Same ids as the manifest's `timezone` options. "eu" = last Sunday of March
# to last Sunday of October, 01:00 UTC. "us" = second Sunday of March 02:00
# local to first Sunday of November 02:00 local.
ZONES = {
    "utc":  (0,  None),
    "uk":   (0,  "eu"),     # UK, Ireland, Portugal
    "cet":  (1,  "eu"),     # Central Europe (CH, DE, FR, IT, ...)
    "eet":  (2,  "eu"),     # Eastern Europe (FI, GR, RO, ...)
    "us_e": (-5, "us"),
    "us_c": (-6, "us"),
    "us_m": (-7, "us"),
    "us_p": (-8, "us"),
    "jp":   (9,  None),     # Japan / Korea, no summer time
}

def _utc(y, m, d, h=0):
    """UTC epoch seconds of a date/hour. The RTC runs on UTC, so mktime is UTC."""
    return time.mktime((y, m, d, h, 0, 0, 0, -1, -1))

def _sunday_on_or_before(y, m, d):
    wd = time.localtime(_utc(y, m, d)).tm_wday            # Monday = 0, Sunday = 6
    return d - ((wd + 1) % 7)

_dst_cache = {}   # (rule, std, year) -> (start_utc, end_utc)

def _dst_window(rule, std, year):
    key = (rule, std, year)
    if key not in _dst_cache:
        if rule == "eu":
            start = _utc(year, 3,  _sunday_on_or_before(year, 3, 31), 1)
            end   = _utc(year, 10, _sunday_on_or_before(year, 10, 31), 1)
        else:   # "us"
            start = _utc(year, 3,  _sunday_on_or_before(year, 3, 14), 2 - std)
            end   = _utc(year, 11, _sunday_on_or_before(year, 11, 7), 2 - (std + 1))
        _dst_cache[key] = (start, end)
    return _dst_cache[key]

def utc_offset_s(utc_now, zone_id):
    std, rule = ZONES.get(zone_id, ZONES["cet"])
    off = std * 3600
    if rule:
        start, end = _dst_window(rule, std, time.localtime(utc_now).tm_year)
        if start <= utc_now < end:
            off += 3600
    return off


# ── Behaviour tuning ───────────────────────────────────────────────────────────
BRIGHT_MIN       = 8       # lowest lamp level: below it colours round to red
LONG_PRESS_S     = 1.0     # button hold -> Sundown / alarm stop
KNOB_HOLD_S      = 2.0     # knob hold -> menu
KNOB_MODE_IDLE_S = 5.0     # colour mode falls back to brightness after this
MENU_IDLE_S      = 20.0    # menu closes by itself after this
SNOOZE_S         = 5 * 60
RING_MAX_S       = {"timer": 5 * 60, "alarm": 10 * 60}   # stop ringing by itself
SUNRISE_STEP_S   = 2.0     # how often the wake-up light may change brightness
BACKLIGHT_ON     = 0.6     # display backlight while the lamp is on
BACKLIGHT_OFF    = 0.15    # dimmer while the lamp is off (bedside)
BACKLIGHT_NIGHT  = 3 / 255  # after a Sundown: dimmest real level (a FRACTION:
                            # backlight(1) would mean 100 %, not raw 1). Raw 1-2 are
                            # BRIGHTER than 3 on the panel: 60-150 ns PWM pulses leave
                            # the backlight MOSFET half-on (bench 4 Oct).
STATUS_SHOW_S    = 3.0     # button LED shows a new colour this long, then dark
LOOP_SLEEP_S     = 0.03
LAMP_REFRESH_S   = 10.0    # re-send the full lamp state this often while on
LAMP_COALESCE_S  = 0.12    # knob turns: at most one LEDs update this often

DEFAULTS = {
    "on": True,
    "brightness": 120,
    "color": rgb_to_hex(WHITES[WARM_WHITE_INDEX]),
    "sundown_minutes": 30,
    "alarm_on": False,
    "alarm_time": "07:00",
    "sunrise_minutes": 15,
    "timezone": "cet",
}
LAMP_KEYS = [k for k in DEFAULTS if k != "timezone"]   # what "Reset lamp" resets


# ── Setup ──────────────────────────────────────────────────────────────────────
c = Conductor()
c.enumerate_all()      # both buses: I2C controls + display, USB LEDs
c.load_roles()         # no roles: every module is a singleton

button  = c.ledbutton[0] if c.ledbutton else None
knob    = c.knob[0]      if c.knob      else None
buzzer  = c.buzzer[0]    if c.buzzer    else None
display = c.display[0]   if c.display   else None
lamps   = list(c.leds16) + list(c.leds)    # every LEDs module, 16x and 8x

if not lamps:
    print("[maxi] FAILED: no USB LEDs module found")
    raise SystemExit("No USB LEDs module found - check wiring.")
if button is None or knob is None or display is None:
    print("[maxi] WARNING missing: button=%s knob=%s display=%s"
          % (button is not None, knob is not None, display is not None))

s = c.settings
s.defaults(DEFAULTS)

def lamp_on():         return bool(s.get("on"))
def brightness():      return max(BRIGHT_MIN, min(255, int(s.get("brightness", 120))))
def color_rgb():       return hex_to_rgb(s.get("color"), WHITES[WARM_WHITE_INDEX])
def sundown_minutes(): return max(1, min(120, int(s.get("sundown_minutes", 30))))
def sunrise_minutes(): return max(1, min(60, int(s.get("sunrise_minutes", 15))))
def alarm_on():        return bool(s.get("alarm_on"))
def alarm_min():       return parse_hhmm(s.get("alarm_time", "07:00"))

def local_now():
    """Local time as a struct_time, or None while the clock is not set (no NTP
    since power-on: the Pico has no battery-backed clock)."""
    utc = time.time()
    if time.localtime(utc).tm_year < 2025:
        return None
    return time.localtime(utc + utc_offset_s(utc, str(s.get("timezone", "cet"))))

def clock_text():
    t = local_now()
    return "--:--" if t is None else "%02d:%02d" % (t.tm_hour, t.tm_min)

s.info("clock", lambda: (clock_text() if local_now() else "not set - no WiFi"))

print("[maxi] up: %d lamp(s), button=%s knob=%s buzzer=%s display=%s, settings=%s"
      % (len(lamps), button is not None, knob is not None, buzzer is not None,
         display is not None, s.all()))


# ── Runtime state (never persisted: a power cut ends a timer or a fade) ────────
sundown_end   = None    # monotonic time the running Sundown fade reaches off
sundown_start = 0.0     # when the running Sundown (re)started
sundown_level = None    # brightness the Sundown fade is at
sunrise_level = None    # brightness the wake-up light is at, or None
sunrise_skip  = None    # monotonic time until which the wake-up light is cancelled
timer_end     = None    # monotonic time the kitchen timer reaches zero
timer_last    = 10      # minutes, preselected next time the timer is opened
ringing       = None    # None / "timer" / "alarm"
ring_start    = 0.0
ring_next     = 0.0     # next buzzer note while ringing
ring_step     = 0
snooze_until  = None    # monotonic time a snoozed alarm rings again
alarm_fired   = None    # (year, yday, alarm minute) last rung — once per day and time

knob_mode     = "bri"   # home screen: "bri" or "col"
lamp_dirty    = False   # a knob turn changed the lamp; sent from the loop
night_dim     = False   # display at night level until the lamp is switched on again
knob_used_at  = 0.0
screen        = "home"  # "home" / "menu" / "edit"
menu_idx      = 0
menu_used_at  = 0.0
edit          = None    # dict while editing a menu item

MENU = ["Timer", "Alarm", "Sundown", "Reset lamp", "Back"]


# ── Buzzer (fire-and-forget notes; play() durations are in 100 ms units) ──────
def beep(freq=1000, ms=100, vol=60):
    if buzzer: buzzer.play(freq, ms, vol)
def beep_on():      beep(1000, 100, 60)
def beep_off():     beep(440, 200, 60)
def beep_ok():      beep(1320, 100, 60)
def beep_sundown():
    if buzzer:       # descending "good night" motif, ~0.5 s, deliberate hold
        for f in (660, 523, 392):
            buzzer.note(f, 150, 55, gap_ms=30)


# ── Lamp output ────────────────────────────────────────────────────────────────
# The LEDs 16x has a real white die (W). Mixing white from R+G+B turns red when
# dimmed (green and blue round down to 0 first), so on the 16x the shared part
# of a colour goes to W: warm white (255,175,95) -> R160 G80 B0 + W95.
def _rgbw(lamp, r, g, b):
    if hasattr(lamp, "white"):           # NoknokLEDs16
        w = min(r, g, b)
        return (r - w, g - w, b - w, w)
    return (r, g, b)

def lamp_color(lamp, r, g, b):
    lamp.set_all(*_rgbw(lamp, r, g, b))

def lamp_preset(lamp, preset, speed, r, g, b):
    c4 = _rgbw(lamp, r, g, b)
    if len(c4) == 4:
        lamp.play_preset(preset, speed, c4[0], c4[1], c4[2], c4[3])
    else:
        lamp.play_preset(preset, speed, r, g, b)

def apply_output(changed=None):
    """Push the settings to every LEDs module and the status LED. Also the
    on_change target (the app changed something)."""
    global sundown_end, sundown_start, sundown_level, status_until
    if changed and "color" in changed:   # a new colour from the app: show it
        status_until = time.monotonic() + STATUS_SHOW_S
    if ringing == "timer":               # the pulse owns the lamp until stopped
        paint_status()
        return
    r, g, b = color_rgb()
    if not lamp_on():
        sundown_end = None
        for lamp in lamps:
            lamp.off()
        paint_status()
        return
    if sundown_end is not None:          # a running Sundown restarts from here
        sundown_start = time.monotonic()
        sundown_end   = sundown_start + sundown_minutes() * 60
        sundown_level = brightness()
    push_lamp(current_level())
    paint_status()

def current_level():
    if sunrise_level is not None:
        return sunrise_level
    if sundown_end is not None and sundown_level is not None:
        return sundown_level
    return brightness()

# Every lamp update sends BOTH brightness and the full colour, and the state is
# re-sent every LAMP_REFRESH_S while on. Reason (bench 3 Oct, DEV-73 finding):
# rapid small USB commands to the LEDs 16x occasionally arrive corrupted — one
# LED or one whole frame goes off-colour. "Set all" rewrites every LED and
# cancels any animation a stray byte started, so a glitch never sticks.
_last_push = 0.0

def push_lamp(level):
    global _last_push
    r, g, b = color_rgb()
    for lamp in lamps:
        lamp.set_brightness(level)
        lamp_color(lamp, r, g, b)
    _last_push = time.monotonic()

# Sundown and the wake-up light are both driven from here with set_brightness,
# NOT with the module's SUNDOWN preset: that preset fades the colour values and
# the module then scales them by brightness again — two roundings, and the mix
# drifts green -> yellow -> red at low levels (seen on the bench 3 Oct). Global
# brightness over a full-value colour rounds once and stays white down to 8.
_sundown_sent = 0.0

def service_sundown(now):
    global sundown_end, sundown_level, _sundown_sent, night_dim
    if sundown_end is None or ringing == "timer":
        return
    total = sundown_end - sundown_start
    p = min(1.0, (now - sundown_start) / total)
    # Eased (fast first, slow crawl), landing on the floor exactly at the end.
    top = max(BRIGHT_MIN, brightness())
    level = BRIGHT_MIN + int((top - BRIGHT_MIN) * (1.0 - p) * (1.0 - p))
    if p >= 1.0:
        sundown_end = None
        night_dim = True                 # it is bedtime: display to its lowest level
        s.set("on", False)               # the app agrees: the lamp is off
        apply_output()
        print("[maxi] sundown finished -> off")
    elif level != sundown_level and now - _sundown_sent >= SUNRISE_STEP_S:
        sundown_level = level
        _sundown_sent = now
        push_lamp(level)

# Button LED: dark by default (bedside). After a colour change it shows the new
# colour for STATUS_SHOW_S, then goes dark again (Christopher, 4 Oct).
status_until = 0.0
_status_shown = None      # what the button LED shows now, to skip repeat writes

def show_color_on_button():
    global status_until
    status_until = time.monotonic() + STATUS_SHOW_S
    paint_status()

def paint_status():
    global _status_shown
    if button is None:
        return
    want = color_rgb() if (lamp_on() and time.monotonic() < status_until) else None
    if want == _status_shown:
        return
    _status_shown = want
    if want:
        button.set_color(*want)
    else:
        button.led_off()

def start_sundown():
    global sundown_end
    cancel_sunrise()
    if not lamp_on():
        s.set("on", True)
    sundown_end = time.monotonic()       # marks it running; apply_output sets the end
    beep_sundown()
    apply_output()
    print("[maxi] sundown %d min" % sundown_minutes())

def cancel_sunrise():
    """The user took over: no more wake-up ramp until this alarm has passed.
    Returns True if a ramp was actually running."""
    global sunrise_level, sunrise_skip
    if sunrise_level is None:
        return False
    sunrise_level = None
    sunrise_skip = time.monotonic() + sunrise_minutes() * 60 + 60
    return True


# ── Ringing (timer at zero, alarm time) ────────────────────────────────────────
def start_ring(kind):
    global ringing, ring_start, ring_next, ring_step, snooze_until
    ringing, ring_start, ring_next, ring_step = kind, time.monotonic(), 0.0, 0
    snooze_until = None
    if kind == "timer":
        r, g, b = color_rgb()
        for lamp in lamps:
            lamp.set_brightness(255)
            lamp_preset(lamp, lamp.PRESET_BREATHE, 0, r, g, b)
    print("[maxi] ringing: %s" % kind)

def stop_ring(snooze=False):
    global ringing, snooze_until
    kind, ringing = ringing, None
    if buzzer: buzzer.stop()
    snooze_until = time.monotonic() + SNOOZE_S if (snooze and kind == "alarm") else None
    apply_output()                       # the lamp back to its settings
    print("[maxi] %s %s" % (kind, "snoozed" if snooze_until else "stopped"))

def service_ring(now):
    global ring_next, ring_step
    if ringing is None:
        return
    if now - ring_start >= RING_MAX_S[ringing]:
        stop_ring()
        return
    if now >= ring_next:
        if ringing == "timer":           # fast double beep
            beep(1760, 100, 80)
            ring_next = now + (0.25 if ring_step % 2 == 0 else 0.9)
        else:                            # alarm: rising three-note call, louder over time
            vol = min(100, 50 + int((now - ring_start) / 6))
            beep((784, 988, 1175)[ring_step % 3], 200, vol)
            ring_next = now + (0.3 if ring_step % 3 < 2 else 1.2)
        ring_step += 1


# ── Alarm + wake-up light ──────────────────────────────────────────────────────
_sunrise_sent = 0.0

def service_alarm(now):
    """Called every loop: fire the alarm at its minute, ramp the wake-up light
    before it, re-ring after a snooze."""
    global alarm_fired, sunrise_level, _sunrise_sent
    if snooze_until is not None and now >= snooze_until and ringing is None:
        start_ring("alarm")
        return
    t = local_now()
    if t is None or not alarm_on():
        if sunrise_level is not None:
            sunrise_level = None
            apply_output()
        return
    now_s  = t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec
    target = alarm_min() * 60
    day    = (t.tm_year, t.tm_yday, target)
    if now_s // 60 == target // 60 and alarm_fired != day:
        alarm_fired = day
        if sunrise_level is not None:    # end of the ramp: full set brightness
            sunrise_level = None
            apply_output()
        if ringing is None:
            start_ring("alarm")
        return
    remaining = (target - now_s) % 86400
    total = sunrise_minutes() * 60
    skipped = sunrise_skip is not None and now < sunrise_skip
    if 0 < remaining <= total and not skipped and ringing is None:
        p = 1.0 - remaining / total                  # 0 -> 1 over the ramp
        level = max(BRIGHT_MIN, int(brightness() * p * p))   # eased: slow start, like a sunrise
        if sunrise_level is None:
            print("[maxi] wake-up light: %d min to the alarm" % (remaining // 60))
            sunrise_level = level
            if not lamp_on():
                s.set("on", True)
            apply_output()
            _sunrise_sent = now
        elif level != sunrise_level and now - _sunrise_sent >= SUNRISE_STEP_S:
            sunrise_level = level
            push_lamp(level)
            _sunrise_sent = now
    elif sunrise_level is not None and remaining > total:
        sunrise_level = None                         # alarm moved / switched off
        apply_output()


# ── Display ────────────────────────────────────────────────────────────────────
# Home screen layout (landscape 160x80):
#   y  2-41  clock, 40 px, centred
#   y 46-61  info line (left)            bell icon (right) when the alarm is armed
#   y 64-79  colour swatch (0-31)        brightness bar (36-159)
_drawn = {}       # region name -> what is on the panel now (repaint on change)

def _layout_home():
    display.clear(BLACK)
    display.region("clock", 0, 2, 160, 40, size=40, color=WHITE, align="center")
    display.region("info", 0, 46, 140, 16, size=16, color=GREY)
    display.region("bell", 144, 46, 16, 16, size=16, color=WHITE)
    _drawn.clear()

def _layout_menu():
    display.clear(BLACK)
    display.region("m_title", 0, 0, 160, 16, size=16, color=GREY, align="center")
    display.region("m_value", 0, 24, 160, 32, size=32, color=WHITE, align="center")
    display.region("m_hint", 0, 64, 160, 16, size=16, color=GREY, align="center")
    _drawn.clear()

def _put(name, value, **kw):
    """Repaint a region only if its content changed."""
    if _drawn.get(name) == value:
        return
    _drawn[name] = value
    if value is None or value == "":
        display.set(name)
    elif name == "bell":
        display.set(name, icon=value)
    else:
        display.set(name, text=value, **kw)

def _lamp_row():
    on = lamp_on()
    rgb = color_rgb()
    level = sunrise_level if sunrise_level is not None else brightness()
    # Each part is redrawn only when it changes, and a brightness change only
    # paints the difference: wiping the whole bar to black first is visible as
    # a flicker on every wake-up step (bench 3 Oct).
    sw = (on, rgb, knob_mode)
    if _drawn.get("sw") != sw:
        _drawn["sw"] = sw
        display.fill_rect(0, 64, 32, 16, WHITE if knob_mode == "col" else DARK_GREY)
        display.fill_rect(2, 66, 28, 12, rgb if on else BLACK)
    frame = knob_mode
    if _drawn.get("frame") != frame:
        _drawn["frame"] = frame
        display.fill_rect(36, 64, 124, 16, WHITE if knob_mode == "bri" else DARK_GREY)
        display.fill_rect(38, 66, 120, 12, BLACK)
        _drawn.pop("bar", None)          # the inside was wiped: repaint the fill
    fill = max(1, (120 * level) // 255)
    col = WHITE if on else DARK_GREY
    old = _drawn.get("bar")
    if old == (fill, col):
        return
    _drawn["bar"] = (fill, col)
    if old is None or old[1] != col:
        display.fill_rect(38, 66, fill, 12, col)
        display.fill_rect(38 + fill, 66, 120 - fill, 12, BLACK)
    elif fill > old[0]:
        display.fill_rect(38 + old[0], 66, fill - old[0], 12, col)
    else:
        display.fill_rect(38 + fill, 66, old[0] - fill, 12, BLACK)

def _info_text(now):
    if ringing == "timer":
        return "TIMER! press"
    if ringing == "alarm":
        return "ALARM! snooze"
    if snooze_until is not None:
        return "Snooze " + fmt_mmss(snooze_until - now)
    if timer_end is not None:
        return "Timer " + fmt_mmss(timer_end - now)
    if sundown_end is not None and lamp_on():
        return "Sundown %d min" % max(1, int((sundown_end - now) / 60 + 0.999))
    if sunrise_level is not None:
        return "Good morning"
    if alarm_on():
        return ("Alarm " + fmt_hhmm(alarm_min())) if local_now() else "Alarm: no WiFi"
    return ""

_backlight = None

def paint_home(now):
    global _backlight, night_dim
    if lamp_on() or ringing:
        night_dim = False                # awake again: normal backlight
        want = BACKLIGHT_ON
    else:
        want = BACKLIGHT_NIGHT if night_dim else BACKLIGHT_OFF
    if want != _backlight:
        display.backlight(want)
        _backlight = want
    _put("clock", clock_text())
    _put("info", _info_text(now))
    _put("bell", "bell" if alarm_on() else None)
    _lamp_row()

def paint_menu():
    if screen == "menu":
        _put("m_title", "MENU %d/%d" % (menu_idx + 1, len(MENU)))
        _put("m_value", MENU[menu_idx])
        _put("m_hint", "tap = open")
    else:
        _put("m_title", edit["title"])
        _put("m_value", edit_value_text())
        _put("m_hint", edit["hint"])

def go_home():
    global screen, edit
    screen, edit = "home", None
    if display:
        _layout_home()

def go_menu(idx=0):
    global screen, menu_idx, menu_used_at, edit
    screen, menu_idx, menu_used_at, edit = "menu", idx, time.monotonic(), None
    if display:
        _layout_menu()


# ── Menu editing ───────────────────────────────────────────────────────────────
def open_item(name):
    global edit, screen
    if name == "Back":
        go_home()
        return
    if name == "Timer":
        edit = {"item": name, "title": "Timer", "hint": "tap = start",
                "v": 0 if timer_end is not None else timer_last}
    elif name == "Alarm":
        edit = {"item": name, "title": "Alarm", "hint": "tap = next",
                "stage": "onoff", "v": 1 if alarm_on() else 0}
    elif name == "Sundown":
        edit = {"item": name, "title": "Sundown fade", "hint": "tap = save",
                "v": sundown_minutes()}
    elif name == "Reset lamp":
        edit = {"item": name, "title": "Reset lamp?", "hint": "tap = confirm", "v": 0}
    screen = "edit"
    _drawn.clear()
    display_title_refresh()

def display_title_refresh():
    _drawn.pop("m_title", None)
    _drawn.pop("m_hint", None)

def edit_value_text():
    it, v = edit["item"], edit["v"]
    if it == "Timer":
        return ("Stop" if timer_end is not None else "Off") if v == 0 else "%d min" % v
    if it == "Alarm":
        if edit["stage"] == "onoff":
            return "On" if v else "Off"
        return fmt_hhmm(v)
    if it == "Sundown":
        return "%d min" % v
    return "Yes" if v else "No"

def edit_turn(delta):
    it, v = edit["item"], edit["v"]
    if it == "Timer":                    # 1-min steps up to 10, then 5-min steps
        for _ in range(abs(delta)):
            if delta > 0:
                v = v + 1 if v < 10 else min(120, v + 5)
            else:
                v = v - 1 if v <= 10 else v - 5
            v = max(0, v)
    elif it == "Alarm":
        if edit["stage"] == "onoff":
            v = (v + delta) % 2
        else:                            # fast turn = 15-min steps
            v = (v + (5 if abs(delta) < 3 else 15) * delta) % 1440
    elif it == "Sundown":
        v = max(5, min(60, v + 5 * delta))
    else:
        v = (v + delta) % 2
    edit["v"] = v

def edit_confirm():
    """Knob tap in an edit screen."""
    global timer_end, timer_last
    it, v = edit["item"], edit["v"]
    if it == "Timer":
        if v == 0:
            timer_end = None
            print("[maxi] timer cleared")
        else:
            timer_last = v
            timer_end = time.monotonic() + v * 60
            print("[maxi] timer %d min" % v)
        beep_ok()
        go_home()
    elif it == "Alarm":
        if edit["stage"] == "onoff":
            if v == 0:
                s.set("alarm_on", False)
                beep_ok()
                go_home()
            else:
                edit["stage"], edit["v"] = "time", alarm_min()
                edit["title"], edit["hint"] = "Alarm time", "tap = save"
                display_title_refresh()
            return
        s.set("alarm_time", fmt_hhmm(v))
        s.set("alarm_on", True)
        print("[maxi] alarm %s" % fmt_hhmm(v))
        beep_ok()
        go_home()
    elif it == "Sundown":
        s.set("sundown_minutes", v)
        beep_ok()
        go_home()
    else:
        if v:
            reset_lamp()
        go_home()

def reset_lamp():
    global timer_end, sundown_end, snooze_until, knob_mode
    timer_end = sundown_end = snooze_until = None
    cancel_sunrise()
    knob_mode = "bri"
    for k in LAMP_KEYS:
        s.set(k, DEFAULTS[k])
    beep_ok()
    apply_output()
    print("[maxi] lamp settings reset to defaults")


# ── Controls ───────────────────────────────────────────────────────────────────
def toggle_lamp():
    cancel_sunrise()
    if lamp_on():
        s.set("on", False)
        beep_off()
    else:
        s.set("on", True)
        beep_on()
    apply_output()
    print("[maxi] lamp %s" % ("on" if lamp_on() else "off"))

def knob_turn_home(delta):
    global knob_mode, lamp_dirty
    if not lamp_on():
        return                           # turning does nothing while off
    changed = cancel_sunrise()
    if knob_mode == "bri":
        level = brightness()
        for _ in range(abs(delta)):      # ~8 % per detent: even feel low and high
            step = max(2, level // 12)
            level = level + step if delta > 0 else level - step
        changed = s.set("brightness", max(BRIGHT_MIN, min(255, level))) or changed
    else:
        idx = palette_index(color_rgb())
        idx = WARM_WHITE_INDEX if idx is None else (idx + delta) % len(PALETTE)
        if s.set("color", rgb_to_hex(PALETTE[idx])):
            changed = True
            show_color_on_button()       # the new colour on the button for 3 s
    # Only when something changed: turning on past the end must not fire USB
    # commands at the LEDs for nothing (that triggered DEV-78 flicks).
    if changed:
        lamp_dirty = True                # sent from the loop, max every LAMP_COALESCE_S


# ── Main loop ──────────────────────────────────────────────────────────────────
s.on_change(apply_output)
apply_output()
if display:
    # The Pico's 8x16 font is half as wide as the module's square 8x8 cells:
    # the 40-px clock is 100 px wide instead of 200, "Reset lamp" fits at 32 px.
    display.native_text = False
    if display.width != 160:             # firmware 0.4+ boots landscape; be sure
        display.rotation(LANDSCAPE)
    go_home()

pb_start = None; pb_long = False; pb_ring = False    # button
kn_start = None; kn_long = False; kn_was = False     # knob

while True:
    now = time.monotonic()
    pb = button.read() if button else None
    kn = knob.read()   if knob   else None

    # ── Button ──────────────────────────────────────────────────────────────
    if pb is not None:
        if pb.press_event:
            pb_start, pb_long = now, False
            pb_ring = ringing is not None        # this press belongs to the ringing
        if pb.pressed and pb_start is not None and not pb_long and now - pb_start >= LONG_PRESS_S:
            pb_long = True
            if pb_ring:
                if ringing: stop_ring()          # hold while ringing = stop
            else:
                start_sundown()
        if pb.release_event:
            if not pb_long:
                if pb_ring:
                    if ringing: stop_ring(snooze=(ringing == "alarm"))
                elif snooze_until is not None:
                    snooze_until = None          # cancel a pending snooze
                    beep_off()
                    print("[maxi] snooze cancelled")
                else:
                    toggle_lamp()
            pb_start = None

    # ── Knob ────────────────────────────────────────────────────────────────
    if kn is not None:
        if kn.pressed and not kn_was:            # press
            kn_start, kn_long = now, False
            if ringing:
                stop_ring(snooze=(ringing == "alarm"))
                kn_long = True                   # swallow the rest of this press
        elif kn.pressed and kn_start is not None and not kn_long and now - kn_start >= KNOB_HOLD_S:
            kn_long = True                       # hold 2 s: menu in / out
            beep_ok()
            if screen == "home":
                go_menu()
            else:
                go_home()
        elif (not kn.pressed) and kn_was:        # release
            if not kn_long:                      # a tap
                if screen == "home":
                    knob_mode = "col" if knob_mode == "bri" else "bri"
                    knob_used_at = now
                elif screen == "menu":
                    menu_used_at = now
                    open_item(MENU[menu_idx])
                else:
                    menu_used_at = now
                    edit_confirm()
            kn_start = None
        kn_was = kn.pressed

        if kn.delta:
            if screen == "home":
                knob_used_at = now
                knob_turn_home(kn.delta)
            elif screen == "menu":
                menu_used_at = now
                menu_idx = (menu_idx + kn.delta) % len(MENU)
            else:
                menu_used_at = now
                edit_turn(kn.delta)

    # ── Timeouts ────────────────────────────────────────────────────────────
    if screen == "home" and knob_mode == "col" and now - knob_used_at >= KNOB_MODE_IDLE_S:
        knob_mode = "bri"
    if screen != "home" and now - menu_used_at >= MENU_IDLE_S:
        go_home()

    # ── Timer, Sundown, alarm, ringing ──────────────────────────────────────
    if timer_end is not None and now >= timer_end:
        timer_end = None
        start_ring("timer")
    if lamp_dirty and now - _last_push >= LAMP_COALESCE_S:
        lamp_dirty = False
        apply_output()
    elif lamp_on() and ringing != "timer" and now - _last_push >= LAMP_REFRESH_S:
        push_lamp(current_level())               # heal any corrupted frame
    if _status_shown is not None and now >= status_until:
        paint_status()                           # colour shown 3 s: button dark again
    service_sundown(now)
    service_alarm(now)
    service_ring(now)

    # ── Screen ──────────────────────────────────────────────────────────────
    if display:
        if screen == "home":
            paint_home(now)
        else:
            paint_menu()

    c.sleep(LOOP_SLEEP_S)   # also services the app channel
