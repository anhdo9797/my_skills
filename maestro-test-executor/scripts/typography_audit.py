#!/usr/bin/env python3
"""Measure font size and font weight *relative to a design reference*.

WHY THIS EXISTS — the failure it fixes
--------------------------------------
Until now this skill said out loud that typography could not be tested: "is this
font 16sp?" cannot be answered from a screenshot, so every typography finding
was filed as a soft note for a human. That is technically true and practically
useless — it meant a title rendering at body size, or a semibold heading
rendering regular, produced no verdict at all. The UI test could not fail, so it
was not a test.

The mistake was the question. "Is this 16sp?" is unanswerable from pixels, but it
is also not what a design comparison needs to know. What it needs is:

  * Is this text the same size as the design says, *proportionally*?
  * Is it still bigger than body text by the same factor the design uses?
  * Is it as heavy as the design, *relative to* the other text on the screen?

Those are ratio questions, and ratios ARE measurable from pixels — reliably, and
independently of device density, system font scaling, and the design export's
scale factor, all of which make absolute pixel values meaningless across the two
images. So this script never claims an sp value. It measures two dimensionless
numbers per text band and compares them:

  size_index   = x-height in width-normalized px      -> how big the text renders
  weight_index = median stroke thickness / x-height   -> how heavy the strokes are

WHAT MAKES THE COMPARISON HONEST — two independent views
--------------------------------------------------------
1. CROSS-IMAGE ratio (actual vs design, after normalizing both to the design's
   width). Catches "every font on this screen renders 15% smaller than design".
2. INTRA-SCREEN ratio (each band vs the median text size *within its own
   image*). Catches "the title is supposed to be 1.8x body and renders 1.1x".
   This one is completely immune to scale: it never compares a pixel in one
   image to a pixel in the other, only a proportion to a proportion.

Both matter, and they fail differently. A screen where the whole type scale is
uniformly shrunk passes (2) and fails (1). A screen where only the heading lost
its style passes (1) and fails (2). Reporting both is what turns "typography
looks off" into a finding a developer can act on in one read.

WEIGHT, HONESTLY
----------------
Stroke thickness divided by x-height is a real, scale-free weight proxy: at the
same nominal size, semibold strokes are measurably thicker than regular. It is
noisier than size — anti-aliasing, sub-pixel rendering, and colour contrast all
move it a few percent — so the default tolerance is wider, and the script
reports `weight_confidence` per band from the sample size it had. Treat a
weight finding backed by `low` confidence as an estimate; treat one backed by
`high` confidence, on a band with plenty of glyphs, as a measurement.

WHAT IT CANNOT DO — say this in the report
------------------------------------------
- It measures rendered ink, not framework values. It proves "this heading
  renders at 0.62x the design's heading-to-body ratio", not `fontSize: 24`.
- It needs text. Bands that are photos, filled shapes, or dividers are detected
  and marked `is_text: false`; they are excluded from typography findings rather
  than guessed at.
- A band is one visual run of ink, so two tightly-leaded lines merge into one
  band. That is correct (a paragraph is one type style) and it happens
  identically on both sides, so the comparison stays fair.
- Data differences shift the band sequence: an empty state where the design
  shows three cards is not a typography defect. Unmatched bands are reported
  as `unmatched_*` and never as findings.

USAGE
-----
  python3 typography_audit.py DESIGN.png ACTUAL.png --out report/TC-01-type.png

  # strip OS chrome first, exactly like spacing_audit
  python3 typography_audit.py DESIGN.png ACTUAL.png \\
      --crop-design-top 6% --crop-design-bottom 2% --crop-actual-top 4% \\
      --out report/TC-01-type.png

  # ignore a live photo / avatar row that is not text
  python3 typography_audit.py DESIGN.png ACTUAL.png \\
      --mask-actual 0%,20%,100%,38% --out report/TC-01-type.png

Reads the JSON on stdout for the numbers; read the PNG only to see which band is
which. Dependency: Pillow (pip3 install Pillow).
"""

import argparse
import json
import os
import statistics
import sys
from functools import reduce

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from PIL import Image, ImageChops, ImageDraw
except ImportError:
    sys.stderr.write(
        "ERROR: Pillow is required for typography_audit.\n"
        "Install it once with:  pip3 install Pillow\n"
    )
    sys.exit(2)

from spacing_audit import (  # noqa: E402  (path set above)
    _load_font,
    align,
    col_extent,
    crop_band,
    ink_mask,
    modal_background,
    parse_len,
    row_profile,
    segment,
)


# --------------------------------------------------------------- measurement

def _apply_masks(img, masks):
    """Paint masked rectangles with the page background so they read as empty.

    Masking to background (rather than to black) keeps the region out of the ink
    profile entirely, so a live photo neither creates a band of its own nor
    bridges the gap between two real ones.
    """
    if not masks:
        return img
    w, h = img.size
    bg = modal_background(img)
    out = img.copy()
    draw = ImageDraw.Draw(out)
    for spec in masks:
        x1, y1, x2, y2 = [p.strip() for p in spec.split(",")]
        draw.rectangle(
            [parse_len(x1, w), parse_len(y1, h), parse_len(x2, w), parse_len(y2, h)],
            fill=bg,
        )
    return out


def ink_gray(img, bg):
    """Per-pixel distance from the background, as an L-mode image.

    The binary mask that `spacing_audit` uses is right for finding *where*
    content is, but typography is measured in fractions of a pixel: a design
    exported at 1x renders an x-height only 8-15 px tall, so rounding every
    edge pixel to fully-ink or fully-empty costs ~7% on the very number the
    verdict turns on. Keeping the anti-aliased grey lets each edge pixel count
    as the fraction of ink it actually is.
    """
    diff = ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, bg))
    return reduce(ImageChops.lighter, diff.split())


