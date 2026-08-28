#!/usr/bin/env python3
"""Compare a design and a build by anchoring on TEXT, then measuring geometry.

WHY THIS EXISTS — the failure it fixes
--------------------------------------
`spacing_audit.py` and `typography_audit.py` find elements by segmenting an
image into horizontal bands of ink, then pair the two sequences by how similar
the bands look. That works on a tidy pair and degrades badly on a real one, in a
way that is expensive rather than merely inaccurate:

  * The pairing is a guess. Bands are matched on height and position, so an
    element that renders at the wrong size stops resembling its own counterpart
    and starts resembling some *other* element that still matches its intended
    size. The measurement is then filed against the wrong element — precise,
    confident, and about the wrong widget.
  * The guess moves when you breathe on it. Change `--roi-bottom` from 39% to
    45% and the same screen pairs differently and reports a different defect.
    Neither run announces that it is fragile.
  * So a human has to referee it, by opening a composite image after every
    parameter change. That loop — run, read JSON, read a 2 MB picture, adjust,
    repeat — is where a one-screen review spends half an hour. The scripts
    themselves take under a second each.

The premise was wrong. Matching *shapes* is guesswork; matching *text* is not.
Both sides of a UI comparison are full of strings, and a string is an identity:
"Popular Plants" in the design is the same element as "Popular Plants" in the
build, whatever size it renders at, wherever it has moved to, and however the
data around it differs. Anchor on that and the alignment problem disappears —
along with every parameter invented to work around it.

WHAT THIS BUYS
--------------
- **No `--roi`, no `--min-gap`, no crop-guessing.** Anchors are found by text,
  so system chrome, a taller status bar, and extra cards simply do not pair and
  drop out. There is nothing left to tune, which is what makes it fast.
- **Pairings you can check by reading them.** Every measurement names the string
  it belongs to. "gap Popular Plants -> Top recommended for you" is auditable in
  the JSON; "gap B2-B3" needed the picture.
- **The same code for a device and for two images.** With a view hierarchy the
  text and the boxes are exact and the result is exact. With images, tesseract
  supplies both at OCR grade and the result says so. One path, stated authority.
- **Typography measured inside a known box.** Cropping to an anchor's own
  rectangle removes the question that made the band approach fragile — whether
  the thing being measured is the thing you meant.

WHAT IT CANNOT DO — say this in the report
------------------------------------------
- It only sees elements that *have* text. An icon row, an image card, or a
  divider has no anchor, so its geometry is not measured here. Those stay with
  the band-based `spacing_audit.py` and with the visual scan.
- Anchors need to survive on both sides. Copy that legitimately differs (live
  data, a translated build) will not pair, and unpaired anchors are reported
  rather than guessed at.
- From images the text is OCR, so a pairing can be wrong where the recognizer
  was. Every anchor carries the similarity it matched at; low ones deserve a
  glance at the crop.

USAGE
-----
  # exact: a device is running (best)
  maestro hierarchy > /tmp/screen.json
  python3 layout_audit.py --design DESIGN.png --actual /tmp/screen.json \\
      --actual-image report/screenshots/TC-010.png --design-width-dp 390

  # image-only: design export vs screenshot, no device
  python3 layout_audit.py --design DESIGN.png --actual ACTUAL.png \\
      --design-width-dp 390 --out report/text/TC-010-layout.json

Prints one JSON with anchors, gaps, heights, margins, and typography, each with
its own `flagged`. Exit 1 when anything is outside tolerance.
Dependencies: Pillow; tesseract only when an input is an image.
"""

import argparse
import difflib
import json
import os
import shutil
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from PIL import Image
except ImportError:
    sys.stderr.write("ERROR: Pillow is required (pip3 install Pillow)\n")
    sys.exit(2)

