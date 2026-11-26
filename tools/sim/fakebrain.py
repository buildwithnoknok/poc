# SPDX-License-Identifier: MIT
# Copyright 2026 noknok (Christopher Houben)
"""fakebrain.py - run a noknok product.py on the PC against fake modules, with a fake clock.

Not a replacement for the bench: it checks the product's LOGIC (timing, state machine, what it
shows and plays), not I2C. Used for the exploration-account products (20 Nov 2026).

    sim = Sim(buttons=4, knob=True, display=True, buzzer=True, leds16=False)
    sim.at(2.0, lambda: sim.tap(0))          # press button 0 at t = 2 s
    sim.run("scripts/quiz_buzzers.py", seconds=30)
    sim.log                                  # list of (t, kind, detail)
"""
import sys, types, time as _realtime, runpy


class StopSim(BaseException):
    pass


class _Status:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeButton:
    def __init__(self, sim, i):
        self.sim, self.i = sim, i
        self.down = False
        self.press_ev = self.release_ev = False
        self.count = 0
        self.color = (0, 0, 0)

    def set_color(self, r, g, b):
        self.color = (r, g, b)
        self.sim.log.append((self.sim.now, "btn%d.color" % self.i, (r, g, b)))

    def led_off(self):
        self.set_color(0, 0, 0)

    def read(self):
        self.sim.poll()
        st = _Status(pressed=self.down, press_event=self.press_ev,
                     release_event=self.release_ev, count=self.count)
        self.press_ev = self.release_ev = False
        return st

    def reset_count(self):
        self.count = 0

    def is_pressed(self):
        return self.down


class FakeKnob:
    def __init__(self, sim):
        self.sim = sim
        self.position = 0
        self.pending = 0
        self.down = False

    def read(self):
        self.sim.poll()
        d, self.pending = self.pending, 0
        return _Status(position=self.position, delta=d, pressed=self.down)

    def reset(self):
        self.position = 0

    def set_position(self, v):
        self.position = v


class FakeBuzzer:
    NOKIA, HAPPY_BIRTHDAY, BEEP_OK, BEEP_ERROR, STARTUP = 1, 2, 3, 4, 5

    def __init__(self, sim):
        self.sim = sim

    def play(self, f, ms, vol=100):
        self.sim.log.append((self.sim.now, "buzz", (f, ms, vol)))

    beep = play

    def note(self, f, ms, vol=100, gap_ms=50):
        self.play(f, ms, vol)
        self.sim.sleep((ms + gap_ms) / 1000)

    def tune(self, i):
        self.sim.log.append((self.sim.now, "tune", i))

    def stop(self):
        self.sim.log.append((self.sim.now, "buzz.stop", None))

    def is_playing(self):
        return False


