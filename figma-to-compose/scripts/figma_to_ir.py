#!/usr/bin/env python3
"""Build UI IR v2 from Figma metadata plus the design-context tree.

Two sources, each used for what it is actually good at:

* `get_metadata` XML — every node's id, name and **absolute geometry**. That geometry is
  what `layout_assert.py` later compares the real Compose bounds against, so every IR node
  that came from the metadata carries a `rect`.
* `context-tree.json` from `context_to_ir.py --tree` — the design's **intent**: auto-layout
  direction, gap, padding, alignment, hug/fill/fixed sizing, weights, absolute positioning,
  every fill/gradient/border/shadow, and the full text style (family, size, weight, line
  height, letter spacing, case, mixed-style runs).

Layout is read from the tree wherever the design used auto-layout (`layoutSource:
"auto-layout"`). Only frames the designer positioned by hand fall back to deriving
direction, gap and padding from geometry (`layoutSource: "geometry"`) — and that path is a
guess, so the IR says which one each container is.

Component instances whose children `get_metadata` did not expand get their subtree grafted
from the context tree. Grafted nodes carry no `rect` (Figma gave no geometry for them),
which `layout_assert.py` reports as unverified rather than passing.

Usage:
    python3 figma_to_ir.py --metadata raw/metadata.xml --tree raw/context-tree.json \\
        --texts raw/texts.json --styles raw/styles.json --assets raw/assets.json \\
        --out ir/screen.ui.json

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
IMAGEISH = re.compile(r"(thumb|avatar|photo|image|cover|artwork|hero[-_]?img|picture|banner)", re.I)
DIVIDERISH = re.compile(r"(divider|separator|hairline|rule)", re.I)


def infer_role(tag: str, name: str, w: float, h: float, has_children: bool, tnode: dict | None = None) -> str:
    lower = name.lower()
    if tnode:
        if tnode.get("text") and not has_children:
            return "text"
        if (asset := tnode.get("asset")) and not has_children:
            scale = (asset.get("style") or {}).get("contentScale")
            if asset.get("ext") == "png" and (scale == "Crop" or IMAGEISH.search(lower) or max(w, h) > 64):
                return "image"
            return "icon"
        if not has_children and tnode.get("style") and tag != "text":
            # A childless frame with its own fill or border and no exported asset is a drawn
            # shape — a radio ring, a dot, a swatch — not an icon slot waiting for a file.
            return "divider" if min(w, h) <= 2 < max(w, h) else "surface"
    if tag == "text":
        return "text"
    if tag == "instance" and not has_children:
        return "component"
    if DIVIDERISH.search(lower) or (min(w, h) <= 2 < max(w, h) and not has_children):
        return "divider"
    if "rect" in tag or tag in ("ellipse", "polygon", "star", "line"):
        return "image" if IMAGEISH.search(lower) else "surface"
    if tag in ("vector", "boolean-operation"):
        return "icon"
    if not has_children:
        if ICONISH.search(lower) or max(w, h) <= 32:
            return "icon"
        return "image" if IMAGEISH.search(lower) else "surface"
    return "container"


UNSUPPORTED_TAGS = {"boolean-operation": "boolean_op", "slice": "slice", "mask": "mask"}


# ---------------------------------------------------------------- geometry → layout (fallback)


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
    """Infer column, row, grid, or stack from child geometry.

    Children are compared in *visual* order. Figma's layer order on a hand-positioned frame
    is whatever order the designer drew in, so comparing neighbours in XML order calls an
    ordinary vertical list a `stack`.
    """
    if len(children) < 2:
        return "column"
    by_y = sorted(((c["_x"], c["_y"], c["_w"], c["_h"]) for c in children), key=lambda b: (b[1], b[0]))
    col = all(
        _overlap(a[0], a[0] + a[2], b[0], b[0] + b[2]) > 0.5 and a[1] + a[3] <= b[1] + 1
        for a, b in zip(by_y, by_y[1:])
    )
    if col:
        return "column"

    x_bands = {round(c["_x"], 1) for c in children}
    y_bands = {round(c["_y"], 1) for c in children}
    if len(x_bands) > 1 and len(y_bands) > 1:
        cells = {(round(c["_x"], 1), round(c["_y"], 1)) for c in children}
        # A full grid, or a grid whose last row is short.
        if len(cells) == len(children) and len(children) > (len(y_bands) - 1) * len(x_bands):
            return "grid"

    by_x = sorted(((c["_x"], c["_y"], c["_w"], c["_h"]) for c in children), key=lambda b: b[0])
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
    if all(abs(g - median) <= 1.5 for g in gaps):
        if median <= 1.0:
            return None
        return max(0.0, round(median, 2))
    return None


def sibling_spacing(children: list[dict], direction: str) -> list[float] | None:
    """Per-gap spacing when the gaps disagree — a single spacedBy() cannot describe them."""
    if direction not in ("column", "row") or len(children) < 2:
        return None
    pos, size = ("_y", "_h") if direction == "column" else ("_x", "_w")
    ordered = sorted(children, key=lambda c: c[pos])
    return [round(b[pos] - (a[pos] + a[size]), 2) for a, b in zip(ordered, ordered[1:])]


def infer_padding(node_w: float, node_h: float, children: list[dict], direction: str) -> tuple[dict | None, dict]:
    """Padding, plus the alignment and trailing space that padding would otherwise fake.

    Children centred inside their parent are an *alignment*, not left/right padding; a
    column whose children stop well short of its bottom has *trailing space*, not 900dp of
    padding.
    """
    if not children:
        return None, {}

    left = min(c["_x"] for c in children)
    top = min(c["_y"] for c in children)
    right = node_w - max(c["_x"] + c["_w"] for c in children)
    bottom = node_h - max(c["_y"] + c["_h"] for c in children)
    extra: dict = {}

    def centred(axis_size: float, starts: list[float], sizes: list[float], near: float, far: float) -> bool:
        """True only when centring is the *unambiguous* reading of the geometry."""
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
        extra["trailingSpace"] = round(bottom, 2)
        bottom = 0.0

    if direction == "row" and "cross" not in extra.get("align", {}):
        # Row children of differing heights sharing one centre line are cross-centred.
        centres = [y + h / 2 for y, h in zip(ys, hs)]
        if max(hs) - min(hs) > 1.5 and max(centres) - min(centres) <= 1.5:
            extra.setdefault("align", {})["cross"] = "center"
            mid = (min(ys) + max(y + h for y, h in zip(ys, hs))) / 2
            top = bottom = max(0.0, min(mid - max(hs) / 2, node_h - mid - max(hs) / 2))

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


def geometry_sizing(child: dict, parent_w: float, parent_h: float, padding: dict | None, direction: str) -> None:
    """Turn a child's measured width into `fill` when it spans its parent's content box.

    The old check compared against the parent's *outer* width, so a 350dp card inside a
    390dp frame with 20dp insets came out as `width: 350` — the frame width leaking into
    code, the exact mistake generation.md tells the generator to undo by hand.
    """
    pad = padding or {}
    content_w = parent_w - pad.get("start", 0) - pad.get("end", 0)
    content_h = parent_h - pad.get("top", 0) - pad.get("bottom", 0)
    layout = child["layout"]
    if direction in ("column", "stack", "grid"):
        if abs(child["_w"] - content_w) <= 0.5:
            layout["width"] = "fill"
        elif direction != "grid" and child["_w"] >= content_w * 0.5:
            # Symmetric insets inside the parent: fill, inset by a margin.
            left = child["_x"] - pad.get("start", 0)
            right = content_w - (left + child["_w"])
            if left > 0 and abs(left - right) <= 1.0:
                layout["width"] = "fill"
                layout["margin"] = {"start": round(left, 2), "end": round(right, 2)}
    if direction == "row" and child["role"] != "text" and abs(child["_h"] - content_h) <= 0.5 and content_h > 0:
        if child["role"] == "container":
            layout["height"] = "fill"


# ---------------------------------------------------------------- context tree → IR fields


def ir_color(entry: dict | None) -> dict | None:
    if not entry or "hex" not in entry:
        return None
    out = {"raw": entry["hex"], "token": None}
    if "alpha" in entry:
        out["alpha"] = entry["alpha"]
    return out


def ir_shadow(s: dict) -> dict:
    out = {k: s[k] for k in ("x", "y", "blur", "spread") if k in s}
    out["color"] = ir_color(s)
    if s.get("inset"):
        out["inset"] = True
    return out


def style_from_tree(t: dict) -> dict:
    src = t.get("style") or {}
    out: dict = {}
    if (fill := ir_color(src.get("fill"))) and fill.get("alpha", 1) > 0:
        out["fill"] = fill
    if (grad := src.get("gradient")):
        out["gradient"] = {
            "type": grad.get("type", "linear"),
            "angle": grad.get("angle"),
            "stops": [{**ir_color(s), **({"position": s["position"]} if "position" in s else {})}
                      for s in grad.get("stops", [])],
        }
    if "radius" in src:
        out["radius"] = {"raw": src["radius"], "token": None}
    if "corners" in src:
        out["corners"] = src["corners"]
    if (b := src.get("border")) and "hex" in b:
        out["border"] = {**ir_color(b), "width": b.get("width", 1)}
        if b.get("sides"):
            out["border"]["sides"] = sorted(set(b["sides"]))
        if b.get("style"):
            out["border"]["style"] = b["style"]
    for key in ("shadows", "dropShadows"):
        if src.get(key):
            out[key] = [ir_shadow(s) for s in src[key]]
    for key in ("opacity", "blur", "backgroundBlur", "rotation", "blend", "contentScale"):
        if key in src:
            out[key] = src[key]
    if (image := src.get("image")):
        out["backgroundImage"] = {"export": image.get("url"), "ext": image.get("ext"),
                                  "contentScale": (image.get("style") or {}).get("contentScale", "Crop")}
    return out


def style_from_flat(flat: dict) -> dict:
    out = {}
    for key in ("fill", "radius", "border"):
        if key in flat:
            out[key] = {"raw": flat[key], "token": None}
    if "fillAlpha" in flat and "fill" in out:
        out["fill"]["alpha"] = flat["fillAlpha"]
    if "borderWidth" in flat and "border" in out:
        out["border"]["width"] = flat["borderWidth"]
    for key in ("gradient", "shadows", "dropShadows", "opacity", "corners"):
        if key in flat:
            out[key] = flat[key]
    return out


def text_from_tree(t: dict, h: float | None) -> dict:
    src = t["text"]
    style = {"token": None}
    for key, dst in (("size", "size"), ("weight", "weight"), ("lineHeight", "lineHeight"),
                     ("family", "fontFamily"), ("fontStyle", "fontStyle"), ("italic", "italic")):
        if key in src:
            style[dst] = src[key]
    if isinstance(ls := src.get("letterSpacing"), dict):
        style["letterSpacing"] = ls.get("px", ls)
    out: dict = {
        "content": src.get("content"),
        "style": style,
        "color": ir_color(src.get("color")) or {"raw": None, "token": None},
    }
    for key in ("align", "textCase", "decoration", "singleLine", "ellipsis", "maxLines", "preserveWhitespace"):
        if key in src:
            out[key] = src[key]
    if src.get("runs"):
        out["runs"] = [
            {k: (ir_color(v) if k == "color" else v) for k, v in run.items()} for run in src["runs"]
        ]
    lh = style.get("lineHeight")
    if isinstance(lh, (int, float)) and lh > 0 and h:
        out["lines"] = max(1, round(h / lh))
    return out


def text_from_flat(content, flat: dict) -> dict:
    return {
        "content": content,
        "style": {**{k: v for k, v in flat.items() if k in ("size", "weight", "lineHeight", "letterSpacing", "fontFamily")},
                  "token": None},
        "color": {"raw": flat.get("color"), "token": None},
    }


def layout_from_tree(t: dict) -> dict:
    """The parts of a context-tree node's layout that describe the node *as a container*."""
    src = t.get("layout") or {}
    out: dict = {}
    if src.get("direction"):
        out["direction"] = src["direction"]
    for key in ("gap", "gapX", "gapY"):
        if src.get(key):
            out[key] = {"raw": src[key], "token": None}
    if (pad := src.get("padding")) and any(pad.values()):
        out["padding"] = {**pad, "token": None}
    if src.get("align"):
        out["align"] = dict(src["align"])
    for key in ("wrap", "columns", "rows", "clip"):
        if key in src:
            out[key] = src[key]
    return out


