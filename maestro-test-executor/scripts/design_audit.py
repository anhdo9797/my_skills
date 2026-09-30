#!/usr/bin/env python3
"""Gate one screen against its design on three measured criteria.

WHY THIS EXISTS — the failure it fixes
--------------------------------------
The other audits each answer one question from pixels alone, and each has to
*guess* which element it is looking at: bands of ink paired by height, OCR boxes
paired by what a recognizer thought it read. On a tidy pair that works. On a
real one the guess moves, the number lands on the wrong widget, and a design
check that is wrong one time in five is a design check nobody acts on.

This script removes the guess. The design arrives as **data** — the Figma node
tree, with every text node's string, box and colour — and the build arrives as
the **view hierarchy** plus its screenshot. Both sides already know what each
element *is*, so elements pair by identity (the string they carry) and every
measurement names the element it belongs to.

THE THREE CRITERIA
------------------
1. TEXT — exact. Every *static* string the test plan lists must render
   character for character (whitespace runs are collapsed; nothing else is).
   Text the plan does not list is API data and is not judged.
2. COLOUR — at least 80% similar. For every paired element the text colour and
   the fill behind it are read from the screenshot and compared with the
   design's. Similarity is 100 - CIE76 delta-E in Lab space, so 80% allows a
   shade or two of drift and rejects a different hue or a different grey tier.
3. SPACING — within 8 dp. The vertical gap above each element and its
   horizontal inset are measured in real dp on both sides and must agree.

All three thresholds are flags; the defaults are the contract in
`references/ui-metrics.md`.

WHAT MAKES THE NUMBERS TRUSTWORTHY
----------------------------------
- **Real dp, not width-normalised px.** A 24 dp spacer is 24 dp on a 360 dp
  phone and on a 412 dp one; scaling the whole screenshot to the design's width
  turns that into 27 and reports a bug that is not there. Pass the device
  density (`adb shell wm density`) and both sides are compared in the unit the
  developer typed.
- **Ink against ink.** A hierarchy box is the widget — sometimes the whole
  button or text field — while a Figma box is the text layer. Both are reduced
  to the pixels the glyphs occupy before anything is measured, and an on-screen
  box that holds more than the text (a border, an icon) is searched for the
  text inside it, using the design's own text size as the prior.
- **Only what is measured can fail.** A reading that rests on a layout box, on
  a thin 1x glyph, or on space the layout is allowed to stretch is reported as
  an advisory with its reason, never as a failure.

WHAT IT CANNOT DO — say this in the report
------------------------------------------
- It anchors on text. An icon, an image or a divider has no anchor: its colour
  is covered only by the advisory palette comparison and its spacing only by
  `spacing_audit.py` and the visual scan.
- It does not measure font size or weight (`typography_audit.py`, advisory),
  corner radius, shadows, or whether text is clipped — the hierarchy reports a
  string in full even when the screen ellipsizes it.
- The distance from the first element to the top of the screen is not
  measured: the design's mock status bar and the device's real one differ.

USAGE
-----
  # Figma MCP: get_metadata -> metadata.xml, get_screenshot -> design.png,
  # colours/strings from get_design_context -> styles.json (optional, exact)
  maestro hierarchy > /tmp/TC-010.json
  python3 design_audit.py \\
      --design report/figma/TC-010.metadata.xml \\
      --design-styles report/figma/TC-010.styles.json \\
      --design-image report/figma/TC-010.png \\
      --actual /tmp/TC-010.json --actual-image report/screenshots/TC-010.png \\
      --density 420 --static-texts report/figma/TC-010_expected.json \\
      --out report/design/TC-010.json --annotate report/vision/TC-010-design.png

  # Figma REST node JSON (figma_fetch.py) carries strings, boxes and colours
  python3 design_audit.py --design report/figma/TC-010.node.json \\
      --design-image report/figma/TC-010.png --actual /tmp/TC-010.json \\
      --actual-image report/screenshots/TC-010.png --density 420 \\
      --static-texts report/figma/TC-010_expected.json --out report/design/TC-010.json

`--design` also accepts a hand-written spec
(`{"frame": {"width": 390, "height": 844}, "elements": [{"text": "Save",
"x": 24, "y": 700, "width": 60, "height": 20, "color": "#FFFFFF",
"background": "#2F9E44"}]}`) or, with tesseract installed, a design image.

stdout carries the verdict and the findings; `--out` holds every measurement.
Exit 0 PASS, 1 FAIL, 3 INCONCLUSIVE, 2 usage error.
Dependencies: Pillow for anything involving an image.
"""

import argparse
import difflib
import json
import math
import os
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from functools import reduce
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from PIL import Image, ImageChops, ImageDraw
except ImportError:
    Image = None

from filter_hierarchy import parse as parse_hierarchy  # noqa: E402
from text_audit import (  # noqa: E402
    IMAGE_SUFFIXES,
    OCR_DECIDABLE,
    _collapse_space,
    _strip_diacritics,
    find_defects,
    load_expected,
    match,
)

# Layers a mock draws for the OS. They are not content: the device brings its
# own, and a mock "9:41" must never pair with anything.
CHROME = re.compile(
    r"status[\s_-]*bar|home[\s_-]*indicator|^notch$|dynamic[\s_-]*island|^keyboard|"
    r"gesture[\s_-]*(bar|nav|pill)|system[\s_-]*(ui|bar|nav)|nav[\s_-]*bar[\s_-]*ios|"
    r"android[\s_-]*(nav|navigation)[\s_-]*bar", re.I)

SLOT = "same slot between two matched elements (different text: dynamic content)"
INK_TOL = 18          # per-channel distance from the background before a pixel is ink
FLAT_MIN = 0.40       # share of a region that must be one colour to call it a flat fill
CORE_MIN = 0.12       # share of glyph pixels at full coverage before a colour read is trusted
MAX_SAMPLES = 12000   # pixels examined per region; more adds time, not accuracy
PAD_DP = 3.0          # margin around a text's ink when reading the fill behind it
FLEX_SLACK_DP = 40.0  # how far mock chrome and real chrome can disagree at the bottom edge


# -------------------------------------------------------------------- colour

def parse_color(value):
    """'#RGB' '#RRGGBB' '#RRGGBBAA' 'rgb()' 'rgba()' or Figma's {r,g,b,a} -> (r, g, b, alpha)."""
    if value is None:
        return None
    if isinstance(value, dict):
        if "raw" in value:
            return parse_color(value["raw"])
        try:
            r, g, b = (float(value[k]) for k in "rgb")
        except (KeyError, TypeError, ValueError):
            return None
        scale = 255.0 if max(r, g, b) <= 1.0 else 1.0
        return (r * scale, g * scale, b * scale, float(value.get("a", 1.0)))
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        alpha = float(value[3]) if len(value) > 3 else 1.0
        return (float(value[0]), float(value[1]), float(value[2]), alpha)
    text = str(value).strip()
    found = re.fullmatch(r"#?([0-9a-fA-F]{3,8})", text)
    if found:
        digits = found.group(1)
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits)
        if len(digits) not in (6, 8):
            return None
        r, g, b = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
        alpha = int(digits[6:8], 16) / 255.0 if len(digits) == 8 else 1.0
        return (float(r), float(g), float(b), alpha)
    found = re.fullmatch(r"rgba?\(([^)]+)\)", text, re.I)
    if found:
        parts = [p for p in re.split(r"[,\s/]+", found.group(1).strip()) if p]
        try:
            rgb = [float(p.rstrip("%")) * (2.55 if p.endswith("%") else 1.0)
                   for p in parts[:3]]
            alpha = 1.0
            if len(parts) > 3:
                alpha = float(parts[3].rstrip("%")) / (100.0 if parts[3].endswith("%") else 1.0)
        except ValueError:
            return None
        return (rgb[0], rgb[1], rgb[2], alpha) if len(rgb) == 3 else None
    return None


def over(paint, backdrop):
    """Composite an (r, g, b, alpha) paint onto an opaque backdrop."""
    if paint is None:
        return None
    alpha = paint[3]
    if alpha >= 0.99:
        return tuple(paint[:3])
    if backdrop is None:
        return None
    return tuple(paint[i] * alpha + backdrop[i] * (1 - alpha) for i in range(3))


