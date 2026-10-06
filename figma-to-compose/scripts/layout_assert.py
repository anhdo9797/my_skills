#!/usr/bin/env python3
"""Per-node layout assertion: compare where Compose actually put each node to the design.

Pixel comparison guesses element boundaries from light and dark pixels, so a photo where
the design has an icon shifts a measurement by 20dp with nothing wrong in the code. This
script does not look at pixels at all. It asks Compose where each composable landed —
exact dp, straight from `LayoutCoordinates` — and compares that to the Figma node it was
generated from.

Input: the IR (which carries every node's Figma geometry), plus a JSON dump of actual
rects keyed by Figma node id, produced by a Compose test (see references/pixel-fidelity.md):

    {"20:12": {"x": 20.0, "y": 182.0, "w": 350.0, "h": 54.0}, ...}

Three deltas per node, because they fail for different reasons and take different fixes:

  size      w/h against the design           -> a wrong modifier on this node
  offset    position within its own parent   -> wrong padding/arrangement in the parent
  gap       distance to the previous sibling -> wrong spacedBy in the parent

Absolute position is reported but never flagged: it accumulates every ancestor's error, so
one wrong padding at the top makes a hundred nodes look broken. Offset-within-parent
isolates the defect to the node that caused it.

Exit codes: 0 within tolerance, 1 something outside it, 2 usage error,
3 UNMEASURED — no design-geometry node was tagged and compared (see --min-coverage).
Exit 3 is unconditional: it fires regardless of --strict, because an unmeasured run is not
a pass under any flag. A verdict of PASS or FINDINGS means something was actually measured;
a verdict of UNMEASURED means nothing was, and the caller must not report convergence,
fidelity, or success from this run. See references/verification.md, "Verdict state machine".

Usage:
    python3 layout_assert.py --ir ir/screen.ui.json --actual render/nodes.json \\
            --out audit/layout.json [--tolerance 1.0] [--strict] [--min-coverage 0.5]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def flatten(node: dict, parent: dict | None = None, prev: dict | None = None, out: list | None = None) -> list[dict]:
    """Every node with its parent and previous visual sibling, in reading order."""
    out = [] if out is None else out
    out.append({"node": node, "parent": parent, "prev": prev})
    previous = None
    for child in node.get("children", []):
        flatten(child, node, previous, out)
        previous = child
    return out


def design_rect(node: dict) -> dict | None:
    """Figma geometry as the IR recorded it, in design dp, absolute within the frame."""
    rect = node.get("rect")
    if not isinstance(rect, dict):
        return None
    try:
        return {k: float(rect[k]) for k in ("x", "y", "w", "h")}
    except (KeyError, TypeError, ValueError):
        return None


def compare(entry: dict, actual: dict[str, dict], tol: float) -> dict | None:
    node = entry["node"]
    node_id = node.get("id")
    got = actual.get(node_id)
    want = design_rect(node)
    if got is None or want is None:
        return None

    result: dict = {
        "node": node_id,
        "name": node.get("name"),
        "design": want,
        "actual": {k: round(float(got.get(k, 0)), 2) for k in ("x", "y", "w", "h")},
        "findings": [],
    }

    for axis, key in (("width", "w"), ("height", "h")):
        delta = result["actual"][key] - want[key]
        if abs(delta) > tol:
            result["findings"].append(
                {"kind": "size", "axis": axis, "design": want[key], "actual": result["actual"][key],
                 "delta": round(delta, 2), "ratio": round(result["actual"][key] / want[key], 3) if want[key] else None}
            )

    parent = entry["parent"]
    if parent is not None:
        p_want, p_got = design_rect(parent), actual.get(parent.get("id"))
        if p_want and p_got:
            for axis, key in (("x", "x"), ("y", "y")):
                want_off = want[key] - p_want[key]
                got_off = result["actual"][key] - float(p_got.get(key, 0))
                delta = got_off - want_off
                if abs(delta) > tol:
                    result["findings"].append(
                        {"kind": "offset", "axis": axis, "parent": parent.get("id"), "parentName": parent.get("name"),
                         "design": round(want_off, 2), "actual": round(got_off, 2), "delta": round(delta, 2)}
                    )

    prev = entry["prev"]
    if prev is not None:
        s_want, s_got = design_rect(prev), actual.get(prev.get("id"))
        if s_want and s_got:
            # Gap along whichever axis the two actually separate on.
            vertical = (want["y"] - (s_want["y"] + s_want["h"])) >= (want["x"] - (s_want["x"] + s_want["w"]))
            if vertical:
                want_gap = want["y"] - (s_want["y"] + s_want["h"])
                got_gap = result["actual"]["y"] - (float(s_got.get("y", 0)) + float(s_got.get("h", 0)))
                axis = "vertical"
            else:
                want_gap = want["x"] - (s_want["x"] + s_want["w"])
                got_gap = result["actual"]["x"] - (float(s_got.get("x", 0)) + float(s_got.get("w", 0)))
                axis = "horizontal"
            delta = got_gap - want_gap
            if want_gap >= 0 and abs(delta) > tol:
                result["findings"].append(
                    {"kind": "gap", "axis": axis, "after": prev.get("id"), "afterName": prev.get("name"),
                     "design": round(want_gap, 2), "actual": round(got_gap, 2), "delta": round(delta, 2)}
                )

    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ir", required=True, type=Path)
    ap.add_argument("--actual", required=True, type=Path, help="node-id -> {x,y,w,h} dump from the Compose test")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--tolerance", type=float, default=1.0, help="dp; use 0.5 for a pixel-perfect run (default 1.0)")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any finding")
    ap.add_argument("--min-coverage", type=float, default=0.5,
                     help="fraction (0-1) of design-geometry nodes that must be tagged and compared "
                          "(default 0.5; a run with 0 nodes compared is UNMEASURED at any setting)")
    args = ap.parse_args()

    try:
        ir = json.loads(args.ir.read_text(encoding="utf-8"))
        actual = json.loads(args.actual.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    entries = flatten(ir["root"])
    compared, missing = [], []
    for entry in entries:
        node_id = entry["node"].get("id")
        if node_id not in actual:
            if design_rect(entry["node"]):
                missing.append({"node": node_id, "name": entry["node"].get("name")})
            continue
        result = compare(entry, actual, args.tolerance)
        if result:
            compared.append(result)

    flagged = [r for r in compared if r["findings"]]
    by_kind: dict[str, int] = {}
    for r in flagged:
        for f in r["findings"]:
            by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1

    # Nodes the design actually gives geometry for, tagged or not — the denominator that
    # matters for "was this screen measured", as distinct from `entries` (every IR node,
    # including containers with no rect of their own).
    eligible = len(compared) + len(missing)
    coverage_of_eligible = len(compared) / eligible if eligible else 0.0
    unmeasured = eligible > 0 and (len(compared) == 0 or coverage_of_eligible < args.min_coverage)
    verdict = "UNMEASURED" if unmeasured else ("FINDINGS" if flagged else "PASS")

    report = {
        "verdict": verdict,
        "tolerance_dp": args.tolerance,
        "min_coverage": args.min_coverage,
        "coverage_of_eligible": round(coverage_of_eligible, 3),
        "nodes_in_ir": len(entries),
        "nodes_compared": len(compared),
        "nodes_untagged": len(missing),
        "nodes_flagged": len(flagged),
        "findings_by_kind": by_kind,
        "untagged": missing[:50],
        "nodes": flagged,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    coverage = len(compared) / len(entries) if entries else 0
    print(f"compared {len(compared)}/{len(entries)} nodes ({coverage:.0%} tagged) at ±{args.tolerance}dp")
    if missing:
        print(f"  {len(missing)} nodes have design geometry but no testTag — they are unverified, not passing")

    if unmeasured:
        print(f"\nverdict: UNMEASURED — {len(compared)}/{eligible} design-geometry nodes were tagged and "
              f"compared ({coverage_of_eligible:.0%}, below --min-coverage {args.min_coverage:.0%}).")
        print("This is not a pass and not a documented failure: no composable was measured against the")
        print("design, so there is no size, offset, or gap finding to report either way. Convergence,")
        print("fidelity, or a clean run cannot be claimed from this output. Wire the tagging helper and")
        print("dump harness (assets/layout-audit/ in this skill) and re-run before claiming any other")
        print("verdict — or, if tagging genuinely cannot be added, fall back to the mandatory ink-band")
        print("audits in references/verification.md and report their numbers instead of this script's.")
        return 3

    if not flagged:
        print("\nverdict: PASS — every tagged node is within tolerance.")
        return 0

    print(f"\nverdict: FINDINGS — {len(flagged)} node(s) outside tolerance — " + ", ".join(f"{k} {n}" for k, n in sorted(by_kind.items())))
    for r in flagged[:20]:
        for f in r["findings"]:
            if f["kind"] == "size":
                detail = f"{f['axis']} {f['actual']} vs {f['design']} ({f['delta']:+})"
            elif f["kind"] == "offset":
                detail = f"{f['axis']} offset in {f['parentName']} {f['actual']} vs {f['design']} ({f['delta']:+})"
            else:
                detail = f"{f['axis']} gap after {f['afterName']} {f['actual']} vs {f['design']} ({f['delta']:+})"
            print(f"  {r['node']:10} {str(r['name'])[:22]:22} {f['kind']:6} {detail}")
    if len(flagged) > 20:
        print(f"  … {len(flagged) - 20} more in {args.out}")

    print("\nFix order: size, then offset, then gap — a wrong size moves everything after it.")
    print("A node in the wrong place shows up as a gap finding on BOTH sides of it. That is one")
    print("defect, not two: move the node, and both gaps resolve.")
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
