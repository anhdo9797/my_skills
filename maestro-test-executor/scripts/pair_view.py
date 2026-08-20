#!/usr/bin/env python3
"""Build an aligned, diff-guided side-by-side comparison for Tier 3 design-mode review.

Why this exists: freeform "read the design screenshot, then read the app
screenshot, then judge if they match" fails in two ways. First, a Figma export
usually has NO status bar / OS nav baked in, while a real device screenshot
always does — so gridding both images independently with the same --cols/--rows
(as the old workflow did) puts cell "C4" over a different region of content in
each image. Any comparison built on that is comparing the wrong things without
anyone noticing. Second, judging "do these match?" as a single mental step
across two separately-read images is exactly the kind of diffuse, low-precision
task vision models under-perform on — small real differences get missed
(false negative), and the "comparison" quietly degrades into two independent
heuristic glances (not an actual comparison against the design).

This script fixes both:
  1. Crops each image to its CONTENT band (strips the design's absent chrome
     vs. the screenshot's real chrome) before anything else, so cell "C4"
     means the same region in both images.
  2. Resizes the cropped design onto the cropped screenshot's exact pixel
     dimensions, then computes a real per-pixel diff (masking known-dynamic
     regions: photos, avatars, live lists) so "this cell differs" is a
     measured fact, not a guess.
  3. Composes ONE image — design | actual, side by side, same grid — with
     every cell whose measured diff exceeds --cell-threshold flagged in amber.
     Reading one paired image beats juggling two: the flags force attention
     onto every cell that actually changed, so a real defect can't be quietly
     skipped, while cells with zero measured diff can't be imagined into a
     finding either.

The vision pass still does the judgment (Critical / Minor / data-driven-so-
excluded) — this script only guarantees nothing measurable gets skipped and
nothing is compared against the wrong region.

SCOPE — what this script deliberately does NOT measure
-----------------------------------------------------
This answers "is the right element here, with the right content and style?".
It cannot answer "is this gap 16dp like the design, or 28dp?", because step 2
resizes the design onto the screenshot's width AND height: force-fitting both
axes rescales the design's vertical rhythm onto the device's, so uniformly
inflated padding is normalized away and the diff comes back clean. Spacing,
margin, and element-size parity are a MEASUREMENT problem, not a diff problem —
run `spacing_audit.py` for those. The two are complementary and a design-mode
review wants both: this one for presence/content/style, spacing_audit for
geometry.

Usage:
  python3 pair_view.py DESIGN.png ACTUAL.png --cols 6 --rows 13 \\
      --crop-actual-top 6% --crop-actual-bottom 4% \\
      --out report/grid/TC-010_pair.png

  # with a dynamic-content mask (coordinates in the CROPPED/resized space,
  # i.e. after crop — percentages are safest since they survive the resize)
  python3 pair_view.py DESIGN.png ACTUAL.png --cols 6 --rows 13 \\
      --crop-actual-top 6% --crop-actual-bottom 4% \\
      --mask 0%,20%,100%,55% \\
      --out report/grid/TC-010_pair.png

Typical crop starting points (verify against the composite — if content still
looks offset, adjust and regenerate before trusting any cell citation):
  iOS w/ notch/Dynamic Island:  --crop-actual-top 7%  --crop-actual-bottom 4%
  iOS home button:              --crop-actual-top 5%  --crop-actual-bottom 1%
  Android gesture nav:          --crop-actual-top 4%  --crop-actual-bottom 3%
  Android 3-button nav:         --crop-actual-top 4%  --crop-actual-bottom 5%
If the Figma export itself includes a device mockup frame (rare — most node
exports are content-only), use --crop-design-top/--crop-design-bottom too.

Dependency: Pillow. Install once with:  pip3 install Pillow
"""

import argparse
import json
import os
import sys
from functools import reduce

try:
    from PIL import Image, ImageDraw, ImageFont, ImageChops
except ImportError:
    sys.stderr.write(
        "ERROR: Pillow is required for pair_view.\n"
        "Install it once with:  pip3 install Pillow\n"
    )
    sys.exit(2)


def _column_label(idx: int) -> str:
    label = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        label = chr(ord("A") + rem) + label
    return label


