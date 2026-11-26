#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright 2026 noknok (Christopher Houben)
"""validate_product.py - check a noknok product before it is published (DEV-255, ADR-010).

Every product, ours or a maker's, passes the same automatic checks before a person reads
the script. Standard library only, runs offline, so a maker (or their AI agent) can run it
on their own computer before opening a pull request.

Usage (from the poc repo root):
  python tools/validate_product.py --all                  every product in catalog.json
  python tools/validate_product.py my-desk-clock-v1       one product (by id) in this repo
  python tools/validate_product.py --folder path/to/dir   a submission folder (upload page):
        manifest.json, product.py (+ other .py libs), image.webp (optional), README.md
  Options: --schema PATH (product-manifest.schema.json; default: ../Ecosystem/software/,
           then a cached download), --json (machine-readable report, used by DEV-258).

Exit code 0 = no errors (warnings are for the human reviewer), 1 = errors, 2 = cannot run.

Checks
  manifest   JSON, the open schema (Ecosystem software/product-manifest.schema.json),
             unique id in catalog.json, firmware minimums only for required modules
  script     parses as Python; size (warning > 30 KB, error > 45 KB, RDM-21; shrink it with
             tools/compact_product.py); SPDX header (error for community products)
  safety     no network modules, no file writes, no storage/microcontroller (Store and crash
             strikes live there, ADR-003), no settings.toml / os.getenv (WiFi password),
             no hard-coded secrets. wifi / noknok_rpc imports and web addresses = warnings.
  image      optional; if given: WebP, 640 x 640 px, at most 60 KB
  licence    submission folder: README.md must say the script is MIT and the manifest and
             picture CC BY-SA 4.0 (in the repo the PR template + LICENSE cover it)
"""

import argparse
import ast
import json
import os
import re
import sys
import urllib.request

SCHEMA_URL = ("https://raw.githubusercontent.com/buildwithnoknok/Ecosystem/main/"
              "software/product-manifest.schema.json")
RAW_MAIN = "https://raw.githubusercontent.com/buildwithnoknok/poc/main/"

SCRIPT_WARN_BYTES = 30 * 1024
SCRIPT_MAX_BYTES = 45 * 1024
IMAGE_MAX_BYTES = 60 * 1024
IMAGE_SIZE = (640, 640)

FORBIDDEN_MODULES = {
    "socketpool": "network access", "socket": "network access", "ssl": "network access",
    "adafruit_requests": "network access", "adafruit_httpserver": "network access",
    "storage": "changing the drive", "microcontroller": "the brain's crash counter and Store",
}
REVIEW_MODULES = {"wifi": "WiFi access", "noknok_rpc": "the app channel",
                  "noknok_feeds": "public data from the internet via the brain library (DEV-281)"}
FORBIDDEN_OS_CALLS = {"remove", "unlink", "rename", "mkdir", "rmdir", "chdir", "getenv", "putenv"}
SECRET_RE = re.compile(r"(password|passwd|api[_-]?key|secret|token)\s*[=:]\s*['\"][^'\"]{4,}",
                       re.I)
URL_RE = re.compile(r"https?://", re.I)
FEEDS_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+noknok_feeds\b", re.M)


class Report:
    def __init__(self, name):
        self.name, self.errors, self.warnings = name, [], []

    def error(self, check, msg):
        self.errors.append((check, msg))

    def warn(self, check, msg):
        self.warnings.append((check, msg))

    def as_dict(self):
        return {"product": self.name, "ok": not self.errors,
                "errors": [{"check": c, "message": m} for c, m in self.errors],
                "warnings": [{"check": c, "message": m} for c, m in self.warnings]}

    def print(self):
        print("%s %s" % ("PASS" if not self.errors else "FAIL", self.name))
        for c, m in self.errors:
            print("  ERROR   [%s] %s" % (c, m))
        for c, m in self.warnings:
            print("  WARNING [%s] %s" % (c, m))


# --- a small JSON-schema checker (the keywords the manifest schema uses) ------------------

