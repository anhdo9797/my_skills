#!/usr/bin/env python3
"""Measure UI spacing as numbers — do not ask vision to estimate gaps.

Why this exists: a vision model cannot tell 8px from 24px on a screenshot. The
Tier 3 checklist used to leave spacing as "looks tight" / 🔍 REVIEW, which
means real padding bugs never fail the case and false nits get raised. This
script is the measurement layer that vision must read *before* judging layout.

Two independent sources, used together when both exist:

  1. View hierarchy (best). Maestro JSON or uiautomator XML carries a `bounds`
     rectangle for every node. Sibling gaps, parent padding, overlap, and
     left-edge alignment are computed from those rectangles — the same numbers
     the compositor used. Pass --logical-width-dp (e.g. 390) to convert px→dp.

  2. Aligned image pair (design vs. actual). After the same chrome-crop +
     resize that pair_view.py uses, the script finds vertical whitespace bands
     and left/right insets and compares them. Use this when the design is a
     PNG (no Figma layout tree). It catches section-level rhythm, not
     icon-to-label gaps inside a row — those need the hierarchy.

Vision still owns clipping, truncation, contrast, and "is this the wrong
state". It does not own spacing. Cite this script's JSON (px, %, optional dp);
never invent a dp/sp value from the pixels.

Usage:
  # Live screen — overlap, padding, sibling gaps, alignment
  maestro hierarchy > /tmp/h.json
  python3 scripts/measure_spacing.py --hierarchy /tmp/h.json --logical-width-dp 390

  # Design PNG vs. screenshot (same crop knobs as pair_view.py)
  python3 scripts/measure_spacing.py \\
      --design report/figma/TC-010.png \\
      --actual report/screenshots/TC-010.png \\
      --crop-actual-top 6% --crop-actual-bottom 4% \\
      --logical-width-dp 390 \\
      --out report/spacing/TC-010.json

  # Both sources in one JSON
  python3 scripts/measure_spacing.py \\
      --hierarchy /tmp/h.json \\
      --design report/figma/TC-010.png --actual report/screenshots/TC-010.png \\
      --crop-actual-top 6% --crop-actual-bottom 4%

Exit codes: 0 no flagged findings, 1 flagged spacing/overlap, 2 usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

# Pillow is optional: hierarchy-only mode must work without it.
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in device (or image) pixels, exclusive right/bottom."""

    l: int
    t: int
    r: int
    b: int

    @property
    def w(self) -> int:
        """Width in pixels."""
        return max(0, self.r - self.l)

    @property
    def h(self) -> int:
        """Height in pixels."""
        return max(0, self.b - self.t)

    @property
    def area(self) -> int:
        """Area in square pixels."""
        return self.w * self.h

    @property
    def cx(self) -> float:
        """Horizontal center."""
        return (self.l + self.r) / 2

    @property
    def cy(self) -> float:
        """Vertical center."""
        return (self.t + self.b) / 2

    def intersection(self, other: "Rect") -> Optional["Rect"]:
        """Return the overlapping rectangle, or None if they don't overlap."""
        l, t = max(self.l, other.l), max(self.t, other.t)
        r, b = min(self.r, other.r), min(self.b, other.b)
        if r > l and b > t:
            return Rect(l, t, r, b)
        return None


@dataclass
class LayoutNode:
    """One node of a view hierarchy, with parsed bounds and children."""

    label: str
    rid: str
    cls: str
    rect: Rect
    children: list = field(default_factory=list)

    def display(self) -> str:
        """Short label for JSON: text, else id, else class."""
        return (self.label or self.rid or self.cls or "node")[:60]


# ---------------------------------------------------------------------------
# Bounds parsing (Maestro JSON + uiautomator XML + iOS frame dicts)
# ---------------------------------------------------------------------------


_BRACKET_BOUNDS = re.compile(
    r"\[(-?\d+),\s*(-?\d+)\]\s*\[(-?\d+),\s*(-?\d+)\]"
)
_NUMS = re.compile(r"-?\d+")