from filter_hierarchy import parse as parse_hierarchy  # noqa: E402
from text_audit import (  # noqa: E402
    OCR_DECIDABLE,
    _collapse_space,
    _strip_diacritics,
    classify,
)
from typography_audit import (  # noqa: E402
    _solid_level,
    coverage_profile,
    ink_gray,
    ink_mask,
    modal_background,
    stroke_from_coverage,
    subpixel_cores,
)

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


# ------------------------------------------------------------------ elements

def _key(text):
    return _strip_diacritics(_collapse_space(text)).casefold()


def elements_from_hierarchy(path):
    """Exact text and exact boxes, straight from the framework."""
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    try:
        nodes = parse_hierarchy(raw)
    except (json.JSONDecodeError, ET.ParseError) as exc:
        raise ValueError(f"could not parse hierarchy: {exc}")

    import re
    out, width = [], 0
    for node in nodes:
        nums = re.findall(r"-?\d+", node.bounds or "")
        if len(nums) < 4:
            continue
        l, t, r, b = (int(v) for v in nums[:4])
        width = max(width, r)
        if node.text and node.text.strip() and r > l and b > t:
            out.append({"text": node.text.strip(), "box": (l, t, r, b),
                        "id": node.rid or ""})
    if not width:
        raise ValueError("hierarchy carried no usable bounds")
    return out, width, "hierarchy"


def elements_from_image(path, lang, psm, min_conf=40):
    """Text and per-line boxes from tesseract's TSV output.

    The plain-text output would give the strings but not where they are, and
    where they are is half the measurement. TSV costs nothing extra — the
    recognizer already computed the boxes — and it is what lets an image-only
    review anchor on the same identities a device-backed one does.
    """
    binary = shutil.which("tesseract")
    if not binary:
        raise ValueError(
            "reading an image needs tesseract (macOS: brew install tesseract, "
            "plus tesseract-lang for non-English screens)")

    with Image.open(path) as img:
        width = img.size[0]
        source, scale = path, 1.0
        if width < 1000:
            scale = 1000 / float(width)
            up = img.convert("RGB").resize(
                (1000, int(round(img.size[1] * scale))), Image.LANCZOS)
            source = os.path.join(
                os.path.dirname(os.path.abspath(path)), f".layout_audit_{os.path.basename(path)}")
            up.save(source)

    result = subprocess.run(
        [binary, source, "stdout", "--psm", str(psm), "-l", lang, "tsv"],
        capture_output=True, text=True)
    if source != path:
        try:
            os.remove(source)
        except OSError:
            pass
    if result.returncode != 0:
        raise ValueError(f"tesseract failed: {result.stderr.strip()[:300]}")

    rows = result.stdout.splitlines()
    if not rows:
        raise ValueError("tesseract returned nothing")
    header = rows[0].split("\t")
    col = {k: i for i, k in enumerate(header)}

    lines = {}
    for row in rows[1:]:
        cells = row.split("\t")
        if len(cells) < len(header):
            continue
        text = cells[col["text"]].strip()
        try:
            conf = float(cells[col["conf"]])
        except ValueError:
            continue
        if not text or conf < min_conf:
            continue
        ident = tuple(cells[col[k]] for k in ("block_num", "par_num", "line_num"))
        l, t = int(cells[col["left"]]), int(cells[col["top"]])
        r, b = l + int(cells[col["width"]]), t + int(cells[col["height"]])
        entry = lines.setdefault(ident, {"words": [], "box": [l, t, r, b]})
        entry["words"].append(text)
        box = entry["box"]
        box[0], box[1] = min(box[0], l), min(box[1], t)
        box[2], box[3] = max(box[2], r), max(box[3], b)

    # Boxes come back in the upscaled frame; return everything in the file's own
    # pixels so the caller's one scale factor stays the only conversion.
    out = []
    for entry in lines.values():
        l, t, r, b = (int(round(v / scale)) for v in entry["box"])
        out.append({"text": " ".join(entry["words"]), "box": (l, t, r, b), "id": ""})
    out.sort(key=lambda e: (e["box"][1], e["box"][0]))
    return out, width, "ocr"