def _type_ok(v, t):
    if isinstance(t, list):
        return any(_type_ok(v, x) for x in t)
    return {"object": isinstance(v, dict), "array": isinstance(v, list),
            "string": isinstance(v, str), "boolean": isinstance(v, bool),
            "integer": isinstance(v, int) and not isinstance(v, bool),
            "number": isinstance(v, (int, float)) and not isinstance(v, bool),
            "null": v is None}.get(t, True)


def schema_errors(value, schema, root, path="manifest"):
    """List of plain-language problems; empty = valid."""
    out = []
    if "$ref" in schema:
        ref = schema["$ref"]
        node = root
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        return schema_errors(value, node, root, path)
    if "type" in schema and not _type_ok(value, schema["type"]):
        return ["%s must be a %s" % (path, schema["type"])]
    if "const" in schema and value != schema["const"]:
        out.append("%s must be %r" % (path, schema["const"]))
    if "enum" in schema and value not in schema["enum"]:
        out.append("%s is %r, allowed: %s" % (path, value, ", ".join(map(str, schema["enum"]))))
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append("%s %r does not have the required form" % (path, value))
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append("%s is too short" % path)
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append("%s is too long (max %d)" % (path, schema["maxLength"]))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            out.append("%s must be at least %s" % (path, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            out.append("%s must be at most %s" % (path, schema["maximum"]))
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                out.append("%s is missing %r" % (path, k))
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                out += schema_errors(v, props[k], root, "%s.%s" % (path, k))
            elif schema.get("additionalProperties") is False:
                out.append("%s has an unknown field %r" % (path, k))
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            out += schema_errors(v, schema["items"], root, "%s[%d]" % (path, i))
    for sub in schema.get("allOf", []):
        out += schema_errors(value, sub, root, path)
    if "if" in schema:
        branch = "then" if not schema_errors(value, schema["if"], root, path) else "else"
        if branch in schema:
            out += schema_errors(value, schema[branch], root, path)
    if "not" in schema and not schema_errors(value, schema["not"], root, path):
        out.append("%s has a combination that is not allowed" % path)
    return out


def load_schema(path=None):
    candidates = [path] if path else [
        os.environ.get("NOKNOK_SCHEMA"),
        os.path.join(os.path.dirname(__file__), "..", "..", "Ecosystem", "software",
                     "product-manifest.schema.json"),
        os.path.join(os.path.dirname(__file__), "..", "_ecosystem", "software",
                     "product-manifest.schema.json"),
        os.path.join(os.path.expanduser("~"), ".cache", "noknok", "product-manifest.schema.json"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            with open(c, encoding="utf-8") as f:
                return json.load(f)
    if path:
        raise SystemExit("schema not found: %s" % path)
    # First run on a maker's machine: download once and keep a copy.
    cache = candidates[-1]
    try:
        with urllib.request.urlopen(SCHEMA_URL, timeout=15) as r:
            data = r.read()
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "wb") as f:
            f.write(data)
        return json.loads(data)
    except Exception as e:
        raise SystemExit("could not find or download the manifest schema (%s). "
                         "Pass --schema path/to/product-manifest.schema.json" % e)


# --- checks ---------------------------------------------------------------------------------

def check_manifest(m, schema, rep):
    for msg in schema_errors(m, schema, schema):
        rep.error("manifest", msg)
    if not isinstance(m, dict):
        return
    required = {r.get("type") for r in m.get("modules_required", []) if isinstance(r, dict)}
    fw = m.get("module_firmware") if isinstance(m.get("module_firmware"), dict) else {}
    for t in fw:
        if t not in required:
            rep.error("modules", "module_firmware names %r, which is not in modules_required" % t)
    # Third-party boards (modules_required[].thirdparty = true, DEV-251) have no firmware: the
    # authoring guide says to leave them out of module_firmware (F3, DEV-281).
    third = {r.get("type") for r in m.get("modules_required", [])
             if isinstance(r, dict) and r.get("thirdparty") is True}
    for t in sorted(x for x in required if x and x not in fw and x not in third):
        rep.warn("modules", "no firmware minimum for %r (add module_firmware.%s.min)" % (t, t))
    for t in sorted(x for x in fw if x in third):
        rep.warn("modules", "module_firmware names %r, a third-party board: it has no firmware "
                            "minimum, leave it out" % t)
    # DEV-268: brain capabilities. `requires` may be left out (derived from the modules);
    # if it is written, it must not hide a USB module's need for a USB host port.
    req = m.get("requires")
    if isinstance(req, list):
        if len(set(map(str, req))) != len(req):
            rep.error("requires", "requires lists a capability twice")
        need = derived_requires(m)
        for cap in sorted(need - set(req)):
            rep.error("requires", "requires leaves out %r, but modules_required has a USB module "
                                  "(write it, or leave `requires` out)" % cap)
    if "brain_type" in m:
        rep.warn("requires", "brain_type is deprecated and ignored (DEV-268): remove it; "
                             "use `requires` only for needs beyond I2C")


USB_HOST_TYPES_PREFIX = "usb_"     # module types that sit on the USB host port (DEV-268)


def derived_requires(m):
    """Capabilities a manifest needs because of its modules: {'usb_host'} when it requires
    a usb_* module (noknok LEDs, LEDs 16x, the old hubs), else empty."""
    out = set()
    for r in m.get("modules_required", []) or []:
        if isinstance(r, dict) and str(r.get("type", "")).startswith(USB_HOST_TYPES_PREFIX):
            out.add("usb_host")
    return out


def effective_requires(m):
    """What the app / brain should check: the written `requires`, else the derived set."""
    req = m.get("requires")
    return set(req) if isinstance(req, list) else derived_requires(m)


def _docstring_nodes(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    getattr(body[0], "value", None), ast.Constant) and isinstance(
                    body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def check_script(name, text, community, rep):
    size = len(text.encode("utf-8"))
    if size > SCRIPT_MAX_BYTES:
        rep.error("size", "%s is %.1f KB, more than %d KB: the brain runs out of memory. Make "
                  "a compact copy with tools/compact_product.py" % (name, size / 1024,
                                                                   SCRIPT_MAX_BYTES // 1024))
    elif size > SCRIPT_WARN_BYTES:
        rep.warn("size", "%s is %.1f KB (over %d KB): consider tools/compact_product.py"
                 % (name, size / 1024, SCRIPT_WARN_BYTES // 1024))
    head = "\n".join(text.splitlines()[:3])
    if "SPDX-License-Identifier: MIT" not in head:
        msg = "%s needs '# SPDX-License-Identifier: MIT' in its first lines" % name
        (rep.error if community else rep.warn)("header", msg)
    try:
        tree = ast.parse(text, filename=name)
    except SyntaxError as e:
        rep.error("syntax", "%s line %s: %s" % (name, e.lineno, e.msg))
        return
    docs = _docstring_nodes(tree)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for mod in mods:
                top = mod.split(".")[0]
                if top in FORBIDDEN_MODULES:
                    rep.error("safety", "%s line %s imports %s (%s is not allowed in a product)"
                              % (name, line, top, FORBIDDEN_MODULES[top]))
                elif top in REVIEW_MODULES:
                    rep.warn("safety", "%s line %s imports %s (%s: the reviewer checks how it "
                             "is used)" % (name, line, top, REVIEW_MODULES[top]))
                elif top == "os" and isinstance(node, ast.ImportFrom):
                    for a in node.names:
                        if a.name in FORBIDDEN_OS_CALLS:
                            rep.error("safety", "%s line %s imports os.%s (no file changes or "
                                      "settings reads in a product)" % (name, line, a.name))
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id == "open":
                mode = None
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    mode = node.args[1].value
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = kw.value.value
                if mode is None and (len(node.args) > 1 or any(k.arg == "mode" for k in node.keywords)):
                    rep.error("safety", "%s line %s opens a file with a computed mode" % (name, line))
                elif isinstance(mode, str) and set(mode) & set("wax+"):
                    rep.error("safety", "%s line %s writes a file (open mode %r). Products must "
                              "not write files at run time (power loss corrupts the drive, "
                              "ADR-003); use c.settings" % (name, line, mode))
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                    and f.value.id == "os" and f.attr in FORBIDDEN_OS_CALLS:
                rep.error("safety", "%s line %s calls os.%s (no file changes or settings reads "
                          "in a product)" % (name, line, f.attr))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            if "settings.toml" in s:
                rep.error("safety", "%s line %s mentions settings.toml (it holds the WiFi "
                          "password; products must not read it)" % (name, line))
            if id(node) not in docs and URL_RE.search(s):
                rep.warn("safety", "%s line %s contains a web address: products must not use "
                         "the network" % (name, line))
    for i, l in enumerate(text.splitlines(), 1):
        if SECRET_RE.search(l):
            rep.error("safety", "%s line %d looks like a password or key in the code. Never put "
                      "secrets in a product (it is readable on the device)" % (name, i))


def webp_size(b):
    """(width, height) of a WebP, or None."""
    if len(b) < 30 or b[:4] != b"RIFF" or b[8:12] != b"WEBP":
        return None
    kind = b[12:16]
    if kind == b"VP8X":
        return (1 + int.from_bytes(b[24:27], "little"), 1 + int.from_bytes(b[27:30], "little"))
    if kind == b"VP8 " and b[23:26] == b"\x9d\x01\x2a":
        return (int.from_bytes(b[26:28], "little") & 0x3FFF,
                int.from_bytes(b[28:30], "little") & 0x3FFF)
    if kind == b"VP8L" and b[20] == 0x2F:
        bits = int.from_bytes(b[21:25], "little")
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    return None


def check_image(name, data, rep):
    if data is None:
        rep.error("image", "%s is named in the manifest but the file is missing" % name)
        return
    if len(data) > IMAGE_MAX_BYTES:
        rep.error("image", "%s is %.1f KB, more than %d KB" % (name, len(data) / 1024,
                                                             IMAGE_MAX_BYTES // 1024))
    size = webp_size(data)
    if size is None:
        rep.error("image", "%s is not a WebP picture" % name)
    elif size != IMAGE_SIZE:
        rep.error("image", "%s is %d x %d px, it must be 640 x 640" % ((name,) + size))


def check_licence(readme, rep):
    if readme is None:
        rep.error("licence", "README.md is missing (say what the product does and its licence)")
        return
    t = readme.lower()
    if "mit" not in t or ("cc by-sa" not in t and "cc-by-sa" not in t):
        rep.error("licence", "README.md must say the script is MIT and the manifest and picture "
                  "are CC BY-SA 4.0")


# --- product sources ------------------------------------------------------------------------

def _read(path, binary=False):
    try:
        with open(path, "rb" if binary else "r", **({} if binary else {"encoding": "utf-8"})) as f:
            return f.read()
    except OSError:
        return None


def validate_manifest_and_files(m, schema, rep, script_for, image_for):
    check_manifest(m, schema, rep)
    if not isinstance(m, dict):
        return
    community = m.get("source") == "community"
    py = [f for f in m.get("files", []) if isinstance(f, dict) and str(f.get("dest", "")).endswith(".py")]
    if not any(f.get("dest") == "product.py" for f in py):
        rep.error("script", "files[] has no entry with dest 'product.py'")
    for f in py:
        name, text = script_for(f)
        if text is None:
            rep.error("script", "%s (for %s) is missing" % (name, f.get("dest")))
        else:
            check_script(name, text, community, rep)
            # DEV-281: a product that reads public data must say so in the manifest (the app
            # shows "needs your home Wi-Fi").
            if FEEDS_IMPORT_RE.search(text) and "internet" not in (m.get("needs") or []):
                rep.error("needs", "%s imports noknok_feeds: the manifest must say "
                                   '"needs": ["internet"]' % name)
    if m.get("image"):
        name, data = image_for(m)
        check_image(name, data, rep)


def validate_repo_product(root, entry, schema, seen_ids):
    pid = entry.get("id", "?")
    rep = Report(pid)
    if pid in seen_ids:
        rep.error("catalog", "id %r is in catalog.json more than once" % pid)
    seen_ids.add(pid)
    url = entry.get("manifest", "")
    if not url.startswith(RAW_MAIN + "manifests/"):
        rep.error("catalog", "manifest URL must start with %smanifests/" % RAW_MAIN)
        return rep
    mpath = os.path.join(root, url[len(RAW_MAIN):])
    raw = _read(mpath)
    if raw is None:
        rep.error("catalog", "%s does not exist" % url[len(RAW_MAIN):])
        return rep
    try:
        m = json.loads(raw)
    except ValueError as e:
        rep.error("manifest", "not valid JSON: %s" % e)
        return rep
    if isinstance(m, dict) and m.get("id") != pid:
        rep.error("catalog", "catalog id %r but manifest id %r" % (pid, m.get("id")))

    def script_for(f):
        u = str(f.get("url", ""))
        if not u.startswith(RAW_MAIN):
            return u, None
        rel = u[len(RAW_MAIN):]
        return rel, _read(os.path.join(root, rel))

    def image_for(mm):
        u = str(mm.get("image", ""))
        rel = u[len(RAW_MAIN):] if u.startswith(RAW_MAIN) else u
        return rel, _read(os.path.join(root, rel), binary=True) if u.startswith(RAW_MAIN) else None

    validate_manifest_and_files(m, schema, rep, script_for, image_for)
    return rep


def validate_folder(folder, schema):
    rep = Report(os.path.basename(os.path.normpath(folder)))
    raw = _read(os.path.join(folder, "manifest.json"))
    if raw is None:
        rep.error("manifest", "manifest.json is missing")
        return rep
    try:
        m = json.loads(raw)
    except ValueError as e:
        rep.error("manifest", "manifest.json is not valid JSON: %s" % e)
        return rep
    if isinstance(m, dict) and m.get("id"):
        rep.name = m["id"]

    def script_for(f):
        name = os.path.basename(str(f.get("dest", "")))
        return name, _read(os.path.join(folder, name))

    def image_for(_m):
        return "image.webp", _read(os.path.join(folder, "image.webp"), binary=True)

    validate_manifest_and_files(m, schema, rep, script_for, image_for)
    check_licence(_read(os.path.join(folder, "README.md")), rep)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check noknok products before publishing.")
    ap.add_argument("ids", nargs="*", help="product ids from catalog.json")
    ap.add_argument("--all", action="store_true", help="every product in catalog.json")
    ap.add_argument("--folder", help="a submission folder (manifest.json, product.py, ...)")
    ap.add_argument("--schema", help="path to product-manifest.schema.json")
    ap.add_argument("--root", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    ap.add_argument("--json", action="store_true", help="print a JSON report")
    a = ap.parse_args(argv)
    schema = load_schema(a.schema)

    reports = []
    if a.folder:
        reports.append(validate_folder(a.folder, schema))
    if a.all or a.ids:
        cat = _read(os.path.join(a.root, "manifests", "catalog.json"))
        if cat is None:
            print("manifests/catalog.json not found under %s" % a.root)
            return 2
        entries = json.loads(cat).get("products", [])
        seen = set()
        for e in entries:
            if a.all or e.get("id") in a.ids:
                reports.append(validate_repo_product(a.root, e, schema, seen))
            else:
                seen.add(e.get("id"))
        for missing in set(a.ids) - {e.get("id") for e in entries}:
            r = Report(missing)
            r.error("catalog", "id %r is not in manifests/catalog.json" % missing)
            reports.append(r)
    if not reports:
        ap.print_help()
        return 2
    if a.json:
        print(json.dumps([r.as_dict() for r in reports], indent=2))
    else:
        for r in reports:
            r.print()
        bad = sum(1 for r in reports if r.errors)
        print("\n%d product(s) checked, %d with errors." % (len(reports), bad))
    return 1 if any(r.errors for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
