#!/usr/bin/env python3
"""Deterministic visual-regression diff between an approved baseline and a fresh app
screenshot.

This is Tier 2 of UI validation: it lets regression runs catch layout/color/visual
drift WITHOUT an Agent in the loop. The Agent's vision is only needed once, at
authoring time, to (a) approve the baseline and (b) decide which regions are dynamic
(API images, live data, system chrome) and must be masked out so they don't produce
false positives on every run.

Masked regions are excluded from the comparison entirely. Provide them as:
  - --ignore-top / --ignore-bottom : strip the status bar and OS nav band (px or %)
  - --mask x1,y1,x2,y2             : rectangle to exclude (repeatable; px or %)
  - --masks-file path.json         : a saved list of masks (see --emit-config)

Output: a JSON summary on stdout and an optional diff heatmap image. Exit code is 0
when the changed-pixel ratio is within --threshold, 1 when it exceeds it (so CI can
gate on it), and 2 on usage/IO errors.

Requires Pillow (`pip install Pillow`).

Examples:
  # Strip top 6% (status bar) and bottom 5% (nav), mask a hero image region, 1% budget
  python3 scripts/compare_screenshots.py baseline/TC-010.png screenshots/TC-010_result.png \\
      --ignore-top 6% --ignore-bottom 5% --mask 0,180,1080,780 \\
      --threshold 0.01 --out report/diff/TC-010_diff.png

  # Reuse masks saved alongside the baseline
  python3 scripts/compare_screenshots.py baseline/TC-010.png screenshots/TC-010_result.png \\
      --masks-file baseline/TC-010.masks.json --threshold 0.01
"""

import argparse
import json
import sys

try:
    from PIL import Image, ImageChops
    from functools import reduce
except ImportError:
    sys.stderr.write(
        "Pillow is required: pip install Pillow\n"
        "(Tier 2 visual diff needs it; Tier 1 assertion-based checks do not.)\n"
    )
    sys.exit(2)


def parse_len(value, total):
    """Parse a length given as pixels ('120') or a percentage of `total` ('6%')."""
    value = str(value).strip()
    if value.endswith("%"):
        return int(round(float(value[:-1]) / 100.0 * total))
    return int(round(float(value)))


def parse_mask(spec, width, height):
    """Parse 'x1,y1,x2,y2' (px or %) into an integer pixel box."""
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 4:
        raise ValueError(f"mask must be x1,y1,x2,y2 — got {spec!r}")
    x1 = parse_len(parts[0], width)
    y1 = parse_len(parts[1], height)
    x2 = parse_len(parts[2], width)
    y2 = parse_len(parts[3], height)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def build_masks(args, width, height):
    masks = []
    if args.ignore_top:
        masks.append((0, 0, width, parse_len(args.ignore_top, height)))
    if args.ignore_bottom:
        band = parse_len(args.ignore_bottom, height)
        masks.append((0, height - band, width, height))
    for spec in args.mask or []:
        masks.append(parse_mask(spec, width, height))
    if args.masks_file:
        with open(args.masks_file) as fh:
            cfg = json.load(fh)
        for spec in cfg.get("masks", []):
            if isinstance(spec, str):
                masks.append(parse_mask(spec, width, height))
            else:  # [x1, y1, x2, y2]
                masks.append(parse_mask(",".join(str(v) for v in spec), width, height))
        if "ignore_top" in cfg:
            masks.append((0, 0, width, parse_len(cfg["ignore_top"], height)))
        if "ignore_bottom" in cfg:
            band = parse_len(cfg["ignore_bottom"], height)
            masks.append((0, height - band, width, height))
    return masks


def main():
    ap = argparse.ArgumentParser(description="Deterministic baseline vs. actual screenshot diff.")
    ap.add_argument("baseline", help="approved baseline image")
    ap.add_argument("actual", help="fresh app screenshot to check")
    ap.add_argument("--ignore-top", help="strip top band (status bar), px or %% (e.g. 6%%)")
    ap.add_argument("--ignore-bottom", help="strip bottom band (OS nav), px or %%")
    ap.add_argument("--mask", action="append", help="x1,y1,x2,y2 region to exclude (repeatable), px or %%")
    ap.add_argument("--masks-file", help="JSON file with {masks:[...], ignore_top, ignore_bottom}")
    ap.add_argument("--tolerance", type=int, default=24,
                    help="per-channel intensity delta below which a pixel counts as unchanged (0-255, default 24)")
    ap.add_argument("--threshold", type=float, default=0.01,
                    help="max allowed changed-pixel ratio over the compared area (default 0.01 = 1%%)")
    ap.add_argument("--out", help="path to write a diff heatmap PNG (optional)")
    args = ap.parse_args()

    try:
        base = Image.open(args.baseline).convert("RGB")
        act = Image.open(args.actual).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"cannot open images: {exc}\n")
        return 2

    # Normalize sizes — resize actual to the baseline's dimensions if they differ.
    resized = False
    if act.size != base.size:
        act = act.resize(base.size)
        resized = True
    width, height = base.size

    try:
        masks = build_masks(args, width, height)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"bad mask spec: {exc}\n")
        return 2

    # Black out masked regions in both images so they contribute zero difference.
    black = (0, 0, 0)
    for box in masks:
        base.paste(black, box)
        act.paste(black, box)

    diff = ImageChops.difference(base, act)

    total = width * height
    masked = 0
    # Approximate masked-pixel count (rectangles may overlap; this is a lower-bound display value).
    for (x1, y1, x2, y2) in masks:
        masked += max(0, x2 - x1) * max(0, y2 - y1)
    masked = min(masked, total)
    compared = max(1, total - masked)

    # Count pixels where ANY channel exceeds the tolerance — done with band-level
    # point()/lighter() so it stays fast on multi-megapixel device screenshots.
    # Masked pixels are (0,0,0) in both images, so their diff is 0 and never counts.
    tol = args.tolerance
    bands = [b.point(lambda v: 255 if v > tol else 0) for b in diff.split()]
    changed_mask = reduce(ImageChops.lighter, bands)
    changed = changed_mask.histogram()[255]

    ratio = changed / compared
    passed = ratio <= args.threshold

    if args.out:
        try:
            # Heatmap: amplify the diff so reviewers can see where it drifted.
            heat = diff.point(lambda v: min(255, v * 4))
            heat.save(args.out)
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"warning: could not write diff image: {exc}\n")

    summary = {
        "baseline": args.baseline,
        "actual": args.actual,
        "resized_actual": resized,
        "image_size": [width, height],
        "masks": len(masks),
        "changed_pixels": changed,
        "compared_pixels": compared,
        "diff_ratio": round(ratio, 5),
        "threshold": args.threshold,
        "passed": passed,
        "diff_image": args.out or None,
    }
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