def hexof(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _lab(rgb):
    def linear(c):
        c = max(0.0, min(255.0, c)) / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def f(t):
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    r, g, b = (linear(c) for c in rgb)
    x = f((r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047)
    y = f(r * 0.2126729 + g * 0.7151522 + b * 0.0721750)
    z = f((r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883)
    return (116.0 * y - 16.0, 500.0 * (x - y), 200.0 * (y - z))


def color_similarity(a, b):
    """1.0 for identical colours, 0.0 for black against white.

    CIE76 — plain distance in Lab — rather than CIEDE2000 or RGB distance, and
    the choice is what makes "80%" mean something. Both alternatives compress
    differences between saturated colours, so a blue button shipped violet
    scores ~88% and passes. In Lab the same pair scores ~76%, while one or two
    shade steps of the *same* hue stay near 90-95%. The threshold then separates
    "rendered slightly differently" from "this is a different colour token",
    which is the question a design check is asking.
    """
    return max(0.0, 1.0 - math.dist(_lab(a), _lab(b)) / 100.0)


# ------------------------------------------------------------ pixel sampling

def _clamp(box, size, pad=0.0):
    left = max(0, int(math.floor(box[0] - pad)))
    top = max(0, int(math.floor(box[1] - pad)))
    right = min(size[0], int(math.ceil(box[2] + pad)))
    bottom = min(size[1], int(math.ceil(box[3] + pad)))
    return left, top, right, bottom


def _ink_mask(crop, bg):
    flat = Image.new("RGB", crop.size, tuple(int(round(c)) for c in bg))
    channels = ImageChops.difference(crop, flat).split()
    return reduce(ImageChops.lighter, channels).point(lambda v: 255 if v > INK_TOL else 0)


def sample(image, box, pad=0.0, colors=True):
    """Read one region: the fill, the ink's extent, and the ink's colour.

    The fill is the modal colour. The ink colour is *not* the mean of the ink
    pixels: an anti-aliased glyph is mostly edge, and every edge pixel is a
    blend of the text colour with the fill, so the mean of thin grey text on
    white reads several shades too light. The blends all lie on the line from
    the fill to the true colour, so the true colour is the far end of that
    line — the pixels furthest from the fill, along the direction most of the
    ink shares. `core` says how much of the ink sits at that far end; when it is
    small the glyphs never reached full coverage and the read is an
    underestimate, which the caller reports instead of failing on.
    """
    left, top, right, bottom = _clamp(box, image.size, pad)
    if right - left < 3 or bottom - top < 3:
        return None
    crop = image.crop((left, top, right, bottom))
    pixels = list(crop.getdata())
    stride = max(1, len(pixels) // MAX_SAMPLES)
    if stride > 1 and crop.size[0] % stride == 0:
        stride += 1  # a stride that divides the width samples the same columns every row
    picked = pixels[::stride]

    lead = Counter((p[0] >> 3, p[1] >> 3, p[2] >> 3) for p in picked).most_common(1)[0][0]
    members = [p for p in picked if (p[0] >> 3, p[1] >> 3, p[2] >> 3) == lead]
    bg = tuple(sum(p[i] for p in members) / float(len(members)) for i in range(3))

    ink, near = [], 0
    for p in picked:
        dr, dg, db = p[0] - bg[0], p[1] - bg[1], p[2] - bg[2]
        if max(abs(dr), abs(dg), abs(db)) <= INK_TOL:
            near += 1
        elif colors:
            ink.append((math.sqrt(dr * dr + dg * dg + db * db), dr, dg, db, p))

    out = {"bg": bg, "bg_share": near / float(len(picked)), "fg": None, "core": 0.0,
           "ink_box": None, "origin": (left, top)}
    out["flat"] = out["bg_share"] >= FLAT_MIN
    bbox = _ink_mask(crop, bg).getbbox()
    if bbox:
        out["ink_box"] = (left + bbox[0], top + bbox[1], left + bbox[2], top + bbox[3])

    if len(ink) >= 3:
        weight, axis = defaultdict(float), defaultdict(lambda: [0.0, 0.0, 0.0])
        for mag, dr, dg, db, _ in ink:
            key = (round(2 * dr / mag), round(2 * dg / mag), round(2 * db / mag))
            weight[key] += mag
            axis[key][0] += dr
            axis[key][1] += dg
            axis[key][2] += db
        ux, uy, uz = axis[max(weight, key=weight.get)]
        norm = math.sqrt(ux * ux + uy * uy + uz * uz) or 1.0
        ux, uy, uz = ux / norm, uy / norm, uz / norm
        along = sorted(((mag, p) for mag, dr, dg, db, p in ink
                        if (dr * ux + dg * uy + db * uz) / mag >= 0.94),
                       key=lambda item: item[0], reverse=True)
        if len(along) >= 3:
            head = along[:max(3, len(along) // 20)]
            out["fg"] = tuple(sum(p[i] for _, p in head) / float(len(head)) for i in range(3))
            peak = sum(mag for mag, _ in head) / len(head)
            out["core"] = sum(1 for mag, _ in along if mag >= 0.9 * peak) / float(len(along))
    return out


def _profile(mask, rows):
    w, h = mask.size
    size = (1, h) if rows else (w, 1)
    return [v / 255.0 for v in mask.convert("F").resize(size, Image.BOX).getdata()]


def _runs(values, threshold, join):
    """Index ranges where `values` exceeds `threshold`, merging near neighbours."""
    runs, start = [], None
    for i, v in enumerate(values):
        if v > threshold:
            if start is None:
                start = i
        elif start is not None:
            runs.append([start, i])
            start = None
    if start is not None:
        runs.append([start, len(values)])
    merged = []
    for run in runs:
        if merged and run[0] - merged[-1][1] < join:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    return merged


def _strip_rules(mask):
    """Erase borders, underlines and dividers from an ink mask, in place.

    Anything that spans most of a row or column is a rule, not a glyph. The
    whole connected shape goes, which takes a rounded border's corners with it —
    erasing only the straight runs would leave four arcs pinning the ink box to
    the control's outline.
    """
    w, h = mask.size
    px = mask.load()
    for y, share in enumerate(_profile(mask, True)):
        if share >= 0.6:
            for x in range(w):
                if px[x, y]:
                    ImageDraw.floodfill(mask, (x, y), 0)
    for x, share in enumerate(_profile(mask, False)):
        if share >= 0.6:
            for y in range(h):
                if px[x, y]:
                    ImageDraw.floodfill(mask, (x, y), 0)


def line_height(image, ink_box, bg):
    """Ink height of one line of the text in `ink_box`, in pixels."""
    left, top, right, bottom = _clamp(ink_box, image.size)
    if right - left < 2 or bottom - top < 2:
        return float(max(1, bottom - top))
    rows = _profile(_ink_mask(image.crop((left, top, right, bottom)), bg), True)
    runs = _runs(rows, 0.002, 2)
    return float(max((r[1] - r[0] for r in runs), default=bottom - top))


def text_ink(image, box, bg, line_h, want_w, px_per_dp, same_string):
    """Find a text's own ink inside a box that holds more than the text.

    A hierarchy node is a widget. For a text field it is the whole field, border
    included; for a merged button it is the button, icon included. Measuring a
    gap from that box measures the control's padding and files it as a spacing
    bug. So: erase the rules, split what is left into columns of ink, keep the
    column that is this text (the design says how wide the string should be),
    and within it keep the block of lines nearest the middle. Returns the ink
    box and how many lines it holds, or None when nothing text-sized is there.
    """
    left, top, right, bottom = _clamp(box, image.size)
    if right - left < 4 or bottom - top < 4:
        return None
    mask = _ink_mask(image.crop((left, top, right, bottom)), bg)
    _strip_rules(mask)
    w, h = mask.size
    columns = _runs(_profile(mask, False), 0.0, max(3.0, 8.0 * px_per_dp))
    if not columns:
        return None
    if same_string:
        c0, c1 = min(columns, key=lambda c: abs(math.log(max(1, c[1] - c[0]) / want_w)))
    else:
        c0, c1 = max(columns, key=lambda c: c[1] - c[0])
    # Lines of one paragraph sit within a line's height of each other.
    blocks = _runs(_profile(mask.crop((c0, 0, c1, h)), True), 0.002, 1.2 * line_h)
    blocks = [b for b in blocks if b[1] - b[0] >= 0.5 * line_h]
    if not blocks:
        return None
    r0, r1 = min(blocks, key=lambda b: abs((b[0] + b[1]) / 2.0 - h / 2.0))
    inner = mask.crop((c0, r0, c1, r1)).getbbox()
    if not inner:
        return None
    found = (left + c0 + inner[0], top + r0 + inner[1],
             left + c0 + inner[2], top + r0 + inner[3])
    lines = max(1, int(round((found[3] - found[1]) / (1.35 * line_h))))
    return found, lines


def _plausible(got, want, same_string=True):
    """Whether an ink box is the size this text could be, given the design's.

    Width only says anything when both sides carry the same string.
    """
    gw, gh = got[2] - got[0], got[3] - got[1]
    if min(gw, gh, want[0], want[1]) <= 0:
        return False
    if same_string and not 0.5 <= gw / want[0] <= 2.0:
        return False
    return 0.55 <= gh / want[1] <= 1.8


def palette(image, top_frac=0.0, bottom_frac=0.0):
    """Dominant colours and their share of the image, coarsest first."""
    w, h = image.size
    crop = image.crop((0, int(h * top_frac), w, int(h * (1 - bottom_frac))))
    small = crop.resize((max(1, min(160, w)), max(1, int(crop.size[1] * min(160, w) / w))),
                        Image.NEAREST)
    pixels = list(small.getdata())
    bins = defaultdict(lambda: [0, 0, 0, 0])
    for r, g, b in pixels:
        slot = bins[(r >> 4, g >> 4, b >> 4)]
        slot[0] += 1
        slot[1] += r
        slot[2] += g
        slot[3] += b
    total = float(len(pixels))
    return sorted(((n / total, (r / n, g / n, b / n)) for n, r, g, b in bins.values()),
                  reverse=True)


# -------------------------------------------------------------- design input

def _key(text):
    return _strip_diacritics(_collapse_space(text)).casefold()


def _element(text, box, ident="", color=None, background=None, ink=None):
    return {"text": _collapse_space(text), "key": _key(text), "id": ident,
            "box": tuple(float(v) for v in box), "color": color,
            "background": background, "ink": ink}


def _attr(el, name):
    try:
        return float(el.get(name) or 0)
    except ValueError:
        return 0.0


def _figma_xml(raw):
    start = raw.find("<")
    tag = re.match(r"<([\w.-]+)\b", raw[start:]) if start >= 0 else None
    if not tag:
        raise ValueError("no XML found in the design metadata file")
    end = raw.rfind(f"</{tag.group(1)}>")
    if end < start:
        raise ValueError("the metadata XML root is not closed — was the output truncated?")
    try:
        return ET.fromstring(raw[start:end + len(tag.group(1)) + 3])
    except ET.ParseError as exc:
        raise ValueError(f"could not parse the design metadata XML: {exc}")


def _coords_are_absolute(root):
    """Figma MCP writes child positions relative to the parent; older dumps and
    other exporters write them absolute. Count which reading keeps children
    inside their parents rather than trusting either."""
    relative = absolute = 0
    stack = [root]
    while stack:
        parent = stack.pop()
        px, py, pw, ph = (_attr(parent, k) for k in ("x", "y", "width", "height"))
        for child in parent:
            cx, cy, cw, ch = (_attr(child, k) for k in ("x", "y", "width", "height"))
            if cx >= -1 and cy >= -1 and cx + cw <= pw + 1 and cy + ch <= ph + 1:
                relative += 1
            if (cx >= px - 1 and cy >= py - 1 and cx + cw <= px + pw + 1
                    and cy + ch <= py + ph + 1):
                absolute += 1
            stack.append(child)
    return absolute > relative


def design_from_metadata(path, texts, styles):
    """Figma MCP `get_metadata` XML, with strings and colours keyed by node id."""
    root = _figma_xml(open(path, encoding="utf-8").read())
    absolute = _coords_are_absolute(root)
    rx, ry = _attr(root, "x"), _attr(root, "y")
    elements, chrome = [], []
    named_by_layer = 0

    def walk(el, ox, oy, bg, is_root):
        nonlocal named_by_layer
        if el.get("hidden") == "true" or el.get("visible") == "false":
            return
        ident, name = el.get("id", ""), el.get("name", "")
        if is_root:
            ax, ay = 0.0, 0.0
        elif absolute:
            ax, ay = _attr(el, "x") - rx, _attr(el, "y") - ry
        else:
            ax, ay = ox + _attr(el, "x"), oy + _attr(el, "y")
        w, h = _attr(el, "width"), _attr(el, "height")
        if not is_root and CHROME.search(name):
            chrome.append({"name": name, "box": [ax, ay, ax + w, ay + h]})
            return
        style = styles.get(ident) or {}
        fill = parse_color(style.get("fill") or style.get("background"))
        if fill is not None:
            bg = over(fill, bg)
        if el.tag.lower() == "text" or (el.get("type") or "").upper() == "TEXT":
            content = texts.get(ident) or style.get("text") or style.get("content")
            if content is None:
                content, named_by_layer = name, named_by_layer + 1
            if content and content.strip() and w > 0 and h > 0:
                elements.append(_element(content, (ax, ay, ax + w, ay + h), ident,
                                         over(parse_color(style.get("color")), bg), bg))
            return
        for child in el:
            walk(child, ax, ay, bg, False)

    walk(root, 0.0, 0.0, None, True)
    info = {"source": "figma-metadata", "chrome": chrome,
            "text_authority": "design-context" if not named_by_layer else "layer-names",
            "node": root.get("id", "")}
    if named_by_layer:
        info["text_note"] = (
            f"{named_by_layer} text node(s) took their string from the layer name "
            f"because --design-texts/--design-styles had no entry. A renamed layer "
            f"will simply not pair; the text verdict does not depend on it.")
    return elements, (_attr(root, "width"), _attr(root, "height")), info


def design_from_rest(data):
    """Figma REST `GET /v1/files/:key/nodes` JSON — strings, boxes and paints in one."""
    nodes = data.get("nodes")
    if nodes:
        if len(nodes) != 1:
            raise ValueError(f"the node JSON holds {len(nodes)} nodes; fetch one frame")
        doc = next(iter(nodes.values())).get("document")
    else:
        doc = data.get("document")
    if not doc or not doc.get("absoluteBoundingBox"):
        raise ValueError("the node JSON has no frame with a bounding box — pass the "
                         "response of /v1/files/:key/nodes?ids=<one frame>")
    origin = doc["absoluteBoundingBox"]
    elements, chrome = [], []

    def rel(box):
        return (box["x"] - origin["x"], box["y"] - origin["y"],
                box["x"] - origin["x"] + box["width"],
                box["y"] - origin["y"] + box["height"])

    def paint(node, opacity):
        fills = [f for f in (node.get("fills") or []) if f.get("visible", True)]
        if not fills:
            return None, None
        top = fills[-1]
        if top.get("type") != "SOLID" or "color" not in top:
            return "complex", None
        c = top["color"]
        alpha = float(c.get("a", 1.0)) * float(top.get("opacity", 1.0)) * opacity
        return "solid", (c["r"] * 255.0, c["g"] * 255.0, c["b"] * 255.0, alpha)

    def walk(node, bg, opacity, is_root):
        if node.get("visible") is False:
            return
        box = node.get("absoluteBoundingBox")
        if not is_root and CHROME.search(node.get("name", "")):
            if box:
                chrome.append({"name": node.get("name", ""), "box": list(rel(box))})
            return
        opacity *= float(node.get("opacity", 1.0))
        kind, colour = paint(node, opacity)
        if node.get("type") == "TEXT":
            chars = node.get("characters") or ""
            if box and chars.strip():
                render = node.get("absoluteRenderBounds")
                elements.append(_element(
                    chars, rel(box), node.get("id", ""),
                    over(colour, bg) if kind == "solid" else None, bg,
                    rel(render) if render else None))
            return
        if kind == "solid":
            bg = over(colour, bg)
        elif kind == "complex":
            bg = None  # a gradient or an image: no single colour to expect
        for child in node.get("children") or []:
            walk(child, bg, opacity, False)

    walk(doc, None, 1.0, True)
    info = {"source": "figma-rest", "chrome": chrome, "text_authority": "design-context",
            "node": doc.get("id", "")}
    return elements, (origin["width"], origin["height"]), info


def design_from_spec(data):
    items = data.get("elements") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError('a design spec needs an "elements" list')
    elements = []
    for item in items:
        text = item.get("text") or item.get("content") or item.get("characters")
        if not text:
            continue
        if "box" in item:
            x, y, w, h = (float(v) for v in item["box"][:4])
        else:
            x, y = float(item.get("x", 0)), float(item.get("y", 0))
            w = float(item.get("width", item.get("w", 0)))
            h = float(item.get("height", item.get("h", 0)))
        if w <= 0 or h <= 0:
            continue
        bg = over(parse_color(item.get("background") or item.get("fill")), None)
        elements.append(_element(text, (x, y, x + w, y + h), str(item.get("id", "")),
                                 over(parse_color(item.get("color")), bg), bg))
    frame = data.get("frame", {}) if isinstance(data, dict) else {}
    width = float(frame.get("width") or max((e["box"][2] for e in elements), default=0))
    height = float(frame.get("height") or max((e["box"][3] for e in elements), default=0))
    return elements, (width, height), {"source": "spec", "chrome": [],
                                       "text_authority": "design-context", "node": ""}


def load_design(args):
    path = args.design
    if path.lower().endswith(IMAGE_SUFFIXES):
        from layout_audit import elements_from_image
        try:
            found, width, _ = elements_from_image(path, args.ocr_lang, args.ocr_psm)
        except ValueError as exc:
            raise ValueError(
                f"{exc}\nA design IMAGE has to be read with OCR. The exact route needs "
                f"none: pass the Figma get_metadata XML (or node JSON) as --design and "
                f"this image as --design-image.")
        with Image.open(path) as img:
            height = img.size[1]
        unit = (args.design_width_dp / width) if args.design_width_dp else 1.0
        elements = [_element(e["text"], tuple(v * unit for v in e["box"])) for e in found]
        return elements, (width * unit, height * unit), {
            "source": "ocr", "chrome": [], "text_authority": "ocr", "node": ""}

    raw = open(path, encoding="utf-8").read()
    if raw.lstrip().startswith(("{", "[")):
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("schema", "").startswith("ui-ir"):
            raise ValueError(
                "that is a UI-IR file, which keeps layout intent but drops absolute "
                "positions. Pass the raw get_metadata XML it was built from instead.")
        if isinstance(data, dict) and ("nodes" in data or "document" in data):
            return design_from_rest(data)
        return design_from_spec(data)

    def keyed(option):
        if not option:
            return {}
        with open(option, encoding="utf-8") as fh:
            loaded = json.load(fh)
        if not isinstance(loaded, dict):
            raise ValueError(f"{option} must be a JSON object keyed by Figma node id")
        return loaded

    return design_from_metadata(path, keyed(args.design_texts), keyed(args.design_styles))


# -------------------------------------------------------------- actual input

def load_actual(args):
    """On-screen text and boxes, in the hierarchy's own units, plus the screen size."""
    path = args.actual
    if path != "-" and path.lower().endswith(IMAGE_SUFFIXES):
        from layout_audit import elements_from_image
        found, width, _ = elements_from_image(path, args.ocr_lang, args.ocr_psm)
        with Image.open(path) as img:
            height = img.size[1]
        return ([_element(e["text"], e["box"]) for e in found], [],
                (float(width), float(height)), "ocr", [None, None])

    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    if not raw.strip():
        raise ValueError("empty hierarchy dump")
    try:
        nodes = parse_hierarchy(raw)
    except (json.JSONDecodeError, ET.ParseError) as exc:
        raise ValueError(f"could not parse the hierarchy (not valid JSON or XML): {exc}")

    boxed = []
    for node in nodes:
        nums = re.findall(r"-?\d+(?:\.\d+)?", node.bounds or "")
        if len(nums) >= 4:
            boxed.append((node, tuple(float(v) for v in nums[:4])))
    if not boxed:
        raise ValueError("the hierarchy carried no usable bounds")

    # The screen is the largest box anchored at the origin. "Furthest right edge"
    # is wrong: a pager's next page sits beyond the screen and would double it.
    area = lambda b: max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])  # noqa: E731
    rooted = [b for _, b in boxed if abs(b[0]) < 1 and abs(b[1]) < 1]
    screen = max(rooted or [b for _, b in boxed], key=area)
    sw, sh = screen[2], screen[3]

    # iOS reports visible copy as an accessibility label, not as `text`.
    use_label = args.include_accessibility or not any(n.text or n.hint for n, _ in boxed)
    found = []
    for node, (l, t, r, b) in boxed:
        value = node.text or node.hint or (node.desc if use_label else "")
        if not value or not value.strip():
            continue
        l, t, r, b = max(0.0, l), max(0.0, t), min(sw, r), min(sh, b)
        if r - l < 1 or b - t < 1:
            continue  # off screen, or collapsed
        found.append(_element(value, (l, t, r, b), node.rid or ""))

    # A merged parent repeats its child's string over a larger box; keep the tightest.
    found.sort(key=lambda e: area(e["box"]))
    kept = []
    for el in found:
        l, t, r, b = el["box"]
        if any(o["key"] == el["key"] and l <= o["box"][0] + 1 and t <= o["box"][1] + 1
               and r >= o["box"][2] - 1 and b >= o["box"][3] - 1 for o in kept):
            continue
        kept.append(el)
    kept.sort(key=lambda e: (e["box"][1], e["box"][0]))
    # The top sliver is the OS status bar: clock, battery, carrier.
    chrome = [e for e in kept if e["box"][3] <= sh * 0.05]
    content = [e for e in kept if e["box"][3] > sh * 0.05]

    # Android's DecorView names the bars it reserves, which is the one honest
    # source for where the app's own area starts and ends.
    insets = [None, None]
    for node, (l, t, r, b) in boxed:
        if node.rid == "statusBarBackground" and t <= 1 and 0 < b <= sh * 0.12:
            insets[0] = b
        elif node.rid == "navigationBarBackground" and b >= sh - 1 and sh - t <= sh * 0.12:
            insets[1] = sh - t
    return content, chrome, (sw, sh), "hierarchy", insets


# ------------------------------------------------------------------- pairing

def pair_elements(design, actual, frame, screen):
    """Pair elements by the string they carry, settling repeats by position.

    A string that appears once on each side is an identity and is claimed
    outright, however far the element has moved — a moved element is exactly
    what this check exists to find. Those pairs then calibrate where everything
    else should be, which is what lets a repeated label ("View all" twice, a
    price on every card) and a near-miss string be matched to the right
    instance instead of to the first one in the list.
    """
    by_d, by_a = defaultdict(list), defaultdict(list)
    for i, e in enumerate(design):
        by_d[e["key"]].append(i)
    for j, e in enumerate(actual):
        by_a[e["key"]].append(j)

    def centre(e):
        box = e["dp"]
        return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0

    pairs = {}
    for key, ds in by_d.items():
        matches = by_a.get(key, [])
        if len(ds) == 1 and len(matches) == 1:
            pairs[ds[0]] = (matches[0], 1.0, "exact")

    def predict(y):
        known = sorted((centre(design[d])[1], centre(actual[a])[1])
                       for d, (a, _, _) in pairs.items())
        if not known:
            return y * screen[1] / frame[1] if frame[1] else y
        if y <= known[0][0]:
            return known[0][1] + (y - known[0][0])
        if y >= known[-1][0]:
            return known[-1][1] + (y - known[-1][0])
        for (y0, t0), (y1, t1) in zip(known, known[1:]):
            if y0 <= y <= y1:
                return t0 + (t1 - t0) * ((y - y0) / (y1 - y0) if y1 > y0 else 0.0)
        return y

    x_scale = screen[0] / frame[0] if frame[0] else 1.0

    def distance(d, a):
        (dx, dy), (ax, ay) = centre(design[d]), centre(actual[a])
        return abs(predict(dy) - ay) + 0.5 * abs(dx * x_scale - ax)

    used = {a for a, _, _ in pairs.values()}
    for key, ds in by_d.items():
        options = [(distance(d, a), d, a) for d in ds if d not in pairs
                   for a in by_a.get(key, []) if a not in used]
        for _, d, a in sorted(options):
            if d not in pairs and a not in used:
                pairs[d] = (a, 1.0, "exact (repeated string, matched by position)")
                used.add(a)

    window = max(60.0, 0.12 * screen[1])
    options = []
    for d, e in enumerate(design):
        if d in pairs or len(e["key"]) < 4:
            continue
        for a, other in enumerate(actual):
            if a in used or len(other["key"]) < 4:
                continue
            ratio = difflib.SequenceMatcher(None, e["key"], other["key"]).ratio()
            if ratio >= 0.75 and abs(predict(centre(e)[1]) - centre(other)[1]) <= window:
                options.append((-ratio, distance(d, a), d, a))
    for neg, _, d, a in sorted(options):
        if d not in pairs and a not in used:
            pairs[d] = (a, round(-neg, 3), "similar string near the expected position")
            used.add(a)

    # Dynamic text has no string in common with the mock — a plant name, a file
    # size — but it still sits in a designed slot. When the same number of
    # unclaimed elements lies between the same two anchors on both sides, they
    # are the same slots in the same order. That is an inference about identity,
    # not a fact, so everything measured on these pairs is reported as a lead.
    def reading(elements):
        return sorted(range(len(elements)),
                      key=lambda i: (elements[i]["dp"][1], elements[i]["dp"][0]))

    order_d, order_a = reading(design), reading(actual)
    where_a = {a: k for k, a in enumerate(order_a)}
    fixed = [(k, d) for k, d in enumerate(order_d) if d in pairs]
    for (k0, d0), (k1, d1) in zip(fixed, fixed[1:]):
        j0, j1 = where_a[pairs[d0][0]], where_a[pairs[d1][0]]
        between_d = order_d[k0 + 1:k1]
        between_a = [a for a in order_a[j0 + 1:j1] if a not in used]
        if j1 <= j0 or len(between_a) != j1 - j0 - 1:
            continue  # the anchors are not neighbours on screen too
        if between_d and len(between_d) == len(between_a) <= 3:
            for d, a in zip(between_d, between_a):
                pairs[d] = (a, 0.0, SLOT)
                used.add(a)
    return pairs


# ------------------------------------------------------------------- spacing

def _gap(label, above, anchor, want, got, lead, tol, spans):
    delta = got - want
    return {
        "between": label, "above": above, "below": anchor["n"],
        "design": round(want, 1), "actual": round(got, 1), "delta": round(delta, 1),
        "flagged": bool(abs(delta) > tol and not lead),
        "advisory": bool(abs(delta) > tol and lead),
        "note": f"a lead, not a measurement: {lead}" if lead and abs(delta) > tol else None,
        "_spans": spans,
    }


def vertical_gaps(design, actual, anchors, tol, d_top, a_top):
    """The gap above each anchor, measured to its nearest neighbour above.

    The first element has no neighbour, only the top of the app's own area —
    which is measurable when both sides say where that is (the mock's status-bar
    layer, the device's `statusBarBackground`), and is left alone otherwise
    rather than compared across two different status bars.
    """
    by_design = {a["design_index"]: a for a in anchors}
    unpaired_actual = [e for j, e in enumerate(actual)
                       if j not in {a["actual_index"] for a in anchors}]
    gaps, skipped = [], []
    if anchors and d_top is not None and a_top is not None:
        first = min(anchors, key=lambda a: a["design_box"][1])
        top = first["design_box"][1]
        if not any(e["dp"][3] <= top + 1.0 for i, e in enumerate(design)
                   if i != first["design_index"]):
            gaps.append(_gap(f"(top of content) -> {first['label']}", None, first,
                             top - d_top, first["actual_box"][1] - a_top,
                             first["lead"], tol,
                             ((d_top, top), (a_top, first["actual_box"][1]))))
    for anchor in sorted(anchors, key=lambda a: a["design_box"][1]):
        below = anchor["design_box"]
        above = [(i, e) for i, e in enumerate(design)
                 if i != anchor["design_index"] and e["dp"][3] <= below[1] + 1.0]
        if not above:
            continue
        nearest = max(e["dp"][3] for _, e in above)
        close = [(i, e) for i, e in above if nearest - e["dp"][3] <= 2.0]
        overlapping = [(i, e) for i, e in close
                       if min(e["dp"][2], below[2]) - max(e["dp"][0], below[0]) > 0]
        index, neighbour = max(overlapping or close, key=lambda item: item[1]["dp"][3])
        other = by_design.get(index)
        label = f"{other['label'] if other else neighbour['text'][:32]} -> {anchor['label']}"
        if other is None:
            skipped.append({"between": label, "reason":
                            "the design's neighbour above has no counterpart on screen "
                            "(dynamic content, or missing) — not a fixed spacing"})
            continue
        box_above, box_below = other["actual_box"], anchor["actual_box"]
        blockers = [u["text"] for u in unpaired_actual
                    if box_above[3] - 1.0 <= (u["dp"][1] + u["dp"][3]) / 2.0
                    <= box_below[1] + 1.0]
        if blockers:
            skipped.append({"between": label, "reason":
                            f"on-screen text with no design counterpart sits inside this "
                            f"gap ({', '.join(repr(b[:24]) for b in blockers[:3])}) — "
                            f"dynamic content, not a fixed spacing"})
            continue
        gaps.append(_gap(label, other["n"], anchor, below[1] - neighbour["dp"][3],
                         box_below[1] - box_above[3],
                         other["lead"] or anchor["lead"], tol,
                         ((neighbour["dp"][3], below[1]), (box_above[3], box_below[1]))))
    return gaps, skipped


def excuse_flexible(gaps, anchors, frame, screen, tol, d_bottom, a_bottom):
    """Demote gaps the layout is *allowed* to stretch.

    A design frame is one viewport showing one data state; the device is another
    viewport showing another. Whatever the layout pins to the bottom edge (a
    CTA, a tab bar) or centres keeps its place, and the difference — a taller
    screen, a shorter list — lands in the gap above it. That is correct
    behaviour, and failing on it would fail every non-scrolling screen on every
    device that is not the mock's.

    The excuse needs evidence: the element below must hold its distance from
    the bottom edge (or the centre) far better than it holds the gap. An
    element that simply slid down by the size of the gap's error has not held
    anything, and stays a failure. The excused gap stays in the report as an
    advisory.
    """
    # The bottom edge of the app's own area, when both sides say where it is.
    # When either does not, the raw screen edge has to do, with slack for a mock
    # home indicator and a real navigation bar being different heights.
    known = d_bottom is not None and a_bottom is not None
    slack = 0.0 if known else FLEX_SLACK_DP
    d_floor = frame[1] - (d_bottom if known else 0.0)
    a_floor = screen[1] - (a_bottom if known else 0.0)
    by_n = {a["n"]: a for a in anchors}
    for gap in gaps:
        if not gap["flagged"]:
            continue
        d, a = by_n[gap["below"]]["design_box"], by_n[gap["below"]]["actual_box"]
        held = 0.5 * abs(gap["delta"])
        bottom_shift = (a_floor - a[3]) - (d_floor - d[3])
        centre_shift = ((a[1] + a[3]) / 2.0 - screen[1] / 2.0) - (
            (d[1] + d[3]) / 2.0 - frame[1] / 2.0)
        if abs(bottom_shift) <= min(tol + slack, held):
            reason = f"holds its distance from the bottom edge ({bottom_shift:+.0f} dp)"
        elif abs(centre_shift) <= min(tol, held):
            reason = f"holds its distance from the screen's centre ({centre_shift:+.0f} dp)"
        else:
            continue
        gap["flagged"], gap["advisory"], gap["flexible"] = False, True, True
        gap["note"] = (
            f"the element below {reason} while this gap changed by {gap['delta']:+g}, so "
            f"this is where flexible space lands — a taller screen or a shorter list. "
            f"Confirm in the image that it is a spacer or weight, not a fixed value.")


def horizontal_insets(anchors, frame, screen, tol):
    """Where each anchor sits across the screen, under every alignment it could have.

    Text is never the same width twice — a different font, a different wrap — so
    an end-aligned price's left edge and a centred title's edges both move for
    reasons that are not layout. An anchor is misplaced only when no reading the
    design supports explains where it is: pinned to the start, or at the same
    fraction of a wider screen — and, where the design suggests it, pinned to
    the end or centred.

    Those last two are offered only on the design's evidence, because offered
    to everything they explain away the most common inset bug there is. On a
    screen 20 dp wider than the mock the centre sits 10 dp further right, so a
    start-aligned title pushed in by 12 dp reads as perfectly centred; and a
    label whose font renders a little narrower keeps its right edge while its
    left edge moves. So "centred" needs the design to centre the element, and
    "end" needs it to live in the far half of the frame.
    """
    out = []
    for a in anchors:
        d, s = a["design_box"], a["actual_box"]
        left = s[0] - d[0]
        right = (screen[0] - s[2]) - (frame[0] - d[2])
        fits = {"start": left,
                "proportional": (s[0] / screen[0] - d[0] / frame[0]) * frame[0]}
        if d[0] >= frame[0] / 2.0:
            fits["end"] = right
        if abs(d[0] - (frame[0] - d[2])) <= 4.0:
            fits["centre"] = ((s[0] + s[2]) / 2.0 - screen[0] / 2.0) - (
                (d[0] + d[2]) / 2.0 - frame[0] / 2.0)
        best = min(fits, key=lambda k: abs(fits[k]))
        over_tol = abs(fits[best]) > tol
        measured = not a["lead"]
        out.append({
            "element": a["label"], "n": a["n"],
            "left": {"design": round(d[0], 1), "actual": round(s[0], 1),
                     "delta": round(left, 1)},
            "right": {"design": round(frame[0] - d[2], 1),
                      "actual": round(screen[0] - s[2], 1), "delta": round(right, 1)},
            "best_fit": best, "deviation": round(fits[best], 1),
            "flagged": bool(over_tol and measured),
            "advisory": bool(over_tol and not measured),
            "note": f"a lead, not a measurement: {a['lead']}" if over_tol and a["lead"] else None,
        })
    return out


# ------------------------------------------------------------------ annotate

def annotate(path, dimg, aimg, frame, screen, design, anchors, gaps, insets, colours,
             text_marks, title):
    from spacing_audit import _load_font

    ppd = 640.0 / frame[0]
    font = _load_font(15)
    small = _load_font(13)
    red, green, amber, grey = (225, 45, 45), (30, 160, 80), (230, 140, 0), (120, 120, 120)

    def panel(img, size_dp):
        size = (int(round(size_dp[0] * ppd)), int(round(size_dp[1] * ppd)))
        if img is None:
            return Image.new("RGB", size, (246, 246, 246))
        return img.convert("RGB").resize(size, Image.LANCZOS)

    left, right = panel(dimg, frame), panel(aimg, screen)
    dl, dr = ImageDraw.Draw(left, "RGBA"), ImageDraw.Draw(right, "RGBA")

    def px(box):
        return [v * ppd for v in box]

    def label(draw, xy, text, colour, fnt=small, anchor="la"):
        box = draw.textbbox(xy, text, font=fnt, anchor=anchor)
        draw.rectangle([box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2], fill=(255, 255, 255, 225))
        draw.text(xy, text, font=fnt, fill=colour, anchor=anchor)

    bad, soft = set(), set()
    for g in gaps:
        (bad if g["flagged"] else soft if g["advisory"] else set()).add(g["below"])
    for i in insets:
        (bad if i["flagged"] else soft if i["advisory"] else set()).add(i["n"])
    for c in colours:
        (bad if c["flagged"] else soft if c.get("advisory") else set()).add(c.get("n"))
    bad |= set(text_marks)

    if dimg is None:
        for e in design:
            dl.rectangle(px(e["dp"]), outline=grey + (255,))
            dl.text((e["dp"][0] * ppd + 2, e["dp"][1] * ppd), e["text"][:28], font=small, fill=(60, 60, 60))
    for a in anchors:
        colour = red if a["n"] in bad else amber if a["n"] in soft else green
        for draw, box in ((dl, a["design_box"]), (dr, a["actual_box"])):
            x0, y0, x1, y1 = px(box)
            draw.rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2], outline=colour + (255,),
                           width=2 if a["n"] in bad else 1)
            draw.text((x0 - 4, y0 - 2), str(a["n"]), font=small, fill=colour, anchor="rs")

    by_n = {a["n"]: a for a in anchors}
    for g in gaps:
        if not (g["flagged"] or g["advisory"]):
            continue
        colour = red if g["flagged"] else amber
        down = by_n[g["below"]]
        for draw, key, span, text in (
                (dl, "design_box", g["_spans"][0], f"{g['design']:g}"),
                (dr, "actual_box", g["_spans"][1],
                 f"{g['actual']:g} (design {g['design']:g}, {g['delta']:+g})")):
            x = (down[key][0] + min(down[key][2], down[key][0] + 60)) / 2.0 * ppd
            y0, y1 = span[0] * ppd, span[1] * ppd
            draw.rectangle([x - 1, min(y0, y1), x + 1, max(y0, y1)], fill=colour + (255,))
            for y in (y0, y1):
                draw.line([(x - 7, y), (x + 7, y)], fill=colour + (255,), width=2)
            label(draw, (x + 10, (y0 + y1) / 2.0), text, colour, anchor="lm")
    for i in insets:
        if not (i["flagged"] or i["advisory"]):
            continue
        colour = red if i["flagged"] else amber
        a = by_n[i["n"]]
        x0, y0, x1, y1 = px(a["actual_box"])
        dr.line([(0, (y0 + y1) / 2.0), (x0, (y0 + y1) / 2.0)], fill=colour + (255,), width=2)
        label(dr, (4, y1 + 3),
              f"left {i['left']['actual']:g} (design {i['left']['design']:g})", colour)
    seen = set()
    for c in colours:
        if not (c["flagged"] or c.get("advisory")) or c.get("n") not in by_n:
            continue
        a = by_n[c["n"]]
        x0, y0, x1, y1 = px(a["actual_box"])
        slot = (c["n"], c["part"])
        if slot in seen:
            continue
        seen.add(slot)
        x = x1 + 8 if x1 + 150 < right.size[0] else max(4, x0 - 150)
        y = y0 - 2 if c["part"] == "text" else y1 + 2
        for k, value in enumerate(c["_rgb"]):
            dr.rectangle([x + k * 18, y, x + k * 18 + 16, y + 16],
                         fill=tuple(int(v) for v in value) + (255,), outline=(0, 0, 0, 255))
        label(dr, (x + 40, y + 1), f"{c['part']} {c['similarity'] * 100:.0f}%",
              red if c["flagged"] else amber)
    for n in text_marks:
        a = by_n.get(n)
        if a:
            x0, y0, x1, y1 = px(a["actual_box"])
            label(dr, (x0, y0 - 18), "text differs", red)

    head, foot, gutter = 46, 30, 16
    canvas = Image.new("RGB", (left.size[0] + right.size[0] + gutter,
                               max(left.size[1], right.size[1]) + head + foot), (24, 24, 24))
    canvas.paste(left, (0, head))
    canvas.paste(right, (left.size[0] + gutter, head))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 6), f"DESIGN  {frame[0]:g} x {frame[1]:g} dp", font=font, fill=(255, 255, 255))
    draw.text((left.size[0] + gutter + 8, 6),
              f"ACTUAL  {screen[0]:.0f} x {screen[1]:.0f} dp", font=font, fill=(255, 255, 255))
    draw.text((8, 26), title[:150], font=small, fill=(255, 210, 120))
    draw.text((8, canvas.size[1] - foot + 8),
              "green: within tolerance    red: outside tolerance    amber: advisory    "
              "numbers: anchors[].n in the JSON    gaps in dp: actual (design, delta)",
              font=small, fill=(200, 200, 200))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    canvas.save(path)


