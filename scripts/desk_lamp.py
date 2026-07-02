# desk_lamp.py — noknok Desk Lamp (Setup 2, USB-C only)
#
# Drives the USB LEDs module to a solid colour at a set brightness.
#
# TODO (Sue): read the customer's colour/brightness picks (manifest config_schema
# "color" / "brightness") from the app — provisioning doesn't plumb config values
# through to product.py yet, only WiFi + script_url + module_firmware. Until that
# exists, this uses a fixed default so the product actually lights up.

from noknok import Conductor

c = Conductor()
c.enumerate_usb()

if not c.leds:
    raise SystemExit("No USB LEDs module found — check wiring.")

lamp = c.leds[0]
lamp.set_brightness(180)
lamp.set_all(255, 200, 120)   # warm white

while True:
    pass
