<!--
SPDX-FileCopyrightText: 2026 noknok (Christopher Houben)
SPDX-License-Identifier: CC-BY-SA-4.0
-->

# tools/sim: run noknok products on the PC

`fakebrain.py` fakes the brain (Conductor, LED Button, Knob, Buzzer, Display, LEDs 16x, c.settings,
and the third-party boards) with a fake clock, so a `product.py` runs in seconds on the PC.
`test_products.py` drives 17 products (the 13 of DEV-278 and the 3 data products of DEV-281, plus the
Quiz/Duel games) with scripted presses and sensor values: 23 scenario groups.

```
python tools/sim/test_products.py                      # the products in this repo
NK_BRAIN=<path to a brain-Pico clone> python tools/sim/test_products.py   # also the data products
```

The data products import `noknok_feeds`; the test serves RECORDED real API answers
(`brain-Pico/tools/fixtures/feeds/`) instead of the internet, and skips those three tests when the
scripts or `noknok_feeds.py` are not there yet.

It checks LOGIC (state machine, timing on the fake clock, what is shown / played / lit, that text
fits its region by character count). It does NOT check I2C, real timing, or how the display looks.
Bench-test on a real brain before publishing.

**New product?** Copy a `test_*` function, script the presses, check what the product shows.
Every new product should get a logic test here before the bench.