# ------------------------------------------------------------------ pipeline

def resolve_units(args, frame, hier, dimg, aimg, notes):
    """Scale factors that put both sides in dp.

    The design is already in dp: a Figma frame's own units. The device is pixels
    over density — and density has to be given, because a 1080 px wide screen is
    360, 393 or 411 dp depending on a number that is in neither the screenshot
    nor the hierarchy.
    """
    u = SimpleNamespace()
    u.d_scale = dimg.size[0] / frame[0] if dimg else 1.0      # design image px per dp
    if dimg and abs(dimg.size[1] / u.d_scale - frame[1]) > 2.0:
        notes.append(f"the design image is {dimg.size[0]}x{dimg.size[1]} px, which is not "
                     f"the {frame[0]:g}x{frame[1]:g} frame at any one scale — boxes may "
                     f"not line up with it. Export exactly the frame the data describes.")
    u.shot_per_unit = 1.0                                     # screenshot px per hierarchy unit
    if aimg:
        u.shot_per_unit = aimg.size[0] / hier[0]
        if abs(u.shot_per_unit - round(u.shot_per_unit)) < 0.03:
            u.shot_per_unit = float(round(u.shot_per_unit))
    if args.density:
        u.density = args.density / 160.0 if args.density > 10 else args.density
        u.density_source = "--density"
    elif u.shot_per_unit >= 1.5:
        u.density, u.density_source = u.shot_per_unit, "hierarchy is in points (iOS)"
    else:
        u.density, u.density_source = hier[0] * u.shot_per_unit / frame[0], "assumed"
        notes.append(
            "no --density given, so the device was ASSUMED to be as wide in dp as the "
            f"design frame ({frame[0]:g}). If it is not, every fixed spacing is scaled by "
            "the difference. Pass --density from `adb shell wm density`.")
    u.unit_per_dp = u.density / u.shot_per_unit               # hierarchy units per dp
    u.screen = (hier[0] / u.unit_per_dp, hier[1] / u.unit_per_dp)
    return u