def _solid_level(gray):
    """Intensity that counts as fully-inked, from the band's own histogram.

    Text drawn in mid-grey on white and text drawn in black on white have very
    different absolute distances from the background, so a fixed "255 = solid"
    scale would read the grey text as permanently half-covered and inflate its
    apparent stroke. Taking a high percentile of the band's own non-background
    pixels calibrates the scale to whatever ink this band actually uses.
    """
    hist = gray.histogram()
    total = sum(hist[8:])  # ignore near-background noise
    if total <= 0:
        return 255
    target = total * 0.90
    running = 0
    for value in range(8, 256):
        running += hist[value]
        if running >= target:
            return max(24, value)
    return 255


def coverage_profile(gray, solid, x0, x1):
    """Per-row mean ink coverage in [0,1] over the band's ink columns."""
    strip = gray.crop((x0, 0, x1, gray.size[1]))
    col = strip.convert("F").resize((1, strip.size[1]), Image.BOX)
    return [min(1.0, col.getpixel((0, y)) / float(solid))
            for y in range(strip.size[1])]


def text_lines(profile, floor_frac=0.12):
    """Split a band's profile into individual lines of text.

    This has to happen before any x-height is measured, and the reason is the
    bug it fixes. The core of a line is found at a fraction of a peak — but if
    that peak is taken across a whole band, a section heading sets it for
    everything beneath, and a smaller, lighter caption on the next line never
    reaches the threshold at all. The caption becomes invisible: not measured
    wrong, simply absent, while the band reports the heading's size as if it
    were the whole block's. A caption that has grown to twice its designed size
    then produces no size finding whatsoever.

    Lines are separated instead by where the ink actually runs out. Between two
    lines the coverage falls to near zero; inside a line it never does, even
    through descenders and the slack middles of round letters. A low floor —
    a small fraction of the band's peak — cuts exactly there, and each line is
    then free to be measured against its own peak.
    """
    if not profile:
        return []
    peak = max(profile)
    if peak <= 0:
        return []
    floor = peak * floor_frac

    runs, start = [], None
    for y, value in enumerate(profile):
        if value > floor:
            if start is None:
                start = y
        elif start is not None:
            runs.append((start, y))
            start = None
    if start is not None:
        runs.append((start, len(profile)))
    return [r for r in runs if r[1] - r[0] >= 2]


def subpixel_cores(profile, peak_frac=0.5):
    """Row ranges above `peak_frac` of the peak, with interpolated boundaries.

    For a line of text this isolates the x-height core — the dense middle where
    almost every glyph has ink — leaving out the sparse ascender and descender
    rows only a few letters reach. The core is the stable part to measure: it
    barely moves when the text happens to contain no 'g' or 'h', whereas the
    full ink extent swings by 30% on wording alone.

    Boundaries are interpolated between the two rows that straddle the level
    rather than snapped to whichever row crossed it. On a 1x design export an
    x-height spans about ten rows, so snapping quantizes the reading to ~10%
    steps — coarser than the tolerance the comparison uses, which would make the
    tool's own rounding the loudest signal in the result.

    Call this per line, on that line's own profile. Handed a whole band it will
    silently report only the boldest line — see `text_lines`.
    """
    if not profile:
        return []
    peak = max(profile)
    if peak <= 0:
        return []
    level = peak * peak_frac

    cores, start = [], None
    for y, value in enumerate(profile):
        above = value >= level
        if above and start is None:
            prev = profile[y - 1] if y > 0 else 0.0
            frac = (level - prev) / (value - prev) if value > prev else 0.0
            start = (y - 1) + frac if y > 0 else float(y)
        elif not above and start is not None:
            prev = profile[y - 1]
            frac = (prev - level) / (prev - value) if prev > value else 0.0
            cores.append((start, (y - 1) + frac))
            start = None
    if start is not None:
        cores.append((start, float(len(profile) - 1)))
    cores = [c for c in cores if c[1] - c[0] >= 1.0]

    # A single line of text does not have flat ink through its x-height. Round
    # letters (o, a, e) put most of their ink in the curves at the top and
    # bottom of the core and comparatively little through the middle, so the
    # profile dips there — and on lighter text that dip can fall below half the
    # peak and split one x-height into two "cores". The median of those halves
    # then reports a glyph roughly a third of its real size, which is not a
    # small error: it is the difference between a clean pass and a fabricated
    # Critical finding.
    #
    # Within a single line every such dip is an artefact, so they all merge.
    # Separating actual lines is `text_lines`' job, done before this is called.
    if len(cores) <= 1:
        return cores
    return [(cores[0][0], cores[-1][1])]


def line_metrics(profile, line):
    """x-height of one text line, measured against that line's own peak."""
    top, bottom = line
    local = profile[top:bottom]
    cores = subpixel_cores(local)
    if not cores:
        return None
    return {
        "top": top + cores[0][0],
        "bottom": top + cores[-1][1],
        "x_height": cores[-1][1] - cores[0][0],
    }


