#!/usr/bin/env python3
"""Overlay a labeled reference grid on a screenshot for vision-based UI QA.

Why this exists: when Claude inspects a raw screenshot it reasons about the UI
as one gestalt glance and misses small, localized defects (a 2px clipped
descender in one corner, a label that overflows only its own cell). A labeled
grid turns the screenshot into a coordinate system: every cell has a stable id
like "C4", so the vision pass can be forced to scan cell-by-cell and can name
*where* a defect is in a way a human reviewer (or a follow-up Maestro flow) can
find again. The grid is an analysis aid, not a design element — keep it light
enough that it never hides the UI underneath.

Cell ids follow spreadsheet convention: columns are letters left→right
(A, B, C, ...), rows are numbers top→bottom (1, 2, 3, ...). So "B3" is the
2nd column, 3rd row. Column headers run along the top band, row headers down
the left band, and each cell carries a faint id in its top-left corner.

Usage:
  python3 grid_overlay.py SHOT.png                    # auto grid, ~square cells
  python3 grid_overlay.py SHOT.png --cols 6           # fix columns, auto rows
  python3 grid_overlay.py SHOT.png --cols 6 --rows 12 # fully explicit
  python3 grid_overlay.py SHOT.png --out SHOT-grid.png --emit-legend

To compare against a design baseline, grid BOTH images with the SAME
--cols/--rows so their cells line up (e.g. `--cols 6 --rows 13` on both).

To produce the annotated result image, wash the defective cells red (default
10% opacity) — only the cells you pass, never a cell without clear evidence:
  python3 grid_overlay.py SHOT.png --highlight "E2,F3,A6:C8" \
      --out VIS-01-report.png

Default output path is "<name>-grid.png" next to the input.

Dependency: Pillow. Install once with:  pip3 install Pillow
"""

import argparse
import json
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.stderr.write(
        "ERROR: Pillow is required for grid overlay.\n"
        "Install it once with:  pip3 install Pillow\n"
    )
    sys.exit(2)