def sizing_from_tree(t: dict) -> dict:
    """How the node sizes itself inside its parent: fill / wrap / fixed, weight, position."""
    src = t.get("layout") or {}
    out: dict = {}
    for axis in ("width", "height"):
        if axis in src:
            out[axis] = src[axis]
    for key in ("weight", "selfAlign", "aspectRatio", "minWidth", "minHeight", "maxWidth", "maxHeight", "cell"):
        if key in src:
            out[key] = src[key]
    if (pos := src.get("position")) and pos.get("absolute"):
        out["position"] = {k: v for k, v in pos.items() if k != "absolute"} or {"top": 0, "start": 0}
    return out


# ---------------------------------------------------------------- tree build


class Extractor:
    def __init__(self, texts: dict, styles: dict, tree_index: dict[str, dict]):
        self.texts = texts
        self.styles = styles
        self.tree = tree_index
        self.chrome: list[dict] = []
        self.unsupported: list[dict] = []
        self.assets: list[dict] = []
        self.missing_text: list[str] = []
        self.grafted = 0
        self.layout_sources = {"auto-layout": 0, "geometry": 0}

    def lookup(self, node_id: str) -> dict | None:
        return self.tree.get(node_id) or self.tree.get(node_id.rsplit(";", 1)[-1])

    # -------------------------------------------------------------- metadata nodes

    def build(self, el: ET.Element, parent_w: float | None = None, parent_h: float | None = None) -> dict | None:
        node_id = el.get("id", "")
        name = el.get("name", "")
        tag = el.tag

        if (handling := chrome_handling(name)):
            self.chrome.append({"id": node_id, "name": name, "handling": handling})
            return None
        if tag in UNSUPPORTED_TAGS:
            self.unsupported.append({"id": node_id, "name": name, "reason": UNSUPPORTED_TAGS[tag]})
            return None

        w, h = _num(el, "width"), _num(el, "height")
        tnode = self.lookup(node_id)
        assets_before = len(self.assets)
        children = [c for c in (self.build(child, w, h) for child in el) if c]

        # An icon is usually a frame of vectors in the metadata and one exported SVG in the
        # context. The SVG is the asset; the vectors are its insides, not layout.
        if tnode and tnode.get("asset") and not tnode.get("children") and children and not any(
            c["role"] in ("text", "container") for c in children
        ):
            children = []
            del self.assets[assets_before:]

        # get_metadata leaves component instances (and over-deep frames) as childless stubs;
        # the context tree has their content.
        if not children and tnode and tnode.get("children"):
            children = [g for c in tnode["children"] if (g := self.graft(c, node_id if tag == "instance" else None))]

        role = infer_role(tag, name, w, h, has_children=bool(children), tnode=tnode)
        node: dict = {"id": node_id, "name": name, "role": role,
                      "_x": _num(el, "x"), "_y": _num(el, "y"), "_w": w, "_h": h}
        is_root = parent_w is None
        sizing = sizing_from_tree(tnode) if tnode else {}
        layout: dict = {
            "width": "fill" if is_root else sizing.get("width", "wrap" if role == "text" else round(w, 2)),
            "height": "fill" if is_root else sizing.get("height", "wrap"),
        }
        layout.update({k: v for k, v in sizing.items() if k not in ("width", "height")})
        node["_sized_by_tree"] = {axis for axis in ("width", "height") if axis in sizing}

        if children:
            tree_layout = layout_from_tree(tnode) if tnode else {}
            if tree_layout.get("direction"):
                layout.update(tree_layout)
                layout["layoutSource"] = "auto-layout"
                self.layout_sources["auto-layout"] += 1
                children = order_like_tree(children, tnode)
            else:
                self.geometry_layout(layout, children, w, h, is_root)
                if tree_layout:
                    layout.update({k: v for k, v in tree_layout.items() if k in ("clip", "padding")})
            if role == "container" and not is_root and "height" not in node["_sized_by_tree"]:
                layout["height"] = round(h, 2) if layout.get("direction") == "stack" else "wrap"
        elif role == "container" and not is_root:
            layout["height"] = round(h, 2)
        node["layout"] = layout

        self.attach_content(node, tnode, h)
        if role in ("icon", "image"):
            self.add_asset(node_id, name, role, tnode)
        node["children"] = children
        if not children:
            node.pop("children")
        return node

    def geometry_layout(self, layout: dict, children: list[dict], w: float, h: float, is_root: bool) -> None:
        self.layout_sources["geometry"] += 1
        metadata_children = [c for c in children if "_x" in c]
        direction = infer_direction(metadata_children)
        layout["direction"] = direction
        layout["layoutSource"] = "geometry"
        gap = infer_gap(metadata_children, direction)
        if gap is not None:
            layout["gap"] = {"raw": gap, "token": None}
        elif (spacing := sibling_spacing(metadata_children, direction)) and len(set(spacing)) > 1:
            layout["spacing"] = spacing   # one value per gap, in visual order
        padding = None
        if not is_root:
            # The screen frame's own insets are an artefact of where the mock's chrome sat.
            padding, extra = infer_padding(w, h, metadata_children, direction)
            if extra.pop("suppressGap", False):
                layout.pop("gap", None)
                layout.pop("spacing", None)
            if padding:
                layout["padding"] = {**padding, "token": None}
            layout.update(extra)
        for child in metadata_children:
            if "width" not in child["_sized_by_tree"] or "height" not in child["_sized_by_tree"]:
                before = {a: child["layout"].get(a) for a in child["_sized_by_tree"]}
                geometry_sizing(child, w, h, padding, direction)
                child["layout"].update(before)
        children.sort(key=visual_key(direction))

    def attach_content(self, node: dict, tnode: dict | None, h: float | None) -> None:
        node_id = node["id"]
        source_id = node_id.rsplit(";", 1)[-1]
        flat = self.styles.get(node_id, self.styles.get(source_id, {}))
        style = style_from_tree(tnode) if tnode else style_from_flat(flat)
        if style:
            node["style"] = style
            if style.get("blend") and style["blend"] not in ("normal", "pass-through"):
                self.unsupported.append({"id": node_id, "name": node["name"], "reason": f"blend_{style['blend']}"})
        if node["role"] == "text":
            if tnode and tnode.get("text"):
                node["text"] = text_from_tree(tnode, h)
            else:
                content = self.texts.get(node_id, self.texts.get(source_id))
                node["text"] = text_from_flat(content, flat)
            if node["text"].get("content") is None:
                self.missing_text.append(node_id)
        if tnode and tnode.get("component"):
            node["mapping"] = {"designComponent": tnode["component"], "props": tnode.get("props", {})}

    def add_asset(self, node_id: str, name: str, role: str, tnode: dict | None) -> None:
        asset = (tnode or {}).get("asset") or {}
        self.assets.append({"id": node_id, "name": name, "kind": role,
                            "export": asset.get("url"), "ext": asset.get("ext"),
                            **({"contentScale": asset["style"]["contentScale"]}
                               if (asset.get("style") or {}).get("contentScale") else {})})

    # -------------------------------------------------------------- grafted nodes

    def graft(self, t: dict, instance_id: str | None) -> dict | None:
        """An IR node built from the context tree alone — no metadata, so no rect."""
        name = t.get("name", "")
        if chrome_handling(name):
            self.chrome.append({"id": t["id"], "name": name, "handling": chrome_handling(name)})
            return None
        node_id = t["id"]
        if instance_id and not node_id.startswith("I"):
            node_id = f"I{instance_id};{node_id}"   # Figma's own id for a node inside an instance
        children = [g for c in t.get("children", []) if (g := self.graft(c, instance_id))]
        size = t.get("layout", {})
        w = size.get("width") if isinstance(size.get("width"), (int, float)) else 0
        hh = size.get("height") if isinstance(size.get("height"), (int, float)) else 0
        role = infer_role(t.get("tag", ""), name, w, hh, bool(children), tnode=t)
        if role == "surface" and not children and not t.get("style"):
            role = "container"
        sizing = sizing_from_tree(t)
        layout = {"width": sizing.get("width", "wrap"), "height": sizing.get("height", "wrap"),
                  **{k: v for k, v in sizing.items() if k not in ("width", "height")}}
        if children:
            layout.update(layout_from_tree(t) or {"direction": "stack"})
            layout["layoutSource"] = "auto-layout" if t.get("layout", {}).get("direction") else "none"
        node = {"id": node_id, "name": name, "role": role, "layout": layout, "_graft": True,
                "_sized_by_tree": set(sizing)}
        self.attach_content(node, t, hh or None)
        if role in ("icon", "image"):
            self.add_asset(node_id, name, role, t)
        if children:
            node["children"] = children
        self.grafted += 1
        return node