def stroke_from_coverage(gray, binary, solid, x0, x1, rows):
    """Mean stroke thickness, from ink area divided by half the edge count.

    A scanline crossing a glyph stem produces one run of ink whose length is the
    stroke thickness, and two ink/background transitions. So across a whole row,
    (total coverage) / (transitions / 2) is the mean run length — the stroke —
    and it stays accurate even when individual runs are one or two pixels wide,
    because the area term is measured in sub-pixel coverage while the divisor is
    a count of edges rather than a rounded length. Counting run lengths directly
    (the obvious approach) fails exactly where it matters: a 1x design export
    puts a regular-weight stem at 1.4 px and a semibold one at 1.9 px, and both
    round to the same integer.

    Runs wider than a quarter of the band are excluded before either term is
    accumulated: those are rules, underlines, filled chips, and icon bodies, and
    a single one of them outweighs every real stem on the line.
    """
    px = binary.load()
    gpx = gray.load()
    max_run = max(3, int((x1 - x0) * 0.25))
    area = 0.0
    edges = 0
    for y in rows:
        run_len, run_cov = 0, 0.0
        for x in range(x0, x1):
            if px[x, y]:
                run_len += 1
                run_cov += min(1.0, gpx[x, y] / float(solid))
            elif run_len:
                if run_len <= max_run:
                    area += run_cov
                    edges += 2
                run_len, run_cov = 0, 0.0
        if run_len and run_len <= max_run:
            area += run_cov
            edges += 2
    if edges == 0:
        return 0.0, 0
    return (2.0 * area) / edges, edges // 2


def _bg_region(band, bg, tolerance):
    """Bounding box of the pixels that ARE the band's local background.

    A label printed white-on-blue inside a filled button breaks the naive
    reading: taking the button's blue as the background correctly makes the
    label ink, but the white page margins on either side of the button differ
    from blue too, so they count as one enormous glyph spanning the full height
    of the band. The measured x-height then comes out as the button's height and
    the finding is nonsense.

    Restricting to where the local background actually appears fixes it without
    a special case: on a plain text band that region is the whole band, and on a
    button band it is exactly the button, which is the only place the label
    lives anyway.
    """
    diff = ink_gray(band, bg)
    inside = diff.point(lambda v: 255 if v <= tolerance else 0)
    return inside.getbbox()


def _style_runs(lines, ratio_threshold=1.25):
    """Group consecutive text lines into runs that share one type style.

    Segmentation groups by ink, so a section header and the caption under it
    become one band whenever their leading is tight — and then a single median
    x-height describes neither of them. That is not a cosmetic inaccuracy: when
    only the caption's size changes, the merged median barely moves, the size
    check passes, and the defect resurfaces as a phantom *weight* change,
    because stroke-over-x-height is the one ratio the merge does distort. The
    tool then reports the wrong property on the right element, which is worse
    than reporting nothing at all.

    Consecutive lines stay together only while their x-heights are within
    `ratio_threshold`. A real type scale steps by more than that between a
    heading and body copy, while the lines *inside* one paragraph vary by a few
    percent — so the split lands on style boundaries rather than on wording.
    """
    if not lines:
        return []
    runs, current = [], [lines[0]]
    for line in lines[1:]:
        reference = statistics.median([l["x_height"] for l in current])
        height = line["x_height"]
        span = max(height, reference) / max(1e-6, min(height, reference))
        if span > ratio_threshold:
            runs.append(current)
            current = [line]
        else:
            current.append(line)
    runs.append(current)
    return runs


def measure_band(img, top, bottom, tolerance):
    """Measure a content band's typography, one entry per type style found.

    The background is re-derived *locally* for each band. A page-level
    background works for text on the page, but a label inside a filled button or
    a coloured card differs from the page background across its whole area, so a
    page-level ink mask paints the entire component as ink and reports it as a
    solid block. Taking the band's own modal colour makes the button's fill the
    background and its label the ink — which is what we actually want to measure.

    Returns a list because one ink band can hold more than one type style; see
    `_style_runs`. Each entry is measured only over its own rows, so a heading
    and its caption get independent sizes, weights, and stem counts.
    """
    w = img.size[0]
    band = img.crop((0, top, w, bottom))
    if band.size[1] < 3:
        return []

    bg = modal_background(band)
    region = _bg_region(band, bg, tolerance)
    x_offset = y_offset = 0
    if region:
        rx0, ry0, rx1, ry1 = region
        if (rx1 - rx0) >= 8 and (ry1 - ry0) >= 3:
            band = band.crop((rx0, ry0, rx1, ry1))
            x_offset, y_offset = rx0, ry0

    binary = ink_mask(band, bg, tolerance)
    extent = col_extent(binary, 0, band.size[1], 0.002)
    if not extent:
        return []
    x0, x1 = extent
    ink_width = x1 - x0
    if ink_width < 4:
        return []

    gray = ink_gray(band, bg)
    solid = _solid_level(gray.crop((x0, 0, x1, band.size[1])))
    profile = coverage_profile(gray, solid, x0, x1)
    lines = [m for m in (line_metrics(profile, line)
                         for line in text_lines(profile)) if m]
    if not lines:
        return []

    runs = _style_runs(lines)
    out = []
    for index, run in enumerate(runs):
        x_height = statistics.median([l["x_height"] for l in run])
        core_rows = [y for l in run
                     for y in range(int(round(l["top"])),
                                    max(int(round(l["top"])) + 1,
                                        int(round(l["bottom"]))))
                     if 0 <= y < band.size[1]]
        if not core_rows:
            continue
        stroke, stems = stroke_from_coverage(gray, binary, solid, x0, x1, core_rows)
        density = sum(profile[y] for y in core_rows) / float(len(core_rows))

        # Each run gets its own horizontal extent: a short heading and a wide
        # caption in the same band have different ink widths, and reusing the
        # band's combined extent would put both boxes around the wider one.
        run_top = max(0, int(round(run[0]["top"])) - 1)
        run_bottom = min(band.size[1], int(round(run[-1]["bottom"])) + 1)
        run_extent = col_extent(binary, run_top, run_bottom, 0.002) or (x0, x1)

        # A run is text when its ink is sparse, broken into many separate stems,
        # organized into cores of a plausible glyph height, and drawn with a
        # stroke that could belong to a typeface. Photos and filled shapes fail
        # the density test; dividers and icons fail the stem count; and the
        # stroke-to-x-height bound catches the leftovers — a chevron, an
        # underline, or the tail of a descender caught as its own run reports a
        # stroke as thick as the mark is tall, which no font does between
        # hairline and black.
        weight = stroke / x_height if x_height else 0.0
        is_text = (
            x_height >= 3.0
            and 0.03 <= density <= 0.62
            and stems >= 10
            and 0.06 <= weight <= 0.55
        )

        out.append({
            "top": top + y_offset + run_top,
            "bottom": top + y_offset + run_bottom,
            "band_top": top,
            "band_bottom": bottom,
            "style_run": index,
            "style_runs_in_band": len(runs),
            "lines": len(run),
            "ink_left": run_extent[0] + x_offset,
            "ink_right": run_extent[1] + x_offset,
            "x_height": round(x_height, 3),
            "ink_height": run_bottom - run_top,
            "stroke": round(stroke, 3),
            "weight_index": round(stroke / x_height, 4) if x_height else None,
            "ink_density": round(density, 4),
            "stroke_samples": stems,
            "is_text": is_text,
        })
    return out


