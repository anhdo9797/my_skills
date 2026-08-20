#!/usr/bin/env python3
"""Camera fixture tooling for the mobile-app-review skill.

Camera-driven flows (scan, OCR, QR, document capture, try-on, AR) are the core
value of a lot of apps, and they are the flows a review usually skips because
"there is no camera". This script removes that excuse: it feeds a *known* image
into the app's capture path so the flow can be run, repeated and compared.

Three routes, in order of fidelity:

  A. Android emulator, virtual-scene camera - the app's live camera really sees
     the fixture image. `scene` installs the poster geometry once, `show` swaps
     the image at runtime with no restart.
  B. Photo library / gallery import - works on emulators, simulators and
     physical devices, but exercises the import path instead of live capture.
  C. Physical rig (real device pointed at a fixture displayed on screen) - the
     only way to exercise live capture on real hardware; needs the user's hands
     once, then everything else stays automated.

See references/camera-flows.md for the protocol, the caveats and what each route
does and does not prove.

Usage:
  camera_fixture.py check [--device SERIAL]
  camera_fixture.py enable-avd-cam --avd NAME [--back MODE] [--front MODE]
  camera_fixture.py scene [--preset fill|fit] [--restore]
  camera_fixture.py show IMAGE [--device SERIAL]
  camera_fixture.py make-fixture --out FILE [--from PHOTO] [--label TEXT]
  camera_fixture.py fetch --subject TEXT --out-dir DIR [--count N]
  camera_fixture.py barcode --type ean13|upca|qr|... --value V --out FILE
  camera_fixture.py degrade IMAGE --mode blur|rotate|dark|... --out FILE
  camera_fixture.py verify IMAGE [--expect PAYLOAD]
  camera_fixture.py manifest DIR
  camera_fixture.py gallery IMAGE [--platform android|ios] [--device SERIAL]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------- #
# Poster presets.
#
# Both were measured on an Android 16 (API 36) arm64 AVD, portrait, back camera
# = virtualscene, with the stock Camera app. `position` is x y z in metres; the
# virtual camera sits at roughly y=0.9 looking down -z, so negative z is "in
# front of the lens" and y raises the poster.
#
#   fill - the fixture covers the whole preview; roughly the central 75% of the
#          image is visible, so keep the subject inside the central 60%.
#   fit  - the whole fixture is visible with the room around it; the subject is
#          smaller but nothing is cropped.
# --------------------------------------------------------------------------- #
PRESETS = {
    "fill": {"size": "2.0 2.6", "position": "0 -0.4 -1.1"},
    "fit": {"size": "1.2 1.6", "position": "0 0.05 -1.7"},
}

TABLE_BLOCK = """poster table
size 1 1
position -2.205 -0.077 3.949
rotation -90 0 120
"""


# --------------------------------------------------------------------------- #
# Fixture manifest
#
# Every fixture carries its provenance next to it, so a resumed session reuses
# the same inputs and the report can state where each input came from and what
# the correct answer was.
# --------------------------------------------------------------------------- #
def manifest_path(target: Path) -> Path:
    return target.parent / "manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def record(target: Path, entry: dict) -> None:
    """Append/replace this file's entry in the sibling manifest.json."""
    mp = manifest_path(target)
    data = {"fixtures": []}
    if mp.exists():
        try:
            data = json.loads(mp.read_text())
        except json.JSONDecodeError:
            pass
    entry = {"file": target.name, "sha256": sha256(target), **entry}
    data["fixtures"] = [f for f in data.get("fixtures", [])
                        if f.get("file") != target.name] + [entry]
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def require_pil():
    try:
        from PIL import Image, ImageDraw  # noqa: F401
        return True
    except ImportError:
        print("This needs Pillow: pip3 install pillow")
        return False