def visual_key(direction: str):
    """Reading order for the children of a container laid out in `direction`.

    Sorting a Row by (y, x) puts a 16dp chevron at y=4 before a 20dp title at y=6 — the
    row is reordered by its own vertical centring.
    """
    if direction == "row":
        return lambda c: (c.get("_x", 0), c.get("_y", 0))
    if direction == "column":
        return lambda c: (c.get("_y", 0), c.get("_x", 0))
    return lambda c: (round(c.get("_y", 0), 1), round(c.get("_x", 0), 1))


def order_like_tree(children: list[dict], tnode: dict) -> list[dict]:
    """Auto-layout order is the DOM order of the design context."""
    order = {}
    for i, c in enumerate(tnode.get("children", [])):
        order.setdefault(c["id"], i)
        order.setdefault(c["id"].rsplit(";", 1)[-1], i)
    if all(c["id"] in order or c["id"].rsplit(";", 1)[-1] in order for c in children):
        return sorted(children, key=lambda c: order.get(c["id"], order.get(c["id"].rsplit(";", 1)[-1], 0)))
    direction = (tnode.get("layout") or {}).get("direction", "column")
    return sorted(children, key=visual_key(direction))


def strip_internals(node: dict, origin: tuple[float, float] = (0.0, 0.0)) -> dict:
    """Drop the working fields, keeping design geometry as an absolute `rect`.

    `layout` says how to *build* the node; `rect` says where the design put it, which is
    what layout_assert.py compares against. Grafted nodes have no design geometry and get no
    rect — they are reported as unverified, never as passing.
    """
    out = {k: v for k, v in node.items() if not k.startswith("_")}
    if node.get("_graft"):
        x, y = origin
    else:
        x = origin[0] + node["_x"]
        y = origin[1] + node["_y"]
        out["rect"] = {"x": round(x, 2), "y": round(y, 2), "w": round(node["_w"], 2), "h": round(node["_h"], 2)}
    if "children" in out:
        out["children"] = [strip_internals(c, (x, y)) for c in node["children"]]
    return out