def _weight_confidence(samples):
    """How much to trust a weight ratio, from how many stems it averaged over.

    Stated per band because it changes how the finding should be written: a
    two-word label gives a handful of stems and a noisy mean, while a paragraph
    gives hundreds and a stable one. Reporting the same certainty for both is
    how a rendering artefact gets filed as a bug.
    """
    if samples >= 120:
        return "high"
    if samples >= 40:
        return "medium"
    return "low"


# ------------------------------------------------------------------ pipeline

def prepare(path, crop_top, crop_bottom, masks, design_width, tolerance,
            min_band_dp, min_gap_dp, roi_top, roi_bottom, measure_width=None):
    """Load -> crop chrome -> mask dynamic areas -> segment -> measure natively.

    Nothing is resampled. The tempting move is to scale both images to a common
    width so the two band sequences share a coordinate system, but resampling is
    exactly what this measurement cannot survive: downscaling a 1080 px
    screenshot to a 390 px design quantizes an x-height to whole rows (~8%
    steps, larger than the tolerance), and upscaling the design blurs its glyph
    edges, which widens its measured core and invents a systematic ~9% "the app
    renders smaller than design" defect out of nothing. Both directions produce
    a confident, wrong number.

    So each image is measured in its own native pixels, at full precision, and
    only the *results* are converted into design px afterwards by each image's
    own width scale. Ratios between the two are then honest, and the thresholds
    the caller passes stay expressed in design px regardless of device density.
    """
    img = Image.open(path).convert("RGB")
    img = crop_band(img, crop_top, crop_bottom)
    img = _apply_masks(img, masks)

    if measure_width and img.size[0] != measure_width:
        scale = measure_width / float(img.size[0])
        img = img.resize(
            (measure_width, max(1, int(round(img.size[1] * scale)))), Image.LANCZOS)

    h = img.size[1]
    y0 = parse_len(roi_top, h) if roi_top else 0
    y1 = h - (parse_len(roi_bottom, h) if roi_bottom else 0)
    if y1 <= y0:
        raise ValueError(f"{path}: roi-top/roi-bottom leave no content")
    img = img.crop((0, y0, img.size[0], y1))

    # design px per native px — the one conversion factor everything downstream
    # uses, so the report speaks in the design's units without any image ever
    # being resized.
    to_design = design_width / float(img.size[0])
    scale = 1.0 / to_design

    mask = ink_mask(img, modal_background(img), tolerance)
    profile = row_profile(mask)
    bands = segment(profile, 0.004,
                    max(2, int(round(min_band_dp * scale))),
                    max(3, int(round(min_gap_dp * scale))))

    measured = []
    for top, bottom in bands:
        for m in measure_band(img, top, bottom, tolerance):
            # Positions and lengths in design px; weight_index and ink_density
            # are already dimensionless and carry over untouched.
            m["top_dp"] = m["top"] * to_design
            m["bottom_dp"] = m["bottom"] * to_design
            m["x_height_px"] = round(m["x_height"] * to_design, 2)
            m["stroke_px"] = round(m["stroke"] * to_design, 3)
            measured.append(m)
    return img, measured


MIN_BANDS_FOR_INTRA = 4


def _leave_one_out_median(values, index):
    """Median of `values` with entry `index` removed.

    A band must not help define the baseline it is then judged against. With a
    handful of text bands, a heading that is genuinely too small drags the
    median toward itself, shrinks its own apparent deviation, and — worse —
    shifts the baseline that every *other* band is measured from, so one real
    defect manufactures phantom ones on innocent elements. Excluding the band
    under test costs nothing and removes that feedback entirely.
    """
    rest = [v for i, v in enumerate(values) if i != index]
    return statistics.median(rest) if rest else None


