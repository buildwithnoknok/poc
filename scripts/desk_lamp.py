# desk_lamp.py — noknok Desk Lamp (Setup 2, USB-C only)
#
# Drives the USB LEDs module to a solid colour at a set brightness.
#
# TODO (Sue): read the customer's colour/brightness picks (manifest config_schema
# "color" / "brightness") from the app — provisioning doesn't plumb config values
# through to product.py yet, only WiFi + script_url + module_firmware. Until that
# exists, this uses a fixed default so the product actually lights up.

from noknok import Conductor

# code.py doesn't capture product.py's own output in log.txt (it exec()s this
# file separately), so log our own outcome there directly - otherwise a
# failure here is invisible to anyone reading log.txt after the fact.
def _log(msg):
    try:
        with open("log.txt", "a") as f:
            f.write("[desk_lamp] " + str(msg) + "\n")
    except Exception:
        pass

try:
    c = Conductor()
    n = c.enumerate_usb()
    _log("enumerate_usb() found %d module(s)" % n)

    if not c.leds:
        _log("FAILED: no USB LEDs module in c.leds after enumeration")
        raise SystemExit("No USB LEDs module found — check wiring.")

    lamp = c.leds[0]
    _log("driving lamp uid=%s fw=%s" % (lamp._uid_hex, lamp.firmware_version))

    lamp.set_brightness(180)
    lamp.set_all(255, 200, 120)   # warm white
    _log("lamp on (warm white, brightness 180)")
except Exception as e:
    _log("EXCEPTION: %s" % e)
    raise

while True:
    pass