def load_elements(path, lang, psm):
    if path != "-" and path.lower().endswith(IMAGE_SUFFIXES):
        return elements_from_image(path, lang, psm)
    return elements_from_hierarchy(path)


# ------------------------------------------------------------------- pairing

def _span(elements):
    if not elements:
        return 1.0
    top = min(e["box"][1] for e in elements)
    bottom = max(e["box"][3] for e in elements)
    return max(1.0, bottom - top), top


def pair_by_text(design, actual, min_similarity=0.75, window=0.18):
    """Match elements by what they say, checked against where they are.

    Exact matches are claimed first: an identical string is strong evidence of
    identity, strong enough to survive an element having moved a long way, which
    is exactly the case a design comparison exists to find. Those exact pairs
    then establish how the two layouts sit relative to each other — a device
    with a taller status bar or a looser header pushes everything down by some
    offset, and the median offset across confident pairs measures it without
    anyone having to declare it.

    Fuzzy matches are then held to that alignment. Without this, similarity
    alone decides, and a short or repeated label ("Explore", "View all", a
    price) can pair with a different instance of itself on the far side of the
    screen — producing a named, plausible, entirely fictional measurement. The
    window is deliberately wide: an element displaced by a real spacing bug must
    still pair, or the tool would hide the defect it is looking for. It is only
    narrow enough to reject a match that would have to have crossed the screen.
    """
    used, pairs = set(), []
    keys_a = [_key(e["text"]) for e in actual]

    for i, d in enumerate(design):
        kd = _key(d["text"])
        for j, ka in enumerate(keys_a):
            if j in used or ka != kd:
                continue
            pairs.append({"design": i, "actual": j, "similarity": 1.0,
                          "position_check": "exact string"})
            used.add(j)
            break

    span_d, origin_d = _span(design)
    span_a, origin_a = _span(actual)

    def rel(e, span, origin):
        return (e["box"][1] - origin) / span

    offsets = [rel(actual[p["actual"]], span_a, origin_a)
               - rel(design[p["design"]], span_d, origin_d) for p in pairs]
    offset = statistics.median(offsets) if len(offsets) >= 2 else 0.0
    anchored = len(offsets) >= 2

    for i, d in enumerate(design):
        if any(p["design"] == i for p in pairs):
            continue
        kd = _key(d["text"])
        best, score, drift = None, 0.0, None
        for j, ka in enumerate(keys_a):
            if j in used:
                continue
            ratio = difflib.SequenceMatcher(None, kd, ka).ratio()
            if ratio <= score:
                continue
            gap = abs((rel(actual[j], span_a, origin_a)
                       - rel(d, span_d, origin_d)) - offset)
            if gap > window:
                continue
            best, score, drift = j, ratio, gap
        if best is not None and score >= min_similarity:
            pairs.append({
                "design": i, "actual": best, "similarity": round(score, 3),
                "position_check": (
                    f"within {drift:.2f} of the layout's median offset"
                    if anchored else
                    f"{drift:.2f} of the screen apart; too few exact matches to "
                    f"calibrate an offset, so this pairing rests on the string alone"),
            })
            used.add(best)

    pairs.sort(key=lambda p: p["design"])
    # Drop pairs that cross: keep the longest run that advances on both sides.
    keep, last = [], -1
    for p in pairs:
        if p["actual"] > last:
            keep.append(p)
            last = p["actual"]
    return keep


# --------------------------------------------------------------- measurement