def relative_sizes(bands):
    """Each text band's size as a multiple of the screen's own body text.

    This is the scale-free half of the comparison: it never compares a pixel in
    one image to a pixel in the other, only a proportion to a proportion, so it
    survives any difference in density or export scale. What it costs is a
    dependency on the screen having enough text to establish what "body" means.

    Body text is the median x-height across text bands, because body copy is
    what a screen has most of and headings are the outliers a median ignores.
    That reasoning needs a real population: with three bands the median is a
    single reading, and one wrong element redefines the baseline for the whole
    screen. Below `MIN_BANDS_FOR_INTRA` the comparison is declined outright
    rather than computed on evidence too thin to carry it.
    """
    text = [b for b in bands if b["is_text"]]
    if len(text) < MIN_BANDS_FOR_INTRA:
        for b in bands:
            b["rel_size"] = None
        return None
    heights = [b["x_height_px"] for b in text]
    for i, b in enumerate(text):
        base = _leave_one_out_median(heights, i)
        b["rel_size"] = round(b["x_height_px"] / base, 3) if base else None
    for b in bands:
        b.setdefault("rel_size", None)
    return round(statistics.median(heights), 2)


def relative_weights(bands):
    """Each text band's stroke ratio as a multiple of the screen's own median."""
    text = [b for b in bands if b["is_text"] and b["weight_index"]]
    if len(text) < MIN_BANDS_FOR_INTRA:
        for b in bands:
            b["rel_weight"] = None
        return None
    indices = [b["weight_index"] for b in text]
    for i, b in enumerate(text):
        base = _leave_one_out_median(indices, i)
        b["rel_weight"] = round(b["weight_index"] / base, 3) if base else None
    for b in bands:
        b.setdefault("rel_weight", None)
    return round(statistics.median(indices), 4)


def tolerances_for(d, a, args, resolution_ratio):
    """Widen the tolerance to whatever precision these two images can support.

    A fixed threshold pretends every input is equally readable, which produces
    the worst failure a measuring tool can have: a confident number that is
    mostly the tool's own error. Two things limit what is knowable here.

    Edge uncertainty: an x-height is only as precise as the glyph edges it is
    read between, and antialiasing smears each edge across about a pixel. On a
    1x design export a body-text x-height spans ~7 px, so one pixel of edge
    uncertainty per side is already ~14% — wider than any font-size bug worth
    reporting. The band simply cannot answer the question, and saying so is the
    only honest option.

    Scale mismatch: a 1x design export next to a 3x screenshot is not one
    measurement repeated, it is two measurements taken through different
    lenses. The low-resolution side reads systematically larger and heavier,
    because proportionally more of each glyph is antialiased edge. That bias is
    not noise and does not average out, so it is charged directly against the
    tolerance in proportion to how mismatched the scales are.

    Both effects shrink to nothing when the design is exported near the device's
    scale — which is why the JSON says so when it matters. The fix is one export
    setting, and it buys back the sensitivity to catch a single-step font-size
    bug.
    """
    mismatch = max(0.0, resolution_ratio - 1.0)

    size_precision = 1.0 / max(1e-6, d["x_height"]) + 1.0 / max(1e-6, a["x_height"])
    size_tol = max(args.size_tolerance, size_precision, 0.06 * mismatch)

    # Stroke is averaged over every stem on the line, so its random error falls
    # with the square root of the sample — a paragraph is far more trustworthy
    # than a two-word label, and the tolerance should reflect that difference
    # rather than treating both as equally certain.
    def stroke_error(band):
        stems = max(1, band["stroke_samples"])
        return (1.0 / max(1e-6, band["stroke"])) / (stems ** 0.5)

    weight_precision = 2.0 * (stroke_error(d) + stroke_error(a))
    weight_tol = max(args.weight_tolerance, weight_precision, 0.10 * mismatch)

    return round(size_tol, 4), round(weight_tol, 4)