def _insets(option):
    if not option:
        return None
    try:
        top, bottom = (float(v) for v in option.split(","))
    except ValueError:
        raise ValueError(f"expected TOP,BOTTOM in dp, got {option!r}")
    return [top, bottom]


def build_anchors(design, actual, pairs, u, dimg, aimg):
    """Turn pairs into anchors, reducing both boxes of each to glyph ink."""
    ink_mode = bool(aimg and (dimg or all(design[d].get("ink") for d in pairs)))
    anchors = []
    order = sorted(pairs, key=lambda i: (design[i]["box"][1], design[i]["box"][0]))
    for n, d in enumerate(order, 1):
        a, score, how = pairs[d]
        de, ae = design[d], actual[a]
        slot = how == SLOT
        anchor = {
            "n": n, "text": de["text"], "actual_text": ae["text"],
            "label": (de["text"][:32] if not slot else
                      f"{de['text'][:20]} (on screen: {ae['text'][:20]})"),
            "text_matches": de["text"] == ae["text"], "similarity": score,
            "pairing": how, "slot": slot,
            "element_id": ae["id"] or None, "design_id": de["id"] or None,
            "design_index": d, "actual_index": a, "boxes": "layout",
            "design_box": de["dp"], "actual_box": ae["dp"]}
        if ink_mode:
            d_ink = a_ink = None
            if dimg:
                rough = sample(dimg, tuple(v * u.d_scale for v in de["box"]), colors=False)
                if rough and rough["ink_box"]:
                    d_ink = tuple(v / u.d_scale for v in rough["ink_box"])
            elif de.get("ink"):
                d_ink = de["ink"]
            a_px = tuple(v * u.shot_per_unit for v in ae["box"])
            rough = sample(aimg, a_px, colors=False)
            if d_ink and rough and rough["ink_box"]:
                want = ((d_ink[2] - d_ink[0]) * u.density, (d_ink[3] - d_ink[1]) * u.density)
                found = rough["ink_box"]
                if not _plausible(found, want, not slot):
                    # One line of this text, in device px, from the design's own render.
                    line = want[1]
                    if dimg:
                        d_px = tuple(v * u.d_scale for v in d_ink)
                        line = line_height(dimg, d_px, sample(dimg, d_px, colors=False)["bg"])
                        line *= u.density / u.d_scale
                    located = text_ink(aimg, a_px, rough["bg"], line, want[0], u.density,
                                       not slot)
                    found = None
                    if located:
                        found, lines = located
                        was = max(1, int(round(want[1] / (1.35 * line))))
                        if lines != was:
                            anchor["wraps"] = {"design_lines": was, "actual_lines": lines}
                        elif not _plausible(found, want, not slot):
                            found = None
                if found:
                    a_ink = tuple(v / u.density for v in found)
                else:
                    anchor["box_note"] = (
                        "the on-screen box holds more than this text and its glyphs could "
                        "not be isolated — spacing here is a lead, not a measurement")
            if d_ink and a_ink:
                anchor.update(boxes="ink", design_box=d_ink, actual_box=a_ink)
                de["dp"] = d_ink
        # Why a reading on this anchor is a lead rather than a measurement.
        anchor["lead"] = (
            "paired by position, not by text — confirm in the image that both sides "
            "are the same element" if slot else
            None if anchor["boxes"] == "ink" else
            "a layout box, not glyph ink")
        anchors.append(anchor)
    return anchors, ink_mode


