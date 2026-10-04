#!/usr/bin/env python3
"""Blocking gate: did the IR actually carry the design, or just its bounding boxes?

Everything the generator sees passes through the IR. That makes the IR a funnel, and until
now nothing measured its throughput. On a real run it came out with seven nodes, every
`text`, `fill` and `type` null, `assets: []` — and `unsupported: 0`, which reads as "I
refused nothing". The generated screen lost all eleven topic-card tints and every Figma
asset. Every downstream gate passed: the code was correct, well-measured, and empty.

An agent working with no skill at all reads `get_design_context` directly and sees every
hex and every asset URL. A skill that routes that source *around* the generator is worse
than no skill. This gate exists so that failure can never again be silent.

    python3 ir_coverage_check.py --ir ir/screen.ui.json \\
        --texts raw/texts.json --styles raw/styles.json --assets raw/assets.json

Exit 1 when the IR dropped more than the thresholds allow. Fix the extraction — do not
lower the threshold, and do not generate from a hollow IR.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def walk(node: dict):
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Refuse to generate from an IR that dropped the design's content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--ir", type=Path, required=True)
    ap.add_argument("--texts", type=Path, help="texts.json from context_to_ir.py")
    ap.add_argument("--styles", type=Path, help="styles.json from context_to_ir.py")
    ap.add_argument("--assets", type=Path, help="assets.json from context_to_ir.py")
    ap.add_argument("--min-text", type=float, default=0.8,
                    help="fraction of the design's strings that must reach the IR (default 0.8)")
    ap.add_argument("--min-style", type=float, default=0.8,
                    help="fraction of the design's styled nodes that must reach the IR (default 0.8)")
    ap.add_argument("--min-asset", type=float, default=0.9,
                    help="fraction of the design's assets that must be bound (default 0.9)")
    args = ap.parse_args()

    ir = json.loads(args.ir.read_text(encoding="utf-8"))
    root = ir.get("root") or {}
    nodes = list(walk(root)) if root else []
    by_id = {n.get("node") or n.get("id"): n for n in nodes}
    source_context = ir.get("sourceContext") or {}

    def load(path: Path | None):
        if path and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    texts = load(args.texts)
    styles = load(args.styles)
    assets = load(args.assets)

    failures: list[str] = []
    tree_share: dict[str, tuple[int, int]] = {}
    lines: list[str] = [f"IR {args.ir}: {len(nodes)} nodes"]

    if texts is not None:
        tree_text_ids = {
            (n.get("id") or "").rsplit(";", 1)[-1]
            for n in nodes
            if ((n.get("text") or {}).get("content") if isinstance(n.get("text"), dict) else n.get("content"))
        }
        preserved_texts = source_context.get("texts") or {}
        tree_carried = sum(1 for node_id in texts if node_id in tree_text_ids)
        context_carried = sum(
            1 for node_id in texts if node_id not in tree_text_ids and node_id in preserved_texts
        )
        carried = tree_carried + context_carried
        want = len(texts)
        tree_share["text"] = (tree_carried, want)
        ratio = carried / want if want else 1.0
        lines.append(
            f"  text    tree {tree_carried} + sourceContext {context_carried} = "
            f"{carried}/{want} strings carried ({ratio:.0%})"
        )
        if ratio < args.min_text:
            failures.append(
                f"text coverage {ratio:.0%} < {args.min_text:.0%} — the design has {want} "
                f"strings and the IR carried {carried}. A screen generated from this has no copy."
            )

    if styles is not None:
        tree_style_ids = {
            (n.get("id") or "").rsplit(";", 1)[-1]
            for n in nodes
            if n.get("fill") or n.get("color") or n.get("style")
        }
        preserved_styles = source_context.get("styles") or {}
        tree_styled = sum(1 for node_id in styles if node_id in tree_style_ids)
        context_styled = sum(
            1 for node_id in styles if node_id not in tree_style_ids and node_id in preserved_styles
        )
        styled = tree_styled + context_styled
        want = len(styles)
        tree_share["style"] = (tree_styled, want)
        ratio = styled / want if want else 1.0
        distinct_design = len({s.get("fill") for s in styles.values() if s.get("fill")})
        tree_fills = {
            ((n.get("style") or {}).get("fill") or {}).get("raw")
            for n in nodes
            if ((n.get("style") or {}).get("fill") or {}).get("raw")
        }
        preserved_fills = {
            s.get("fill") for s in preserved_styles.values() if isinstance(s, dict) and s.get("fill")
        }
        context_fills = preserved_fills - tree_fills
        distinct_ir = len(tree_fills | context_fills)
        lines.append(
            f"  style   tree {tree_styled} + sourceContext {context_styled} = "
            f"{styled}/{want} styled nodes carried ({ratio:.0%}); "
            f"fills tree {len(tree_fills)} + sourceContext {len(context_fills)} = "
            f"{distinct_ir}/{distinct_design}"
        )
        if ratio < args.min_style:
            failures.append(
                f"style coverage {ratio:.0%} < {args.min_style:.0%} — the design styles {want} "
                f"nodes and the IR carried {styled}."
            )
        if distinct_design > 1 and distinct_ir <= 1:
            failures.append(
                f"the design uses {distinct_design} distinct fills and the IR carries "
                f"{distinct_ir}. Per-variant colour was lost — every instance of a repeated "
                f"component will render identically. Check the variant ternaries in context_to_ir.py."
            )

    if assets is not None:
        want = len({a.get("url") for a in assets if a.get("url")})
        tree_assets = {a.get("export") for a in (ir.get("assets") or []) if a.get("export")}
        preserved_assets = {
            a.get("url") for a in (source_context.get("assets") or [])
            if a.get("id") and a.get("url")
        }
        context_assets = preserved_assets - tree_assets
        bound = len(tree_assets | context_assets)
        tree_share["asset"] = (len(tree_assets), want)
        ratio = bound / want if want else 1.0
        lines.append(
            f"  asset   tree {len(tree_assets)} + sourceContext {len(context_assets)} = "
            f"{bound}/{want} assets bound ({ratio:.0%})"
        )
        if ratio < args.min_asset:
            failures.append(
                f"asset coverage {ratio:.0%} < {args.min_asset:.0%} — the design exports {want} "
                f"images and the IR bound {bound}. Unbound assets get silently replaced by "
                f"stock glyphs, which is how a bespoke nav bar ships as five identical house icons."
            )

    if texts is None and styles is None and assets is None:
        print(
            "error: nothing to compare against. Pass --texts / --styles / --assets from\n"
            "       context_to_ir.py. Checking an IR against itself proves nothing.",
            file=sys.stderr,
        )
        return 2

    print("\n".join(lines))

    # A complete union with an almost-empty tree is the component-instance case, and it is
    # worth saying out loud. `get_metadata` does not expand instances, so 11 "Topic card"
    # siblings arrive as childless nodes; their per-instance colour, icon and label exist
    # only in the flat sourceContext maps, keyed by node id, with no structural link back to
    # "card 3 of 11". Coverage is honestly 100% — the content did arrive — but whoever
    # generates from this has to recover the grouping by hand from the design context, and
    # nothing used to warn them before they hit it.
    thin = [k for k, (in_tree, want) in tree_share.items() if want >= 8 and in_tree / want < 0.35]
    if thin and not failures:
        print(
            "\n  note: the tree carries little of the design — "
            + "; ".join(f"{k} {tree_share[k][0]}/{tree_share[k][1]} in tree" for k in thin)
            + ".\n        The rest arrived through sourceContext, which is flat and keyed by node"
            "\n        id, so repeated component instances have no structural grouping. Expect to"
            "\n        read raw/<node>/context.json directly to rebuild 'which instance is which'."
            "\n        See references/ui-ir-schema.md."
        )

    if failures:
        print("\nIR COVERAGE FAILED")
        for f in failures:
            print(f"  · {f}")
        print(
            "\nFix the extraction, not the threshold. An IR that dropped the design produces\n"
            "code that every other gate will certify as clean and correct."
        )
        return 1
    print("\nIR COVERAGE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
