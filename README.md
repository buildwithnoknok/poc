# noknok PoC — Public Data Files

This repository hosts the **public data files** consumed by the noknok PoC app at
runtime. It is intentionally separate from the app source code (which stays private):
the app downloads these files over HTTPS, so they must be publicly readable.

> Note: this repo is currently named `poc-1` while it is being prepared. It will be
> renamed to **`poc`** and made public. All URLs below already use `.../poc/main/...`
> so they resolve correctly once the rename + visibility flip happen — no app change
> is required.

## What's in here

```
manifests/
  catalog.json                  # index of all PoC products (the app fetches this first)
  light-sound-controller.json   # per-product manifests, referenced by catalog.json
  chime-box.json
  two-button-box.json
  desk-lamp.json
  desk-lamp-dimmer.json
scripts/
  trio_demo.py                  # product.py scripts the Pico downloads + runs
  chime_box.py
  two_button_box.py
  desk_lamp.py
  desk_lamp_dimmer.py
```

## How the app uses it

1. The app fetches the catalog index:
   `https://raw.githubusercontent.com/buildwithnoknok/poc/main/manifests/catalog.json`
2. `catalog.json` lists each product with the URL of its manifest (also in `manifests/`).
3. Each manifest's `files[]` entry with `dest: "product.py"` gives a `url` pointing at the
   matching script in `scripts/`. The app passes that `script_url` to the Pico during setup;
   the Pico downloads and runs it.

Adding a product = publishing a new manifest (+ script) and adding it to `catalog.json`.
No app code changes.

## License

- **Product scripts (`scripts/*.py`)** — [MIT](LICENSE)
- **Catalog & manifests (`manifests/*.json`)** — [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