def check_text(static, degraded, ignore, design, actual, anchors, info, hier, aimg, u,
               findings, advisories):
    """Criterion 1 — every static string renders exactly."""
    text = {"status": "SKIPPED", "checked": 0, "exact": 0, "mismatched": [], "missing": [],
            "defects": [], "not_rendered": [], "not_in_design": []}
    marks = []
    on_screen = [{"text": e["text"], "bounds": e["box"], "source": "text", "id": e["id"]}
                 for e in actual]
    by_actual = {a["actual_index"]: a for a in anchors}
    for defect in find_defects(on_screen, hier, degraded):
        if defect["type"] == "untranslated_key":
            # A lead, not a failure: `home.title` and `report.pdf` have the same
            # shape. A real leaked key also leaves its static string missing,
            # and that is what fails the case.
            text["defects"].append(defect)
            advisories.append({"check": "text", "element": defect["text"], "message":
                               f'"{defect["text"]}" has the shape of a translation key '
                               f"that leaked to the UI (or is a file name / domain)"})
        elif defect["type"] == "truncated":
            advisories.append({"check": "text", "element": defect["text"], "message":
                               f'"{defect["text"]}" arrives already ellipsized. Fine for '
                               f"API data, a defect for static copy."})
    if not static:
        text["note"] = ("no --static-texts given, so copy was not gated. Pass the plan's "
                        "static strings for this screen.")
        for a in anchors:
            if not a["text_matches"] and not a["slot"]:
                advisories.append({"check": "text", "element": a["text"], "message":
                                   f'design says "{a["text"]}", screen says '
                                   f'"{a["actual_text"]}". Add it to --static-texts if '
                                   f"this copy is fixed."})
        return text, marks

    expected = [_collapse_space(s) for s in static]
    results, extra, ignored = match(expected, on_screen, [re.compile(p) for p in ignore])
    text.update(status="PASS", checked=len(expected), extra_on_screen=extra,
                ignored_as_dynamic=ignored)
    design_texts = {e["text"] for e in design}
    for want, result in zip(expected, results):
        if result["status"] == "exact":
            text["exact"] += 1
            if aimg:
                # The hierarchy proves the string is right, not that it is drawn.
                seen = sample(aimg, tuple(v * u.shot_per_unit
                                          for v in actual[result["node"]]["box"]),
                              colors=False)
                if seen and not seen["ink_box"]:
                    text["not_rendered"].append(want)
                    advisories.append({"check": "text", "element": want, "message":
                                       f'"{want}" is in the hierarchy but no glyph pixels '
                                       f"were found in its box — check it is actually "
                                       f"visible"})
        elif result["status"] == "mismatch":
            node = on_screen[result["node"]]
            kind = result["difference"]
            decidable = (not degraded) or kind in OCR_DECIDABLE
            text["mismatched"].append({
                "expected": want, "actual": node["text"], "difference": kind,
                "element_id": node["id"] or None, "decidable": decidable,
                "alternative_match": result.get("alternative_match")})
            entry = {"check": "text", "element": want, "message":
                     f'"{want}" renders as "{node["text"]}" — {kind}'
                     + (f' (id {node["id"]})' if node["id"] else "")}
            if decidable:
                findings.append(entry)
                if result["node"] in by_actual:
                    marks.append(by_actual[result["node"]]["n"])
            else:
                entry["message"] += " — OCR cannot settle this; read it from the hierarchy"
                advisories.append(entry)
        else:
            text["missing"].append(want)
            findings.append({"check": "text", "element": want,
                             "message": f'"{want}" is not on screen'})
        if info["text_authority"] == "design-context" and want not in design_texts:
            close = difflib.get_close_matches(want, list(design_texts), 1, 0.6)
            text["not_in_design"].append(want)
            advisories.append({"check": "text", "element": want, "message":
                               f'the plan lists "{want}" but the design frame has no such '
                               f"text" + (f' (closest: "{close[0]}")' if close else "")
                               + " — one of the two is out of date"})
    if any(f["check"] == "text" for f in findings):
        text["status"] = "FAIL"
    return text, marks