def measure_typography(image, box, tolerance=28):
    """x-height and stroke weight inside one known rectangle.

    Measuring inside an anchor's own box is what makes this trustworthy: the
    band approach had to infer which pixels belonged to which element, and that
    inference was the fragile part. Here the box came with the identity.
    """
    l, t, r, b = box
    if r - l < 4 or b - t < 4:
        return None
    crop = image.crop((l, max(0, t - 1), r, min(image.size[1], b + 1))).convert("RGB")
    bg = modal_background(crop)
    binary = ink_mask(crop, bg, tolerance)
    gray = ink_gray(crop, bg)
    solid = _solid_level(gray)
    profile = coverage_profile(gray, solid, 0, crop.size[0])
    cores = subpixel_cores(profile)
    if not cores:
        return None
    x_height = cores[-1][1] - cores[0][0]
    rows = [y for y in range(int(round(cores[0][0])), int(round(cores[-1][1])) + 1)
            if 0 <= y < crop.size[1]]
    stroke, stems = stroke_from_coverage(gray, binary, solid, 0, crop.size[0], rows)
    if x_height <= 0 or stroke <= 0:
        return None
    return {"x_height": x_height, "stroke": stroke, "stems": stems,
            "weight_index": stroke / x_height}


def ink_extent(image, box, tolerance=28):
    """Shrink a widget box to the rows its glyphs actually occupy.

    This is what makes a hierarchy box and an OCR box mean the same thing, so
    that a measurement taken from one can be compared against the other.
    """
    l, t, r, b = box
    l, t = max(0, l), max(0, t)
    r, b = min(image.size[0], r), min(image.size[1], b)
    if r - l < 4 or b - t < 4:
        return None
    crop = image.crop((l, t, r, b))
    mask = ink_mask(crop, modal_background(crop), tolerance)
    bbox = mask.getbbox()
    if not bbox:
        return None
    return (l + bbox[0], t + bbox[1], l + bbox[2], t + bbox[3])


def flag(design_value, actual_value, tol_pct, tol_abs):
    """Both thresholds must be exceeded — see ui-metrics.md for why."""
    if design_value is None or actual_value is None:
        return None, None, False
    delta = actual_value - design_value
    ratio = actual_value / design_value if design_value else None
    over = abs(delta) > tol_abs and (
        not design_value or abs(delta) / design_value > tol_pct)
    return round(delta, 1), (round(ratio, 3) if ratio else None), bool(over)


