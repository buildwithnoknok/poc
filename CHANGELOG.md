# Changelog - poc (product manifests and scripts)

Newest first. One entry per version bump, written in the same commit as the bump. Format:
`## <version> - <date>` then `- DEV-xx - what changed and why. Breaking: yes/no.`
Convention: Confluence "Development Conventions" (SD space, page 120160257).

## Products + tooling - 2026-11-25 (DEV-278, DEV-281)

- DEV-278 - 13 new products on main (not yet in `catalog.json`, so not published): Quiz Buzzers, Reaction Duel, Focus Timer, Puzzle Box, Breathing Guide, Plant Climate Monitor, Desk Guard, Metronome, Dice Roller, Stopwatch, Morse Tapper, Spirit Level, Light Meter (manifest + script each, v1.0.0). Each script read by Sue before merge; validator 0 errors. They enter the catalog only with the catalog PR after the bench PASS per product (Bob). Breaking: no.
- DEV-281 - `tools/sim/`: the PC product simulator (fake brain + fake clock + scenario tests, 23 groups) moved here from the exploration repo; new products get a logic test before the bench. Breaking: no.
- DEV-281 - `tools/validate_product.py`: third-party boards no longer get "no firmware minimum" warnings (the authoring guide says to leave them out; naming one in `module_firmware` is now a warning); importing `noknok_feeds` is a review warning and an ERROR unless the manifest says `"needs": ["internet"]` (needs the schema field from Ecosystem PR "needs[internet]"). Breaking: no.

## Scripts - 2026-11-23 (DEV-258)

- DEV-258 - `scripts/button_light.py`: SPDX licence header (MIT) and its own description; the header still described it as the brain-Pico bench product it started from. Found by the validator on the first maker-upload test. Comment-only change, no behaviour change. Breaking: no.

## Manifests + tooling - 2026-11-20 (DEV-268)

- DEV-268 - manifests no longer carry `brain_type` (deprecated in the Ecosystem schema: it named a board, not a need). The five products with a USB LEDs module (Smart Lamp, Smart Lamp Mini, Smart Lamp Maxi, Smart Alarm Maxi, Multicolor Lamp 16x) now say `"requires": ["usb_host"]`; Button Light and Whack-a-Mole need nothing beyond I2C. `tools/validate_product.py`: `requires` must not leave out `usb_host` when a `usb_*` module is required (error), a capability twice is an error, a leftover `brain_type` is a warning; `derived_requires()` / `effective_requires()` give the rule the app uses too. Tests +6 (28). Product versions unchanged (nothing a customer sees changes; the app never read `brain_type`). Breaking: no.

## Tooling - 2026-11-18 (DEV-259)

- DEV-259 - `tools/dev_install.py`: a maker puts a product that is not published yet onto their OWN brain (already set up with the app, on home WiFi): `python tools/dev_install.py --manifest <file or raw URL> --brain <ip or noknok-XXXX.local>`. Runs the validator first (no install with ERRORs), then sends the same product switch the app sends (`provision` op on the home network: the brain downloads product.py from the manifest URL, compile-checks it, keeps the old product if that fails). Standard library only. Breaking: no.

## Tooling - 2026-11-18 (DEV-255)

- DEV-255 - `tools/validate_product.py`: one check for every product before it is published (ADR-010), Python standard library only, offline. Modes: `<id>` / `--all` (this repo, via catalog.json) and `--folder <dir>` (upload folder: manifest.json, product.py, image.webp, README.md); `--json` for the upload page (DEV-258). Checks: manifest against the Ecosystem schema, catalog id unique and matching, firmware minimums only for required modules; script parses, size (warning > 30 KB, error > 45 KB), SPDX header (error for community, warning for ours), no network modules / file writes / storage / microcontroller / settings.toml / os.getenv / secrets (wifi and noknok_rpc imports and web addresses = warnings); image WebP 640x640 <= 60 KB; licence note in a folder README. GitHub Action `.github/workflows/validate-products.yml` runs the self-test and `--all` on every pull request and push to main. Tests: `tools/test_validate_product.py` (22). All 7 products pass (warnings: 4 scripts without SPDX header, Smart Lamp Maxi 36 KB, Smart Alarm Maxi imports wifi/noknok_rpc). Breaking: no.

## Repo docs - 2026-11-18 (DEV-256)

- DEV-256 - contributing notes for makers in README.md (flat layout, unique id, `source: community`, optional `maker` credit, licence, merge = published), pull-request template and CODEOWNERS (`@TunalunaORG`). Pictures licence line added. No product or catalog change. Breaking: no.

## catalog 2.7.0 - 2026-11-18

- DEV-240 - product pictures: new optional manifest field `image` (raw URL of `images/<product-id>.webp`, 640x640 transparent WebP, max 60 KB, CC BY-SA 4.0; spec in Ecosystem `software/product-manifest.md`). Set for Multicolor Lamp 16x, Smart Lamp Maxi, Smart Alarm Maxi and Whack-a-Mole; Button Light, Smart Lamp Mini and Smart Lamp (Midi) have no photo yet and show the app's placeholder. Product versions unchanged (no script or settings change). Breaking: no.