def check_colour(design, actual, anchors, dimg, aimg, u, threshold, findings, advisories):
    """Criterion 2 — text colour and the fill behind it, per anchor."""
    colour = {"status": "SKIPPED", "checked": 0, "passed": 0, "comparisons": [],
              "not_comparable": []}
    if not aimg:
        colour["note"] = "needs --actual-image: colours are read from the screenshot"
        return colour
    for a in anchors:
        de = design[a["design_index"]]
        d_read = None
        if a["boxes"] == "ink":
            a_read = sample(aimg, tuple(v * u.density for v in a["actual_box"]),
                            PAD_DP * u.density)
            if dimg:
                d_read = sample(dimg, tuple(v * u.d_scale for v in a["design_box"]),
                                PAD_DP * u.d_scale)
        else:
            a_read = sample(aimg, tuple(v * u.shot_per_unit
                                        for v in actual[a["actual_index"]]["box"]))
            if dimg:
                d_read = sample(dimg, tuple(v * u.d_scale for v in de["box"]))
        if not a_read:
            continue
        if not a_read["flat"] or (d_read and not d_read["flat"]):
            colour["not_comparable"].append({
                "element": a["label"], "n": a["n"],
                "reason": "sits on an image or gradient, not a flat fill"})
            continue
        for part, spec, key in (("text", de["color"], "fg"),
                                ("background", de["background"], "bg")):
            got = a_read[key]
            refs = []
            if spec is not None:
                refs.append(("design data", spec))
            if d_read and d_read[key] is not None:
                refs.append(("design render", d_read[key]))
            if got is None or not refs:
                continue
            # The design data is the intent, so it is judged first. The render is
            # the fallback for what the data cannot express — a layer opacity, an
            # overlay — where the exported pixels are the truth.
            source, want = refs[0]
            score = color_similarity(want, got)
            if score < threshold and len(refs) == 2:
                other = color_similarity(refs[1][1], got)
                if other >= threshold:
                    (source, want), score = refs[1], other
            # A colour read off thin glyphs is biased toward the fill. With no
            # exact value from the design data to fall back on, that bias is
            # indistinguishable from a real difference.
            thin = part == "text" and spec is None and (
                a_read["core"] < CORE_MIN or d_read["core"] < CORE_MIN)
            why = ("read off thin glyphs with no exact design value, so the read is "
                   "biased toward the fill — pass --design-styles or a 2x+ design "
                   "export" if thin else
                   "dynamic content paired by position; a state-dependent colour (a "
                   "status, a price) can differ legitimately" if a["slot"] else None)
            colour["comparisons"].append({
                "element": a["label"], "n": a["n"], "part": part,
                "design": hexof(want), "actual": hexof(got),
                "similarity": round(score, 3), "matched_against": source,
                "flagged": bool(score < threshold and not why),
                "advisory": bool(score < threshold and why),
                "note": why if score < threshold else None,
                "_rgb": (want, got),
            })

    checked = colour["comparisons"]
    colour["checked"] = len(checked)
    colour["passed"] = sum(1 for c in checked if c["similarity"] >= threshold)
    if checked:
        colour["mean_similarity"] = round(statistics.mean(c["similarity"] for c in checked), 3)
        colour["min_similarity"] = min(c["similarity"] for c in checked)
    # One wrong token usually shows up on several elements; report it once.
    grouped = defaultdict(list)
    for c in checked:
        if c["flagged"] or c["advisory"]:
            grouped[(c["part"], c["design"], c["actual"], c["flagged"])].append(c)
    for (part, want, got, hard), members in grouped.items():
        names = ", ".join(f'"{m["element"]}"' for m in members[:3])
        if len(members) > 3:
            names += f" and {len(members) - 3} more"
        entry = {"check": "colour", "element": members[0]["element"], "message":
                 f"{'text colour of' if part == 'text' else 'fill behind'} {names}: {got} "
                 f"on screen, design {want} — {members[0]['similarity'] * 100:.0f}% "
                 f"similar (minimum {threshold * 100:.0f}%)"}
        if hard:
            findings.append(entry)
        else:
            entry["message"] += f" — {members[0]['note']}"
            advisories.append(entry)
    colour["status"] = ("FAIL" if any(c["flagged"] for c in checked)
                        else "PASS" if checked else "INCONCLUSIVE")

    if dimg:
        # Everything above is anchored on text. This is the only look at colour
        # that is not — and with photos and live data in the way it can only
        # ever be a lead.
        ours = palette(aimg, 0.06, 0.05)
        loose = []
        for share, rgb in palette(dimg):
            if share < 0.02:
                break
            best = max((color_similarity(rgb, other) for s, other in ours if s >= 0.003),
                       default=0.0)
            if best < threshold:
                loose.append({"design": hexof(rgb), "share_of_design": round(share, 3),
                              "closest_on_screen": round(best, 3)})
        colour["palette_unmatched"] = loose
        for item in loose[:5]:
            advisories.append({"check": "colour", "element": item["design"], "message":
                               f"{item['design']} covers {item['share_of_design'] * 100:.0f}% "
                               f"of the design and nothing on screen is within "
                               f"{threshold * 100:.0f}% of it (closest "
                               f"{item['closest_on_screen'] * 100:.0f}%). Could be an icon, "
                               f"a shape, or a photo — look before filing."})
    return colour


