#!/usr/bin/env python3
"""Hard gate on generated Compose layout: no fixed dimensions around text, no unbounded text,
no Row that can push its own icons off screen, no image that loses the design's ratio, no
Text with a silently inherited colour, no self-painted button stretched by a misplaced weight.

These are correctness rules, not taste. A screen that violates them matches the design at
exactly one width with exactly one string length, and breaks on a longer filename, a larger
font scale, or a wider device — all of which are normal, not edge cases. That is why this
gate exits 1 while the token and literal checks only report.

No escape hatch by design. The rules are written narrowly enough that legitimate fixed
geometry — a 24dp icon, a 1dp divider, a 3dp accent bar — passes untouched. If something
legitimate trips a rule, the rule is wrong and gets fixed; it does not get an exemption
comment, because exemption comments are how a gate quietly stops meaning anything.

Exit codes: 0 clean, 1 violations, 2 usage error.

Usage:
    python3 layout_rules_check.py --files app/src/main/java/.../HomeScreen.kt [...]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Fixed-dimension modifiers. `heightIn` / `widthIn` / `sizeIn` are deliberately absent —
# a minimum is the correct way to honour a design's dimension without freezing it.
FIXED_DIM = re.compile(r"\.(height|width|size)\s*\(")
DIM_IN = re.compile(r"\.(heightIn|widthIn|sizeIn|requiredHeightIn|requiredWidthIn)\s*\(")
TEXT_CALL = re.compile(r"\b(Text|BasicText)\s*\(")
ROW_CALL = re.compile(r"\bRow\s*\(")
IMAGE_CALL = re.compile(r"\b(Image|AsyncImage|SubcomposeAsyncImage)\s*\(")
COMPOSABLE_FUN = re.compile(r"@Composable[^\n]*\n(?:@\w+[^\n]*\n)*\s*(?:\w+\s+)*fun\s+(\w+)\s*\(")


def blank_comments(source: str) -> str:
    """Blank out comments, preserving offsets so line numbers stay true."""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    source = re.sub(r"/\*.*?\*/", blank, source, flags=re.S)
    return re.sub(r"//[^\n]*", blank, source)


def balanced(text: str, open_idx: int, pair: str = "()") -> tuple[int, int]:
    """(start, end) of the content inside the bracket opening at `open_idx`."""
    opener, closer = pair
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return open_idx + 1, i
    return open_idx + 1, len(text)


def call_span(text: str, call_start: int) -> tuple[int, int]:
    """Full extent of a composable call: its parentheses plus any trailing lambda."""
    paren = text.find("(", call_start)
    if paren < 0:
        return call_start, call_start
    _, close = balanced(text, paren)
    rest = text[close + 1 : close + 40]
    brace_offset = rest.find("{")
    if brace_offset >= 0 and rest[:brace_offset].strip() == "":
        brace = close + 1 + brace_offset
        _, brace_close = balanced(text, brace, "{}")
        return call_start, brace_close
    return call_start, close


def modifier_chain(text: str, start: int, end: int) -> str:
    """The call's own modifier expression — not its children's.

    Taken from the argument list only, so a `Modifier.size()` on a nested child does not
    look like it belongs to the parent.
    """
    paren = text.find("(", start)
    if paren < 0 or paren > end:
        return ""
    arg_start, arg_end = balanced(text, paren)
    args = text[arg_start:arg_end]
    m = re.search(r"modifier\s*=\s*", args)
    if m:
        return args[m.end() : m.end() + 400]
    # Positional `Modifier.…` as the first argument (common for Icon/Image/Spacer).
    m = re.search(r"\bModifier\s*\.", args)
    return args[m.start() : m.start() + 400] if m else ""


def line_of(text: str, idx: int) -> int:
    return text[:idx].count("\n") + 1


def is_self_painted_hug_row(chain: str) -> bool:
    """A Row's own modifier chain draws a shape (clip + background) and never claims a
    width of its own (fillMaxWidth / fillMaxSize / width). That is a button, pill, or chip —
    it is supposed to hug its content, not fill its parent. R3 and R6 both key off this: R3
    skips these (its weight(1f)-on-the-text fix is exactly what stretches them, see R6), and
    R6 is the rule that actually governs them.
    """
    return (
        ".clip(" in chain
        and ".background(" in chain
        and not re.search(r"\.(fillMaxWidth|fillMaxSize|width)\s*\(", chain)
    )


def split_top_level(args: str) -> list[str]:
    """Split a call's argument list on its own top-level commas.

    Needed to tell a call's own named arguments (`color = …`) apart from ones buried inside
    a nested call in the same list (`modifier = Modifier.background(color = …)`), which a
    plain substring search cannot distinguish.
    """
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in args:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def direct_children(text: str, body_start: int, body_end: int) -> list[tuple[str, int]]:
    """Top-level calls inside a lambda body, skipping anything nested deeper."""
    out: list[tuple[str, int]] = []
    i = body_start
    while i < body_end:
        m = re.compile(r"\b([A-Z]\w*)\s*\(").search(text, i, body_end)
        if not m:
            break
        name, start = m.group(1), m.start()
        _, end = call_span(text, start)
        out.append((name, start))
        i = max(end + 1, start + 1)
    return out


def check_file(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = blank_comments(raw)
    findings: list[dict] = []

    def add(rule: str, idx: int, what: str, fix: str) -> None:
        findings.append({"file": str(path), "line": line_of(text, idx), "rule": rule, "what": what, "fix": fix})

    # ---- R2 · every Text declares how it behaves when the string does not fit -------
    for m in TEXT_CALL.finditer(text):
        start, end = call_span(text, m.start())
        body = text[start:end]
        missing = [k for k in ("maxLines", "overflow") if k not in body]
        if missing:
            add(
                "R2",
                m.start(),
                f"{m.group(1)}( without {' and '.join(missing)}",
                "declare both — the design drew one string of one length and cannot answer "
                "what happens to a longer one",
            )

    # ---- R1 · a fixed dimension on anything containing text ------------------------
    for m in re.finditer(r"\b([A-Z]\w*)\s*\(", text):
        name, start = m.group(1), m.start()
        if name in ("Modifier",):
            continue
        _, end = call_span(text, start)
        chain = modifier_chain(text, start, end)
        if not FIXED_DIM.search(chain):
            continue
        # Does this node render text anywhere beneath it?
        if not TEXT_CALL.search(text[start:end]):
            continue
        dim = FIXED_DIM.search(chain).group(1)
        add(
            "R1",
            start,
            f"{name}( fixes .{dim}() and contains text",
            f"use {dim}In(min = …) — text grows with font scale and with longer locales, so a "
            "fixed dimension clips it",
        )

    # ---- R3 · a Row whose text can push its siblings out ---------------------------
    for m in ROW_CALL.finditer(text):
        start, end = call_span(text, m.start())
        brace = text.find("{", text.find("(", start))
        if brace < 0 or brace > end:
            continue
        if is_self_painted_hug_row(modifier_chain(text, start, end)):
            # A button/pill/chip: R6 owns this shape, and R6's fix (no weight on the label)
            # is the opposite of what R3 would suggest here. See is_self_painted_hug_row.
            continue
        body_start, body_end = balanced(text, brace, "{}")
        body = text[body_start:body_end]
        children = direct_children(text, body_start, body_end)
        has_text = any(n in ("Text", "BasicText") for n, _ in children)
        if not has_text or len(children) < 2:
            continue
        if "weight(" in body:
            continue
        add(
            "R3",
            m.start(),
            f"Row with {len(children)} children including text, none takes weight()",
            "give the text weight(1f) — without it a long string pushes the trailing icon "
            "off screen instead of shrinking",
        )

    # ---- R4 · an image stretched into a box whose ratio nobody declared -------------
    for m in IMAGE_CALL.finditer(text):
        start, end = call_span(text, m.start())
        body = text[start:end]
        chain = modifier_chain(text, start, end)
        if "aspectRatio" in chain or "ContentScale" in body:
            continue
        # `.size(x)` pins a square box and Compose's default Fit keeps the artwork's ratio
        # inside it — that is how icon drawables are drawn, and it is correct. The risk is
        # an image poured into a box of a different shape with no instruction.
        if re.search(r"\.size\s*\(", chain):
            continue
        if not re.search(r"\.(fillMax(Width|Size|Height)|height|width|weight)\s*\(", chain):
            continue
        add(
            "R4",
            m.start(),
            f"{m.group(1)}( fills a non-square box with no aspectRatio or ContentScale",
            "the design gives this node a width and a height — carry the ratio with "
            "Modifier.aspectRatio(w / h), and say which ContentScale (Crop fills and trims, "
            "Fit letterboxes). Without one the artwork stretches",
        )

    # ---- R5 · every Text declares its own colour, never inherits one silently --------
    for m in TEXT_CALL.finditer(text):
        start, end = call_span(text, m.start())
        paren = text.find("(", start)
        arg_start, arg_end = balanced(text, paren)
        args = text[arg_start:arg_end]

        has_own_color = False
        has_provable_style_color = False
        for part in split_top_level(args):
            stripped = part.strip()
            if re.match(r"color\s*=", stripped):
                has_own_color = True
                break
            style_lit = re.match(r"style\s*=\s*TextStyle\s*\(", stripped)
            if style_lit and re.search(r"\bcolor\s*=", stripped[style_lit.end() - 1 :]):
                has_provable_style_color = True

        if has_own_color or has_provable_style_color:
            continue
        add(
            "R5",
            m.start(),
            f"{m.group(1)}( with no color argument and no inline TextStyle(color = …)",
            "pass color = explicitly, resolved from the design's hex — a style = token "
            "(LocalAppTypography.current.*, or any other TextStyle val) cannot be proven from "
            "this file alone to carry a colour, so this check treats it as if it does not. "
            "Without an explicit color, the text falls back to whatever LocalContentColor the "
            "surrounding theme happens to provide — that is how a #141414 title renders pale "
            "grey on a pink background, and how a card's own label renders white-on-white",
        )

    # ---- R6 · weight() on a label inside a Row that paints its own shape -------------
    for m in ROW_CALL.finditer(text):
        start, _ = call_span(text, m.start())
        paren = text.find("(", start)
        _, close = balanced(text, paren)
        chain = modifier_chain(text, start, close)
        if not is_self_painted_hug_row(chain):
            continue

        rest = text[close + 1 : close + 40]
        brace_offset = rest.find("{")
        if brace_offset < 0 or rest[:brace_offset].strip() != "":
            continue  # no trailing content lambda to inspect
        brace = close + 1 + brace_offset
        body_start, body_end = balanced(text, brace, "{}")

        for name, cstart in direct_children(text, body_start, body_end):
            if name not in ("Text", "BasicText"):
                continue
            _, cend = call_span(text, cstart)
            child_chain = modifier_chain(text, cstart, cend)
            if "weight(" not in child_chain:
                continue
            add(
                "R6",
                cstart,
                f"{name}( takes weight() inside a Row that clips and paints its own background",
                "drop weight() from the label — a Row that clips itself and paints a background "
                "is drawn as a button/pill/chip, and a button hugs its label, it does not stretch "
                "to fill its parent. weight() forces the Row to claim its parent's full width "
                "regardless of what the Row's own modifiers say, which is how a ~160dp pill "
                "becomes a full-width bar. If the design genuinely wants this row edge-to-edge, "
                "say so on the Row itself with fillMaxWidth() — weight() on the label is not "
                "how you spell that",
            )

    return findings


RULE_TITLES = {
    "R1": "fixed dimension around text",
    "R2": "text with no overflow contract",
    "R3": "row that can push its own children off screen",
    "R4": "image that loses the design's ratio",
    "R5": "text with no declared colour",
    "R6": "weight() on a label inside a self-painted row",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--files", required=True, nargs="+", type=Path)
    ap.add_argument("--warn-only", action="store_true", help="report without failing (migrating an existing screen)")
    args = ap.parse_args()

    all_findings: list[dict] = []
    for path in args.files:
        if not path.exists():
            print(f"error: {path} does not exist", file=sys.stderr)
            return 2
        all_findings.extend(check_file(path))

    if not all_findings:
        print(f"LAYOUT CONTRACT PASSED — {len(args.files)} file(s) clean")
        return 0

    by_rule: dict[str, list[dict]] = {}
    for f in all_findings:
        by_rule.setdefault(f["rule"], []).append(f)

    for rule in sorted(by_rule):
        items = by_rule[rule]
        print(f"\n{rule} · {RULE_TITLES[rule]} — {len(items)} violation(s)")
        print(f"   fix: {items[0]['fix']}")
        for f in items[:12]:
            print(f"   {Path(f['file']).name}:{f['line']}  {f['what']}")
        if len(items) > 12:
            print(f"   … {len(items) - 12} more")

    total = len(all_findings)
    if args.warn_only:
        print(f"\n{total} violation(s) — --warn-only, not failing. See references/layout-contract.md")
        return 0
    print(f"\nLAYOUT CONTRACT FAILED — {total} violation(s). See references/layout-contract.md")
    print("These are correctness rules: the screen matches the design at one width with one")
    print("string length and breaks outside that. Fix them rather than widening the rule.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