def run(cmd: list[str], **kw) -> tuple[int, str]:
    """Run a command, returning (returncode, combined output)."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=kw.pop("timeout", 60)
        )
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, f"{' '.join(cmd)}: timed out"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# --------------------------------------------------------------------------- #
# SDK / device discovery
# --------------------------------------------------------------------------- #
def sdk_root() -> Path | None:
    """Locate the Android SDK."""
    for env in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        v = os.environ.get(env)
        if v and Path(v).is_dir():
            return Path(v)
    for c in (Path.home() / "Library/Android/sdk", Path.home() / "Android/Sdk"):
        if c.is_dir():
            return c
    return None


def emulator_bin() -> Path | None:
    root = sdk_root()
    if root and (root / "emulator/emulator").exists():
        return root / "emulator/emulator"
    found = shutil.which("emulator")
    return Path(found) if found else None


def resources_dir() -> Path | None:
    """The emulator's resources directory, which holds Toren1BD.posters."""
    bin_ = emulator_bin()
    if not bin_:
        return None
    d = bin_.parent / "resources"
    return d if d.is_dir() else None


def adb(args: list[str], serial: str | None = None) -> tuple[int, str]:
    cmd = ["adb"] + (["-s", serial] if serial else []) + args
    return run(cmd)


def android_devices() -> list[str]:
    rc, out = run(["adb", "devices"])
    if rc != 0:
        return []
    return [
        line.split()[0]
        for line in out.splitlines()[1:]
        if line.strip() and line.split()[-1] == "device"
    ]


def pick_device(serial: str | None) -> str | None:
    if serial:
        return serial
    devs = android_devices()
    if len(devs) == 1:
        return devs[0]
    if not devs:
        print("No Android device/emulator connected (`adb devices` is empty).")
    else:
        print(f"Several devices connected: {', '.join(devs)} - pass --device.")
    return None


def getprop(serial: str, prop: str) -> str:
    _, out = adb(["shell", "getprop", prop], serial)
    return out.strip()


def is_emulator(serial: str) -> bool:
    return serial.startswith("emulator-") or getprop(serial, "ro.boot.qemu") == "1"


def avd_name(serial: str) -> str | None:
    rc, out = adb(["emu", "avd", "name"], serial)
    if rc != 0:
        return None
    lines = [l.strip() for l in out.splitlines() if l.strip() and l.strip() != "OK"]
    return lines[0] if lines else None


def avd_config(name: str) -> Path | None:
    home = os.environ.get("ANDROID_AVD_HOME") or str(Path.home() / ".android/avd")
    p = Path(home) / f"{name}.avd/config.ini"
    return p if p.exists() else None


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def cmd_check(args) -> int:
    print("== Android ==")
    devs = android_devices()
    if not devs:
        print("  no device/emulator connected")
    for s in devs:
        emu = is_emulator(s)
        model = getprop(s, "ro.product.model") or "?"
        api = getprop(s, "ro.build.version.sdk") or "?"
        print(f"  {s}  {model}  API {api}  ({'emulator' if emu else 'physical'})")
        if not emu:
            print("     route B (gallery import) or route C (physical rig).")
            print("     Live-capture injection is not possible without root.")
            continue
        name = avd_name(s)
        cfg = avd_config(name) if name else None
        back = front = "?"
        if cfg:
            for line in cfg.read_text().splitlines():
                if line.startswith("hw.camera.back="):
                    back = line.split("=", 1)[1].strip()
                elif line.startswith("hw.camera.front="):
                    front = line.split("=", 1)[1].strip()
        print(f"     AVD {name or '?'}  hw.camera.back={back}  front={front}")
        if back != "virtualscene":
            print(f"     !! back camera is '{back}' - the app cannot open a camera.")
            print(f"        fix: {sys.argv[0]} enable-avd-cam --avd {name}"
                  " , then cold-boot the emulator")
        rc, out = adb(["emu", "help", "virtualscene-image"], s)
        live = rc == 0 and "virtualscene" in out.lower()
        print(f"     live image swap (adb emu virtualscene-image): "
              f"{'yes' if live else 'no - restart per fixture'}")
        gles = getprop(s, "ro.kernel.qemu.gles")
        if gles == "0":
            print("     !! software GL - the virtual scene will be low-res/blocky."
                  " Relaunch the emulator with -gpu host.")
        if back == "virtualscene" and live:
            print("     route A available: scene -> show -> run the flow.")

    res = resources_dir()
    print("\n== Virtual-scene poster file ==")
    if not res:
        print("  emulator resources dir not found (is the SDK installed?)")
    else:
        posters = res / "Toren1BD.posters"
        print(f"  {posters}")
        if posters.exists():
            txt = posters.read_text()
            applied = next(
                (n for n, p in PRESETS.items()
                 if p["size"] in txt and p["position"] in txt), None)
            print(f"  preset applied: {applied or 'none (stock geometry)'}")
        backup = res / "Toren1BD.posters.orig"
        print(f"  backup present: {'yes' if backup.exists() else 'no'}")

    print("\n== Host webcams visible to the emulator ==")
    bin_ = emulator_bin()
    if bin_:
        rc, out = run([str(bin_), "-webcam-list"], timeout=30)
        listed = [l for l in out.splitlines() if l.strip()]
        print("  " + ("\n  ".join(listed) if listed else
                      "none (no host camera, or macOS camera permission missing)"))
        print("  A host webcam or a virtual camera (OBS) can be piped in with"
              " -camera-back webcam0.")

    print("\n== iOS ==")
    rc, out = run(["xcrun", "simctl", "list", "devices", "booted"])
    booted = [l.strip() for l in out.splitlines() if "(Booted)" in l]
    if rc != 0:
        print("  xcrun not available")
    elif booted:
        for b in booted:
            print(f"  {b}")
        print("  Simulator has NO camera device - route B only"
              " (xcrun simctl addmedia), or a real device.")
    else:
        print("  no booted simulator")
    return 0