def check_spacing(design, actual, anchors, frame, u, tol, d_insets, a_insets, ink_mode,
                  findings, advisories):
    """Criterion 3 — gaps and insets, in dp."""
    screen = u.screen
    gaps, skipped = vertical_gaps(design, actual, anchors, tol, d_insets[0], a_insets[0])
    excuse_flexible(gaps, anchors, frame, screen, tol, d_insets[1], a_insets[1])
    insets = horizontal_insets(anchors, frame, screen, tol)
    for a in anchors:
        if a.get("wraps"):
            advisories.append({"check": "spacing", "element": a["label"], "message":
                               f'"{a["label"]}" runs to {a["wraps"]["actual_lines"]} '
                               f'line(s) where the design has {a["wraps"]["design_lines"]}. '
                               f"Normal on a narrower screen or with longer copy, and the "
                               f"gaps around it are still measured — check the text is not "
                               f"clipped."})
    for g in gaps:
        entry = {"check": "spacing", "element": g["between"], "message":
                 f"gap {g['between']}: {g['actual']:g} dp, design {g['design']:g} "
                 f"({g['delta']:+g}; tolerance ±{tol:g})"}
        if g["flagged"]:
            findings.append(entry)
        elif g["advisory"]:
            entry["message"] += f" — {g['note']}"
            advisories.append(entry)
    for i in insets:
        side = "right" if i["best_fit"] == "end" else "left"
        entry = {"check": "spacing", "element": i["element"], "message":
                 f'"{i["element"]}" sits {i[side]["actual"]:g} dp from the {side} edge, '
                 f'design {i[side]["design"]:g} ({i[side]["delta"]:+g}; tolerance ±{tol:g})'}
        if i["best_fit"] == "proportional" and abs(screen[0] - frame[0]) > 1.0:
            entry["message"] += (f" — still {i['deviation']:+g} if it scales with the "
                                 f"{screen[0] - frame[0]:+.0f} dp wider screen")
        if i["flagged"]:
            findings.append(entry)
        elif i["advisory"]:
            entry["message"] += f" — {i['note']}"
            advisories.append(entry)
    measured = sum(1 for a in anchors if not a["lead"])
    spacing = {
        "status": ("FAIL" if any(f["check"] == "spacing" for f in findings)
                   else "PASS" if measured >= 2 else "INCONCLUSIVE"),
        "tolerance_dp": tol, "checked": len(gaps) + len(insets),
        "gaps_measured": len(gaps), "anchors_measured": measured,
        "flagged": sum(1 for x in gaps + insets if x["flagged"]),
        "boxes": "ink" if ink_mode else "layout",
        "vertical": gaps, "horizontal": insets, "not_comparable": skipped,
    }
    if not ink_mode:
        spacing["note"] = ("measured on layout boxes because one side has no image. A "
                           "widget box and a Figma text box do not mean the same thing, so "
                           "nothing here can fail. Pass --design-image and --actual-image.")
    return spacing


