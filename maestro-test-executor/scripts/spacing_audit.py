#!/usr/bin/env python3
"""Measure vertical spacing and horizontal margins against a design reference.

WHY THIS EXISTS — the failure it fixes
--------------------------------------
Pixel-diff comparison (`pair_view.py`) answers "is the right thing here, styled
right?". It cannot answer "is the gap between these two sections 16dp like the
design, or 28dp?" — and worse, the way it prepares the images actively destroys
that evidence: it resizes the design onto the screenshot's exact width AND
height. Force-fitting both axes rescales the design's vertical rhythm to the
device's, so a uniformly inflated set of paddings gets normalized away and the
diff comes back clean. Then, because the two aspect ratios don't match, the diff
gets suppressed as "unreliable" and the run reports nothing at all. A real,
obvious, "spacing is way bigger than the design" bug survives both stages
untouched. That is a false negative on the single most common design-parity
defect there is.

Vision can't rescue it either. Asked to eyeball two screenshots, a model says
"spacing looks a bit loose" — an impression, at the wrong altitude to act on. A
developer needs "the gap under the search bar is 30dp, design says 22dp".

THE METHOD — measure, don't diff
--------------------------------
1. Scale by WIDTH ONLY. Mobile layouts pin horizontal metrics (side padding,
   card width) and let content flow vertically, so width is the honest shared
   unit. Normalizing both images to the design's width puts every measurement
   into design px — which, for a 1x design export (e.g. a 390pt iPhone frame
   exported at 390px), IS dp. Crucially, heights are NOT forced to match, so
   vertical error stays in the data instead of being scaled out of it.
2. Segment each image into horizontal content BANDS separated by empty GAPS,
   using an ink profile (per-row fraction of pixels differing from the modal
   background colour). Bands are the elements; gaps are the spacing.
3. Align the two band sequences in order (allowing skips, since real data
   differs from mockup data), then compare GAP BY GAP and BAND HEIGHT BY BAND
   HEIGHT.
4. Report every deviation as a number, plus a systematic-inflation factor — the
   median actual/design gap ratio. A factor of 1.35 means "every gap on this
   screen is ~35% bigger than the design", which is a single root cause (one
   wrong spacing token / theme value), not fifteen separate findings.

Because gaps are DIFFERENCES between positions, this comparison is immune to the
constant offset a taller/shorter status bar introduces — the thing that makes
absolute-position comparison useless across platforms.

WHAT IT CANNOT DO — say this in the report
------------------------------------------
- It measures rendered pixels, not framework values. It proves "this gap renders
  at 30 design px where the design shows 22" — strong, actionable evidence. It
  does not read `SizedBox(height: 24)`, so cite it as a measurement of the
  render, and let the developer map it to the token.
- It needs visible separation. A full-bleed photo or a gradient with no empty
  rows cannot be segmented; the tool says so (few bands) instead of guessing.
  Use --roi-top/--roi-bottom to audit the part of the screen that does separate.
- A band is whatever renders as one visual run of ink, not a widget. Two text
  lines 8px apart merge into one band (correctly — that is a paragraph, and
  merging it the same way on both sides is what makes the comparison fair).
  --min-gap controls where that line sits; `auto` picks the value that makes the
  two sequences most comparable and prints its choice.
- Data differences shift the sequence: an empty-state card where the design shows
  three plant cards is not a defect. Unmatched bands are reported separately as
  `unmatched_*`, never as spacing findings — judge those from the image.

USAGE
-----
  python3 spacing_audit.py DESIGN.png ACTUAL.png --out report/TC-01-spacing.png

  # strip OS chrome first so the top/bottom bands aren't status bar / nav bar
  python3 spacing_audit.py DESIGN.png ACTUAL.png \\
      --crop-design-top 6% --crop-design-bottom 3% \\
      --crop-actual-top 4% --crop-actual-bottom 3% \\
      --out report/TC-01-spacing.png

  # ignore a floating FAB / debug overlay that bridges gaps in the screenshot
  python3 spacing_audit.py DESIGN.png ACTUAL.png \\
      --mask-actual 60%,88%,100%,100% --out report/TC-01-spacing.png

  # design frame is 390pt exported at 2x (780px wide) -> report real dp
  python3 spacing_audit.py DESIGN.png ACTUAL.png --design-width-dp 390 \\
      --out report/TC-01-spacing.png

Reads the JSON on stdout for the numbers; read the PNG with vision to see which
band is which. Dependency: Pillow (pip3 install Pillow).
"""

