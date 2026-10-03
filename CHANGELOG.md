# Changelog - poc (product manifests and scripts)

Newest first. One entry per version bump, written in the same commit as the bump. Format:
`## <version> - <date>` then `- DEV-xx - what changed and why. Breaking: yes/no.`
Convention: Confluence "Development Conventions" (SD space, page 120160257).

## 2.5.0 (catalog) - 2026-10-03

- DEV-73 - NEW Smart Lamp Maxi 1.0.0 (`smart-lamp-maxi-v1`, `scripts/smart_lamp_maxi.py`): LEDs 16x + LED Button + Knob + Buzzer + Display. Lamp, clock, kitchen timer (1-120 min) and wake-up light (eased sunrise before the alarm). The knob sets brightness, or colour after a tap; hold it 2 s for the menu. Time zone is a setting, and summer time (EU/US rules) is computed on the brain. Sundown and sunrise are stepped from the Pico with global brightness (the module's SUNDOWN preset drifts in colour at low levels). Every lamp update re-sends the full colour and the state is re-asserted every 10 s, so the occasional corrupted LED frame (DEV-78) heals by itself. Breaking: no.

## Baseline - 2026-10-02

- Changelog starts here. Current: button-light 1.0.1, multicolor-lamp-16x 1.0.0, smart-lamp-mini 1.0.0, smart-lamp 2.0.0, whack-a-mole 1.0.0. Name the product in each entry. Earlier history: git log and the README.