def compare(bands_d, bands_a, args, resolution_ratio=1.0):
    """Pair bands, then judge each pair on four ratios.

    Cross-image and intra-screen ratios are both computed for size and weight
    because they catch different bugs and a screen can pass one while failing the
    other. Each pair carries its own `reasons` list so the report can quote the
    specific ratio that failed instead of a generic "typography mismatch".
    """
    # Align on design-px coordinates: `align` weighs band height against band
    # height, so feeding it native pixels from two different densities would
    # make every height look mismatched and collapse the pairing onto position
    # alone.
    # Position-dominant on purpose. The default weighting leans on band height,
    # which is exactly the quantity a font-size defect corrupts: a subtitle
    # rendering 65% too large stops resembling its own counterpart and starts
    # resembling whatever *other* run still matches its intended height. The
    # pairing then slides onto the wrong element and the finding is filed
    # against it. Vertical order survives any size bug, so it leads here.
    pairs = align(
        [(int(round(b["top_dp"])), int(round(b["bottom_dp"]))) for b in bands_d],
        [(int(round(b["top_dp"])), int(round(b["bottom_dp"]))) for b in bands_a],
        height_weight=0.25,
    )

    rows, matched_d, matched_a = [], set(), set()
    for i, j in pairs:
        d, a = bands_d[i], bands_a[j]
        matched_d.add(i)
        matched_a.add(j)
        if not (d["is_text"] and a["is_text"]):
            rows.append({
                "design_band": i, "actual_band": j,
                "comparable": False,
                "note": "not a text band on both sides (photo, divider, or filled shape)",
            })
            continue

        size_ratio = a["x_height_px"] / d["x_height_px"] if d["x_height_px"] else None
        rel_ratio = (
            a["rel_size"] / d["rel_size"]
            if d.get("rel_size") and a.get("rel_size") else None
        )
        weight_ratio = (
            a["weight_index"] / d["weight_index"] if d["weight_index"] else None
        )
        rel_weight_ratio = (
            a["rel_weight"] / d["rel_weight"]
            if d.get("rel_weight") and a.get("rel_weight") else None
        )
        confidence = _weight_confidence(min(d["stroke_samples"], a["stroke_samples"]))
        size_tol, weight_tol = tolerances_for(d, a, args, resolution_ratio)

        # Cross-image reasons are authoritative: they compare this element to
        # its own counterpart in the design and depend on nothing else on the
        # screen. Intra-screen reasons are kept separate because they are
        # relative to a baseline the screen itself defines — powerful for
        # catching a heading that lost its style, but not something that should
        # fail an element whose direct comparison against the design is clean.
        reasons, secondary = [], []
        if size_ratio and abs(size_ratio - 1) > size_tol:
            reasons.append(
                f"font size renders {size_ratio:.2f}x the design "
                f"({d['x_height_px']:.1f} -> {a['x_height_px']:.1f} x-height)"
            )
        if rel_ratio and abs(rel_ratio - 1) > size_tol:
            secondary.append(
                f"size relative to body text is {a['rel_size']:.2f}x on device vs "
                f"{d['rel_size']:.2f}x in design ({rel_ratio:.2f}x of intended)"
            )
        if weight_ratio and abs(weight_ratio - 1) > weight_tol:
            direction = "lighter" if weight_ratio < 1 else "heavier"
            reasons.append(
                f"stroke weight renders {weight_ratio:.2f}x the design ({direction}; "
                f"confidence {confidence})"
            )
        if rel_weight_ratio and abs(rel_weight_ratio - 1) > weight_tol:
            secondary.append(
                f"weight relative to the screen's body text is {a['rel_weight']:.2f}x "
                f"vs {d['rel_weight']:.2f}x in design (confidence {confidence})"
            )

        rows.append({
            "design_band": i,
            "actual_band": j,
            "comparable": True,
            "design": {k: d[k] for k in
                       ("x_height_px", "rel_size", "weight_index", "rel_weight",
                        "stroke_px", "lines")},
            "actual": {k: a[k] for k in
                       ("x_height_px", "rel_size", "weight_index", "rel_weight",
                        "stroke_px", "lines")},
            "size_ratio": round(size_ratio, 3) if size_ratio else None,
            "rel_size_ratio": round(rel_ratio, 3) if rel_ratio else None,
            "weight_ratio": round(weight_ratio, 3) if weight_ratio else None,
            "rel_weight_ratio": round(rel_weight_ratio, 3) if rel_weight_ratio else None,
            "weight_confidence": confidence,
            "size_tolerance_used": size_tol,
            "weight_tolerance_used": weight_tol,
            "style_run": f"{d['style_run'] + 1}/{d['style_runs_in_band']}",
            "mixed_style_band": d["style_runs_in_band"] > 1
                                or a["style_runs_in_band"] > 1,
            "flagged": bool(reasons),
            "reasons": reasons,
            "flagged_secondary": bool(secondary),
            "secondary_reasons": secondary,
        })

    unmatched_d = [i for i in range(len(bands_d)) if i not in matched_d]
    unmatched_a = [j for j in range(len(bands_a)) if j not in matched_a]
    return rows, unmatched_d, unmatched_a


def systematic(rows, key):
    """Median of one ratio across comparable pairs — a whole-screen signal.

    One band off is a component bug; every band off by the same factor is a
    single wrong theme value. Collapsing that into one number is what stops the
    report from filing nine findings for one root cause.
    """
    values = [r[key] for r in rows if r.get("comparable") and r.get(key)]
    return round(statistics.median(values), 3) if len(values) >= 3 else None


# ------------------------------------------------------------------ annotate