# ---------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(
        description="Anchor on text, then measure geometry and typography.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--design", required=True,
                   help="design export image, or a hierarchy/spec dump")
    p.add_argument("--actual", required=True,
                   help="view-hierarchy dump (exact) or a screenshot (OCR)")
    p.add_argument("--actual-image", default=None,
                   help="screenshot to measure typography from when --actual is a "
                        "hierarchy; the hierarchy supplies the boxes, the image the "
                        "glyphs")
    p.add_argument("--design-image", default=None,
                   help="design image for typography when --design is not one")
    p.add_argument("--design-width-dp", type=float, default=None,
                   help="logical width of the design frame (e.g. 390) so results "
                        "read in real dp")
    p.add_argument("--ocr-lang", default="eng")
    p.add_argument("--ocr-psm", type=int, default=4)
    p.add_argument("--gap-tolerance-pct", type=float, default=0.18)
    p.add_argument("--gap-tolerance-px", type=float, default=4.0)
    p.add_argument("--size-tolerance", type=float, default=0.08)
    p.add_argument("--weight-tolerance", type=float, default=0.14)
    p.add_argument("--margin-tolerance-px", type=float, default=4.0)
    p.add_argument("--out", default=None, help="write the JSON here as well")
    args = p.parse_args()

    try:
        design, dw, design_src = load_elements(args.design, args.ocr_lang, args.ocr_psm)
        actual, aw, actual_src = load_elements(args.actual, args.ocr_lang, args.ocr_psm)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2

    # Everything is expressed in design px, which IS dp for a 1x export. Only
    # width is used to normalize: mobile layouts pin horizontal metrics and let
    # content flow vertically, so width is the honest shared unit and vertical
    # error stays in the data instead of being scaled out of it.
    unit = args.design_width_dp / dw if args.design_width_dp else 1.0
    sd = unit
    sa = (dw / float(aw)) * unit

    # Box semantics must match on both sides before any gap is comparable, and
    # neither source hands them over already matching. A hierarchy box is the
    # widget, including the line-height padding the framework reserves. A
    # tesseract line box is the recognizer's idea of the line, which carries its
    # own leading. Compare one against the other and a pixel-perfect screen
    # reports a ~25% deficit on every gap — a confident number produced entirely
    # by the two tools disagreeing about where a line of text ends.
    #
    # So every side that has an image behind it is reduced to the ink its glyphs
    # actually occupy, which is the one definition both sources can agree on.
    # A side with no image keeps whatever box it came with, and the mismatch is
    # then declared rather than measured through.
    design_image_path = args.design_image or (
        args.design if args.design.lower().endswith(IMAGE_SUFFIXES) else None)
    actual_image_path = args.actual_image or (
        args.actual if args.actual.lower().endswith(IMAGE_SUFFIXES) else None)

    def tighten(elements, image_path):
        if not image_path or not os.path.exists(image_path):
            return False
        with Image.open(image_path) as raw:
            raw = raw.convert("RGB")
            for e in elements:
                tight = ink_extent(raw, e["box"])
                if tight:
                    e["box"] = tight
        return True

    design_ink = tighten(design, design_image_path)
    actual_ink = tighten(actual, actual_image_path)
    design_boxes = "ink" if design_ink else (
        "widget" if design_src == "hierarchy" else "ocr-line")
    actual_boxes = "ink" if actual_ink else (
        "widget" if actual_src == "hierarchy" else "ocr-line")
    box_semantics_match = design_boxes == actual_boxes

    for e in design:
        e["dp"] = tuple(v * sd for v in e["box"])
    for e in actual:
        e["dp"] = tuple(v * sa for v in e["box"])

    pairs = pair_by_text(design, actual)

    anchors = []
    for pair in pairs:
        d, a = design[pair["design"]], actual[pair["actual"]]
        dl, dt, dr, db = d["dp"]
        al, at, ar, ab = a["dp"]
        h_delta, h_ratio, h_over = flag(db - dt, ab - at,
                                        args.gap_tolerance_pct, args.gap_tolerance_px)
        left_delta = round(al - dl, 1)
        right_delta = round((dw * unit - ar) - (dw * unit - dr), 1)
        margin_over = (abs(left_delta) > args.margin_tolerance_px
                       or abs(right_delta) > args.margin_tolerance_px)
        # An anchor that matched only fuzzily is a copy difference wearing a
        # geometry finding's clothes. Geometry is this script's job and exact
        # text is text_audit's, but staying silent here would let a missing word
        # pass as a successful pairing — which is the opposite of useful.
        text_differs = _key(d["text"]) != _key(a["text"])
        anchors.append({
            "text": d["text"],
            "text_matches": not text_differs,
            "actual_text": a["text"],
            "similarity": pair["similarity"],
            "position_check": pair["position_check"],
            "element_id": a["id"] or None,
            "design_box": [round(v, 1) for v in d["dp"]],
            "actual_box": [round(v, 1) for v in a["dp"]],
            "height": {"design": round(db - dt, 1), "actual": round(ab - at, 1),
                       "delta": h_delta, "ratio": h_ratio, "flagged": h_over},
            "margins": {"left_delta": left_delta, "right_delta": right_delta,
                        "flagged": bool(margin_over)},
        })

    # Gaps between consecutive anchors. Because a gap is a difference between
    # two positions, a taller status bar, a different screen size, and a
    # different pixel density all cancel out of the arithmetic.
    gaps = []
    for n in range(len(anchors) - 1):
        top, bottom = anchors[n], anchors[n + 1]
        gd = bottom["design_box"][1] - top["design_box"][3]
        ga = bottom["actual_box"][1] - top["actual_box"][3]
        if gd < 0 or ga < 0:
            continue  # elements overlap or share a line; not a vertical gap
        delta, ratio, over = flag(gd, ga, args.gap_tolerance_pct, args.gap_tolerance_px)
        gaps.append({
            "between": f"{top['text'][:28]} -> {bottom['text'][:28]}",
            "design": round(gd, 1), "actual": round(ga, 1),
            "delta": delta, "ratio": ratio, "flagged": over,
        })

    # Typography, measured inside each anchor's own box.
    design_img, actual_img = design_image_path, actual_image_path
    typography = []
    if design_img and actual_img:
        with Image.open(design_img) as di, Image.open(actual_img) as ai:
            di, ai = di.convert("RGB"), ai.convert("RGB")
            for n, pair in enumerate(pairs):
                md = measure_typography(di, design[pair["design"]]["box"])
                ma = measure_typography(ai, actual[pair["actual"]]["box"])
                if not md or not ma:
                    continue
                size_ratio = (ma["x_height"] * sa) / (md["x_height"] * sd)
                weight_ratio = ma["weight_index"] / md["weight_index"]
                reasons = []
                if abs(size_ratio - 1) > args.size_tolerance:
                    reasons.append(
                        f"font size renders {size_ratio:.2f}x the design "
                        f"({md['x_height'] * sd:.1f} -> {ma['x_height'] * sa:.1f} "
                        f"x-height)")
                if abs(weight_ratio - 1) > args.weight_tolerance:
                    direction = "lighter" if weight_ratio < 1 else "heavier"
                    reasons.append(
                        f"stroke weight renders {weight_ratio:.2f}x the design "
                        f"({direction})")
                typography.append({
                    "text": design[pair["design"]]["text"][:40],
                    "_native_x": (md["x_height"], ma["x_height"]),
                    "size_ratio": round(size_ratio, 3),
                    "weight_ratio": round(weight_ratio, 3),
                    "design_x_height": round(md["x_height"] * sd, 2),
                    "actual_x_height": round(ma["x_height"] * sa, 2),
                    "stems": min(md["stems"], ma["stems"]),
                    "flagged": bool(reasons),
                    "reasons": reasons,
                })

    # An OCR box traces the ink, not the widget. That distinction decides what
    # may fail a build. A gap between two ink extents is still a fair
    # measurement, because both sides are measured the same way and the error
    # largely cancels. A box *height* is not the control's height — it grows and
    # shrinks with whether the line happens to contain a descender — and a box's
    # left edge is not the layout's padding. Failing a build on either would be
    # failing it on the recognizer's habits.
    ocr_boxes = "ocr" in (design_src, actual_src)
    if ocr_boxes:
        for a in anchors:
            for field in ("height", "margins"):
                if a[field]["flagged"]:
                    a[field]["flagged"] = False
                    a[field]["advisory"] = True
                    a[field]["note"] = (
                        "text-ink box, not the widget box — a lead to confirm on a "
                        "device hierarchy, not a failure")

    # The same resolution bias typography_audit accounts for: a 1x design export
    # beside a 3x screenshot reads systematically larger on the low-resolution
    # side, because proportionally more of each glyph is antialiased edge. It is
    # a bias, not noise, so it does not average out and must be charged against
    # the tolerance rather than reported as a screen-wide defect.
    resolution_ratio = max(dw, aw) / float(min(dw, aw))
    size_tol = max(args.size_tolerance, 0.06 * max(0.0, resolution_ratio - 1))
    weight_tol = max(args.weight_tolerance, 0.10 * max(0.0, resolution_ratio - 1))
    ratios = [t["size_ratio"] for t in typography if t["size_ratio"]]
    systematic_size = round(statistics.median(ratios), 3) if len(ratios) >= 3 else None

    for t in typography:
        # Per-anchor edge uncertainty, on top of the screen-wide scale bias. An
        # x-height is only as precise as the glyph edges it is read between, and
        # antialiasing smears each edge across about a pixel — so a 7 px x-height
        # in a 1x export cannot resolve better than ~14%, and pretending
        # otherwise turns the tool's own rounding into the loudest finding.
        nd, na = t.pop("_native_x")
        precision = 1.0 / max(1e-6, nd) + 1.0 / max(1e-6, na)
        t_size_tol = max(size_tol, precision)
        t_weight_tol = max(weight_tol, precision)

        reasons = []
        if t["size_ratio"] and abs(t["size_ratio"] - 1) > t_size_tol:
            reasons.append(
                f"font size renders {t['size_ratio']:.2f}x the design "
                f"({t['design_x_height']} -> {t['actual_x_height']} x-height)")
        if t["weight_ratio"] and abs(t["weight_ratio"] - 1) > t_weight_tol:
            direction = "lighter" if t["weight_ratio"] < 1 else "heavier"
            reasons.append(
                f"stroke weight renders {t['weight_ratio']:.2f}x the design "
                f"({direction})")
        t["reasons"] = reasons
        t["flagged"] = bool(reasons)
        t["tolerance_used"] = {"size": round(t_size_tol, 4),
                               "weight": round(t_weight_tol, 4)}

    if not box_semantics_match:
        for g in gaps:
            if g["flagged"]:
                g["flagged"] = False
                g["advisory"] = True
                g["note"] = (
                    f"the two sides measure different things ({design_boxes} vs "
                    f"{actual_boxes}), so this difference is not a measurement. "
                    f"Pass --design-image/--actual-image so both can be reduced to "
                    f"ink.")

    flagged_gaps = [g for g in gaps if g["flagged"]]
    flagged_heights = [a for a in anchors if a["height"]["flagged"]]
    flagged_margins = [a for a in anchors if a["margins"]["flagged"]]
    advisory = [a for a in anchors
                if a["height"].get("advisory") or a["margins"].get("advisory")]
    flagged_type = [t for t in typography if t["flagged"]]

    exact = "exact" if (design_src, actual_src) == ("hierarchy", "hierarchy") else (
        "actual exact, design from OCR" if actual_src == "hierarchy" else "both from OCR")

    # Evidence grade travels with each finding AND with the headline. The per-row
    # fields were already honest, but a reader who acts on `verdict` alone was
    # getting a verdict stated more firmly than an OCR-derived measurement can
    # support — and `verdict` is exactly what a reader acts on alone.
    ocr_evidence = "ocr" in (design_src, actual_src)
    grade = "recognizer-grade (OCR)" if ocr_evidence else "exact (framework bounds)"
    for g in gaps:
        g["evidence"] = grade
    for t in typography:
        t["evidence"] = grade
    # text_differences is tagged below, once it exists.

    # Reuse text_audit's classifier rather than reporting a bare "these differ".
    # The kind of difference is the whole finding: a missing word is a defect at
    # any evidence grade, while a shifted line break or a stray comma read off
    # pixels is the recognizer talking about itself. Without the distinction
    # every wrapped paragraph on the screen arrives as a copy defect.
    text_differences = []
    for n, a in enumerate(anchors):
        if a["text_matches"]:
            continue
        context = {
            "prev_expected": anchors[n - 1]["text"] if n else "",
            "next_expected": anchors[n + 1]["text"] if n + 1 < len(anchors) else "",
            "prev_actual": anchors[n - 1]["actual_text"] if n else "",
            "next_actual": anchors[n + 1]["actual_text"] if n + 1 < len(anchors) else "",
        }
        kind = classify(a["text"], a["actual_text"], context) or "wording"
        decidable = (not ocr_evidence) or kind in OCR_DECIDABLE
        text_differences.append({
            "design": a["text"], "actual": a["actual_text"],
            "difference": kind, "decidable": decidable,
            "similarity": a["similarity"], "element_id": a["element_id"],
            "evidence": grade,
            "note": None if decidable else
                    f"a {kind} difference cannot be settled from OCR — capture the "
                    f"view hierarchy on the device",
        })

    hard_text = [t for t in text_differences if t["decidable"]]
    soft_text = [t for t in text_differences if not t["decidable"]]

    unpaired_design = [design[i]["text"] for i in range(len(design))
                       if not any(p["design"] == i for p in pairs)]
    unpaired_actual = [actual[j]["text"] for j in range(len(actual))
                       if not any(p["actual"] == j for p in pairs)]

    if len(pairs) < 2:
        verdict = (f"INCONCLUSIVE — only {len(pairs)} text anchor(s) matched between "
                   f"the two sides. Either the copy genuinely differs, or the OCR "
                   f"language is wrong. Nothing below is safe to quote.")
    elif not (flagged_gaps or flagged_heights or flagged_margins or flagged_type
              or hard_text):
        verdict = (f"PASS — {len(pairs)} anchors matched; spacing, element heights, "
                   f"side margins and typography all within tolerance "
                   f"({grade}).")
        if soft_text:
            verdict += (f" {len(soft_text)} text difference(s) OCR cannot settle "
                        f"({', '.join(sorted({t['difference'] for t in soft_text}))}) "
                        f"— leads, not failures.")
        if advisory:
            verdict += (f" {len(advisory)} anchor(s) differ in ink-box height or "
                        f"edge; those are recognizer artefacts unless a hierarchy "
                        f"confirms them.")
    elif systematic_size and abs(systematic_size - 1) > size_tol:
        verdict = (f"FAIL — the whole type scale is off: every anchored string "
                   f"renders ~{systematic_size:.2f}x the design's size. One root "
                   f"cause (a text theme or density setting), not one finding per "
                   f"string.")
    else:
        parts = []
        for name, items in (("gap", flagged_gaps), ("height", flagged_heights),
                            ("margin", flagged_margins), ("typography", flagged_type),
                            ("text", hard_text)):
            if items:
                parts.append(f"{len(items)} {name}")
        verdict = (f"FAIL — {', '.join(parts)} outside tolerance across "
                   f"{len(pairs)} matched anchors. Every measurement below names "
                   f"the string it belongs to, so each one can be checked without "
                   f"opening an image.")
        if ocr_evidence:
            verdict += (
                f" EVIDENCE IS {grade.upper()}: both boxes and strings were "
                f"recognized from images, not read from the framework. Gaps "
                f"survive that well — both sides are measured the same way, so "
                f"the error largely cancels. A typography ratio or a "
                f"single-character text difference does not: capture the view "
                f"hierarchy on a device before filing either as a defect.")

    result = {
        "verdict": verdict,
        "authority": exact,
        "evidence_grade": grade,
        "unit": "dp" if args.design_width_dp else "design px",
        "anchors_matched": len(pairs),
        "resolution_ratio": round(resolution_ratio, 2),
        "systematic_size_ratio": systematic_size,
        "tolerances": {"gap_pct": args.gap_tolerance_pct,
                       "gap_px": args.gap_tolerance_px,
                       "size": round(size_tol, 4), "weight": round(weight_tol, 4)},
        "advisory_anchors": len(advisory),
        "sources": {"design": design_src, "actual": actual_src},
        "text_differences": text_differences,
        "text_differences_decidable": len(hard_text),
        "box_semantics_match": box_semantics_match,
        "box_semantics": {"design": design_boxes, "actual": actual_boxes},
        "gaps": gaps,
        "anchors": anchors,
        "typography": typography,
        "unpaired_design": unpaired_design,
        "unpaired_actual": unpaired_actual,
        "note": "Only elements carrying text are anchored here. Icons, images, and "
                "dividers have no anchor and are not measured — use spacing_audit.py "
                "and the visual scan for those.",
    }

    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload)
    print(payload)
    return 1 if (flagged_gaps or flagged_heights or flagged_margins
                 or flagged_type or hard_text) else 0


if __name__ == "__main__":
    raise SystemExit(main())
