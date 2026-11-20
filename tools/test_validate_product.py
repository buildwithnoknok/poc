#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 noknok (Christopher Houben)
"""Tests for validate_product.py (DEV-255): one good submission folder passes, and one
broken copy per check fails with its own message. Standard library only.

Run from the poc repo root:  python tools/test_validate_product.py
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate_product as vp  # noqa: E402

ROOT = os.path.join(HERE, "..")
GOOD_IMAGE = os.path.join(ROOT, "images", "whack-a-mole-v1.webp")

GOOD_MANIFEST = {
    "id": "test-light-v1", "name": "Test Light", "version": "1.0.0", "author": "ada",
    "setup_pattern": "Setup 1 (I2C only)",
    "description": "A test product.", "source": "community",
    "maker": {"name": "Ada", "url": "https://ada.example"},
    "image": "https://raw.githubusercontent.com/buildwithnoknok/poc/main/images/test-light-v1.webp",
    "modules_required": [{"type": "led_button", "count": 1}],
    "module_firmware": {"led_button": {"min": "2.1.0"}},
    "files": [{"dest": "product.py", "url": "https://raw.githubusercontent.com/buildwithnoknok/"
               "poc/main/scripts/test_light.py", "version": "1.0.0", "required": True}],
}
GOOD_SCRIPT = ("# SPDX-License-Identifier: MIT\n"
               "import time\nfrom noknok import Conductor\n\n"
               "c = Conductor()\nc.enumerate()\nwhile True:\n    time.sleep(0.1)\n")


def image_bytes():
    with open(GOOD_IMAGE, "rb") as f:
        return f.read()


GOOD_README = "Test Light. Script: MIT. Manifest and picture: CC BY-SA 4.0.\n"


class ValidatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = vp.load_schema(os.environ.get("NOKNOK_SCHEMA"))

    def folder(self, manifest=None, script=GOOD_SCRIPT, readme=GOOD_README,
               image=GOOD_IMAGE, extra=None):
        d = tempfile.mkdtemp(prefix="dev255_")
        self.addCleanup(shutil.rmtree, d)
        m = GOOD_MANIFEST if manifest is None else manifest
        with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
            f.write(m if isinstance(m, str) else json.dumps(m))
        if script is not None:
            with open(os.path.join(d, "product.py"), "w", encoding="utf-8") as f:
                f.write(script)
        if readme is not None:
            with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
                f.write(readme)
        if isinstance(image, bytes):
            with open(os.path.join(d, "image.webp"), "wb") as f:
                f.write(image)
        elif image:
            shutil.copy(image, os.path.join(d, "image.webp"))
        for name, text in (extra or {}).items():
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(text)
        return vp.validate_folder(d, self.schema)

    def assertFails(self, rep, check, words):
        hits = [m for c, m in rep.errors if c == check]
        self.assertTrue(hits, "expected an error in [%s], got %r" % (check, rep.errors))
        self.assertTrue(any(words.lower() in m.lower() for m in hits),
                        "message %r does not mention %r" % (hits, words))

    def with_(self, **kw):
        m = json.loads(json.dumps(GOOD_MANIFEST))
        m.update(kw)
        return m

    # --- the good folder -------------------------------------------------------------------
    def test_good_folder_passes(self):
        rep = self.folder()
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.name, "test-light-v1")

    def test_no_image_is_fine(self):
        m = self.with_()
        del m["image"]
        self.assertEqual(self.folder(manifest=m, image=None).errors, [])

    # --- one broken fixture per check ------------------------------------------------------
    def test_manifest_not_json(self):
        self.assertFails(self.folder(manifest="{oops"), "manifest", "not valid JSON")

    def test_manifest_schema_missing_field(self):
        m = self.with_()
        del m["name"]
        self.assertFails(self.folder(manifest=m), "manifest", "missing 'name'")

    def test_unknown_module_type(self):
        m = self.with_(modules_required=[{"type": "laser", "count": 1}])
        self.assertFails(self.folder(manifest=m), "manifest", "laser")

    def test_firmware_for_module_not_required(self):
        m = self.with_(module_firmware={"led_button": {"min": "2.1.0"}, "knob": {"min": "2.0.0"}})
        self.assertFails(self.folder(manifest=m), "modules", "knob")

    # --- DEV-268: brain capabilities ------------------------------------------------------
    USB = [{"type": "usb_leds_16x", "count": 1}]
    USB_FW = {"usb_leds_16x": {"min": "2.2.1"}}

    def test_old_manifest_with_brain_type_still_passes_with_a_warning(self):
        rep = self.folder(manifest=self.with_(brain_type="pico_w"))
        self.assertEqual(rep.errors, [])
        self.assertTrue(any(c == "requires" and "brain_type" in m for c, m in rep.warnings))

    def test_usb_product_without_requires_is_derived(self):
        m = self.with_(modules_required=self.USB, module_firmware=self.USB_FW)
        self.assertEqual(self.folder(manifest=m).errors, [])
        self.assertEqual(vp.effective_requires(m), {"usb_host"})
        self.assertEqual(vp.effective_requires(self.with_()), set())

    def test_usb_product_with_requires_usb_host_passes(self):
        m = self.with_(modules_required=self.USB, module_firmware=self.USB_FW,
                       requires=["usb_host"])
        self.assertEqual(self.folder(manifest=m).errors, [])

    def test_requires_that_hides_usb_host_fails(self):
        m = self.with_(modules_required=self.USB, module_firmware=self.USB_FW, requires=["i2c_b"])
        self.assertFails(self.folder(manifest=m), "requires", "usb_host")

    def test_requires_unknown_capability_fails(self):
        self.assertFails(self.folder(manifest=self.with_(requires=["laser"])), "manifest", "laser")

    def test_requires_twice_fails(self):
        m = self.with_(requires=["i2c_b", "i2c_b"])
        self.assertFails(self.folder(manifest=m), "requires", "twice")

    def test_script_missing(self):
        self.assertFails(self.folder(script=None), "script", "missing")

    def test_script_too_big(self):
        big = GOOD_SCRIPT + "x = 1\n" * 9000
        self.assertFails(self.folder(script=big), "size", "compact_product")

    def test_spdx_header_missing_community(self):
        self.assertFails(self.folder(script=GOOD_SCRIPT.split("\n", 1)[1]), "header", "SPDX")

    def test_syntax_error(self):
        self.assertFails(self.folder(script=GOOD_SCRIPT + "if True\n"), "syntax", "line")

    def test_file_write(self):
        s = GOOD_SCRIPT + "open('log.txt', 'a').write('x')\n"
        self.assertFails(self.folder(script=s), "safety", "writes a file")

    def test_settings_toml(self):
        s = GOOD_SCRIPT + "data = open('/settings.toml').read()\n"
        self.assertFails(self.folder(script=s), "safety", "settings.toml")

    def test_os_getenv(self):
        s = GOOD_SCRIPT + "import os\npw = os.getenv('CIRCUITPY_WIFI_PASSWORD')\n"
        self.assertFails(self.folder(script=s), "safety", "os.getenv")

    def test_network_module(self):
        s = GOOD_SCRIPT + "import socketpool\n"
        self.assertFails(self.folder(script=s), "safety", "network")

    def test_microcontroller(self):
        s = GOOD_SCRIPT + "import microcontroller\nmicrocontroller.nvm[0] = 0\n"
        self.assertFails(self.folder(script=s), "safety", "crash counter")

    def test_secret_in_code(self):
        s = GOOD_SCRIPT + "API_KEY = 'sk-12345678'\n"
        self.assertFails(self.folder(script=s), "safety", "password or key")

    def test_image_wrong_size(self):
        img = image_bytes()
        # VP8X canvas 320 x 320 instead of 640 x 640.
        bad = img[:24] + (319).to_bytes(3, "little") + (319).to_bytes(3, "little") + img[30:]
        self.assertFails(self.folder(image=bad), "image", "640 x 640")

    def test_image_too_big(self):
        img = image_bytes() + b"\0" * (61 * 1024)
        self.assertFails(self.folder(image=img), "image", "KB")

    def test_image_not_webp(self):
        self.assertFails(self.folder(image=b"\x89PNG\r\n\x1a\n" + b"\0" * 40), "image", "not a WebP")

    def test_licence_note_missing(self):
        self.assertFails(self.folder(readme="My light.\n"), "licence", "CC BY-SA")

    # --- warnings, not errors ---------------------------------------------------------------
    def test_wifi_import_is_a_warning(self):
        rep = self.folder(script=GOOD_SCRIPT + "import wifi\n")
        self.assertEqual(rep.errors, [])
        self.assertTrue(any("wifi" in m for _, m in rep.warnings))

    # --- the real catalog -------------------------------------------------------------------
    def test_existing_products_pass(self):
        with open(os.path.join(ROOT, "manifests", "catalog.json"), encoding="utf-8") as f:
            entries = json.load(f)["products"]
        seen = set()
        for e in entries:
            rep = vp.validate_repo_product(ROOT, e, self.schema, seen)
            self.assertEqual(rep.errors, [], "%s: %r" % (e["id"], rep.errors))


if __name__ == "__main__":
    unittest.main(verbosity=1)