def parse_bounds(raw: Any) -> Optional[Rect]:
    """Parse a bounds value from any common mobile-hierarchy encoding.

    Accepts ``[l,t][r,b]`` strings, ``l,t,r,b`` / ``x,y,w,h`` tuples, and
    dicts with ``x/y/width/height`` or ``left/top/right/bottom``.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        if any(k in raw for k in ("width", "w", "height", "h")):
            x = int(float(raw.get("x", raw.get("left", 0)) or 0))
            y = int(float(raw.get("y", raw.get("top", 0)) or 0))
            w = int(float(raw.get("width", raw.get("w", 0)) or 0))
            h = int(float(raw.get("height", raw.get("h", 0)) or 0))
            if w <= 0 or h <= 0:
                return None
            return Rect(x, y, x + w, y + h)
        if "left" in raw and "right" in raw:
            return Rect(
                int(float(raw["left"])),
                int(float(raw["top"])),
                int(float(raw["right"])),
                int(float(raw["bottom"])),
            )
        inner = raw.get("bounds") or raw.get("frame")
        if inner is not None and inner is not raw:
            return parse_bounds(inner)
        return None
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        return parse_bounds(",".join(str(v) for v in raw))
    s = str(raw).strip()
    m = _BRACKET_BOUNDS.search(s)
    if m:
        l, t, r, b = (int(v) for v in m.groups())
        if r > l and b > t:
            return Rect(l, t, r, b)
        return None
    nums = [int(v) for v in _NUMS.findall(s)]
    if len(nums) == 4:
        a, b, c, d = nums
        # Prefer l,t,r,b when the second pair looks like a corner.
        if c > a and d > b:
            return Rect(a, b, c, d)
        if c > 0 and d > 0:
            return Rect(a, b, a + c, b + d)
    return None


def _first_text(attrs: dict) -> str:
    for key in ("text", "accessibilityText", "content-desc", "contentDescription",
                "label", "hintText", "hint"):
        val = attrs.get(key)
        if val:
            return str(val).strip()[:80]
    return ""


def _short_id(resource_id: str) -> str:
    return resource_id.split("/", 1)[-1] if "/" in resource_id else resource_id


def _short_class(class_name: str) -> str:
    return class_name.rsplit(".", 1)[-1] if class_name else ""


def _attrs_of(node: dict) -> dict:
    attrs = node.get("attributes")
    return attrs if isinstance(attrs, dict) else node


def _is_hidden(attrs: dict) -> bool:
    vis = str(attrs.get("visible", attrs.get("visibility", "true"))).lower()
    return vis in ("false", "gone", "invisible", "0")


def _from_json(node: Any) -> Optional[LayoutNode]:
    if not isinstance(node, dict):
        return None
    attrs = _attrs_of(node)
    if _is_hidden(attrs):
        return None
    rect = parse_bounds(
        attrs.get("bounds")
        or attrs.get("frame")
        or node.get("bounds")
        or node.get("frame")
    )
    children: list[LayoutNode] = []
    for child in node.get("children") or []:
        parsed = _from_json(child)
        if parsed is not None:
            children.append(parsed)
    if rect is None:
        if not children:
            return None
        # Wrapper with no bounds of its own: union of children.
        rect = Rect(
            min(c.rect.l for c in children),
            min(c.rect.t for c in children),
            max(c.rect.r for c in children),
            max(c.rect.b for c in children),
        )
    if rect.area <= 0:
        return None
    rid = _short_id(str(
        attrs.get("resource-id") or attrs.get("resourceId") or attrs.get("id") or ""
    ))
    cls = _short_class(str(
        attrs.get("class") or attrs.get("className") or attrs.get("elementType") or ""
    ))
    return LayoutNode(_first_text(attrs), rid, cls, rect, children)


def _from_xml(elem: ET.Element) -> Optional[LayoutNode]:
    attrs = dict(elem.attrib)
    if _is_hidden(attrs):
        return None
    rect = parse_bounds(attrs.get("bounds") or attrs.get("frame"))
    children = [n for n in (_from_xml(c) for c in list(elem)) if n is not None]
    if rect is None:
        if not children:
            return None
        rect = Rect(
            min(c.rect.l for c in children),
            min(c.rect.t for c in children),
            max(c.rect.r for c in children),
            max(c.rect.b for c in children),
        )
    rid = _short_id(str(attrs.get("resource-id") or attrs.get("id") or ""))
    cls = _short_class(str(attrs.get("class") or ""))
    return LayoutNode(_first_text(attrs), rid, cls, rect, children)


def _strip_to_payload(raw: str) -> str:
    """Trim Maestro CLI banners so the first `{` or `<` is the payload."""
    for marker in ("{", "<"):
        idx = raw.find(marker)
        if idx != -1:
            return raw[idx:]
    return raw


def load_hierarchy(raw: str) -> LayoutNode:
    """Parse a Maestro JSON or uiautomator XML dump into a layout tree."""
    payload = _strip_to_payload(raw)
    if payload.lstrip().startswith("{"):
        data = json.loads(payload)
        for key in ("tree", "root", "hierarchy", "element"):
            if isinstance(data, dict) and key in data:
                data = data[key]
                break
        node = _from_json(data)
        if node is None:
            raise ValueError("JSON hierarchy had no nodes with bounds")
        return node
    root = ET.fromstring(payload)
    if root.tag == "hierarchy":
        kids = [n for n in (_from_xml(c) for c in list(root)) if n is not None]
        if not kids:
            raise ValueError("XML hierarchy had no nodes with bounds")
        if len(kids) == 1:
            return kids[0]
        union = Rect(
            min(k.rect.l for k in kids),
            min(k.rect.t for k in kids),
            max(k.rect.r for k in kids),
            max(k.rect.b for k in kids),
        )
        return LayoutNode("hierarchy", "", "", union, kids)
    node = _from_xml(root)
    if node is None:
        raise ValueError("XML hierarchy had no nodes with bounds")
    return node


# ---------------------------------------------------------------------------
# Grid helpers (cell addresses match grid_overlay / pair_view)
# ---------------------------------------------------------------------------


def _column_label(idx: int) -> str:
    label = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        label = chr(ord("A") + rem) + label
    return label


def auto_grid(width: int, height: int, cols: int, rows: int) -> tuple[int, int]:
    """Resolve cols/rows so cells stay roughly square (same rule as grid_overlay)."""
    if cols and rows:
        return cols, rows
    if not cols:
        cols = 6 if width <= height else max(6, round(6 * width / height))
    if not rows:
        cell = width / cols
        rows = max(1, round(height / cell))
    return int(cols), int(rows)


def cell_for(x: float, y: float, width: int, height: int, cols: int, rows: int) -> str:
    """Return the spreadsheet cell id covering pixel (x, y)."""
    c = min(cols - 1, max(0, int(x / width * cols)))
    r = min(rows - 1, max(0, int(y / height * rows)))
    return f"{_column_label(c)}{r + 1}"


def parse_len(value: str, total: int) -> int:
    """Parse a length given as pixels ('120') or a percentage of `total` ('6%')."""
    value = str(value).strip()
    if value.endswith("%"):
        return int(round(float(value[:-1]) / 100.0 * total))
    return int(round(float(value)))


# ---------------------------------------------------------------------------
# Hierarchy measurements
# ---------------------------------------------------------------------------

# Layout wrappers that fill their parent and should be walked through.
_WRAPPER_FILL = 0.92
# Two children share a row when their y-overlap is at least this fraction of
# the shorter one — used to split sibling gaps into vertical vs. horizontal.
_ROW_OVERLAP = 0.5


def _px_to_dp(px: int, screen_w: int, logical_w: Optional[int]) -> Optional[float]:
    if not logical_w or screen_w <= 0:
        return None
    return round(px * logical_w / screen_w, 1)


def _in_ignore_band(rect: Rect, screen: Rect, ignore_top: int, ignore_bottom: int) -> bool:
    if rect.cy < screen.t + ignore_top:
        return True
    if rect.cy > screen.b - ignore_bottom:
        return True
    return False


def _layout_children(node: LayoutNode) -> list[LayoutNode]:
    """Skip full-size wrappers so gaps are between real content, not FrameLayouts."""
    out: list[LayoutNode] = []
    for child in node.children:
        if child.rect.area <= 0:
            continue
        fill = child.rect.area / node.rect.area if node.rect.area else 0
        if fill >= _WRAPPER_FILL and child.children:
            out.extend(_layout_children(child))
        else:
            out.append(child)
    return out


def _same_row(a: Rect, b: Rect) -> bool:
    overlap = max(0, min(a.b, b.b) - max(a.t, b.t))
    shorter = min(a.h, b.h) or 1
    return overlap / shorter >= _ROW_OVERLAP


def _finding(
    kind: str,
    severity: str,
    *,
    a: str = "",
    b: str = "",
    direction: str = "",
    actual_px: Optional[int] = None,
    design_px: Optional[int] = None,
    cells: Optional[list] = None,
    note: str = "",
    screen_w: int = 0,
    logical_w: Optional[int] = None,
) -> dict:
    """Build one finding dict with px, optional dp, and optional design delta."""
    rec: dict[str, Any] = {
        "kind": kind,
        "severity": severity,
        "a": a,
        "b": b,
        "direction": direction,
        "note": note,
        "cells": cells or [],
    }
    if actual_px is not None:
        rec["actual_px"] = actual_px
        dp = _px_to_dp(actual_px, screen_w, logical_w)
        if dp is not None:
            rec["actual_dp"] = dp
    if design_px is not None:
        rec["design_px"] = design_px
        dp = _px_to_dp(design_px, screen_w, logical_w)
        if dp is not None:
            rec["design_dp"] = dp
        if actual_px is not None:
            rec["delta_px"] = actual_px - design_px
            rec["delta_ratio"] = (
                round((actual_px - design_px) / design_px, 3) if design_px else None
            )
    return rec


def measure_hierarchy(
    root: LayoutNode,
    *,
    ignore_top: int,
    ignore_bottom: int,
    min_gap_px: int,
    flag_px: int,
    cols: int,
    rows: int,
    logical_w: Optional[int],
) -> tuple[list[dict], list[dict]]:
    """Walk the tree and return (findings, all_gaps).

    Findings are the flagged subset (overlap, cramped, misaligned, inconsistent
    list spacing). ``all_gaps`` is the compact measurement log vision can cite.
    """
    screen = root.rect
    findings: list[dict] = []
    gaps: list[dict] = []

    def cells_for(rect: Rect) -> list[str]:
        return [cell_for(rect.cx, rect.cy, screen.w or 1, screen.h or 1, cols, rows)]

    def walk(node: LayoutNode) -> None:
        kids = [
            k for k in _layout_children(node)
            if not _in_ignore_band(k.rect, screen, ignore_top, ignore_bottom)
            and k.rect.area > 4
        ]
        if len(kids) < 1:
            for child in node.children:
                walk(child)
            return

        # Parent padding (content inset), only when 2+ children so a single
        # stretched child doesn't look like "zero padding".
        if len(kids) >= 2:
            pad = {
                "left": min(k.rect.l for k in kids) - node.rect.l,
                "right": node.rect.r - max(k.rect.r for k in kids),
                "top": min(k.rect.t for k in kids) - node.rect.t,
                "bottom": node.rect.b - max(k.rect.b for k in kids),
            }
            for side, px in pad.items():
                if px < 0:
                    continue  # child extends outside — overlap, caught below
                gaps.append(_finding(
                    "padding", "info", a=node.display(), direction=side,
                    actual_px=px, cells=cells_for(node.rect),
                    screen_w=screen.w, logical_w=logical_w,
                    note=f"padding {side} of {node.display()}",
                ))

        # Overlap between siblings (not parent/child). Ignore tiny 1–2px
        # compositor rounding.
        for i, left in enumerate(kids):
            for right in kids[i + 1:]:
                hit = left.rect.intersection(right.rect)
                if hit and hit.area > 4:
                    findings.append(_finding(
                        "overlap", "critical",
                        a=left.display(), b=right.display(),
                        actual_px=min(hit.w, hit.h),
                        cells=list(dict.fromkeys(
                            cells_for(left.rect) + cells_for(right.rect)
                        )),
                        screen_w=screen.w, logical_w=logical_w,
                        note=(
                            f"siblings overlap by {hit.w}×{hit.h}px: "
                            f"{left.display()!r} ∩ {right.display()!r}"
                        ),
                    ))

        # Cluster into rows (shared y), then measure horizontal gaps in-row
        # and vertical gaps between rows.
        ordered = sorted(kids, key=lambda k: (k.rect.t, k.rect.l))
        rows_cluster: list[list[LayoutNode]] = []
        for kid in ordered:
            placed = False
            for cluster in rows_cluster:
                if _same_row(cluster[0].rect, kid.rect):
                    cluster.append(kid)
                    placed = True
                    break
            if not placed:
                rows_cluster.append([kid])
        for cluster in rows_cluster:
            cluster.sort(key=lambda k: k.rect.l)

        for cluster in rows_cluster:
            for i in range(len(cluster) - 1):
                a, b = cluster[i], cluster[i + 1]
                gap = b.rect.l - a.rect.r
                rec = _finding(
                    "sibling-gap", "info", a=a.display(), b=b.display(),
                    direction="horizontal", actual_px=gap,
                    cells=list(dict.fromkeys(cells_for(a.rect) + cells_for(b.rect))),
                    screen_w=screen.w, logical_w=logical_w,
                    note=f"horizontal gap {a.display()!r} → {b.display()!r}",
                )
                if gap >= min_gap_px or gap < 0:
                    gaps.append(rec)
                if 0 <= gap <= 2 and min(a.rect.w, b.rect.w) > 8:
                    findings.append({**rec, "kind": "cramped", "severity": "critical",
                                     "note": rec["note"] + " (≤2px — colliding)"})

        for i in range(len(rows_cluster) - 1):
            above = rows_cluster[i]
            below = rows_cluster[i + 1]
            a_bottom = max(k.rect.b for k in above)
            b_top = min(k.rect.t for k in below)
            gap = b_top - a_bottom
            a_name = " + ".join(k.display() for k in above[:2])
            b_name = " + ".join(k.display() for k in below[:2])
            rec = _finding(
                "sibling-gap", "info", a=a_name, b=b_name,
                direction="vertical", actual_px=gap,
                cells=[cell_for(
                    (above[0].rect.cx + below[0].rect.cx) / 2,
                    (a_bottom + b_top) / 2,
                    screen.w or 1, screen.h or 1, cols, rows,
                )],
                screen_w=screen.w, logical_w=logical_w,
                note=f"vertical gap {a_name!r} → {b_name!r}",
            )
            if gap >= min_gap_px or gap < 0:
                gaps.append(rec)
            if 0 <= gap <= 2:
                findings.append({**rec, "kind": "cramped", "severity": "critical",
                                 "note": rec["note"] + " (≤2px — colliding)"})

        # Left-edge alignment of a vertical stack (3+ rows, similar left).
        if len(rows_cluster) >= 3:
            lefts = [min(k.rect.l for k in c) for c in rows_cluster]
            spread = max(lefts) - min(lefts)
            if spread >= flag_px:
                findings.append(_finding(
                    "alignment", "minor",
                    a=rows_cluster[0][0].display(),
                    b=rows_cluster[-1][0].display(),
                    direction="left-edge",
                    actual_px=spread,
                    cells=cells_for(node.rect),
                    screen_w=screen.w, logical_w=logical_w,
                    note=(
                        f"left edges of {len(rows_cluster)} stacked siblings "
                        f"spread {spread}px (want aligned)"
                    ),
                ))

        # Inconsistent gaps in a regular list (3+ similar-height rows).
        v_gaps = []
        for i in range(len(rows_cluster) - 1):
            above_h = max(k.rect.h for k in rows_cluster[i])
            below_h = max(k.rect.h for k in rows_cluster[i + 1])
            if abs(above_h - below_h) <= max(8, 0.4 * max(above_h, below_h, 1)):
                a_bottom = max(k.rect.b for k in rows_cluster[i])
                b_top = min(k.rect.t for k in rows_cluster[i + 1])
                v_gaps.append(b_top - a_bottom)
        if len(v_gaps) >= 2:
            spread = max(v_gaps) - min(v_gaps)
            if spread >= flag_px:
                findings.append(_finding(
                    "inconsistent-gaps", "minor",
                    a=node.display(), direction="vertical",
                    actual_px=spread,
                    cells=cells_for(node.rect),
                    screen_w=screen.w, logical_w=logical_w,
                    note=(
                        f"list-like rows under {node.display()!r} have gaps "
                        f"{min(v_gaps)}–{max(v_gaps)}px (spread {spread}px)"
                    ),
                ))

        for child in node.children:
            walk(child)

    walk(root)
    return findings, gaps


# ---------------------------------------------------------------------------
# Image-pair measurements (design PNG vs. actual screenshot)
# ---------------------------------------------------------------------------


def _require_pillow() -> None:
    if Image is None:
        sys.stderr.write(
            "ERROR: Pillow is required for image-pair spacing.\n"
            "Install it once with:  pip3 install Pillow\n"
        )
        sys.exit(2)


def _crop_band(img, top: Optional[str], bottom: Optional[str]):
    w, h = img.size
    y0 = parse_len(top, h) if top else 0
    y1 = h - (parse_len(bottom, h) if bottom else 0)
    if y1 <= y0:
        raise ValueError("crop-top/crop-bottom leave no content band")
    return img.crop((0, y0, w, y1))


def _row_edge_energy(gray_bytes: bytes, width: int, height: int) -> list[int]:
    """Sum of |pixel - right-neighbour| per row. High = content, low = flat gap."""
    energy = []
    for y in range(height):
        row = gray_bytes[y * width:(y + 1) * width]
        acc = 0
        for x in range(width - 1):
            acc += abs(row[x] - row[x + 1])
        energy.append(acc)
    return energy


def _bands_from_energy(
    energy: list[int],
    width: int,
    min_gap_px: int,
    merge_px: int = 3,
) -> list[dict]:
    """Split a 1-D energy profile into alternating content / gap bands.

    A row is content when its edge energy exceeds a fraction of (width * 8) —
    enough to ignore compression noise but not drop a hairline divider.
    Isolated 1–``merge_px`` content/gap flips are merged so anti-aliased edges
    don't become fake 2px gaps.
    """
    threshold = max(width * 6, 1)
    is_content = [e >= threshold for e in energy]
    # Merge short runs into their neighbours.
    n = len(is_content)
    i = 0
    while i < n:
        j = i
        while j < n and is_content[j] == is_content[i]:
            j += 1
        if 0 < j - i <= merge_px and i > 0:
            fill = is_content[i - 1]
            for k in range(i, j):
                is_content[k] = fill
        i = j
    bands = []
    i = 0
    while i < n:
        j = i
        kind = "content" if is_content[i] else "gap"
        while j < n and is_content[j] == is_content[i]:
            j += 1
        h = j - i
        if kind == "gap" and h < min_gap_px:
            i = j
            continue
        bands.append({"type": kind, "y0": i, "y1": j, "h": h})
        i = j
    return bands


def _median(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    return s[len(s) // 2]


def _insets(gray_bytes: bytes, width: int, height: int, is_content_row: list[bool]) -> dict:
    """Median left/right inset of content rows (screen-level horizontal padding)."""
    lefts, rights = [], []
    # Inset threshold: treat near-flat pixels as background. Use the row's
    # own edges: walk in until |px - next| is significant.
    for y, flag in enumerate(is_content_row):
        if not flag:
            continue
        row = gray_bytes[y * width:(y + 1) * width]
        l = 0
        while l < width - 1 and abs(row[l] - row[min(l + 8, width - 1)]) < 10:
            l += 1
        r = 0
        while r < width - 1 and abs(row[width - 1 - r] - row[max(width - 1 - r - 8, 0)]) < 10:
            r += 1
        lefts.append(l)
        rights.append(r)
    return {"left": _median(lefts), "right": _median(rights)}


def _match_gaps(design: list[dict], actual: list[dict], height: int) -> list[tuple[dict, dict]]:
    """Pair design/actual gap bands whose centers sit at a similar Y fraction."""
    d_gaps = [b for b in design if b["type"] == "gap"]
    a_gaps = [b for b in actual if b["type"] == "gap"]
    used = set()
    pairs = []
    for g in d_gaps:
        dc = (g["y0"] + g["y1"]) / 2 / max(height, 1)
        best_i, best_dist = None, 0.08
        for i, a in enumerate(a_gaps):
            if i in used:
                continue
            ac = (a["y0"] + a["y1"]) / 2 / max(height, 1)
            dist = abs(dc - ac)
            if dist < best_dist:
                best_i, best_dist = i, dist
        if best_i is not None:
            used.add(best_i)
            pairs.append((g, a_gaps[best_i]))
    return pairs


def measure_image_pair(
    design_path: str,
    actual_path: str,
    *,
    crop_design_top: Optional[str],
    crop_design_bottom: Optional[str],
    crop_actual_top: Optional[str],
    crop_actual_bottom: Optional[str],
    min_gap_px: int,
    flag_px: int,
    flag_ratio: float,
    cols: int,
    rows: int,
    logical_w: Optional[int],
) -> tuple[list[dict], list[dict], tuple[int, int]]:
    """Compare vertical rhythm + side insets of two chrome-aligned images."""
    _require_pillow()
    design = Image.open(design_path).convert("RGB")
    actual = Image.open(actual_path).convert("RGB")
    if crop_design_top or crop_design_bottom:
        design = _crop_band(design, crop_design_top, crop_design_bottom)
    if crop_actual_top or crop_actual_bottom:
        actual = _crop_band(actual, crop_actual_top, crop_actual_bottom)
    aw, ah = actual.size
    design = design.resize((aw, ah))
    cols, rows = auto_grid(aw, ah, cols, rows)

    def profile(img) -> tuple[list[dict], dict]:
        gray = img.convert("L")
        data = gray.tobytes()
        energy = _row_edge_energy(data, aw, ah)
        bands = _bands_from_energy(energy, aw, min_gap_px)
        is_content = [False] * ah
        for b in bands:
            if b["type"] == "content":
                for y in range(b["y0"], b["y1"]):
                    is_content[y] = True
        insets = _insets(data, aw, ah, is_content)
        return bands, insets

    d_bands, d_insets = profile(design)
    a_bands, a_insets = profile(actual)

    findings: list[dict] = []
    measurements: list[dict] = []

    for side in ("left", "right"):
        actual_px = a_insets[side]
        design_px = d_insets[side]
        rec = _finding(
            "inset", "info", direction=side,
            actual_px=actual_px, design_px=design_px,
            cells=[cell_for(0 if side == "left" else aw - 1, ah / 2, aw, ah, cols, rows)],
            screen_w=aw, logical_w=logical_w,
            note=f"screen {side} inset vs design",
        )
        measurements.append(rec)
        if abs(actual_px - design_px) >= flag_px and (
            design_px == 0 or abs(actual_px - design_px) / max(design_px, 1) >= flag_ratio
        ):
            findings.append({**rec, "severity": "minor",
                             "note": rec["note"] + " (delta over threshold)"})

    for d_gap, a_gap in _match_gaps(d_bands, a_bands, ah):
        y_mid = (a_gap["y0"] + a_gap["y1"]) / 2
        rec = _finding(
            "gap-delta", "info", direction="vertical",
            actual_px=a_gap["h"], design_px=d_gap["h"],
            cells=[cell_for(aw / 2, y_mid, aw, ah, cols, rows)],
            screen_w=aw, logical_w=logical_w,
            note=(
                f"vertical whitespace at y={a_gap['y0']}-{a_gap['y1']} "
                f"(design {d_gap['h']}px vs actual {a_gap['h']}px)"
            ),
        )
        measurements.append(rec)
        delta = abs(a_gap["h"] - d_gap["h"])
        ratio = delta / max(d_gap["h"], 1)
        if delta >= flag_px and ratio >= flag_ratio:
            severity = "minor"
            # A section gap collapsing to near-zero is user-visible density, not a nit.
            if a_gap["h"] <= 4 and d_gap["h"] >= 16:
                severity = "critical"
                rec["note"] += " (section gap collapsed)"
            findings.append({**rec, "severity": severity,
                             "note": rec["note"] + " (delta over threshold)"})

    return findings, measurements, (aw, ah)


# ---------------------------------------------------------------------------
# Overlay (optional evidence image)
# ---------------------------------------------------------------------------


def _load_font(size: int):
    _require_pillow()
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def write_overlay(src: str, dest: str, findings: list[dict], screen: tuple[int, int]) -> None:
    """Wash flagged cells is grid_overlay's job; this draws gap numbers on the shot."""
    _require_pillow()
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    # If we measured a cropped/resized actual, overlay on that size.
    if screen and (w, h) != tuple(screen):
        img = img.resize(tuple(screen)).convert("RGBA")
        w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _load_font(max(14, int(min(w, h) * 0.018)))
    for i, f in enumerate(findings[:20]):
        cells = f.get("cells") or []
        label = f"{f.get('actual_px', '?')}px"
        if f.get("design_px") is not None:
            label = f"{f['actual_px']}px (d {f['design_px']})"
        color = (220, 30, 30, 220) if f.get("severity") == "critical" else (20, 90, 220, 220)
        y = 8 + i * (font.size + 6) if hasattr(font, "size") else 8 + i * 20
        y = min(y, h - 20)
        draw.rectangle([6, y, 6 + 8 + len(label) * 8, y + 18], fill=(0, 0, 0, 160))
        draw.text((10, y), f"{','.join(cells)} {label}", font=font, fill=color)
    Image.alpha_composite(img, layer).convert("RGB").save(dest)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point: measure hierarchy and/or design-vs-actual spacing."""
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--hierarchy", help="Maestro JSON or uiautomator XML dump")
    ap.add_argument("--design", help="design/Figma PNG (image-pair mode)")
    ap.add_argument("--actual", help="device screenshot (image-pair mode)")
    ap.add_argument("--crop-design-top", default=None)
    ap.add_argument("--crop-design-bottom", default=None)
    ap.add_argument("--crop-actual-top", default=None,
                    help="status-bar crop, px or %% — same knob as pair_view.py")
    ap.add_argument("--crop-actual-bottom", default=None,
                    help="OS-nav crop, px or %% — same knob as pair_view.py")
    ap.add_argument("--ignore-top", default="0",
                    help="hierarchy: skip nodes whose center is in this top band (px or %%)")
    ap.add_argument("--ignore-bottom", default="0",
                    help="hierarchy: skip nodes whose center is in this bottom band")
    ap.add_argument("--logical-width-dp", type=int, default=0,
                    help="logical screen width (e.g. 390) so findings include dp as well as px")
    ap.add_argument("--min-gap-px", type=int, default=8,
                    help="ignore gaps thinner than this (line-height, AA). Default 8")
    ap.add_argument("--flag-px", type=int, default=8,
                    help="minimum absolute delta (px) to flag vs design. Default 8")
    ap.add_argument("--flag-ratio", type=float, default=0.30,
                    help="minimum relative delta vs design to flag. Default 0.30 = 30%%")
    ap.add_argument("--cols", type=int, default=0)
    ap.add_argument("--rows", type=int, default=0)
    ap.add_argument("--out", help="write the JSON report to this path (also printed)")
    ap.add_argument("--overlay", help="annotate the actual screenshot with flagged px values")
    args = ap.parse_args(argv)

    if not args.hierarchy and not (args.design and args.actual):
        ap.error("provide --hierarchy and/or --design + --actual")

    logical_w = args.logical_width_dp or None
    findings: list[dict] = []
    measurements: list[dict] = []
    modes: list[str] = []
    screen_px = [0, 0]
    cols, rows = args.cols, args.rows

    if args.hierarchy:
        try:
            with open(args.hierarchy, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            sys.stderr.write(f"ERROR: cannot read hierarchy: {exc}\n")
            return 2
        try:
            root = load_hierarchy(raw)
        except (ValueError, json.JSONDecodeError, ET.ParseError) as exc:
            sys.stderr.write(f"ERROR: bad hierarchy: {exc}\n")
            return 2
        screen = root.rect
        screen_px = [screen.w, screen.h]
        cols, rows = auto_grid(screen.w, screen.h, cols, rows)
        try:
            ign_top = parse_len(args.ignore_top, screen.h)
            ign_bot = parse_len(args.ignore_bottom, screen.h)
        except ValueError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 2
        h_findings, h_gaps = measure_hierarchy(
            root,
            ignore_top=ign_top,
            ignore_bottom=ign_bot,
            min_gap_px=args.min_gap_px,
            flag_px=args.flag_px,
            cols=cols, rows=rows, logical_w=logical_w,
        )
        findings.extend(h_findings)
        measurements.extend(h_gaps)
        modes.append("hierarchy")

    if args.design and args.actual:
        for p in (args.design, args.actual):
            if not os.path.exists(p):
                sys.stderr.write(f"ERROR: file not found: {p}\n")
                return 2
        try:
            i_findings, i_meas, size = measure_image_pair(
                args.design, args.actual,
                crop_design_top=args.crop_design_top,
                crop_design_bottom=args.crop_design_bottom,
                crop_actual_top=args.crop_actual_top,
                crop_actual_bottom=args.crop_actual_bottom,
                min_gap_px=args.min_gap_px,
                flag_px=args.flag_px,
                flag_ratio=args.flag_ratio,
                cols=cols, rows=rows, logical_w=logical_w,
            )
        except ValueError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 2
        screen_px = [size[0], size[1]]
        cols, rows = auto_grid(size[0], size[1], cols, rows)
        findings.extend(i_findings)
        measurements.extend(i_meas)
        modes.append("image-pair")

    # Dedup findings that share kind+a+b+direction.
    seen = set()
    unique = []
    for f in findings:
        key = (f.get("kind"), f.get("a"), f.get("b"), f.get("direction"), f.get("actual_px"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    findings = unique

    summary = {
        "modes": modes,
        "screen_px": screen_px,
        "logical_width_dp": logical_w,
        "cols": cols,
        "rows": rows,
        "flag_px": args.flag_px,
        "flag_ratio": args.flag_ratio,
        "flagged": len(findings),
        "critical": sum(1 for f in findings if f.get("severity") == "critical"),
        "minor": sum(1 for f in findings if f.get("severity") == "minor"),
    }
    report = {
        "summary": summary,
        "findings": findings,
        "measurements": measurements,
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        parent = os.path.dirname(args.out)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.write("\n")
    if args.overlay:
        src = args.actual or args.hierarchy
        # Overlay needs an image; skip silently if hierarchy-only.
        if args.actual:
            write_overlay(args.actual, args.overlay, findings, tuple(screen_px))

    if any(f.get("severity") in ("critical", "minor") for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
