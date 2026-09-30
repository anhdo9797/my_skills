#!/usr/bin/env python3
"""Normalize Figma MCP metadata into UI IR v1.

Input is the XML that `get_metadata` returns — node ids, names, types, and absolute
geometry. Layout intent (column vs row, gaps, padding) is *derived from geometry* rather
than read from auto-layout properties, because hand-positioned frames have no auto-layout
and derived numbers are checkable against the screenshot either way.

Text content is not in the metadata. Pass it separately with --texts as a
{"nodeId": "string"} map built from get_design_context; nodes with no entry get
"content": null and are flagged, never invented.

Usage:
    python3 figma_to_ir.py --metadata raw/metadata.xml --out ir/screen.ui.json \\
                           [--texts raw/texts.json] [--styles raw/styles.json]

See references/ui-ir-schema.md for the output contract.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ---------------------------------------------------------------- chrome

CHROME_PATTERNS = [
    (re.compile(r"^(status[-_ ]?bar|statusbar)$", re.I), "statusBarsPadding"),
    (re.compile(r"^(home[-_ ]?indicator.*|nav[-_ ]?bar[-_ ]?ios)$", re.I), "navigationBarsPadding"),
    (re.compile(r"^(notch|dynamic[-_ ]?island)$", re.I), "statusBarsPadding"),
    (re.compile(r"^(ios|android)[-_].*(signal|wifi|battery)", re.I), "drop"),
    (re.compile(r"^keyboard$", re.I), "drop"),
]


def chrome_handling(name: str) -> str | None:
    for pattern, handling in CHROME_PATTERNS:
        if pattern.match(name.strip()):
            return handling
    return None


# ---------------------------------------------------------------- roles

ICONISH = re.compile(r"(icon|chevron|arrow|plus|zap|cog|crown|house|folder|music|image|search|menu|star|check)", re.I)
IMAGEISH = re.compile(r"(thumb|avatar|photo|image|cover|artwork|hero[-_]?img)", re.I)
DIVIDERISH = re.compile(r"(divider|separator|hairline|rule)", re.I)


def infer_role(tag: str, name: str, w: float, h: float, has_children: bool) -> str:
    lower = name.lower()
    if tag == "text":
        return "text"
    if DIVIDERISH.search(lower) or (min(w, h) <= 2 < max(w, h)):
        return "divider"
    if "rect" in tag or tag in ("ellipse", "polygon", "star", "line"):
        return "image" if IMAGEISH.search(lower) else "surface"
    if tag in ("vector", "boolean-operation"):
        return "icon"
    if not has_children:
        # A childless frame at icon scale is an icon slot; anything larger is a filled shape.
        if ICONISH.search(lower) or max(w, h) <= 32:
            return "icon"
        return "image" if IMAGEISH.search(lower) else "surface"
    return "container"


UNSUPPORTED_TAGS = {"boolean-operation": "boolean_op", "slice": "slice", "mask": "mask"}


# ---------------------------------------------------------------- geometry → layout


def _num(el: ET.Element, attr: str) -> float:
    try:
        return float(el.get(attr, 0) or 0)
    except ValueError:
        return 0.0


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    """Fraction of the smaller span that the two intervals share."""
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    smaller = min(a1 - a0, b1 - b0)
    return inter / smaller if smaller > 0 else 0.0


def infer_direction(children: list[dict]) -> str:
    """Infer column, row, grid, or stack from child geometry."""
    if len(children) < 2:
        return "column"
    boxes = [(c["_x"], c["_y"], c["_w"], c["_h"]) for c in children]

    col = all(
        _overlap(a[0], a[0] + a[2], b[0], b[0] + b[2]) > 0.5 and a[1] + a[3] <= b[1] + 1
        for a, b in zip(boxes, boxes[1:])
    )
    if col:
        return "column"

    x_bands = {round(c["_x"], 1) for c in children}
    y_bands = {round(c["_y"], 1) for c in children}
    if len(x_bands) > 1 and len(y_bands) > 1 and len(x_bands) * len(y_bands) == len(children):
        cells = {(round(c["_x"], 1), round(c["_y"], 1)) for c in children}
        if len(cells) == len(children):
            return "grid"

    by_x = sorted(boxes, key=lambda b: b[0])
    row = all(
        _overlap(a[1], a[1] + a[3], b[1], b[1] + b[3]) > 0.5 and a[0] + a[2] <= b[0] + 1
        for a, b in zip(by_x, by_x[1:])
    )
    return "row" if row else "stack"


def infer_gap(children: list[dict], direction: str) -> float | None:
    """The consistent gap between consecutive children, or None when they disagree."""
    if direction == "stack" or len(children) < 2:
        return None
    if direction == "grid":
        rows: dict[float, list[dict]] = {}
        columns: dict[float, list[dict]] = {}
        for child in children:
            rows.setdefault(round(child["_y"], 1), []).append(child)
            columns.setdefault(round(child["_x"], 1), []).append(child)
        gaps = []
        for band in rows.values():
            ordered = sorted(band, key=lambda c: c["_x"])
            gaps.extend(b["_x"] - (a["_x"] + a["_w"]) for a, b in zip(ordered, ordered[1:]))
        for band in columns.values():
            ordered = sorted(band, key=lambda c: c["_y"])
            gaps.extend(b["_y"] - (a["_y"] + a["_h"]) for a, b in zip(ordered, ordered[1:]))
    elif direction == "column":
        ordered = sorted(children, key=lambda c: c["_y"])
        gaps = [b["_y"] - (a["_y"] + a["_h"]) for a, b in zip(ordered, ordered[1:])]
    else:
        ordered = sorted(children, key=lambda c: c["_x"])
        gaps = [b["_x"] - (a["_x"] + a["_w"]) for a, b in zip(ordered, ordered[1:])]

    gaps = [round(g, 2) for g in gaps if g >= -1]
    if not gaps:
        return None
    median = statistics.median(gaps)
    # A single spacedBy() only describes the layout when the gaps actually agree.
    if all(abs(g - median) <= 1.5 for g in gaps):
        if median <= 1.0:
            return None
        return max(0.0, round(median, 2))
    return None


def infer_padding(node_w: float, node_h: float, children: list[dict], direction: str) -> tuple[dict | None, dict]:
    """Padding, plus the alignment and trailing space that padding would otherwise fake.

    Two shapes must not become padding. Children centred inside their parent are an
    *alignment* — emitting the measured left/right insets as padding produces a button
    whose label drifts the moment the string changes length. And a column whose children
    stop well short of its bottom has *trailing space*, not 900dp of padding; that space is
    the scroll container being taller than its content.
    """
    if not children:
        return None, {}

    left = min(c["_x"] for c in children)
    top = min(c["_y"] for c in children)
    right = node_w - max(c["_x"] + c["_w"] for c in children)
    bottom = node_h - max(c["_y"] + c["_h"] for c in children)
    extra: dict = {}

    def centred(axis_size: float, starts: list[float], sizes: list[float], near: float, far: float) -> bool:
        """True only when centring is the *unambiguous* reading of the geometry.

        Symmetric insets are ambiguous: `padding(20.dp)` on stretched children and
        `Alignment.Center` on wrap-width children produce identical boxes. Padding is the
        safer default (it survives a longer string), so centring is claimed only when the
        insets are asymmetric — or when children of differing sizes all sit on the
        parent's centre line, which padding cannot produce.
        """
        if axis_size <= 0 or not starts:
            return False
        offsets = [abs((s + z / 2) - axis_size / 2) for s, z in zip(starts, sizes)]
        if max(offsets) > 1.5:
            return False
        symmetric = abs(near - far) <= 1.5
        differing = max(sizes) - min(sizes) > 1.5
        single_wrap = len(sizes) == 1 and sizes[0] <= axis_size * 0.8
        return (not symmetric and near >= 0 and far >= 0) or (symmetric and (differing or single_wrap))

    xs = [c["_x"] for c in children]
    ws = [c["_w"] for c in children]
    if centred(node_w, xs, ws, left, right):
        extra.setdefault("align", {})["cross" if direction == "column" else "main"] = "center"
        left = right = 0.0

    ys = [c["_y"] for c in children]
    hs = [c["_h"] for c in children]
    if centred(node_h, ys, hs, top, bottom):
        extra.setdefault("align", {})["main" if direction == "column" else "cross"] = "center"
        top = bottom = 0.0
    elif direction == "column" and bottom > max(48.0, top * 2):
        # Content ends here; the rest is empty container.
        extra["trailingSpace"] = round(bottom, 2)
        bottom = 0.0

    if direction == "column" and max(xs) - min(xs) <= 1.5 and (
        max(ws) - min(ws) > 1.5 or right > max(48.0, left * 2)
    ):
        extra.setdefault("align", {})["cross"] = "start"
        right = 0.0
    elif direction == "row" and max(hs) - min(hs) > 1.5 and max(ys) - min(ys) <= 1.5:
        extra.setdefault("align", {})["cross"] = "start"
        bottom = 0.0

    if direction == "row":
        ordered = sorted(children, key=lambda c: c["_x"])
        gaps = [b["_x"] - (a["_x"] + a["_w"]) for a, b in zip(ordered, ordered[1:])]
        if gaps and min(gaps) > 48 and abs(left - right) <= 1.5:
            extra.setdefault("align", {})["main"] = "spaceBetween"
            extra["suppressGap"] = True
        elif right > max(48.0, left * 2):
            extra["trailingSpace"] = round(right, 2)
            right = 0.0

    pad = {
        "start": round(max(0.0, left), 2),
        "top": round(max(0.0, top), 2),
        "end": round(max(0.0, right), 2),
        "bottom": round(max(0.0, bottom), 2),
    }
    return (pad if any(v > 0 for v in pad.values()) else None), extra


def infer_width(node_w: float, parent_w: float | None) -> str | float:
    if parent_w and abs(node_w - parent_w) < 0.5:
        return "fill"
    return round(node_w, 2)


# ---------------------------------------------------------------- tree build


class Extractor:
    def __init__(self, texts: dict[str, str], styles: dict[str, dict]):
        self.texts = texts
        self.styles = styles
        self.chrome: list[dict] = []
        self.unsupported: list[dict] = []
        self.assets: list[dict] = []
        self.missing_text: list[str] = []

    def build(self, el: ET.Element, parent_w: float | None = None, parent_h: float | None = None) -> dict | None:
        node_id = el.get("id", "")
        name = el.get("name", "")
        tag = el.tag

        handling = chrome_handling(name)
        if handling:
            self.chrome.append({"id": node_id, "name": name, "handling": handling})
            return None

        if tag in UNSUPPORTED_TAGS:
            self.unsupported.append({"id": node_id, "name": name, "reason": UNSUPPORTED_TAGS[tag]})
            return None

        w, h = _num(el, "width"), _num(el, "height")
        raw_children = [self.build(c, w, h) for c in el]
        children = [c for c in raw_children if c]
        role = infer_role(tag, name, w, h, has_children=bool(children))

        node: dict = {
            "id": node_id,
            "name": name,
            "role": role,
            "_x": _num(el, "x"),
            "_y": _num(el, "y"),
            "_w": w,
            "_h": h,
        }

        is_root = parent_w is None
        layout: dict = {
            "width": "fill" if is_root else infer_width(w, parent_w),
            "height": "fill" if is_root else ("wrap" if role != "container" else round(h, 2)),
        }
        if is_root and children:
            # The screen frame's own insets are an artefact of where the mock's chrome sat,
            # and that chrome has just been stripped. Real insets come from the window.
            layout["direction"] = infer_direction(children)
            gap = infer_gap(children, layout["direction"])
            if gap is not None:
                layout["gap"] = {"raw": gap, "token": None}
        elif role == "container" and children:
            direction = infer_direction(children)
            layout["direction"] = direction
            gap = infer_gap(children, direction)
            if gap is not None:
                layout["gap"] = {"raw": gap, "token": None}
            padding, extra = infer_padding(w, h, children, direction)
            if extra.pop("suppressGap", False):
                layout.pop("gap", None)
            if padding:
                layout["padding"] = {**padding, "token": None}
            layout.update(extra)
        node["layout"] = layout

        style = self.styles.get(node_id, {})
        if style:
            node["style"] = {
                key: {"raw": value, "token": None}
                for key, value in style.items()
                if key in ("fill", "radius", "border", "borderWidth")
            }

        if role == "text":
            content = self.texts.get(node_id)
            if content is None:
                self.missing_text.append(node_id)
            node["text"] = {
                "content": content,
                "style": {**{k: v for k, v in style.items() if k in ("size", "weight", "lineHeight")}, "token": None},
                "color": {"raw": style.get("color"), "token": None},
            }

        if role in ("icon", "image"):
            self.assets.append({"id": node_id, "name": name, "kind": role, "export": None})

        # Visual order: a Compose file should read the way the screen reads.
        node["children"] = sorted(children, key=lambda c: (round(c["_y"], 1), round(c["_x"], 1)))
        if not node["children"]:
            node.pop("children")
        return node


def strip_internals(node: dict) -> dict:
    node = {k: v for k, v in node.items() if not k.startswith("_")}
    if "children" in node:
        node["children"] = [strip_internals(c) for c in node["children"]]
    return node


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata", required=True, type=Path, help="get_metadata XML output")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--texts", type=Path, help='{"17:35": "NÉN VIDEO NGAY"} from get_design_context')
    ap.add_argument("--styles", type=Path, help='{"17:28": {"fill": "#0F1511", "radius": 22}} from get_design_context')
    ap.add_argument("--file-key", default="", help="recorded in source metadata")
    args = ap.parse_args()

    raw = args.metadata.read_text(encoding="utf-8")
    start = raw.find("<")
    if start < 0:
        print("error: no XML found in metadata file", file=sys.stderr)
        return 2
    root_match = re.match(r"<([\w-]+)\b", raw[start:])
    if root_match is None:
        print("error: could not identify metadata XML root", file=sys.stderr)
        return 2
    closing = f"</{root_match.group(1)}>"
    end = raw.rfind(closing)
    if end < start:
        print("error: metadata XML root is not closed", file=sys.stderr)
        return 2
    xml = raw[start : end + len(closing)]
    try:
        root_el = ET.fromstring(xml)
    except ET.ParseError as exc:
        print(f"error: could not parse metadata XML: {exc}", file=sys.stderr)
        return 2

    texts = json.loads(args.texts.read_text(encoding="utf-8")) if args.texts else {}
    styles = json.loads(args.styles.read_text(encoding="utf-8")) if args.styles else {}

    extractor = Extractor(texts, styles)
    root = extractor.build(root_el)
    if root is None:
        print("error: root node was classified as chrome — check the nodeId", file=sys.stderr)
        return 2

    ir = {
        "schema": "ui-ir/v1",
        "source": {
            "fileKey": args.file_key,
            "nodeId": root_el.get("id", ""),
            "name": root_el.get("name", ""),
        },
        "frame": {"width": _num(root_el, "width"), "height": _num(root_el, "height")},
        "platformChrome": extractor.chrome,
        "root": strip_internals(root),
        "assets": extractor.assets,
        "unsupported": extractor.unsupported,
        "mapping": {"resolvedCount": 0, "unmapped": [], "resolved": False},
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(ir, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def count(node: dict) -> int:
        return 1 + sum(count(c) for c in node.get("children", []))

    print(f"wrote {args.out}")
    print(f"  nodes          {count(ir['root'])}")
    print(f"  chrome removed {len(extractor.chrome)}  {[c['name'] for c in extractor.chrome]}")
    print(f"  assets         {len(extractor.assets)}")
    print(f"  unsupported    {len(extractor.unsupported)}")
    if extractor.missing_text:
        print(f"  MISSING TEXT   {len(extractor.missing_text)} nodes — pass --texts from get_design_context")
    print("\nnext: resolve_tokens.py --ir <out> --adapter .figma/adapter.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