def annotate(img, bands, rows, side, title):
    """Draw each measured band with its numbers; flagged bands in red."""
    out = img.convert("RGB").copy()
    draw = ImageDraw.Draw(out, "RGBA")
    font = _load_font(max(11, img.size[0] // 42))
    flagged = {r[f"{side}_band"] for r in rows if r.get("flagged")}

    for idx, b in enumerate(bands):
        colour = (220, 38, 38) if idx in flagged else (
            (37, 99, 235) if b["is_text"] else (148, 163, 184))
        draw.rectangle([b["ink_left"], b["top"], b["ink_right"], b["bottom"]],
                       outline=colour, width=2)
        if b["is_text"]:
            label = f"#{idx} x{b.get('x_height_px', b['x_height']):.0f} w{b['weight_index']:.2f}"
            if b.get("rel_size"):
                label += f" ({b['rel_size']:.2f}x body)"
        else:
            label = f"#{idx} non-text"
        ty = max(0, b["top"] - font.size - 2)
        draw.rectangle([b["ink_left"], ty, b["ink_left"] + len(label) * font.size * 0.58,
                        ty + font.size + 2], fill=(255, 255, 255, 215))
        draw.text((b["ink_left"] + 2, ty), label, fill=colour, font=font)

    header = Image.new("RGB", (out.size[0], font.size + 10), (17, 24, 39))
    ImageDraw.Draw(header).text((6, 4), title, fill=(255, 255, 255), font=font)
    canvas = Image.new("RGB", (out.size[0], out.size[1] + header.size[1]), (17, 24, 39))
    canvas.paste(header, (0, 0))
    canvas.paste(out, (0, header.size[1]))
    return canvas


# ---------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(
        description="Measure font size and weight relative to a design reference.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("design")
    p.add_argument("actual")
    p.add_argument("--out", required=True, help="annotated side-by-side PNG")
    p.add_argument("--crop-design-top", default=None)
    p.add_argument("--crop-design-bottom", default=None)
    p.add_argument("--crop-actual-top", default=None)
    p.add_argument("--crop-actual-bottom", default=None)
    p.add_argument("--mask-design", action="append", default=[], metavar="X1,Y1,X2,Y2")
    p.add_argument("--mask-actual", action="append", default=[], metavar="X1,Y1,X2,Y2")
    p.add_argument("--roi-top", default=None)
    p.add_argument("--roi-bottom", default=None)
    p.add_argument("--ink-tolerance", type=int, default=28,
                   help="per-channel difference from the local background that counts "
                        "as ink (default 28)")
    p.add_argument("--min-band", type=int, default=6)
    p.add_argument("--min-gap", default="auto",
                   help="gaps thinner than this merge into one band (design px). "
                        "Default 'auto' tries a range and keeps the value that pairs "
                        "the most bands — hand-tuning this was the single biggest "
                        "time sink in a review, and a wrong guess can drop a whole "
                        "line of text from the comparison")
    p.add_argument("--design-width-dp", type=float, default=None,
                   help="logical width of the design frame (e.g. 390) when the export "
                        "is not 1x, so measurements read in real dp")
    p.add_argument("--size-tolerance", type=float, default=0.08,
                   help="floor for the allowed |ratio-1| on font size (default 0.08). "
                        "Type scales step in discrete sizes (16->18 is +12.5%%), so "
                        "8%% separates adjacent steps while staying above the "
                        "measurement noise. Widened per band when the inputs cannot "
                        "support that precision - see size_tolerance_used")
    p.add_argument("--weight-tolerance", type=float, default=0.14,
                   help="floor for the allowed |ratio-1| on stroke weight (default "
                        "0.14). Wider than size because stroke measurement is "
                        "noisier; also widened per band - see weight_tolerance_used")
    p.add_argument("--measure-width", type=int, default=None,
                   help="resample both images to this width before measuring. Off by "
                        "default: resampling either blurs the smaller image or "
                        "quantizes the larger one, and both bias the result")
    args = p.parse_args()

    design_w = Image.open(args.design).size[0]
    # Measurements are reported in the design's own pixel unit — which IS dp for
    # a 1x export. --design-width-dp rescales that unit when the export is 2x/3x,
    # so the numbers in the report match what a developer reads in the design
    # file rather than the export's pixel count.
    dp_unit = (args.design_width_dp / design_w) if args.design_width_dp else 1.0
    unit = "dp" if args.design_width_dp else "design px"

    def segment_both(min_gap):
        d = prepare(args.design, args.crop_design_top, args.crop_design_bottom,
                    args.mask_design, design_w, args.ink_tolerance, args.min_band,
                    min_gap, args.roi_top, args.roi_bottom,
                    measure_width=args.measure_width)
        a = prepare(args.actual, args.crop_actual_top, args.crop_actual_bottom,
                    args.mask_actual, design_w, args.ink_tolerance, args.min_band,
                    min_gap, args.roi_top, args.roi_bottom,
                    measure_width=args.measure_width)
        return d, a

    # Searching this is ~0.4s per candidate and a whole agent turn per candidate
    # when a human does it by hand. The asymmetry is the point: try them all here
    # and hand back one answer, rather than making the caller iterate.
    if str(args.min_gap) == "auto":
        best = None
        for candidate in (6, 8, 10, 12, 14, 18):
            (id_, bd), (ia, ba) = segment_both(candidate)
            text_d = [b for b in bd if b["is_text"]]
            text_a = [b for b in ba if b["is_text"]]
            paired = len(align(
                [(int(round(b["top_dp"])), int(round(b["bottom_dp"]))) for b in bd],
                [(int(round(b["top_dp"])), int(round(b["bottom_dp"]))) for b in ba],
                height_weight=0.25))
            # Rank by how well the two sequences correspond, not by how many
            # bands were found. Counting bands rewards over-segmentation, which
            # produces more candidates for the aligner to choose wrongly among;
            # the match rate rewards the segmentation where each side's elements
            # actually have counterparts, which is the condition every number
            # downstream depends on.
            rate = paired / max(1, max(len(bd), len(ba)))
            dropped = (len(bd) - len(text_d)) + (len(ba) - len(text_a))
            score = (round(rate, 2), paired, -dropped, -candidate)
            if best is None or score > best[0]:
                best = (score, candidate, (id_, bd), (ia, ba))
        min_gap_used = best[1]
        (img_d, bands_d), (img_a, bands_a) = best[2], best[3]
    else:
        min_gap_used = int(args.min_gap)
        (img_d, bands_d), (img_a, bands_a) = segment_both(min_gap_used)

    if dp_unit != 1.0:
        for band in bands_d + bands_a:
            band["x_height_px"] = round(band["x_height_px"] * dp_unit, 2)
            band["stroke_px"] = round(band["stroke_px"] * dp_unit, 3)

    body_d = relative_sizes(bands_d)
    body_a = relative_sizes(bands_a)
    relative_weights(bands_d)
    relative_weights(bands_a)

    actual_w = Image.open(args.actual).size[0]
    resolution_ratio = max(design_w, actual_w) / float(min(design_w, actual_w))
    rows, unmatched_d, unmatched_a = compare(bands_d, bands_a, args, resolution_ratio)
    comparable = [r for r in rows if r.get("comparable")]
    flagged = [r for r in comparable if r["flagged"]]
    secondary_only = [r for r in comparable
                      if r["flagged_secondary"] and not r["flagged"]]

    sys_size = systematic(comparable, "size_ratio")
    sys_weight = systematic(comparable, "weight_ratio")

    widened = [r for r in comparable
               if r["size_tolerance_used"] > args.size_tolerance * 1.25]
    resolution_note = None
    if resolution_ratio > 1.5:
        resolution_note = (
            f"Design export is {resolution_ratio:.1f}x smaller in width than the "
            f"screenshot ({design_w} vs {actual_w} px), so tolerances were widened "
            f"and a one-step font-size change may not be detectable. Re-export the "
            f"design at the device's scale (Figma: 2x/3x) to regain that sensitivity."
        )
    elif len(widened) > len(comparable) / 2:
        resolution_note = (
            "Most bands needed a widened tolerance: the text is too small in these "
            "images to resolve a font-size step. Export the design and capture the "
            "screenshot at a higher scale for a sharper verdict."
        )

    if len(comparable) < 2:
        verdict = ("INCONCLUSIVE — fewer than 2 text bands matched. Crop the chrome, "
                   "mask photos, or narrow with --roi-* before quoting any number.")
    elif not flagged:
        verdict = (f"PASS — {len(comparable)} text bands compared; size and weight "
                   f"within tolerance against the design (floor "
                   f"+/-{args.size_tolerance:.0%} size, "
                   f"+/-{args.weight_tolerance:.0%} weight, widened per band where "
                   f"the inputs could not support it).")
        if secondary_only:
            verdict += (f" {len(secondary_only)} band(s) differ only in their ratio "
                        f"to the screen's own body text — see secondary_reasons; "
                        f"that is a lead to check, not a failure, because it "
                        f"depends on a baseline this screen defines.")
    elif sys_size and abs(sys_size - 1) > statistics.median(
            [r["size_tolerance_used"] for r in comparable]):
        verdict = (f"FAIL — whole-screen type scale is off: every text band renders "
                   f"~{sys_size:.2f}x the design's size. One root cause (a text theme "
                   f"or density setting), not {len(flagged)} separate findings.")
    else:
        verdict = (f"FAIL — {len(flagged)} of {len(comparable)} text bands outside "
                   f"tolerance against the design. See bands[].reasons for the "
                   f"specific ratio that failed.")
        if secondary_only:
            verdict += (f" A further {len(secondary_only)} band(s) differ only "
                        f"relative to the screen's own body text "
                        f"(secondary_reasons) — leads, not failures.")

    dropped_d = [b for b in bands_d if not b["is_text"]]
    dropped_a = [b for b in bands_a if not b["is_text"]]
    # A run that was measured and then set aside is not the same as a screen
    # with nothing there. A PASS that quietly dropped a visible line of text is
    # the worst output this tool can produce, because it looks exactly like a
    # clean screen — so the count travels with the verdict, not just the JSON.
    if dropped_a or dropped_d:
        verdict += (f" Excluded from comparison as non-text: {len(dropped_d)} "
                    f"design run(s), {len(dropped_a)} actual run(s). If a real "
                    f"line of text is in there, this verdict does not cover it — "
                    f"check the PNG and adjust --min-gap or the masks.")

    # How far the two band sequences actually correspond. A caller can read this
    # instead of opening the composite to decide whether to trust the numbers —
    # which is the expensive step, in tokens and in time.
    match_rate = len(pairs_meta := [r for r in rows]) and round(
        len(comparable) / max(1, max(len(bands_d), len(bands_a))), 2)
    if match_rate >= 0.6:
        pairing_confidence = "high"
    elif match_rate >= 0.35:
        pairing_confidence = "medium — open the PNG and confirm each pairing names "\
                             "the element you would name out loud"
    else:
        pairing_confidence = "low — most bands found no counterpart; the segmentation "\
                             "or the ROI is wrong, and no ratio below is safe to quote"

    result = {
        "verdict": verdict,
        "match_rate": match_rate,
        "pairing_confidence": pairing_confidence,
        "unit": unit,
        "min_gap_used": min_gap_used,
        "design_width_px": design_w,
        "actual_width_px": Image.open(args.actual).size[0],
        "px_to_dp": round(dp_unit, 4),
        "body_x_height": {"design": body_d, "actual": body_a},
        "systematic_size_ratio": sys_size,
        "systematic_weight_ratio": sys_weight,
        "matched_text_bands": len(comparable),
        "flagged_bands": len(flagged),
        "secondary_only_bands": len(secondary_only),
        "excluded_as_non_text": {"design": len(dropped_d), "actual": len(dropped_a)},
        "intra_screen_baseline": (
            "used" if body_d and body_a else
            f"declined — fewer than {MIN_BANDS_FOR_INTRA} text bands, so the "
            f"screen's own 'body text' median would rest on too few readings to "
            f"judge anything against"
        ),
        "bands": rows,
        "unmatched_design": unmatched_d,
        "unmatched_actual": unmatched_a,
        "tolerances": {
            "size_floor": args.size_tolerance,
            "weight_floor": args.weight_tolerance,
            "note": "per-band tolerance is widened to the precision the inputs "
                    "support; see size_tolerance_used / weight_tolerance_used",
        },
        "resolution_ratio": round(resolution_ratio, 2),
        "resolution_note": resolution_note,
        "out": args.out,
    }

    left = annotate(img_d, bands_d, rows, "design", "DESIGN")
    right = annotate(img_a, bands_a, rows, "actual", "ACTUAL")
    gap = 12
    canvas = Image.new(
        "RGB",
        (left.size[0] + right.size[0] + gap, max(left.size[1], right.size[1])),
        (17, 24, 39),
    )
    canvas.paste(left, (0, 0))
    canvas.paste(right, (left.size[0] + gap, 0))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    canvas.save(args.out)

    print(json.dumps(result, indent=2))
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