# --------------------------------------------------------------------------- #
# enable-avd-cam
# --------------------------------------------------------------------------- #
def cmd_enable_avd_cam(args) -> int:
    cfg = avd_config(args.avd)
    if not cfg:
        print(f"config.ini for AVD '{args.avd}' not found.")
        return 1
    backup = cfg.with_suffix(".ini.orig")
    if not backup.exists():
        shutil.copy2(cfg, backup)
        print(f"backed up -> {backup}")
    lines = cfg.read_text().splitlines()
    wanted = {"hw.camera.back": args.back, "hw.camera.front": args.front}
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in wanted:
            out.append(f"{key}={wanted[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in wanted.items():
        if key not in seen:
            out.append(f"{key}={val}")
    cfg.write_text("\n".join(out) + "\n")
    print(f"{cfg}: hw.camera.back={args.back} hw.camera.front={args.front}")
    print("Cold-boot the emulator for this to take effect:")
    print(f"  emulator -avd {args.avd} -gpu host -camera-back {args.back}"
          " -no-snapshot-load")
    return 0


# --------------------------------------------------------------------------- #
# scene
# --------------------------------------------------------------------------- #
def cmd_scene(args) -> int:
    res = resources_dir()
    if not res:
        print("emulator resources dir not found - is the Android SDK installed?")
        return 1
    posters = res / "Toren1BD.posters"
    backup = res / "Toren1BD.posters.orig"

    if args.restore:
        if not backup.exists():
            print(f"no backup at {backup} - nothing to restore")
            return 1
        shutil.copy2(backup, posters)
        print(f"restored stock geometry from {backup}")
        return 0

    if posters.exists() and not backup.exists():
        shutil.copy2(posters, backup)
        print(f"backed up stock geometry -> {backup}")

    p = PRESETS[args.preset]
    posters.write_text(
        f"poster wall\nsize {p['size']}\nposition {p['position']}\n"
        f"rotation 0 0 0\ndefault poster.png\n\n{TABLE_BLOCK}"
    )
    print(f"{posters}: preset '{args.preset}' "
          f"(size {p['size']}, position {p['position']})")
    print("Geometry is read at emulator start, so cold-boot once:")
    print("  emulator -avd <NAME> -gpu host -camera-back virtualscene"
          " -virtualscene-poster wall=/abs/path/fixture.png -no-snapshot-load")
    print("After that, swap fixtures live with:  camera_fixture.py show <image>")
    return 0


# --------------------------------------------------------------------------- #
# show
# --------------------------------------------------------------------------- #
def cmd_show(args) -> int:
    img = Path(args.image).expanduser().resolve()
    if not img.exists():
        print(f"{img}: no such file")
        return 1
    if img.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        print(f"{img.suffix}: the virtual scene only accepts png/jpeg")
        return 1
    serial = pick_device(args.device)
    if not serial:
        return 1
    rc, out = adb(["emu", "virtualscene-image", "wall", str(img)], serial)
    ok = rc == 0 and "KO" not in out
    print(f"{'shown' if ok else 'failed'}: {img}")
    if not ok:
        print(out.strip())
        print("The emulator must be running with -camera-back virtualscene.")
        return 1
    print("The app's live camera now sees this image. Screenshot the preview to"
          " confirm framing before you run the case.")
    return 0


# --------------------------------------------------------------------------- #
# make-fixture
# --------------------------------------------------------------------------- #
def cmd_make_fixture(args) -> int:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("make-fixture needs Pillow (`pip3 install pillow`).")
        print("Or supply your own image: portrait 3:4 (e.g. 1200x1600), subject"
              " inside the central 60%.")
        return 1

    W, H = 1200, 1600
    safe = args.safe
    canvas = Image.new("RGB", (W, H), args.bg)
    box_w, box_h = int(W * safe), int(H * safe)
    ox, oy = (W - box_w) // 2, (H - box_h) // 2

    if args.source:
        src = Image.open(args.source).convert("RGB")
        if args.fit == "cover":
            # Scale to cover the safe box, then centre-crop: no letterbox bands,
            # which is what you want when the photo should fill the frame.
            scale = max(box_w / src.width, box_h / src.height)
            src = src.resize((max(1, round(src.width * scale)),
                              max(1, round(src.height * scale))), Image.LANCZOS)
            left, top = (src.width - box_w) // 2, (src.height - box_h) // 2
            src = src.crop((left, top, left + box_w, top + box_h))
        else:
            src.thumbnail((box_w, box_h))
        canvas.paste(src, (ox + (box_w - src.width) // 2,
                           oy + (box_h - src.height) // 2))
    else:
        d = ImageDraw.Draw(canvas)
        # A test card: quadrants for orientation, a line ramp for resolution.
        d.rectangle([ox, oy, ox + box_w // 2, oy + box_h // 2], fill="#d62828")
        d.rectangle([ox + box_w // 2, oy + box_h // 2, ox + box_w, oy + box_h],
                    fill="#1d4ed8")
        for i in range(24):
            x = ox + 10 + i * (box_w - 20) // 24
            d.line([(x, oy + box_h - 140), (x, oy + box_h - 20)],
                   fill="black", width=1 if i % 2 else 5)

    d = ImageDraw.Draw(canvas)
    d.rectangle([ox, oy, ox + box_w, oy + box_h], outline="black", width=6)
    if args.label:
        d.text((ox + 20, oy + 20), args.label, fill="black", font_size=84)
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)

    # Inherit provenance from the raw candidate this was promoted from, and mark
    # it verified - promoting a candidate means you looked at it and agreed it
    # shows the subject.
    parent = {}
    if args.source:
        src = Path(args.source).expanduser().resolve()
        mp = manifest_path(src)
        if mp.exists():
            try:
                for f in json.loads(mp.read_text()).get("fixtures", []):
                    if f.get("file") == src.name:
                        parent = f
            except json.JSONDecodeError:
                pass
    record(out, {
        "kind": "fixture",
        "subject": parent.get("subject") or args.label,
        "expected": parent.get("expected"),
        "source": parent.get("source"),
        "licence": parent.get("licence"),
        "author": parent.get("author"),
        "promoted_from": Path(args.source).name if args.source else None,
        "verified": True,
    })
    print(f"{out}  ({W}x{H}, subject inside central {int(safe * 100)}%)")
    return 0


# --------------------------------------------------------------------------- #
# fetch - source a candidate subject image from the internet
#
# Wikimedia Commons is the default source on purpose: no API key, stable direct
# URLs, an explicit licence, and a file title that usually *names the subject*
# (species, dish, landmark) - which is the ground truth you need to judge what
# the app answers.
# --------------------------------------------------------------------------- #
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
UA = "mobile-app-review-skill/1.0 (camera fixture sourcing)"


def cmd_fetch(args) -> int:
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:bitmap {args.subject}",
        "gsrnamespace": "6", "gsrlimit": str(args.count),
        "prop": "imageinfo", "iiprop": "url|extmetadata|size",
        "iiurlwidth": str(args.width),
    }
    url = f"{COMMONS_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception as e:  # network, DNS, rate limit
        print(f"Commons search failed: {e}")
        return 1

    pages = list(data.get("query", {}).get("pages", {}).values())
    if not pages:
        print(f"no results for '{args.subject}' - try a more common name")
        return 1

    outdir = Path(args.out_dir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for i, page in enumerate(pages, 1):
        info = page.get("imageinfo", [{}])[0]
        src = info.get("thumburl") or info.get("url")
        if not src:
            continue
        meta = info.get("extmetadata", {})
        ext = Path(urllib.parse.urlparse(src).path).suffix.lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png"):
            continue
        dest = outdir / f"raw-{slug(args.subject)}-{i:02d}{ext}"
        if i > 1:
            time.sleep(1.0)  # Commons rate-limits bursts with HTTP 429
        try:
            req = urllib.request.Request(src, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                dest.write_bytes(r.read())
        except Exception as e:
            print(f"  download failed ({e})")
            continue
        record(dest, {
            "kind": "raw-candidate",
            "subject": args.subject,
            "expected": args.expected or args.subject,
            "source": info.get("descriptionurl"),
            "licence": meta.get("LicenseShortName", {}).get("value"),
            "author": re.sub("<[^>]+>", "",
                             meta.get("Artist", {}).get("value", ""))[:80] or None,
            "commons_title": page.get("title"),
            "verified": False,
        })
        print(f"  {dest.name}  {page.get('title')}  "
              f"[{meta.get('LicenseShortName', {}).get('value')}]")
        saved += 1

    if not saved:
        print("nothing downloadable in the results")
        return 1
    print(f"\n{saved} candidate(s) in {outdir}, recorded in manifest.json as"
          " verified:false")
    print("NOW LOOK AT THEM. Open each file and confirm it really shows the"
          " subject, one clear instance of it, no watermark/collage/diagram.")
    print("Then promote the one you trust:")
    print(f"  make-fixture --from {outdir}/raw-... --out"
          f" {outdir}/fixture-01-{slug(args.subject)}.png --label FIXTURE-01")
    return 0


# --------------------------------------------------------------------------- #
# barcode - generate a code whose payload you already know
#
# Barcodes are never downloaded: a fixture is only useful if you know what the
# correct decode is, and an image found on the web carries an unknown payload.
# EAN-13/UPC-A are drawn here from the standard pattern tables; QR needs segno
# (pip3 install segno); anything else is delegated to python-barcode.
# --------------------------------------------------------------------------- #
EAN_L = ["0001101", "0011001", "0010011", "0111101", "0100011",
         "0110001", "0101111", "0111011", "0110111", "0001011"]
EAN_G = ["0100111", "0110011", "0011011", "0100001", "0011101",
         "0111001", "0000101", "0010001", "0001001", "0010111"]
EAN_R = ["1110010", "1100110", "1101100", "1000010", "1011100",
         "1001110", "1010000", "1000100", "1001000", "1110100"]
EAN_PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
              "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def ean13_check_digit(twelve: str) -> str:
    s = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(twelve))
    return str((10 - s % 10) % 10)


def ean13_modules(code: str) -> str:
    """Return the 95-module bar pattern ('1' = bar) for a 13-digit code."""
    parity = EAN_PARITY[int(code[0])]
    left = "".join((EAN_L if parity[i] == "L" else EAN_G)[int(d)]
                   for i, d in enumerate(code[1:7]))
    right = "".join(EAN_R[int(d)] for d in code[7:])
    return "101" + left + "01010" + right + "101"


def cmd_barcode(args) -> int:
    if not require_pil():
        return 1
    from PIL import Image, ImageDraw

    W, H = 1200, 1600
    value = args.value
    kind = args.type
    canvas = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(canvas)

    if kind in ("ean13", "upca"):
        digits = re.sub(r"\D", "", value)
        if kind == "upca":
            digits = "0" + digits
        if len(digits) == 12:
            digits += ean13_check_digit(digits)
        if len(digits) != 13 or not digits.isdigit():
            print(f"{kind} needs 12 or 13 digits, got '{value}'")
            return 1
        if digits[-1] != ean13_check_digit(digits[:12]):
            print(f"warning: check digit {digits[-1]} is wrong for"
                  f" {digits[:12]} (correct: {ean13_check_digit(digits[:12])})"
                  " - keeping it, which is what an invalid-checksum case needs")
        bars = ean13_modules(digits)
        # The code occupies 62% of the width, which survives the `fill` preset.
        mod = int(W * 0.62) // len(bars)
        bar_w = mod * len(bars)
        bar_h = int(H * 0.30)
        x0, y0 = (W - bar_w) // 2, (H - bar_h) // 2
        for i, m in enumerate(bars):
            if m == "1":
                d.rectangle([x0 + i * mod, y0, x0 + (i + 1) * mod - 1,
                             y0 + bar_h], fill="black")
        d.text((x0, y0 + bar_h + 24), " ".join(digits), fill="black",
               font_size=64)
        payload, label = digits, f"{kind.upper()} {digits}"

    elif kind == "qr":
        try:
            import segno
        except ImportError:
            print("QR needs segno: pip3 install segno")
            return 1
        qr = segno.make(value, error="m")
        tmp = Path(args.out).with_suffix(".qr.png")
        qr.save(tmp, scale=20, border=4)
        code = Image.open(tmp).convert("RGB")
        side = int(min(W, H) * 0.55)
        code = code.resize((side, side), Image.NEAREST)
        canvas.paste(code, ((W - side) // 2, (H - side) // 2))
        tmp.unlink(missing_ok=True)
        payload, label = value, f"QR {value[:40]}"

    else:
        try:
            import barcode as pybarcode
            from barcode.writer import ImageWriter
        except ImportError:
            print(f"'{kind}' needs python-barcode: pip3 install python-barcode")
            return 1
        gen = pybarcode.get(kind, value, writer=ImageWriter())
        tmp = Path(args.out).with_suffix(".tmp")
        path = Path(gen.save(str(tmp)))
        code = Image.open(path).convert("RGB")
        code.thumbnail((int(W * 0.8), int(H * 0.4)))
        canvas.paste(code, ((W - code.width) // 2, (H - code.height) // 2))
        path.unlink(missing_ok=True)
        payload, label = value, f"{kind} {value}"

    if args.label:
        d.text((60, 60), args.label, fill="black", font_size=72)
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    record(out, {"kind": "generated-code", "symbology": kind,
                 "expected": payload, "subject": label, "verified": True})
    print(f"{out}  {label}")
    print(f"expected decode: {payload}")
    return 0


# --------------------------------------------------------------------------- #
# degrade - derive a boundary-case variant from a fixture you already trust
# --------------------------------------------------------------------------- #
def cmd_degrade(args) -> int:
    if not require_pil():
        return 1
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    src_path = Path(args.image).expanduser().resolve()
    if not src_path.exists():
        print(f"{src_path}: no such file")
        return 1
    im = Image.open(src_path).convert("RGB")
    W, H = im.size
    mode = args.mode

    if mode == "blur":
        im = im.filter(ImageFilter.GaussianBlur(radius=max(2, W * 0.012)))
    elif mode == "rotate":
        im = im.rotate(args.angle, expand=False, fillcolor="white")
    elif mode == "dark":
        im = ImageEnhance.Brightness(im).enhance(0.22)
    elif mode == "lowcontrast":
        im = ImageEnhance.Contrast(im).enhance(0.28)
    elif mode == "invert":
        im = ImageOps.invert(im)
    elif mode == "crop":
        keep = im.crop((0, 0, int(W * 0.62), H))
        im = Image.new("RGB", (W, H), "white")
        im.paste(keep, (0, 0))
    elif mode == "small":
        small = im.copy()
        small.thumbnail((int(W * 0.3), int(H * 0.3)))
        im = Image.new("RGB", (W, H), "white")
        im.paste(small, ((W - small.width) // 2, (H - small.height) // 2))

    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    parent = {}
    mp = manifest_path(src_path)
    if mp.exists():
        try:
            for f in json.loads(mp.read_text()).get("fixtures", []):
                if f.get("file") == src_path.name:
                    parent = f
        except json.JSONDecodeError:
            pass
    record(out, {"kind": "degraded", "degrade": mode,
                 "derived_from": src_path.name,
                 "subject": parent.get("subject"),
                 "expected": parent.get("expected"),
                 "verified": True})
    print(f"{out}  ({mode} of {src_path.name})")
    return 0


# --------------------------------------------------------------------------- #
# manifest - what fixtures do I have, and what is each one for
# --------------------------------------------------------------------------- #
def cmd_manifest(args) -> int:
    mp = Path(args.dir).expanduser().resolve() / "manifest.json"
    if not mp.exists():
        print(f"no manifest at {mp}")
        return 1
    data = json.loads(mp.read_text())
    for f in data.get("fixtures", []):
        flag = "ok " if f.get("verified") else "?? "
        print(f"{flag}{f['file']}")
        for k in ("kind", "subject", "expected", "symbology", "degrade",
                  "derived_from", "licence", "source"):
            if f.get(k):
                print(f"      {k}: {f[k]}")
    unver = [f["file"] for f in data.get("fixtures", []) if not f.get("verified")]
    if unver:
        print(f"\n?? not yet verified by eye: {', '.join(unver)}")
    return 0


# --------------------------------------------------------------------------- #
# verify - is this code actually readable?
#
# The question that separates "the app's scanner is weak" from "your fixture was
# unreadable". Run it on the fixture file, and again on the screenshot of the
# app's camera preview: if the code decodes in what the camera sees and the app
# still shows nothing, that is a finding about the app. If it doesn't decode,
# it's your fixture and no finding at all.
# --------------------------------------------------------------------------- #
def decode_codes(path: Path) -> tuple[list[tuple[str, str]], str]:
    """Decode every code in an image. Returns (results, backend used)."""
    try:
        import cv2  # noqa
        import zxingcpp
        img = cv2.imread(str(path))
        if img is None:
            return [], "zxing-cpp"
        return ([(r.format.name, r.text) for r in zxingcpp.read_barcodes(img)],
                "zxing-cpp")
    except ImportError:
        pass
    try:
        import cv2
        img = cv2.imread(str(path))
        if img is None:
            return [], "opencv"
        text, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
        return ([("QRCode", text)] if text else []), "opencv (QR only)"
    except ImportError:
        return [], "none"


def cmd_verify(args) -> int:
    img = Path(args.image).expanduser().resolve()
    if not img.exists():
        print(f"{img}: no such file")
        return 1
    results, backend = decode_codes(img)
    if backend == "none":
        print("No decoder installed. For the strongest check:")
        print("  pip3 install zxing-cpp opencv-python-headless")
        print("Without it you cannot tell an unreadable fixture from a weak"
              " scanner - say so in the report instead of guessing.")
        return 1
    print(f"decoder: {backend}")
    if not results:
        print(f"{img.name}: NO CODE DECODED")
        print("If this is a fixture, it is unusable as a happy-path input"
              " (fine as a deliberate unreadable case).")
        print("If this is a camera screenshot, fix framing/preset before"
              " blaming the app - try --preset fit for rotated or long codes.")
        return 2
    for fmt, text in results:
        print(f"{img.name}: {fmt}  {text}")
    if args.expect:
        got = [text for _, text in results]
        ok = args.expect in got
        print(f"expected '{args.expect}': {'PASS' if ok else 'MISMATCH'}")
        return 0 if ok else 2
    return 0


# --------------------------------------------------------------------------- #
# gallery
# --------------------------------------------------------------------------- #
def cmd_gallery(args) -> int:
    img = Path(args.image).expanduser().resolve()
    if not img.exists():
        print(f"{img}: no such file")
        return 1

    platform = args.platform
    if platform == "auto":
        platform = "android" if android_devices() else "ios"

    if platform == "ios":
        rc, out = run(["xcrun", "simctl", "addmedia", "booted", str(img)])
        if rc != 0:
            print(out.strip() or "addmedia failed")
            print("Boot a simulator first: xcrun simctl boot <UDID>")
            return 1
        print(f"added to the simulator photo library: {img.name}")
        print("If the Photos app was open, kill and reopen it to see the new"
              " item.")
        return 0

    serial = pick_device(args.device)
    if not serial:
        return 1
    dest = f"/sdcard/Pictures/{img.name}"
    rc, out = adb(["push", str(img), dest], serial)
    if rc != 0:
        print(out.strip())
        return 1
    # adb push registers the file with MediaProvider on modern Android; the
    # broadcast is a harmless fallback for older builds.
    adb(["shell", "am", "broadcast", "-a",
         "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
         "-d", f"file://{dest}"], serial)
    _, q = adb(["shell", "content", "query", "--uri",
                "content://media/external/images/media",
                "--projection", "_data"], serial)
    indexed = img.name in q
    print(f"pushed {dest}")
    print(f"MediaStore: {'indexed - visible in the gallery/picker' if indexed else 'NOT indexed yet'}")
    if not indexed:
        print("Open the app's picker anyway; some pickers scan on open.")
    return 0


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Feed a known image into a mobile app's camera path.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="report camera capabilities of the target")
    p.add_argument("--device")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("enable-avd-cam",
                       help="turn the camera on in an AVD (needs cold boot)")
    p.add_argument("--avd", required=True)
    p.add_argument("--back", default="virtualscene",
                   choices=["virtualscene", "emulated", "webcam0", "none"])
    p.add_argument("--front", default="emulated",
                   choices=["virtualscene", "emulated", "webcam0", "none"])
    p.set_defaults(func=cmd_enable_avd_cam)

    p = sub.add_parser("scene", help="install/restore the poster geometry")
    p.add_argument("--preset", default="fill", choices=sorted(PRESETS))
    p.add_argument("--restore", action="store_true")
    p.set_defaults(func=cmd_scene)

    p = sub.add_parser("show", help="swap the live virtual-scene image")
    p.add_argument("image")
    p.add_argument("--device")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("make-fixture", help="build a poster-ready fixture image")
    p.add_argument("--out", required=True)
    p.add_argument("--from", dest="source", help="photo to place in the safe area")
    p.add_argument("--label", help="text drawn in the corner, e.g. FIXTURE-01")
    p.add_argument("--safe", type=float, default=0.6,
                   help="fraction of the canvas the subject may use (default .6)")
    p.add_argument("--bg", default="#ffffff")
    p.add_argument("--fit", default="contain", choices=["contain", "cover"],
                   help="contain keeps the whole photo (letterboxed); cover"
                        " centre-crops it to fill the frame")
    p.set_defaults(func=cmd_make_fixture)

    p = sub.add_parser("fetch",
                       help="download candidate subject images from Wikimedia Commons")
    p.add_argument("--subject", required=True,
                   help='what the app should recognise, e.g. "Monstera deliciosa"')
    p.add_argument("--out-dir", required=True)
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--width", type=int, default=1600)
    p.add_argument("--expected",
                   help="the answer the app should give, if not the subject name")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("barcode",
                       help="generate a scannable code with a known payload")
    p.add_argument("--type", required=True,
                   help="ean13 | upca | qr | any python-barcode name (code128...)")
    p.add_argument("--value", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--label")
    p.set_defaults(func=cmd_barcode)

    p = sub.add_parser("degrade", help="derive a boundary-case variant")
    p.add_argument("image")
    p.add_argument("--mode", required=True,
                   choices=["blur", "rotate", "dark", "lowcontrast", "invert",
                            "crop", "small"])
    p.add_argument("--angle", type=float, default=90)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_degrade)

    p = sub.add_parser("verify",
                       help="decode a fixture or a camera screenshot")
    p.add_argument("image")
    p.add_argument("--expect", help="payload the decode must match")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("manifest", help="list the fixtures and their provenance")
    p.add_argument("dir")
    p.set_defaults(func=cmd_manifest)

    p = sub.add_parser("gallery", help="seed a fixture into the photo library")
    p.add_argument("image")
    p.add_argument("--platform", default="auto",
                   choices=["auto", "android", "ios"])
    p.add_argument("--device")
    p.set_defaults(func=cmd_gallery)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
