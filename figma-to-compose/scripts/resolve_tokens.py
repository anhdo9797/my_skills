#!/usr/bin/env python3
"""Annotate a UI IR with the project's design tokens, where they fit.

**Optional step.** The pipeline generates Compose with or without it. Run it when the
project has a design system worth reusing; skip it entirely when it does not, or when the
design is a new visual direction the codebase has not adopted yet.

What it does: each `{"raw": X, "token": null}` pair gets a token name when one matches, and
is listed in `mapping.unmapped` when none does. Unmapped is **information, not a failure** —
the generator emits the raw value with a marker so review can see it, which is where the
"should this be a token" conversation belongs. A value within `tolerance.snapDistance` is
pulled to the nearest token and marked `"snapped": true`, so a design drawn at 15dp becomes
spacing.md instead of a 41st spacing constant.

Exit codes: 0 normally (even with unmapped values), 1 only with --strict and something
unmapped, 2 usage error. Use --strict in CI for a project that has decided its screens may
not introduce new raw values.

Usage:
    python3 resolve_tokens.py --ir ir/screen.ui.json --adapter .figma/adapter.json \\
                              --out ir/screen.ui.json --report ir/mapping-report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------- colour


def hex_to_rgb(value: str) -> tuple[float, float, float] | None:
    if not isinstance(value, str):
        return None
    h = value.strip().lstrip("#")
    if len(h) == 8:  # AARRGGBB from the Kotlin side
        h = h[2:]
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + (16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a: str, b: str) -> float | None:
    """CIE76. Good enough to answer 'is this the same design colour or a different one'."""
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    if ra is None or rb is None:
        return None
    la, lb = rgb_to_lab(ra), rgb_to_lab(rb)
    return sum((x - y) ** 2 for x, y in zip(la, lb)) ** 0.5


# ---------------------------------------------------------------- resolver


class Resolver:
    def __init__(self, adapter: dict):
        theme = adapter.get("theme", {})
        self.spacing: dict[str, float] = theme.get("spacing", {})
        self.radii: dict[str, float] = {**theme.get("shapes", {}), **theme.get("radii", {})}
        self.colors: dict[str, str] = theme.get("colors", {})

        # Both halves of the project's type system are candidates. The scanner splits them
        # because generated code reaches them differently — a Material slot is
        # `MaterialTheme.typography.x`, a project style goes through the theme's own
        # accessor — but a *design* value must be matched against both or a project that
        # defined exactly the compact style the design asked for is told it has no token.
        # The prefix carries the distinction downstream.
        self.typography: dict[str, tuple[str, dict]] = {
            **{name: ("typography", entry) for name, entry in theme.get("typography", {}).items()},
            **{name: ("typeScale", entry) for name, entry in theme.get("typeScale", {}).items()},
        }

        tol = adapter.get("tolerance", {})
        self.snap = tol.get("snapDistance", {})
        self.color_tol = tol.get("colorDeltaE", 6)

        self.resolved = 0
        self.snapped: list[dict] = []
        self.unmapped: dict[tuple, dict] = {}

    # -- generic numeric ------------------------------------------------

    def _numeric(self, raw, table: dict[str, float], prefix: str, kind: str, node_id: str, limit: float):
        if not isinstance(raw, (int, float)) or not table:
            return None
        if raw == 0:
            return None  # zero is the absence of a value, not a token
        name, value = min(table.items(), key=lambda kv: abs(kv[1] - raw))
        distance = abs(value - raw)
        if distance < 0.01:
            self.resolved += 1
            return f"{prefix}.{name}"
        if distance <= limit:
            self.resolved += 1
            self.snapped.append({"kind": kind, "raw": raw, "token": f"{prefix}.{name}", "distance": round(distance, 2), "node": node_id})
            return f"{prefix}.{name}"
        self._miss(kind, raw, node_id, f"{prefix}.{name}", round(distance, 2))
        return None

    def spacing_token(self, raw, node_id: str):
        return self._numeric(raw, self.spacing, "spacing", "spacing", node_id, self.snap.get("spacing", 2))

    def radius_token(self, raw, node_id: str):
        return self._numeric(raw, self.radii, "radii", "radius", node_id, self.snap.get("radius", 3))

    # -- colour ---------------------------------------------------------

    def color_token(self, raw, node_id: str):
        if not isinstance(raw, str) or hex_to_rgb(raw) is None:
            return None
        scored = [(role, delta_e(raw, hexv)) for role, hexv in self.colors.items()]
        scored = [(role, d) for role, d in scored if d is not None]
        if not scored:
            self._miss("color", raw, node_id, None, None)
            return None
        role, distance = min(scored, key=lambda kv: kv[1])
        if distance <= 0.5:
            self.resolved += 1
            return f"colorScheme.{role}"
        if distance <= self.color_tol:
            self.resolved += 1
            self.snapped.append({"kind": "color", "raw": raw, "token": f"colorScheme.{role}", "distance": round(distance, 2), "node": node_id})
            return f"colorScheme.{role}"
        self._miss("color", raw, node_id, f"colorScheme.{role}", round(distance, 2))
        return None

    # -- typography -----------------------------------------------------

    def type_token(self, style: dict, node_id: str):
        size = style.get("size")
        if not isinstance(size, (int, float)) or not self.typography:
            return None
        weight = style.get("weight")
        limit = self.snap.get("fontSize", 1)

        def score(entry: dict) -> tuple[float, float]:
            size_gap = abs(entry.get("size", 0) - size)
            weight_gap = abs(entry.get("weight", 400) - weight) if isinstance(weight, (int, float)) else 0
            # Rank by size first. Ranking by weight first makes every bold value report the
            # nearest *bold* style regardless of size — an 11sp label comes back as
            # "nearest headlineMedium (25sp)", which tells a reader nothing about what to do.
            return (size_gap, weight_gap)

        name, (group, entry) = min(self.typography.items(), key=lambda kv: score(kv[1][1]))
        size_gap, weight_gap = score(entry)
        token = f"{group}.{name}"
        # A style is only the same style when both the size and the weight agree; a 16sp
        # regular is not a 16sp semibold, and swapping them is exactly the bug the
        # intra-screen type ratio is meant to catch.
        if weight_gap == 0 and size_gap < 0.01:
            self.resolved += 1
            return token
        if weight_gap <= 100 and size_gap <= limit:
            self.resolved += 1
            self.snapped.append({"kind": "typography", "raw": f"{size}sp/{weight}", "token": token, "distance": round(size_gap, 2), "node": node_id})
            return token
        self._miss("typography", f"{size}sp/{weight}", node_id, token, round(size_gap, 2))
        return None

    # -- misses ---------------------------------------------------------

    def _miss(self, kind: str, raw, node_id: str, nearest: str | None, distance):
        key = (kind, str(raw))
        entry = self.unmapped.setdefault(key, {"kind": kind, "raw": raw, "nodes": [], "nearest": nearest, "distance": distance})
        if node_id not in entry["nodes"]:
            entry["nodes"].append(node_id)


# ---------------------------------------------------------------- walk


def resolve_node(node: dict, r: Resolver) -> None:
    node_id = node.get("id", "")
    layout = node.get("layout") or {}

    gap = layout.get("gap")
    if isinstance(gap, dict) and gap.get("token") is None:
        gap["token"] = r.spacing_token(gap.get("raw"), node_id)

    padding = layout.get("padding")
    if isinstance(padding, dict):
        sides = {s: padding.get(s) for s in ("start", "top", "end", "bottom")}
        tokens = {s: r.spacing_token(v, node_id) for s, v in sides.items() if v}
        # Collapse to the shorthand Compose actually reads well.
        if tokens.get("start") and tokens["start"] == tokens.get("end"):
            tokens["horizontal"] = tokens.pop("start")
            tokens.pop("end", None)
        if tokens.get("top") and tokens["top"] == tokens.get("bottom"):
            tokens["vertical"] = tokens.pop("top")
            tokens.pop("bottom", None)
        padding["token"] = tokens or None

    # trailingSpace is deliberately not resolved: it is the container being taller than its
    # content, not a spacing decision, and forcing it through the token table would report
    # a 900dp "unmapped spacing" on every scroll frame.

    style = node.get("style") or {}
    for key, slot in (("fill", "color"), ("border", "color"), ("radius", "radius")):
        entry = style.get(key)
        if isinstance(entry, dict) and entry.get("token") is None:
            entry["token"] = r.color_token(entry.get("raw"), node_id) if slot == "color" else r.radius_token(entry.get("raw"), node_id)

    text = node.get("text")
    if isinstance(text, dict):
        tstyle = text.get("style")
        if isinstance(tstyle, dict) and tstyle.get("token") is None:
            tstyle["token"] = r.type_token(tstyle, node_id)
        color = text.get("color")
        if isinstance(color, dict) and color.get("token") is None and color.get("raw"):
            color["token"] = r.color_token(color.get("raw"), node_id)

    for child in node.get("children", []):
        resolve_node(child, r)


# ---------------------------------------------------------------- component mapping


# Kept in sync with scan_design_system.py — words that say where a box sits, not what it is.
GENERIC_TOKENS = {
    "row", "column", "col", "bar", "group", "wrap", "inner", "outer", "content", "section",
    "item", "left", "right", "top", "bottom", "start", "end", "main", "container", "frame",
    "view", "screen", "app", "entry", "area", "block", "part", "box", "layout", "header",
    "footer", "body", "list", "grid", "stack", "panel", "info", "detail", "default",
}


def match_component(name: str, components: list[dict]) -> tuple[str, str] | None:
    lower = name.lower()
    for comp in components:
        for hint in comp.get("figmaHints", []):
            h = hint.lower()
            if h == lower:
                return comp["name"], f"exact:{hint}"
    # Hint wildcards, most specific first. `#` is the one that matters: designers number
    # repeated instances (`tool-0`, `recent-item-2`), and a plain `tool-*` also swallows
    # `tool-section-compress` and `tools-grid-edit`, which are not the same thing at all.
    for wildcard in ("#", "*"):
        for comp in components:
            for hint in comp.get("figmaHints", []):
                h = hint.lower()
                if wildcard not in h:
                    continue
                if wildcard == "#":
                    if re.fullmatch(re.escape(h).replace(r"\#", r"\d+"), lower):
                        return comp["name"], f"glob:{hint}"
                    continue
                if h.startswith("*") and h.endswith("*"):
                    if h.strip("*-") in lower:
                        return comp["name"], f"glob:{hint}"
                elif h.endswith("*") and lower.startswith(h.rstrip("*-")):
                    return comp["name"], f"glob:{hint}"
                elif h.startswith("*") and lower.endswith(h.lstrip("*-")):
                    return comp["name"], f"glob:{hint}"
    # Token overlap is the weakest tier and the one that produces nonsense, because every
    # design is full of rows, bars and sections. Two distinctive words must agree before it
    # claims a match — one shared generic word matched `tab-Settings` to `SettingsScreen`
    # and `hero-top-row` to `MetricRow`. Under-mapping is cheap: a human adds the hint.
    tokens = set(t for t in lower.replace("_", "-").split("-") if len(t) > 2) - GENERIC_TOKENS
    best: tuple[int, str, str] | None = None
    for comp in components:
        hints = set(h.lower().rstrip("-*") for h in comp.get("figmaHints", [])) - GENERIC_TOKENS
        shared = tokens & hints
        if len(shared) >= 2 and (best is None or len(shared) > best[0]):
            best = (len(shared), comp["name"], f"tokens:{sorted(shared)}")
    return (best[1], best[2]) if best else None


def map_components(node: dict, components: list[dict], stats: dict) -> None:
    if node.get("role") == "container":
        hit = match_component(node.get("name", ""), components)
        if hit:
            node["mapping"] = {"component": hit[0], "via": hit[1]}
            stats["mapped"] += 1
        else:
            node["mapping"] = {"component": None, "via": None}
            stats["unmappedContainers"].append({"id": node.get("id"), "name": node.get("name")})
    for child in node.get("children", []):
        map_components(child, components, stats)


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ir", required=True, type=Path)
    ap.add_argument("--adapter", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--strict", action="store_true", help="exit 1 when anything is unmapped (CI gate; off by default)")
    args = ap.parse_args()

    try:
        ir = json.loads(args.ir.read_text(encoding="utf-8"))
        adapter = json.loads(args.adapter.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    resolver = Resolver(adapter)
    resolve_node(ir["root"], resolver)

    stats = {"mapped": 0, "unmappedContainers": []}
    map_components(ir["root"], adapter.get("components", []), stats)

    unmapped = sorted(resolver.unmapped.values(), key=lambda e: (e["kind"], -len(e["nodes"])))
    by_kind: dict[str, int] = defaultdict(int)
    for entry in unmapped:
        by_kind[entry["kind"]] += 1

    ir["mapping"] = {
        "resolved": True,
        "resolvedCount": resolver.resolved,
        "snappedCount": len(resolver.snapped),
        "unmapped": unmapped,
        "componentsMapped": stats["mapped"],
        "containersWithoutComponent": len(stats["unmappedContainers"]),
    }

    report = {
        "source": ir.get("source"),
        "adapter": str(args.adapter),
        "resolvedCount": resolver.resolved,
        "unmappedByKind": dict(by_kind),
        "unmapped": unmapped,
        "snapped": resolver.snapped,
        "componentsMapped": stats["mapped"],
        "containersWithoutComponent": stats["unmappedContainers"],
        "verdict": "clean" if not unmapped else ("BLOCKED" if args.strict else "raw-values-present"),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(ir, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"resolved   {resolver.resolved} values ({len(resolver.snapped)} snapped to nearest token)")
    print(f"components {stats['mapped']} mapped, {len(stats['unmappedContainers'])} containers with no match")
    if unmapped:
        print(f"\n{len(unmapped)} distinct values have no matching token — these stay raw in the generated code:")
        for entry in unmapped[:15]:
            near = f"nearest {entry['nearest']} (Δ{entry['distance']})" if entry["nearest"] else "no candidate"
            print(f"  {entry['kind']:10} {str(entry['raw']):24} ×{len(entry['nodes']):<3} {near}")
        if len(unmapped) > 15:
            print(f"  … {len(unmapped) - 15} more in {args.report}")
        if args.strict:
            print("\n--strict: stopping. Resolve these, or drop --strict to generate with raw values.")
            return 1
        print("\nGeneration proceeds. Each raw value carries a marker comment naming its Figma node,")
        print("so review can decide what deserves a token. Whole families unmatched usually means")
        print("the design is a new visual direction — worth saying so in the PR description.")
        return 0

    print(f"\nEvery value resolved to a token. Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