# ---------------------------------------------------------------- main


def index_tree(root: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    stack = [root]
    while stack:
        n = stack.pop()
        if n.get("id"):
            index.setdefault(n["id"], n)
            if n.get("componentId"):
                index.setdefault(n["componentId"], n)
        stack.extend(reversed(n.get("children", [])))
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata", required=True, type=Path, help="get_metadata XML output")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--tree", type=Path, help="context-tree.json from context_to_ir.py --tree — the source of auto-layout, sizing and full style")
    ap.add_argument("--texts", type=Path, help="texts.json from context_to_ir.py")
    ap.add_argument("--styles", type=Path, help="styles.json from context_to_ir.py")
    ap.add_argument("--assets", type=Path, help="assets.json from context_to_ir.py")
    ap.add_argument("--file-key", default="", help="recorded in source metadata")
    ap.add_argument("--geometry-only", action="store_true",
                    help="deliberately build a geometry-only IR with no text, fills or assets. "
                         "Almost never what you want — see the refusal message.")
    args = ap.parse_args()

    # An IR with no content looks like success. On a real run the flags were omitted, the IR
    # came out as seven empty boxes, and the generated screen lost every colour and asset.
    if not args.geometry_only and not (args.texts and args.styles):
        missing = " and ".join(n for n, v in (("--texts", args.texts), ("--styles", args.styles)) if not v)
        print(
            f"error: {missing} not supplied — the IR would carry geometry and nothing else.\n"
            "       Build them (and the tree) from the design context first:\n"
            "         python3 context_to_ir.py --context raw/context.json --tree raw/context-tree.json \\\n"
            "             --texts raw/texts.json --styles raw/styles.json --assets raw/assets.json\n"
            "       Pass --geometry-only if a box-only IR is genuinely what you want.",
            file=sys.stderr,
        )
        return 2

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
    xml = raw[start: end + len(closing)] if end >= start else raw[start: raw.find(">", start) + 1]
    try:
        root_el = ET.fromstring(xml)
    except ET.ParseError as exc:
        print(f"error: could not parse metadata XML: {exc}", file=sys.stderr)
        return 2

    texts = json.loads(args.texts.read_text(encoding="utf-8")) if args.texts else {}
    styles = json.loads(args.styles.read_text(encoding="utf-8")) if args.styles else {}
    raw_assets: list[dict] = []
    if args.assets and args.assets.exists():
        raw_assets = json.loads(args.assets.read_text(encoding="utf-8"))
    asset_urls = {}
    for entry in raw_assets:
        if entry.get("id"):
            asset_urls.setdefault(entry["id"], entry)

    tree_doc = None
    tree_index: dict[str, dict] = {}
    if args.tree:
        tree_doc = json.loads(args.tree.read_text(encoding="utf-8"))
        tree_index = index_tree(tree_doc["root"])
    else:
        print("note: no --tree — layout will be derived from geometry alone, and line height,\n"
              "      letter spacing, font family, shadows and gradients will be missing from the IR.\n"
              "      Run context_to_ir.py with --tree and pass it here.", file=sys.stderr)

    extractor = Extractor(texts, styles, tree_index)
    root = extractor.build(root_el)
    if root is None:
        print("error: root node was classified as chrome — check the nodeId", file=sys.stderr)
        return 2

    assets = []
    for a in extractor.assets:
        if not a.get("export"):
            fallback = asset_urls.get(a["id"], asset_urls.get(a["id"].rsplit(";", 1)[-1], {})) or {}
            a = {**a, "export": fallback.get("url"), "ext": fallback.get("ext")}
        assets.append(a)

    ir = {
        "schema": "ui-ir/v2",
        "source": {"fileKey": args.file_key, "nodeId": root_el.get("id", ""), "name": root_el.get("name", "")},
        "frame": {"width": _num(root_el, "width"), "height": _num(root_el, "height")},
        "fonts": (tree_doc or {}).get("fonts", []),
        "platformChrome": extractor.chrome,
        "root": strip_internals(root, (-root["_x"], -root["_y"])),
        "assets": assets,
        # Flat fallback: every string, style and asset the context carried, keyed by node id,
        # in case a node never made it into the tree above.
        "sourceContext": {"texts": texts, "styles": styles, "assets": raw_assets},
        "unsupported": extractor.unsupported,
        "mapping": {"resolvedCount": 0, "unmapped": [], "resolved": False},
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(ir, indent=2, ensure_ascii=False, default=sorted) + "\n", encoding="utf-8")

    def count(node: dict) -> int:
        return 1 + sum(count(c) for c in node.get("children", []))

    src = extractor.layout_sources
    print(f"wrote {args.out}")
    print(f"  nodes          {count(ir['root'])}  ({extractor.grafted} grafted from the context tree, no rect)")
    print(f"  containers     {src['auto-layout']} auto-layout · {src['geometry']} derived from geometry")
    print(f"  chrome removed {len(extractor.chrome)}  {[c['name'] for c in extractor.chrome]}")
    print(f"  assets         {len(assets)}  ({sum(1 for a in assets if not a.get('export'))} without an export URL)")
    print(f"  unsupported    {len(extractor.unsupported)}")
    if ir["fonts"]:
        print(f"  fonts          {', '.join(ir['fonts'])}")
    if extractor.missing_text:
        print(f"  MISSING TEXT   {len(extractor.missing_text)} nodes — pass --tree/--texts from context_to_ir.py")
    if src["geometry"] and src["auto-layout"] == 0 and args.tree:
        print("  note: no container matched an auto-layout node in the tree — check that the tree and\n"
              "        the metadata come from the same nodeId.")
    print("\nnext: ir_coverage_check.py, then (optionally) resolve_tokens.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