def judge(anchors, design, text, statuses, findings, advisories):
    """Overall status and the one-line verdict."""
    counts = Counter(f["check"] for f in findings)
    # Evidence sufficiency is settled before any finding gets to speak. A flow
    # that stopped one screen early produces a wall of "missing" strings and
    # mismatched colours, and every one of them is the same non-defect.
    gone = len(text["missing"]) / float(text["checked"]) if text["checked"] else 0.0
    if len(anchors) < 2 or (gone > 0.5 and len(anchors) < 0.34 * len(design)):
        status = "INCONCLUSIVE"
        verdict = (f"INCONCLUSIVE — only {len(anchors)} of the design's {len(design)} text "
                   f"elements were found on screen"
                   + (f", and {len(text['missing'])} of {text['checked']} static strings "
                      f"are missing" if text["checked"] else "")
                   + ". This is the wrong screen or state, or design data for another "
                     "frame — not a list of defects. Fix the flow or the inputs first; "
                     "nothing below is safe to file.")
    elif findings:
        status = "FAIL"
        verdict = ("FAIL — " + ", ".join(f"{counts[k]} {k}"
                                          for k in ("text", "colour", "spacing") if counts[k])
                   + f" outside tolerance across {len(anchors)} paired elements.")
    else:
        status = "PASS"
        verdict = (f"PASS — {len(anchors)} elements paired; "
                   + "; ".join(f"{k} {v}" for k, v in statuses.items()) + ".")
    if advisories:
        verdict += f" {len(advisories)} advisory note(s) to confirm in the image."
    unmeasured = [k for k, v in statuses.items() if v == "INCONCLUSIVE"]
    if status != "INCONCLUSIVE" and unmeasured:
        verdict += f" {', '.join(unmeasured)} could not be measured — see its section."
    return status, verdict


# ---------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(
        description="Gate a screen against its design: exact text, colour similarity, "
                    "spacing in dp.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--design", required=True,
                   help="Figma get_metadata XML, Figma REST node JSON, a design-spec "
                        "JSON, or a design image (OCR, needs tesseract)")
    p.add_argument("--design-image", default=None,
                   help="render of the same frame (Figma get_screenshot). Needed to "
                        "reduce design boxes to glyph ink, and to read colours the "
                        "design data does not carry")
    p.add_argument("--design-texts", default=None,
                   help='{"nodeId": "string"} for a metadata XML (from get_design_context)')
    p.add_argument("--design-styles", default=None,
                   help='{"nodeId": {"color": "#..", "fill": "#..", "text": ".."}} for a '
                        "metadata XML — exact colours instead of sampled ones")
    p.add_argument("--design-width-dp", type=float, default=None,
                   help="logical width of a design IMAGE input that is not 1x")
    p.add_argument("--actual", required=True,
                   help="view-hierarchy dump (Maestro JSON / uiautomator XML), '-' for "
                        "stdin, or a screenshot (OCR)")
    p.add_argument("--actual-image", default=None, help="the screenshot of that same state")
    p.add_argument("--density", type=float, default=None,
                   help="device pixels per dp. Android: `adb shell wm density` (420 or "
                        "2.625 both work). iOS is detected. Without it the device is "
                        "assumed to be as wide in dp as the design frame")
    p.add_argument("--design-insets", default=None, metavar="TOP,BOTTOM",
                   help="dp the mock gives to the status bar and the home indicator, "
                        "when its chrome layers are not named so (default: detected)")
    p.add_argument("--actual-insets", default=None, metavar="TOP,BOTTOM",
                   help="dp the device gives to the status bar and the navigation bar, "
                        "when the hierarchy does not say (default: detected)")
    p.add_argument("--static-texts", default=None,
                   help="the plan's static copy for this screen: JSON array or one string "
                        "per line. Omit and text is not gated")
    p.add_argument("--ignore", action="append", default=[], metavar="REGEX",
                   help="on-screen text matching this is dynamic (repeatable)")
    p.add_argument("--spacing-tolerance", type=float, default=8.0,
                   help="allowed spacing difference in dp (default 8)")
    p.add_argument("--color-threshold", type=float, default=0.80,
                   help="minimum colour similarity, 0-1 (default 0.80)")
    p.add_argument("--include-accessibility", action="store_true",
                   help="also read accessibility labels as on-screen text")
    p.add_argument("--ocr-lang", default="eng")
    p.add_argument("--ocr-psm", type=int, default=4)
    p.add_argument("--out", default=None, help="write the full JSON here")
    p.add_argument("--annotate", default=None,
                   help="write the side-by-side evidence image here")
    p.add_argument("--verbose", action="store_true", help="print the full JSON to stdout")
    args = p.parse_args()

    images = [args.design_image, args.actual_image, args.annotate]
    images += [x for x in (args.design, args.actual) if x.lower().endswith(IMAGE_SUFFIXES)]
    if Image is None and any(images):
        sys.stderr.write("ERROR: Pillow is required to read images (pip3 install Pillow)\n")
        return 2

    def image_for(explicit, fallback):
        path = explicit or (fallback if fallback.lower().endswith(IMAGE_SUFFIXES) else None)
        return Image.open(path).convert("RGB") if path else None

    try:
        design, frame, info = load_design(args)
        actual, actual_chrome, hier, actual_src, bars = load_actual(args)
        static, static_src = (load_expected(args.static_texts, args.ocr_lang, args.ocr_psm)
                              if args.static_texts else ([], None))
        given_d, given_a = _insets(args.design_insets), _insets(args.actual_insets)
        dimg = image_for(args.design_image, args.design)
        aimg = image_for(args.actual_image, args.actual)
        if not frame[0] or not frame[1]:
            raise ValueError("the design carries no frame size")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2

    notes = []
    u = resolve_units(args, frame, hier, dimg, aimg, notes)
    for e in design:
        e["dp"] = e["box"]
    for e in actual + actual_chrome:
        e["dp"] = tuple(v / u.unit_per_dp for v in e["box"])

    # The app's own area: below the status bar, above the navigation bar.
    tops = [c["box"][3] for c in info["chrome"] if c["box"][1] <= 1.0]
    bottoms = [frame[1] - c["box"][1] for c in info["chrome"] if c["box"][3] >= frame[1] - 1.0]
    d_insets = given_d or [max(tops) if tops else None, max(bottoms) if bottoms else None]
    a_insets = given_a or [v / u.unit_per_dp if v is not None else None for v in bars]

    pairs = pair_elements(design, actual, frame, u.screen)
    anchors, ink_mode = build_anchors(design, actual, pairs, u, dimg, aimg)

    findings, advisories = [], []
    text, text_marks = check_text(
        static, actual_src == "ocr" or static_src == "ocr", args.ignore, design, actual,
        anchors, info, hier, aimg, u, findings, advisories)
    colour = check_colour(design, actual, anchors, dimg, aimg, u, args.color_threshold,
                          findings, advisories)
    spacing = check_spacing(design, actual, anchors, frame, u, args.spacing_tolerance,
                            d_insets, a_insets, ink_mode, findings, advisories)
    statuses = {"text": text["status"], "colour": colour["status"],
                "spacing": spacing["status"]}
    status, verdict = judge(anchors, design, text, statuses, findings, advisories)

    if args.annotate:
        annotate(args.annotate, dimg, aimg, frame, u.screen, design, anchors,
                 spacing["vertical"], spacing["horizontal"], colour["comparisons"],
                 text_marks, verdict)
    used_d, used_a = set(pairs), {a for a, _, _ in pairs.values()}
    for c in colour["comparisons"]:
        c.pop("_rgb", None)
    for g in spacing["vertical"]:
        g.pop("_spans", None)
    for a in anchors:
        a.pop("design_index", None)
        a.pop("actual_index", None)
        a["design_box"] = [round(v, 1) for v in a["design_box"]]
        a["actual_box"] = [round(v, 1) for v in a["actual_box"]]

    top_known = d_insets[0] is not None and a_insets[0] is not None
    summary = {
        "verdict": verdict,
        "status": status,
        "criteria": statuses,
        "thresholds": {"text": "exact, static strings only",
                       "colour_min_similarity": args.color_threshold,
                       "spacing_tolerance_dp": args.spacing_tolerance},
        "findings": findings,
        "advisories": advisories,
        "anchors_paired": len(anchors),
        "unit": {"name": "dp", "design_frame": [round(v, 1) for v in frame],
                 "screen": [round(v, 1) for v in u.screen], "density": round(u.density, 3),
                 "density_source": u.density_source,
                 "design_insets_top_bottom": [v if v is None else round(v, 1)
                                              for v in d_insets],
                 "actual_insets_top_bottom": [v if v is None else round(v, 1)
                                              for v in a_insets]},
        "sources": {"design": info["source"], "actual": actual_src,
                    "design_strings": info["text_authority"], "boxes": spacing["boxes"]},
        "notes": notes + ([info["text_note"]] if info.get("text_note") else []),
        "not_measured": "elements without text (icons, images, dividers), font size and "
                        "weight, corner radius, shadows, clipping"
                        + ("" if top_known else
                           ", and the distance from the first element to the top of the "
                           "screen (one side does not say where its status bar ends — "
                           "pass --design-insets / --actual-insets)"),
    }
    if args.annotate:
        summary["annotated"] = args.annotate
    full = dict(summary)
    full.update({
        "text": text, "colour": colour, "spacing": spacing, "anchors": anchors,
        "unpaired_design": [e["text"] for i, e in enumerate(design) if i not in used_d],
        "unpaired_actual": [e["text"] for j, e in enumerate(actual) if j not in used_a],
        "design_chrome": info["chrome"],
    })
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(full, indent=2, ensure_ascii=False))
        summary["detail"] = args.out
        if len(advisories) > 10:  # findings are never trimmed; leads can be
            summary["advisories"] = advisories[:10] + [{
                "check": "-", "element": "-",
                "message": f"{len(advisories) - 10} more advisory note(s) in {args.out}"}]
    print(json.dumps(full if args.verbose or not args.out else summary,
                     indent=2, ensure_ascii=False))
    return {"PASS": 0, "FAIL": 1}.get(status, 3)


if __name__ == "__main__":
    raise SystemExit(main())