import argparse
import json
import os
import sys
from functools import reduce

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except ImportError:
    sys.stderr.write(
        "ERROR: Pillow is required for spacing_audit.\n"
        "Install it once with:  pip3 install Pillow\n"
    )
    sys.exit(2)

GAP_CANDIDATES = (8, 10, 12, 14, 16, 20, 24)


# ---------------------------------------------------------------- primitives

def _load_font(size: int):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def parse_len(value, total):
    """Length given as pixels ('120') or a percentage of `total` ('6%')."""
    value = str(value).strip()
    if value.endswith("%"):
        return int(round(float(value[:-1]) / 100.0 * total))
    return int(round(float(value)))


def crop_band(img, top, bottom):
    w, h = img.size
    y0 = parse_len(top, h) if top else 0
    y1 = h - (parse_len(bottom, h) if bottom else 0)
    if y1 <= y0:
        raise ValueError("crop-top/crop-bottom leave no content band")
    return img.crop((0, y0, w, y1))


def modal_background(img):
    """Dominant colour, taken as the page background.

    Quantizing first keeps this cheap and robust to the anti-aliasing noise that
    makes a raw histogram of a real screenshot mostly-unique colours.
    """
    q = img.convert("RGB").quantize(colors=16)
    palette = q.getpalette()
    counts = q.getcolors() or [(0, 0)]
    _, index = max(counts, key=lambda cv: cv[0])
    return tuple(palette[index * 3:index * 3 + 3])


def ink_mask(img, bg, tolerance):
    """Binary mask (L mode): 255 where the pixel differs from `bg`."""
    diff = ImageChops.difference(img, Image.new("RGB", img.size, bg))
    channels = [c.point(lambda v: 255 if v > tolerance else 0) for c in diff.split()]
    return reduce(ImageChops.lighter, channels)


def row_profile(mask):
    """Per-row fraction of ink pixels.

    Averaging with a box resize down to a single column is exact and fast; the
    F-mode conversion keeps float precision, which matters because the
    interesting thresholds (a row holding one thin line of text) live around
    1% and would be lost to 8-bit quantization.
    """
    w, h = mask.size
    col = mask.convert("F").resize((1, h), Image.BOX)
    return [col.getpixel((0, y)) / 255.0 for y in range(h)]


def col_extent(mask, y0, y1, threshold):
    """(left, right) ink extent within rows [y0, y1) — the band's own margins."""
    w, h = mask.size
    y0, y1 = max(0, y0), min(h, y1)
    if y1 <= y0:
        return None
    strip = mask.crop((0, y0, w, y1)).convert("F").resize((w, 1), Image.BOX)
    vals = [strip.getpixel((x, 0)) / 255.0 for x in range(w)]
    hits = [x for x, v in enumerate(vals) if v > threshold]
    return (hits[0], hits[-1] + 1) if hits else None


# ------------------------------------------------------------- segmentation

def segment(profile, ink_threshold, min_band, min_gap):
    """Ink profile -> ordered list of (top, bottom) content bands.

    Gaps thinner than `min_gap` are absorbed into the surrounding band (they are
    line leading inside a paragraph, not layout spacing); bands thinner than
    `min_band` are dropped as speckle (a divider hairline, a stray shadow).
    """
    runs = []
    start = None
    for y, value in enumerate(profile):
        if value > ink_threshold:
            if start is None:
                start = y
        elif start is not None:
            runs.append((start, y))
            start = None
    if start is not None:
        runs.append((start, len(profile)))

    merged = []
    for band in runs:
        if merged and band[0] - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], band[1])
        else:
            merged.append(band)
    return [b for b in merged if b[1] - b[0] >= min_band]