def _column_label(idx: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA (spreadsheet-style)."""
    label = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        label = chr(ord("A") + rem) + label
    return label


def _load_font(size: int):
    """Best-effort truetype load; falls back to Pillow's bitmap font."""
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


def _parse_cell(cid: str):
    """'E2' -> (col_index=4, row_index=1), both 0-based."""
    cid = cid.strip().upper()
    i = 0
    while i < len(cid) and cid[i].isalpha():
        i += 1
    letters, digits = cid[:i], cid[i:]
    if not letters or not digits.isdigit():
        raise ValueError(f"bad cell id: {cid!r}")
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return col - 1, int(digits) - 1


def _expand_highlight(spec: str):
    """Parse a highlight spec into a set of (col, row) cells.

    Accepts a comma list of single cells ("E2") and/or rectangular ranges
    ("A6:C8" = every cell from A6 to C8 inclusive). Ranges let a finding that
    spans a region be marked in one token.
    """
    cells = set()
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if ":" in tok:
            a, b = tok.split(":", 1)
            c0, r0 = _parse_cell(a)
            c1, r1 = _parse_cell(b)
            for c in range(min(c0, c1), max(c0, c1) + 1):
                for r in range(min(r0, r1), max(r0, r1) + 1):
                    cells.add((c, r))
        else:
            cells.add(_parse_cell(tok))
    return cells


def _auto_grid(width: int, height: int, cols: int, rows: int):
    """Resolve cols/rows to keep cells roughly square.

    Portrait phone screenshots are much taller than wide, so a fixed square
    grid would produce very few, very tall cells. Anchoring on a column count
    and deriving rows from the aspect ratio keeps each cell close to square,
    which is what makes spatial reasoning ("is this centered?") reliable.
    """
    if cols and rows:
        return cols, rows
    if not cols:
        # Aim for ~6 columns on a typical phone width; scale a little for
        # very wide (tablet/landscape) captures so cells stay square-ish.
        cols = 6 if width <= height else max(6, round(6 * width / height))
    if not rows:
        cell = width / cols
        rows = max(1, round(height / cell))
    return int(cols), int(rows)


def overlay(
    src: str,
    out: str,
    cols: int,
    rows: int,
    opacity: int,
    line_rgb,
    emit_legend: bool,
    highlight=None,
    highlight_alpha: int = 26,
):
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    cols, rows = _auto_grid(w, h, cols, rows)

    overlay_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay_layer)

    cell_w = w / cols
    cell_h = h / rows

    # Font sizes scale with cell size so labels stay legible but small.
    id_font = _load_font(max(11, int(min(cell_w, cell_h) * 0.16)))
    hdr_font = _load_font(max(13, int(min(cell_w, cell_h) * 0.22)))

    line = (line_rgb[0], line_rgb[1], line_rgb[2], opacity)
    line_w = max(1, int(min(w, h) * 0.0016))

    # Highlight cells that have a clear defect: a faint red wash (default 10%
    # opacity) marks *where* the problem is without hiding the pixels that are
    # the evidence. A thin, more-opaque red border makes the cell findable even
    # when the wash is subtle. Only cells passed in are marked — never tint a
    # cell whose defect isn't visibly evident.
    hi = _expand_highlight(highlight) if highlight else set()
    for (c, r) in hi:
        if 0 <= c < cols and 0 <= r < rows:
            x0, y0 = c * cell_w, r * cell_h
            x1, y1 = (c + 1) * cell_w, (r + 1) * cell_h
            draw.rectangle([x0, y0, x1, y1], fill=(255, 0, 0, highlight_alpha))
            draw.rectangle([x0, y0, x1 - 1, y1 - 1], outline=(220, 20, 20, 200),
                           width=max(2, line_w + 1))

    # Grid lines.
    for c in range(cols + 1):
        x = round(c * cell_w)
        draw.line([(x, 0), (x, h)], fill=line, width=line_w)
    for r in range(rows + 1):
        y = round(r * cell_h)
        draw.line([(0, y), (w, y)], fill=line, width=line_w)

    def _text(x, y, s, font, anchor):
        # Draw a dark halo then bright text so labels read on any background.
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text((x + dx, y + dy), s, font=font, anchor=anchor,
                      fill=(0, 0, 0, 235))
        draw.text((x, y), s, font=font, anchor=anchor, fill=(255, 255, 0, 255))

    # Per-cell id in each cell's top-left corner.
    legend = {}
    for r in range(rows):
        for c in range(cols):
            cid = f"{_column_label(c)}{r + 1}"
            x0, y0 = c * cell_w, r * cell_h
            _text(x0 + line_w + 2, y0 + line_w + 1, cid, id_font, "la")
            if emit_legend:
                x1, y1 = (c + 1) * cell_w, (r + 1) * cell_h
                legend[cid] = {
                    "px": [round(x0), round(y0), round(x1), round(y1)],
                    "center_norm": [round((x0 + x1) / 2 / w, 4),
                                    round((y0 + y1) / 2 / h, 4)],
                }

    # Column headers across the top, row headers down the left.
    for c in range(cols):
        _text(c * cell_w + cell_w / 2, 2, _column_label(c), hdr_font, "ma")
    for r in range(rows):
        _text(2, r * cell_h + cell_h / 2, str(r + 1), hdr_font, "lm")

    Image.alpha_composite(img, overlay_layer).convert("RGB").save(out)

    meta = {"out": out, "size": [w, h], "cols": cols, "rows": rows,
            "cell_px": [round(cell_w), round(cell_h)]}
    if hi:
        meta["highlighted"] = sorted(
            f"{_column_label(c)}{r + 1}" for (c, r) in hi
            if 0 <= c < cols and 0 <= r < rows)
    if emit_legend:
        meta["legend"] = legend
    print(json.dumps(meta))


def main():
    ap = argparse.ArgumentParser(description="Overlay a labeled grid on a screenshot.")
    ap.add_argument("src", help="input screenshot (png/jpg)")
    ap.add_argument("--out", help="output path (default <name>-grid.png)")
    ap.add_argument("--cols", type=int, default=0, help="columns (0 = auto)")
    ap.add_argument("--rows", type=int, default=0, help="rows (0 = auto from aspect)")
    ap.add_argument("--opacity", type=int, default=140,
                    help="grid line opacity 0-255 (default 140)")
    ap.add_argument("--line", default="255,60,60",
                    help="grid line RGB (default 255,60,60)")
    ap.add_argument("--emit-legend", action="store_true",
                    help="print cell->pixel/normalized-center map as JSON")
    ap.add_argument("--highlight", default="",
                    help="cells with a clear defect to wash red, e.g. "
                         "'E2,F3,A6:C8' (single cells and A:B ranges). Produces "
                         "the annotated result image.")
    ap.add_argument("--highlight-opacity", type=int, default=26,
                    help="red wash alpha 0-255 (default 26 ~= 10%%)")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        sys.stderr.write(f"ERROR: file not found: {args.src}\n")
        sys.exit(1)

    out = args.out
    if not out:
        base, _ = os.path.splitext(args.src)
        out = base + "-grid.png"

    try:
        line_rgb = tuple(int(v) for v in args.line.split(","))
        assert len(line_rgb) == 3
    except Exception:
        sys.stderr.write("ERROR: --line must be R,G,B (e.g. 255,60,60)\n")
        sys.exit(1)

    overlay(args.src, out, args.cols, args.rows, args.opacity, line_rgb,
            args.emit_legend, args.highlight, args.highlight_opacity)


if __name__ == "__main__":
    main()