def _load_font(size: int):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def parse_len(value, total):
    """Parse a length given as pixels ('120') or a percentage of `total` ('6%')."""
    value = str(value).strip()
    if value.endswith("%"):
        return int(round(float(value[:-1]) / 100.0 * total))
    return int(round(float(value)))


def parse_mask(spec, width, height):
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 4:
        raise ValueError(f"mask must be x1,y1,x2,y2 — got {spec!r}")
    x1 = parse_len(parts[0], width)
    y1 = parse_len(parts[1], height)
    x2 = parse_len(parts[2], width)
    y2 = parse_len(parts[3], height)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def build_masks(mask_specs, masks_file, width, height):
    masks = []
    for spec in mask_specs or []:
        masks.append(parse_mask(spec, width, height))
    if masks_file:
        with open(masks_file) as fh:
            cfg = json.load(fh)
        for spec in cfg.get("masks", []):
            if isinstance(spec, str):
                masks.append(parse_mask(spec, width, height))
            else:
                masks.append(parse_mask(",".join(str(v) for v in spec), width, height))
    return masks


def _crop_band(img, top, bottom):
    w, h = img.size
    y0 = parse_len(top, h) if top else 0
    y1 = h - (parse_len(bottom, h) if bottom else 0)
    if y1 <= y0:
        raise ValueError("crop-top/crop-bottom leave no content band")
    return img.crop((0, y0, w, y1))


def _auto_grid(width, height, cols, rows):
    if cols and rows:
        return cols, rows
    if not cols:
        cols = 6 if width <= height else max(6, round(6 * width / height))
    if not rows:
        cell = width / cols
        rows = max(1, round(height / cell))
    return int(cols), int(rows)


def _text(draw, x, y, s, font, anchor, fg=(255, 255, 0, 255)):
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw.text((x + dx, y + dy), s, font=font, anchor=anchor, fill=(0, 0, 0, 235))
    draw.text((x, y), s, font=font, anchor=anchor, fill=fg)