## smart-alarm-maxi 1.0.2 - 2026-11-15

- DEV-236 - new menu page "Info": turn the knob to page through WiFi up/down, IP address, free memory now, the lowest free memory seen since start, and the WiFi drop / rejoin counters. Read on the lamp itself, so it also works when the app cannot reach the lamp (added to find why the brain left the WiFi while 1.0.1 ran). Breaking: no.

## smart-alarm-maxi 1.0.1 - 2026-11-15

- DEV-236 - 1.0.0 stopped on the brain with MemoryError (three crashes, then parked): the brain keeps the whole product source text in RAM, and the 45 KB script did not fit next to everything else. The brain now gets a compact copy without comments (26 KB): `scripts/smart_alarm_maxi.py` is GENERATED by the new `tools/compact_product.py` from the readable source in `scripts/src/smart_alarm_maxi.py`. Edit the source, then regenerate. Same behaviour as 1.0.0. Breaking: no.

## smart-alarm-maxi 1.0.0 / 2.6.0 (catalog) - 2026-11-15

- DEV-236 - NEW Smart Alarm Maxi (`smart-alarm-maxi-v1`, `scripts/smart_alarm_maxi.py`), same modules as the Smart Lamp Maxi (which stays unchanged at 1.1.1). Two alarms (`alarm1_time`, `alarm2_time`) armed with one setting `alarm_armed` = off / 1 / 2 / both; the wake-up light ramps towards the next armed alarm. LED Button on the home screen: press = arm Alarm 1 -> Alarm 2 -> both -> off (1/2/3 beeps, low beep = off), double press = Sundown, hold 1 s = lamp on/off. In the menu the LED Button goes one step back, the knob tap is OK. Six alarm tones (`alarm_tone`): Classic, Gentle chime, Mozart (Eine kleine Nachtmusik), Chiptune, Birds, Sunrise scale, previewed while choosing in the menu. Display direction setting (`rotation` 0/90/180/270) with its own portrait layout, changeable in the app and in the menu. Everything is drawn inside a 150x70 (portrait 70x150) safe area because the panel has rounded corners. Menu "Reset" keeps the time zone and the display direction. Breaking: no (new product).

## smart-lamp-maxi 1.1.1 - 2026-10-23

- DEV-151 - switching the lamp on and off several times very quickly could leave it in the wrong colour for up to 10 seconds. The lamp now sends its state once more half a second after the last press, so it shows the right colour (or stays off) right away. Breaking: no.

## smart-lamp-maxi 1.1.0 - 2026-10-04

- DEV-73 - Smart Lamp Maxi 1.1.0 (Christopher's bench feedback): the button LED stays dark and only shows a new colour for 3 s after a change (knob or app). After a Sundown ends, the display backlight drops to its dimmest real level (raw 3; raw 1-2 are brighter on this panel) until the lamp is switched on again or an alarm/timer rings. Breaking: no.

## 2.5.0 (catalog) - 2026-10-03

- DEV-73 - NEW Smart Lamp Maxi 1.0.0 (`smart-lamp-maxi-v1`, `scripts/smart_lamp_maxi.py`): LEDs 16x + LED Button + Knob + Buzzer + Display. Lamp, clock, kitchen timer (1-120 min) and wake-up light (eased sunrise before the alarm). The knob sets brightness, or colour after a tap; hold it 2 s for the menu. Time zone is a setting, and summer time (EU/US rules) is computed on the brain. Sundown and sunrise are stepped from the Pico with global brightness (the module's SUNDOWN preset drifts in colour at low levels). Every lamp update re-sends the full colour and the state is re-asserted every 10 s, so the occasional corrupted LED frame (DEV-78) heals by itself. Breaking: no.

## Baseline - 2026-10-02

- Changelog starts here. Current: button-light 1.0.1, multicolor-lamp-16x 1.0.0, smart-lamp-mini 1.0.0, smart-lamp 2.0.0, whack-a-mole 1.0.0. Name the product in each entry. Earlier history: git log and the README.

## multicolor-lamp-16x 1.0.0 / 2.4.0 (catalog) - 2026-10-02 (backfilled for DEV-46)

- DEV-46 - NEW Multicolor Lamp 16x (`multicolor-lamp-16x-v1`), the first product for the LEDs 16x (manifest type `usb_leds_16x`, needs one, app-controlled). Settings: on, brightness, Light = White / Colour / Colour + white, colour, white amount. Two read-only `info` rows: Temperature (°C) and Light (Normal / Dimmed - warm / Dimmed - weak USB power / Off - too hot / Off - USB power too weak / Off), sharing one GET_STATUS per app poll (0.5 s cache). Drives every connected 16x. `min 2.2.0` in the manifest cannot be enforced yet (`usb_leds_16x` is not in the module registry). Needs brain `noknok.py` 1.11 and `noknok_usb.py` 1.1. Breaking: no.