class FakeDisplay:
    width, height = 160, 80

    def __init__(self, sim):
        self.sim = sim
        self.regions_ = {}
        self.shown = {}          # region -> last text/icon
        self.texts = []          # free text calls
        self.colors = {}         # region -> last colour

    def _l(self, kind, d):
        self.sim.log.append((self.sim.now, kind, d))

    def clear(self, color=0):
        self.shown.clear()
        self._l("disp.clear", color)

    def fill_rect(self, x, y, w, h, color):
        self._l("disp.rect", (x, y, w, h, color))

    def text(self, s, size=16, color=0xFFFFFF, bg="auto", x=0, y=0, **kw):
        self.texts.append(str(s))
        self.shown["@%d,%d" % (x, y)] = str(s)
        self._l("disp.text", (str(s), size, x, y))
        if x + len(str(s).split("\n")[0]) * (size if size % 8 == 0 else size // 2) > self.width + 0:
            raise AssertionError("text %r (size %d) does not fit at x=%d" % (s, size, x))

    def print(self, *a, **kw):
        self._l("disp.print", " ".join(str(x) for x in a))

    def region(self, name, x, y, w, h, size=16, color=0xFFFFFF, bg="auto", align="left"):
        if x + w > self.width or y + h > self.height:
            raise ValueError("region %r is off the panel" % name)
        self.regions_[name] = dict(x=x, y=y, w=w, h=h, size=size)
        return name

    def set(self, name, text=None, icon=None, image=None, size=None, color=None, **kw):
        self.colors[name] = color
        r = self.regions_[name]
        size = size or r["size"]
        if text is not None:
            cell = size if size % 8 == 0 else size // 2
            first = str(text).split("\n")[0]
            if len(first) * cell > r["w"]:
                raise AssertionError("region %r: %r (size %d) wider than %d px" % (name, first, size, r["w"]))
            self.shown[name] = str(text)
        elif icon is not None:
            self.shown[name] = "icon:" + icon
        else:
            self.shown[name] = ""
        self._l("disp.set", (name, self.shown[name]))
        return True

    def icon(self, *a, **kw):
        self._l("disp.icon", a)

    def backlight(self, level):
        self._l("disp.backlight", level)

    def on(self): self._l("disp.on", None)
    def off(self): self._l("disp.off", None)
    def sleep(self): self._l("disp.sleep", None)
    def rotation(self, r): self._l("disp.rotation", r)


class FakeLeds16:
    LED_COUNT = 16

    def __init__(self, sim):
        self.sim = sim
        self.frame = [(0, 0, 0, 0)] * 16

    def _l(self):
        self.sim.log.append((self.sim.now, "leds16", tuple(self.frame)))

    def set_all(self, r, g, b, w=0):
        self.frame = [(r, g, b, w)] * 16; self._l()

    def fill(self, hexc, w=0):
        self.set_all((hexc >> 16) & 255, (hexc >> 8) & 255, hexc & 255, w)

    def white(self, level=255):
        self.set_all(0, 0, 0, level)

    def off(self):
        self.set_all(0, 0, 0, 0)

    def set_pixel(self, i, r, g, b, w=0):
        self.frame = list(self.frame); self.frame[i] = (r, g, b, w); self._l()

    def set_all_pixels(self, px):
        px = [tuple(p) + (0,) * (4 - len(p)) for p in list(px)[:16]]
        px += [(0, 0, 0, 0)] * (16 - len(px))
        self.frame = px; self._l()

    def set_brightness(self, b):
        pass

    def status(self):
        return {"limited": False}

    def temperature(self):
        return 30.0


class FakeSettings:
    def __init__(self):
        self.v, self.infos, self.cb = {}, {}, None

    def defaults(self, d):
        for k, x in d.items():
            self.v.setdefault(k, x)

    def get(self, k, default=None):
        return self.v.get(k, default)

    def set(self, k, x):
        if k in self.infos:
            raise ValueError("info values are read-only")
        self.v[k] = x

    def all(self):
        return dict(self.v)

    def info(self, k, fn):
        self.infos[k] = fn

    def on_change(self, cb):
        self.cb = cb

    def app_sets(self, **kw):               # simulate the app changing values
        self.v.update(kw)
        if self.cb:
            self.cb(dict(kw))


class FakeConductor:
    sim = None

    def __init__(self, *a, **kw):
        s = FakeConductor.sim
        self.buzzer = [s.buzzer] if s.buzzer else []
        self.knob = [s.knob] if s.knob else []
        self.ledbutton = list(s.buttons)
        self.display = [s.display] if s.display else []
        self.leds = []
        self.leds16 = [s.leds16] if s.leds16 else []
        self.settings = s.settings
        self.picohub = None
        self.role = {}
        for name, lst in s.thirdparty.items():
            setattr(self, name, lst)

    def enumerate(self, *a, **k): return 0
    def enumerate_all(self, *a, **k): return 0
    def load_roles(self, *a, **k): return None
    def sleep(self, s): FakeConductor.sim.sleep(s)


class Sim:
    def __init__(self, buttons=0, knob=False, display=False, buzzer=False, leds16=False,
                 thirdparty=None, epoch0=None):
        self.epoch0 = epoch0      # wall clock (UTC epoch) at sim time 0; None = leave time.time alone
        self.now = 0.0
        self.log = []
        self.events = []
        self.buttons = [FakeButton(self, i) for i in range(buttons)]
        self.knob = FakeKnob(self) if knob else None
        self.display = FakeDisplay(self) if display else None
        self.buzzer = FakeBuzzer(self) if buzzer else None
        self.leds16 = FakeLeds16(self) if leds16 else None
        self.settings = FakeSettings()
        self.thirdparty = thirdparty or {}
        self.end = 0

    # -- scenario helpers
    def at(self, t, fn):
        self.events.append((t, fn))
        self.events.sort(key=lambda e: e[0])

    def tap(self, i, hold=0.12, t=None):
        t0 = self.now if t is None else t
        b = self.buttons[i]

        def down():
            b.down = True; b.press_ev = True; b.count = (b.count + 1) & 255

        def up():
            b.down = False; b.release_ev = True
        self.at(t0, down); self.at(t0 + hold, up)

    def press(self, i, t, hold):
        self.tap(i, hold=hold, t=t)

    def turn(self, t, n):
        def f():
            self.knob.position += n; self.knob.pending += n
        self.at(t, f)

    def knob_tap(self, t, hold=0.12):
        def down(): self.knob.down = True
        def up(): self.knob.down = False
        self.at(t, down); self.at(t + hold, up)

    # -- clock
    def poll(self):
        while self.events and self.events[0][0] <= self.now:
            self.events.pop(0)[1]()
        if self.now >= self.end:
            raise StopSim()

    def sleep(self, s):
        self.now += max(0.0, s)
        self.poll()

    def monotonic(self):
        return self.now

    # -- find log entries
    def where(self, kind, since=0, until=1e9):
        return [(t, d) for (t, k, d) in self.log if k == kind and since <= t <= until]

    def run(self, path, seconds=60):
        self.end = seconds
        FakeConductor.sim = self
        fake = types.ModuleType("noknok")
        fake.Conductor = FakeConductor
        tp = types.ModuleType("noknok_thirdparty")
        tp.attach = lambda c, *a, **k: None
        tp.assign = lambda *a, **k: None
        saved = {k: sys.modules.get(k) for k in ("noknok", "noknok_thirdparty")}
        sys.modules["noknok"], sys.modules["noknok_thirdparty"] = fake, tp
        real = (_realtime.monotonic, _realtime.sleep, _realtime.time)
        _realtime.monotonic, _realtime.sleep = self.monotonic, self.sleep
        if self.epoch0 is not None:
            _realtime.time = lambda: self.epoch0 + self.now
        try:
            try:
                runpy.run_path(path, run_name="__main__")
            except StopSim:
                pass
        finally:
            _realtime.monotonic, _realtime.sleep, _realtime.time = real
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        return self