def _draw_grid(img, cols, rows, flagged_ratios=None):
    """Return an RGB image with grid lines, cell ids, and (if given) amber
    flags on cells whose measured diff ratio exceeds the caller's threshold."""
    img = img.convert("RGBA")
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cell_w, cell_h = w / cols, h / rows
    id_font = _load_font(max(11, int(min(cell_w, cell_h) * 0.16)))
    hdr_font = _load_font(max(13, int(min(cell_w, cell_h) * 0.22)))
    line_w = max(1, int(min(w, h) * 0.0016))
    line = (255, 60, 60, 140)

    if flagged_ratios:
        for (c, r), ratio in flagged_ratios.items():
            x0, y0 = c * cell_w, r * cell_h
            x1, y1 = (c + 1) * cell_w, (r + 1) * cell_h
            draw.rectangle([x0, y0, x1, y1], fill=(255, 165, 0, 60))
            draw.rectangle([x0, y0, x1 - 1, y1 - 1], outline=(230, 140, 0, 220),
                           width=max(2, line_w + 1))
            _text(draw, x1 - 3, y1 - 3, f"{round(ratio * 100)}%", id_font, "rb",
                  fg=(255, 210, 90, 255))

    for c in range(cols + 1):
        x = round(c * cell_w)
        draw.line([(x, 0), (x, h)], fill=line, width=line_w)
    for r in range(rows + 1):
        y = round(r * cell_h)
        draw.line([(0, y), (w, y)], fill=line, width=line_w)

    for r in range(rows):
        for c in range(cols):
            cid = f"{_column_label(c)}{r + 1}"
            x0, y0 = c * cell_w, r * cell_h
            _text(draw, x0 + line_w + 2, y0 + line_w + 1, cid, id_font, "la")
    for c in range(cols):
        _text(draw, c * cell_w + cell_w / 2, 2, _column_label(c), hdr_font, "ma")
    for r in range(rows):
        _text(draw, 2, r * cell_h + cell_h / 2, str(r + 1), hdr_font, "lm")

    return Image.alpha_composite(img, layer).convert("RGB")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("design", help="design/Figma reference image")
    ap.add_argument("actual", help="real device screenshot")
    ap.add_argument("--out", required=True, help="output composite image path")
    ap.add_argument("--cols", type=int, default=0, help="columns (0 = auto)")
    ap.add_argument("--rows", type=int, default=0, help="rows (0 = auto from aspect)")
    ap.add_argument("--crop-design-top", default=None, help="px or %% to strip from design top")
    ap.add_argument("--crop-design-bottom", default=None, help="px or %% to strip from design bottom")
    ap.add_argument("--crop-actual-top", default=None,
                    help="px or %% to strip from actual top (status bar) — the usual knob")
    ap.add_argument("--crop-actual-bottom", default=None,
                    help="px or %% to strip from actual bottom (OS nav) — the usual knob")
    ap.add_argument("--mask", action="append",
                    help="x1,y1,x2,y2 (px or %%, in the cropped/resized space) region to "
                         "exclude from the diff — repeatable, use for dynamic content")
    ap.add_argument("--masks-file", help='JSON file: {"masks": ["x1,y1,x2,y2", ...]}')
    ap.add_argument("--tolerance", type=int, default=24,
                    help="per-channel intensity delta below which a pixel counts as "
                         "unchanged (0-255, default 24, absorbs anti-aliasing/font hinting)")
    ap.add_argument("--cell-threshold", type=float, default=0.08,
                    help="fraction of a cell's pixels that must differ for the cell to be "
                         "flagged amber (default 0.08 = 8%%)")
    ap.add_argument("--aspect-tolerance", type=float, default=0.03,
                    help="max allowed relative difference between the design's and actual's "
                         "cropped aspect ratio before per-cell diffs are distrusted (default "
                         "0.03 = 3%%). Beyond this, a crop can align one edge but content in "
                         "between (e.g. a bottom-anchored button on a taller/shorter screen) "
                         "shifts by a different amount — measured diffs stop being trustworthy "
                         "evidence of a real defect.")
    args = ap.parse_args()

    for p in (args.design, args.actual):
        if not os.path.exists(p):
            sys.stderr.write(f"ERROR: file not found: {p}\n")
            sys.exit(1)

    design = Image.open(args.design).convert("RGB")
    actual = Image.open(args.actual).convert("RGB")

    try:
        if args.crop_design_top or args.crop_design_bottom:
            design = _crop_band(design, args.crop_design_top, args.crop_design_bottom)
        if args.crop_actual_top or args.crop_actual_bottom:
            actual = _crop_band(actual, args.crop_actual_top, args.crop_actual_bottom)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        sys.exit(1)

    # A crop only aligns a fixed top/bottom chrome band. If the two images'
    # cropped CONTENT aspect ratios still disagree beyond tolerance, no single
    # crop can be right everywhere — a responsive layout (e.g. a bottom-anchored
    # button, a cover-fit background photo) places the "same" element at a
    # different fractional height on a relatively taller/shorter screen, purely
    # as correct adaptive behavior, not a defect. Per-cell diffs computed under
    # that condition are noise, not evidence, so flag it loudly rather than let
    # a wall of amber cells masquerade as measured facts.
    dw, dh = design.size
    aw0, ah0 = actual.size
    design_aspect = dw / dh
    actual_aspect = aw0 / ah0
    aspect_mismatch_pct = abs(design_aspect - actual_aspect) / actual_aspect
    aspect_unreliable = aspect_mismatch_pct > args.aspect_tolerance

    # Normalize the design onto the actual's cropped pixel size — after this,
    # every cell address covers the same fractional content region in both,
    # PROVIDED the aspect ratios agree (see check above).
    aw, ah = actual.size
    design_resized = design.resize((aw, ah))

    cols, rows = _auto_grid(aw, ah, args.cols, args.rows)

    try:
        masks = build_masks(args.mask, args.masks_file, aw, ah)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"ERROR: bad mask spec: {exc}\n")
        sys.exit(1)

    design_cmp = design_resized.copy()
    actual_cmp = actual.copy()
    for box in masks:
        design_cmp.paste((0, 0, 0), box)
        actual_cmp.paste((0, 0, 0), box)

    diff = ImageChops.difference(design_cmp, actual_cmp)
    tol = args.tolerance
    bands = [b.point(lambda v: 255 if v > tol else 0) for b in diff.split()]
    changed_mask = reduce(ImageChops.lighter, bands)

    cell_w, cell_h = aw / cols, ah / rows
    cell_diff_ratio = {}
    flagged = {}
    for r in range(rows):
        for c in range(cols):
            x0, y0 = int(c * cell_w), int(r * cell_h)
            x1, y1 = int((c + 1) * cell_w), int((r + 1) * cell_h)
            crop = changed_mask.crop((x0, y0, x1, y1))
            hist = crop.histogram()
            total_px = max(1, crop.width * crop.height)
            changed_px = hist[255] if len(hist) > 255 else 0
            ratio = changed_px / total_px
            cid = f"{_column_label(c)}{r + 1}"
            cell_diff_ratio[cid] = round(ratio, 4)
            if ratio > args.cell_threshold:
                flagged[(c, r)] = ratio

    # If the aspect ratios disagree beyond tolerance, the per-cell diff is not
    # trustworthy evidence — don't draw amber flags that look like measured
    # facts. Still compute cell_diff_ratio (printed below) for anyone who wants
    # the raw numbers, but the composite itself only shows real flags when the
    # alignment holds.
    draw_flagged = {} if aspect_unreliable else flagged

    design_grid = _draw_grid(design_resized, cols, rows)
    actual_grid = _draw_grid(actual, cols, rows, flagged_ratios=draw_flagged)

    gap = max(4, int(aw * 0.01))
    label_h = max(20, int(ah * 0.03))
    warn_h = max(28, int(ah * 0.035)) if aspect_unreliable else 0
    canvas_w = aw * 2 + gap
    canvas_h = ah + label_h + warn_h
    canvas = Image.new("RGB", (canvas_w, canvas_h), (30, 30, 30))
    canvas.paste(design_grid, (0, label_h + warn_h))
    canvas.paste(actual_grid, (aw + gap, label_h + warn_h))

    draw = ImageDraw.Draw(canvas)
    hdr_font = _load_font(max(14, int(label_h * 0.6)))
    actual_label = ("ACTUAL (diff unreliable — see warning above)" if aspect_unreliable
                    else "ACTUAL (amber = measured diff)")
    draw.text((aw / 2, label_h / 2 + warn_h), "DESIGN", font=hdr_font, anchor="mm",
              fill=(255, 255, 255))
    draw.text((aw + gap + aw / 2, label_h / 2 + warn_h), actual_label, font=hdr_font,
              anchor="mm", fill=(255, 210, 90) if not aspect_unreliable else (255, 120, 120))

    if aspect_unreliable:
        warn_font = _load_font(max(14, int(warn_h * 0.55)))
        draw.rectangle([0, 0, canvas_w, warn_h], fill=(120, 20, 20))
        draw.text(
            (canvas_w / 2, warn_h / 2),
            f"⚠ ASPECT RATIO MISMATCH ({aspect_mismatch_pct * 100:.1f}%) — cell diffs are "
            f"NOT reliable here; judge presence/content visually, run spacing_audit.py "
            f"for geometry",
            font=warn_font, anchor="mm", fill=(255, 255, 255),
        )

    canvas.save(args.out)

    summary = {
        "out": args.out,
        "design": args.design,
        "actual": args.actual,
        "cols": cols,
        "rows": rows,
        "compared_size": [aw, ah],
        "masks": len(masks),
        "cell_threshold": args.cell_threshold,
        "design_aspect": round(design_aspect, 4),
        "actual_aspect": round(actual_aspect, 4),
        "aspect_mismatch_pct": round(aspect_mismatch_pct, 4),
        "aspect_ratio_reliable": not aspect_unreliable,
        "flagged_cells": [] if aspect_unreliable else sorted(
            f"{_column_label(c)}{r + 1}" for (c, r) in flagged
        ),
        "cell_diff_ratio": cell_diff_ratio,
    }
    if aspect_unreliable:
        summary["warning"] = (
            f"Design and actual content aspect ratios differ by "
            f"{aspect_mismatch_pct * 100:.1f}% (> {args.aspect_tolerance * 100:.0f}% tolerance) "
            "after cropping. No single crop aligns a responsive layout across two different "
            "aspect ratios, so flagged_cells is intentionally empty and cell_diff_ratio should "
            "be treated as advisory only, not proof of a defect. Judge presence, content, "
            "and style from the composite instead — and do NOT conclude 'spacing looks "
            "fine': this script cannot see spacing error at all (it resized both axes). "
            "Run spacing_audit.py on the same pair to measure gaps/margins, which is "
            "aspect-ratio independent because it scales by width only and compares "
            "differences between element positions."
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