def align(bands_d, bands_a):
    """Order-preserving alignment allowing skips on either side.

    Real screens rarely contain exactly the mockup's data, so a strict 1:1
    pairing would either fail outright or silently pair the wrong elements —
    which is how a "comparison" ends up measuring a plant card against an
    empty-state illustration. Skips are cheap so extra/missing elements drop out
    as unmatched instead of corrupting every measurement after them.
    """
    if not bands_d or not bands_a:
        return []

    span_d = max(1.0, bands_d[-1][1] - bands_d[0][0])
    span_a = max(1.0, bands_a[-1][1] - bands_a[0][0])
    origin_d, origin_a = bands_d[0][0], bands_a[0][0]

    def cost(i, j):
        hd, ha = bands_d[i][1] - bands_d[i][0], bands_a[j][1] - bands_a[j][0]
        height = abs(hd - ha) / max(hd, ha, 1)
        pos_d = (bands_d[i][0] - origin_d) / span_d
        pos_a = (bands_a[j][0] - origin_a) / span_a
        return 0.65 * min(1.0, height) + 0.35 * min(1.0, abs(pos_d - pos_a) * 2.5)

    skip = 0.55
    n, m = len(bands_d), len(bands_a)
    table = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        table[i][0] = i * skip
    for j in range(1, m + 1):
        table[0][j] = j * skip
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            table[i][j] = min(
                table[i - 1][j - 1] + cost(i - 1, j - 1),
                table[i - 1][j] + skip,
                table[i][j - 1] + skip,
            )

    pairs, i, j = [], n, m
    while i > 0 and j > 0:
        if table[i][j] == table[i - 1][j - 1] + cost(i - 1, j - 1):
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif table[i][j] == table[i - 1][j] + skip:
            i -= 1
        else:
            j -= 1
    return list(reversed(pairs))


# ----------------------------------------------------------------- annotate

def annotate(img, bands, labels, gap_notes, px_to_dp, title, flagged_gaps):
    """Draw band boundaries and per-gap measurements onto one side."""
    out = img.convert("RGB")
    w, h = out.size
    draw = ImageDraw.Draw(out, "RGBA")
    font = _load_font(max(11, int(w * 0.030)))
    small = _load_font(max(10, int(w * 0.026)))

    for (top, bottom), label in zip(bands, labels):
        colour = (60, 160, 90, 220) if label.startswith("B") else (150, 110, 220, 220)
        draw.rectangle([0, top, w - 1, bottom - 1], outline=colour, width=2)
        draw.text((4, top + 2), label, font=small, fill=colour[:3])

    for (top, bottom, text, key) in gap_notes:
        bad = key in flagged_gaps
        fill = (235, 60, 60, 70) if bad else (70, 130, 230, 45)
        edge = (235, 60, 60) if bad else (70, 130, 230)
        draw.rectangle([0, top, w - 1, max(top, bottom - 1)], fill=fill)
        y = (top + bottom) / 2
        draw.line([(w * 0.34, top), (w * 0.34, bottom)], fill=edge, width=2)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text((w * 0.37 + dx, y + dy), text, font=font, anchor="lm",
                      fill=(0, 0, 0, 235))
        draw.text((w * 0.37, y), text, font=font, anchor="lm", fill=edge)

    header = max(24, int(w * 0.075))
    canvas = Image.new("RGB", (w, h + header), (24, 24, 24))
    canvas.paste(out, (0, header))
    d2 = ImageDraw.Draw(canvas)
    unit = "dp" if px_to_dp != 1.0 else "px"
    d2.text((w / 2, header / 2), f"{title}  (values in design {unit})",
            font=_load_font(max(12, int(header * 0.5))), anchor="mm",
            fill=(255, 255, 255))
    return canvas


# --------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("design", help="design reference image (Figma export / mockup)")
    ap.add_argument("actual", help="real device screenshot")
    ap.add_argument("--out", required=True, help="annotated side-by-side PNG to write")
    ap.add_argument("--crop-design-top", default=None, help="px or %% off the design top")
    ap.add_argument("--crop-design-bottom", default=None, help="px or %% off the design bottom")
    ap.add_argument("--crop-actual-top", default=None,
                    help="px or %% off the screenshot top (status bar)")
    ap.add_argument("--crop-actual-bottom", default=None,
                    help="px or %% off the screenshot bottom (OS nav / home indicator)")
    ap.add_argument("--mask-design", action="append", metavar="X1,Y1,X2,Y2",
                    help="region to blank before measuring (px or %%) — repeatable")
    ap.add_argument("--mask-actual", action="append", metavar="X1,Y1,X2,Y2",
                    help="region to blank before measuring, e.g. a FAB or debug "
                         "overlay that bridges a gap (px or %%) — repeatable")
    ap.add_argument("--roi-top", default=None,
                    help="restrict measuring to below this point in BOTH images (px or %%)")
    ap.add_argument("--roi-bottom", default=None,
                    help="restrict measuring to above this point in BOTH images (px or %%)")
    ap.add_argument("--ink-tolerance", type=int, default=18,
                    help="per-channel delta from the background before a pixel counts "
                         "as ink (default 18)")
    ap.add_argument("--row-threshold", type=float, default=0.006,
                    help="fraction of a row that must be ink for the row to be content "
                         "(default 0.006 — about one thin text stroke)")
    ap.add_argument("--min-band", type=int, default=3,
                    help="drop bands thinner than this many design px (default 3)")
    ap.add_argument("--min-gap", default="auto",
                    help="gaps thinner than this many design px are absorbed into the "
                         "band (line leading, not layout spacing). 'auto' (default) "
                         f"tries {list(GAP_CANDIDATES)} and keeps the most comparable.")
    ap.add_argument("--design-width-dp", type=float, default=0.0,
                    help="logical width of the design frame in dp/pt. Set it when the "
                         "export is not 1x (e.g. 390pt frame exported 780px wide) so "
                         "the report is in real dp instead of export px.")
    ap.add_argument("--gap-tolerance-px", type=float, default=4.0,
                    help="absolute slack per gap in design px (default 4) — below this, "
                         "a difference is rendering noise, not a spacing bug")
    ap.add_argument("--gap-tolerance-pct", type=float, default=0.18,
                    help="relative slack per gap (default 0.18 = 18%%). A gap is flagged "
                         "only when it exceeds BOTH tolerances.")
    ap.add_argument("--margin-tolerance-px", type=float, default=4.0,
                    help="slack on a band's left/right ink extent in design px (default 4)")
    args = ap.parse_args()

    for path in (args.design, args.actual):
        if not os.path.exists(path):
            sys.stderr.write(f"ERROR: file not found: {path}\n")
            sys.exit(1)

    design = Image.open(args.design).convert("RGB")
    actual = Image.open(args.actual).convert("RGB")

    try:
        if args.crop_design_top or args.crop_design_bottom:
            design = crop_band(design, args.crop_design_top, args.crop_design_bottom)
        if args.crop_actual_top or args.crop_actual_bottom:
            actual = crop_band(actual, args.crop_actual_top, args.crop_actual_bottom)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        sys.exit(1)

    # Width-only normalization: the design's width becomes the measurement unit
    # and vertical error is preserved rather than scaled away.
    unit_w = design.width
    scale = unit_w / actual.width
    actual = actual.resize((unit_w, max(1, int(round(actual.height * scale)))),
                           Image.LANCZOS)
    px_to_dp = (args.design_width_dp / unit_w) if args.design_width_dp else 1.0

    def prepare(img, masks):
        img = img.copy()
        for spec in masks or []:
            parts = [p.strip() for p in spec.split(",")]
            if len(parts) != 4:
                raise ValueError(f"mask must be x1,y1,x2,y2 — got {spec!r}")
            box = (parse_len(parts[0], img.width), parse_len(parts[1], img.height),
                   parse_len(parts[2], img.width), parse_len(parts[3], img.height))
            img.paste(modal_background(img), box)
        bg = modal_background(img)
        mask = ink_mask(img, bg, args.ink_tolerance)
        y0 = parse_len(args.roi_top, img.height) if args.roi_top else 0
        y1 = (img.height - parse_len(args.roi_bottom, img.height)
              if args.roi_bottom else img.height)
        if y1 <= y0:
            raise ValueError("roi-top/roi-bottom leave no content band")
        if y0 or y1 != img.height:
            blank = Image.new("L", mask.size, 0)
            blank.paste(mask.crop((0, y0, img.width, y1)), (0, y0))
            mask = blank
        return img, mask, bg

    try:
        design, mask_d, bg_d = prepare(design, args.mask_design)
        actual, mask_a, bg_a = prepare(actual, args.mask_actual)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        sys.exit(1)

    prof_d, prof_a = row_profile(mask_d), row_profile(mask_a)

    if args.min_gap == "auto":
        best = None
        for candidate in GAP_CANDIDATES:
            bd = segment(prof_d, args.row_threshold, args.min_band, candidate)
            ba = segment(prof_a, args.row_threshold, args.min_band, candidate)
            matched = len(align(bd, ba))
            unmatched = (len(bd) - matched) + (len(ba) - matched)
            score = (matched, -unmatched, -candidate)
            if best is None or score > best[0]:
                best = (score, candidate, bd, ba)
        min_gap, bands_d, bands_a = best[1], best[2], best[3]
    else:
        min_gap = int(args.min_gap)
        bands_d = segment(prof_d, args.row_threshold, args.min_band, min_gap)
        bands_a = segment(prof_a, args.row_threshold, args.min_band, min_gap)

    pairs = align(bands_d, bands_a)
    matched_d = {i for i, _ in pairs}
    matched_a = {j for _, j in pairs}

    def dp(value):
        return round(value * px_to_dp, 1)

    labels_d = ["?"] * len(bands_d)
    labels_a = ["?"] * len(bands_a)
    for n, (i, j) in enumerate(pairs, start=1):
        labels_d[i] = labels_a[j] = f"B{n}"
    extra = 0
    for i in range(len(bands_d)):
        if i not in matched_d:
            extra += 1
            labels_d[i] = f"D{extra}"
    extra = 0
    for j in range(len(bands_a)):
        if j not in matched_a:
            extra += 1
            labels_a[j] = f"A{extra}"

    # Band heights: catches a control that renders taller/shorter than designed
    # (font scale, image box, button height) as opposed to the space around it.
    band_rows = []
    for n, (i, j) in enumerate(pairs, start=1):
        hd = bands_d[i][1] - bands_d[i][0]
        ha = bands_a[j][1] - bands_a[j][0]
        delta = ha - hd
        band_rows.append({
            "band": f"B{n}",
            "design": dp(hd),
            "actual": dp(ha),
            "delta": dp(delta),
            "delta_pct": round(delta / hd * 100, 1) if hd else None,
        })

    # Gaps are only comparable when the two bands bounding them are adjacent in
    # BOTH sequences; otherwise something unmatched sits inside the gap and the
    # measurement would be of two different things.
    gap_rows, flagged_d, flagged_a = [], set(), set()
    for n in range(len(pairs) - 1):
        (i0, j0), (i1, j1) = pairs[n], pairs[n + 1]
        key = f"G{n + 1}"
        if i1 != i0 + 1 or j1 != j0 + 1:
            gap_rows.append({
                "gap": key, "between": f"B{n + 1}-B{n + 2}",
                "comparable": False,
                "reason": "an unmatched band sits inside this gap on one side",
            })
            continue
        gd = bands_d[i1][0] - bands_d[i0][1]
        ga = bands_a[j1][0] - bands_a[j0][1]
        delta = ga - gd
        over = abs(delta) > args.gap_tolerance_px and (
            gd == 0 or abs(delta) / gd > args.gap_tolerance_pct)
        if over:
            flagged_d.add(key)
            flagged_a.add(key)
        gap_rows.append({
            "gap": key, "between": f"B{n + 1}-B{n + 2}", "comparable": True,
            "design": dp(gd), "actual": dp(ga), "delta": dp(delta),
            "delta_pct": round(delta / gd * 100, 1) if gd else None,
            "ratio": round(ga / gd, 3) if gd else None,
            "flagged": over,
        })

    ratios = sorted(r["ratio"] for r in gap_rows
                    if r.get("comparable") and r.get("ratio"))
    if ratios:
        mid = len(ratios) // 2
        systematic = (ratios[mid] if len(ratios) % 2
                      else (ratios[mid - 1] + ratios[mid]) / 2)
    else:
        systematic = None

    # Horizontal extent per matched band: a side-padding or width bug shows up
    # here, and it is measured in the same unit as everything else.
    margin_rows = []
    for n, (i, j) in enumerate(pairs, start=1):
        ed = col_extent(mask_d, bands_d[i][0], bands_d[i][1], args.row_threshold)
        ea = col_extent(mask_a, bands_a[j][0], bands_a[j][1], args.row_threshold)
        if not ed or not ea:
            continue
        left_delta, right_delta = ea[0] - ed[0], (unit_w - ea[1]) - (unit_w - ed[1])
        if (abs(left_delta) > args.margin_tolerance_px
                or abs(right_delta) > args.margin_tolerance_px):
            margin_rows.append({
                "band": f"B{n}",
                "design_left": dp(ed[0]), "actual_left": dp(ea[0]),
                "left_delta": dp(left_delta),
                "design_right": dp(unit_w - ed[1]), "actual_right": dp(unit_w - ea[1]),
                "right_delta": dp(right_delta),
            })

    unit = "dp" if px_to_dp != 1.0 else "px"

    def notes(bands, pair_index, side):
        out = []
        for n in range(len(pairs) - 1):
            idx0, idx1 = pairs[n][pair_index], pairs[n + 1][pair_index]
            top, bottom = bands[idx0][1], bands[idx1][0]
            if bottom <= top:
                continue
            row = gap_rows[n]
            if not row.get("comparable"):
                text = f"G{n + 1} n/a"
            elif side == "design":
                text = f"G{n + 1} {row['design']}{unit}"
            else:
                arrow = "+" if (row["delta"] or 0) > 0 else ""
                text = (f"G{n + 1} {row['actual']}{unit} "
                        f"({arrow}{row['delta']} vs {row['design']})")
            out.append((top, bottom, text, f"G{n + 1}"))
        return out

    left = annotate(design, bands_d, labels_d, notes(bands_d, 0, "design"),
                    px_to_dp, "DESIGN", set())
    right = annotate(actual, bands_a, labels_a, notes(bands_a, 1, "actual"),
                     px_to_dp, "ACTUAL", flagged_a)

    gap_px = max(4, int(unit_w * 0.02))
    canvas = Image.new("RGB", (unit_w * 2 + gap_px, max(left.height, right.height)),
                       (24, 24, 24))
    canvas.paste(left, (0, 0))
    canvas.paste(right, (unit_w + gap_px, 0))
    canvas.save(args.out)

    flagged = [r for r in gap_rows if r.get("flagged")]
    summary = {
        "out": args.out,
        "design": args.design,
        "actual": args.actual,
        "unit": f"design {unit}",
        "measurement_width": unit_w,
        "actual_scaled_to": [actual.width, actual.height],
        "design_size": [design.width, design.height],
        "min_gap_used": min_gap,
        "bands_design": len(bands_d),
        "bands_actual": len(bands_a),
        "matched_bands": len(pairs),
        "unmatched_design": [labels_d[i] for i in range(len(bands_d))
                             if i not in matched_d],
        "unmatched_actual": [labels_a[j] for j in range(len(bands_a))
                             if j not in matched_a],
        "systematic_gap_ratio": round(systematic, 3) if systematic else None,
        "flagged_gap_count": len(flagged),
        "gaps": gap_rows,
        "band_heights": band_rows,
        "margin_deviations": margin_rows,
    }

    if systematic and abs(systematic - 1.0) > args.gap_tolerance_pct:
        direction = "larger" if systematic > 1 else "smaller"
        summary["verdict"] = (
            f"SPACING DEVIATION: gaps on the device are systematically "
            f"{abs(systematic - 1) * 100:.0f}% {direction} than the design "
            f"(median ratio {systematic:.2f} across {len(ratios)} comparable gaps). "
            "A single ratio across most gaps points at one wrong spacing value / "
            "theme token rather than many independent mistakes — report it as one "
            "finding with the per-gap table as evidence."
        )
    elif flagged:
        summary["verdict"] = (
            f"{len(flagged)} individual gap(s) outside tolerance while overall rhythm "
            "matches — localized spacing bug, see `gaps` for which."
        )
    elif len(pairs) < 3:
        summary["verdict"] = (
            f"INCONCLUSIVE: only {len(pairs)} band(s) matched, too few to judge "
            "spacing. The screen may be full-bleed (no empty rows to segment), the "
            "crops may be wrong, or the data states differ too much. Check the PNG, "
            "then adjust --crop-*/--roi-*/--min-gap, or fall back to visual review."
        )
    else:
        summary["verdict"] = (
            f"Spacing within tolerance across {len(ratios)} comparable gaps "
            f"(median ratio {systematic:.2f})." if ratios else
            "No comparable gaps found."
        )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
