#!/usr/bin/env python3
"""Turn a `get_design_context` response into the inputs `figma_to_ir.py` needs.

`get_design_context` already carries every string, every hex, every corner radius and
every asset URL in the frame.  Earlier versions of this skill asked the agent to "derive
`texts.json` and `styles.json` from the design context" by hand.  On the first run where
the brief did not spell that step out, nobody did it, `figma_to_ir.py` accepted the missing
flags silently, and the IR came out as seven empty boxes — no text, no fill, no assets —
while reporting `unsupported: 0`.  The generated screen lost all eleven topic-card tints
and every Figma asset, because the pipeline had routed the rich source *around* the
generator.

A step a human has to remember is a step that gets skipped.  This script removes it.

    python3 context_to_ir.py --context raw/context.tsx \\
        --texts raw/texts.json --styles raw/styles.json --assets raw/assets.json

Variants are the part worth being careful about.  A component set comes back as nested
ternaries keyed on the same condition names in the same order:

    id={isSpicy ? "node-5_7804" : isRelationship ? "node-5_7764" : "node-5_7744"}
    className={`... ${isSpicy ? "bg-[#ffe9ea]" : isRelationship ? "bg-[#ecfdf5]" : "bg-[#fbeff5]"}`}

Joining the two chains on the condition name is what recovers "this instance is pink, that
one is red" — the exact information whose loss made a redesign render as eleven identical
white cards.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HEX = r"#[0-9a-fA-F]{3,8}"

# bg-[#fbeff5] · bg-[var(--pink\/pink-500,#fd75a7)] · text-[color:var(--text\/base-primary,#141414)]
CLASS_COLOR = re.compile(
    r"\b(bg|text|border|from|to)-\[(?:color:)?(?:var\([^,)]*,\s*)?(" + HEX + r")\)?\]"
)
CLASS_RADIUS = re.compile(r"\brounded-(?:t[lr]-)?\[(\d+(?:\.\d+)?)px\]")
CLASS_SIZE = re.compile(r"\btext-\[(\d+(?:\.\d+)?)px\]")
CLASS_DIM = re.compile(r"\b(?:size|w|h)-\[(\d+(?:\.\d+)?)px\]")
CLASS_WEIGHT = re.compile(r"\bfont-(normal|medium|semibold|bold|black)\b")
WEIGHTS = {"normal": 400, "medium": 500, "semibold": 600, "bold": 700, "black": 900}

ASSET_CONST = re.compile(
    r'const\s+(\w+)\s*=\s*"(https://www\.figma\.com/api/mcp/asset/[^"]+)"'
)
DATA_NODE_ID = re.compile(r'data-node-id="([0-9I:;\-]+)"')
NODE_TOKEN = re.compile(r'"node-([0-9I]+)_([0-9]+)"')
SRC_REF = re.compile(r"src=\{(\w+)\}")
TERNARY_ARM = re.compile(r"(\w+)\s*\?\s*(?:String\.raw)?[`\"]([^`\"]*)[`\"]")


def norm_node(raw: str) -> str:
    """`5_7744` / `5:7744` / `I5:8532;3:412` all become the canonical colon form."""
    return raw.replace("_", ":")


def strip_escapes(text: str) -> str:
    """Tailwind arbitrary values escape `/` in CSS var names: `--pink\\/pink-500`."""
    return text.replace("\\/", "/")


def ternary_chain(expr: str) -> tuple[list[tuple[str, str]], str | None]:
    """Split `a ? "x" : b ? "y" : "z"` into ([("a","x"),("b","y")], "z").

    The trailing arm may be followed by a closing brace or whitespace, because the chain is
    read out of `id={…}` and out of a `${…}` slot inside a template literal.
    """
    arms = [(m.group(1), m.group(2)) for m in TERNARY_ARM.finditer(expr)]
    tail = re.search(r':\s*(?:String\.raw)?[`"]([^`"]*)[`"]\s*\}?\s*$', expr.strip())
    return arms, tail.group(1) if tail else None


def balanced(src: str, open_idx: int, opener: str = "{", closer: str = "}") -> str:
    """Return the text between `src[open_idx]` and its matching closer, quotes respected."""
    depth, quote, i = 0, None, open_idx
    while i < len(src):
        c = src[i]
        if quote:
            if c == quote and src[i - 1] != "\\":
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return src[open_idx + 1 : i]
        i += 1
    return src[open_idx + 1 :]


def attr_expr(attrs: str, name: str) -> str | None:
    """Read one JSX attribute's value, whether it is `name="..."` or `name={...}`."""
    m = re.search(rf'\b{name}=(\{{|")', attrs)
    if not m:
        return None
    if m.group(1) == '"':
        end = attrs.find('"', m.end())
        return attrs[m.end() : end] if end != -1 else None
    return balanced(attrs, m.end() - 1)


def template_slots(expr: str) -> list[str]:
    """Every `${…}` interpolation inside a template literal, brace-balanced."""
    slots, i = [], 0
    while (i := expr.find("${", i)) != -1:
        slots.append(balanced(expr, i + 1))
        i += 2
    return slots


def scan_tags(src: str):
    """Yield (tag_name, attr_text, body) for every JSX element opening.

    Walks the source tracking quote and brace state, because className values are template
    literals full of `>` `?` `:` and nested braces that a regex splits in the wrong place.
    """
    i, n = 0, len(src)
    while i < n:
        if src[i] != "<" or i + 1 >= n or not (src[i + 1].isalpha()):
            i += 1
            continue
        start = i
        i += 1
        while i < n and (src[i].isalnum() or src[i] in "-_"):
            i += 1
        tag = src[start + 1 : i]
        depth, quote, j = 0, None, i
        while j < n:
            c = src[j]
            if quote:
                if c == quote and src[j - 1] != "\\":
                    quote = None
            elif c in "\"'`":
                quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == ">" and depth == 0:
                break
            j += 1
        attrs = src[i:j]
        body = ""
        if not attrs.rstrip().endswith("/"):
            close = src.find(f"</{tag}>", j)
            if close != -1:
                body = src[j + 1 : close]
        yield tag, attrs, body
        i = j + 1


def extract_text(body: str) -> str | None:
    """Pull the literal string out of an element body, or None if it is not a plain string."""
    body = body.strip()
    if not body or "<" in body:
        return None
    m = re.fullmatch(r"\{\s*`([^`]*)`\s*\}", body)
    if m:
        return m.group(1)
    if body.startswith("{"):
        return None  # a conditional — handled per-variant by the caller
    return re.sub(r"\s+", " ", body).strip() or None


def parse_styles(class_text: str) -> dict:
    """Read the non-conditional part of a className into a style dict."""
    out: dict = {}
    text = strip_escapes(class_text)
    for kind, hexval in CLASS_COLOR.findall(text):
        key = {"bg": "fill", "text": "color", "border": "border"}.get(kind)
        if key and key not in out:
            out[key] = hexval.upper()
    if m := CLASS_RADIUS.search(text):
        out["radius"] = float(m.group(1))
    if m := CLASS_SIZE.search(text):
        out["size"] = float(m.group(1))
    if m := CLASS_WEIGHT.search(text):
        out["weight"] = WEIGHTS[m.group(1)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="get_design_context → texts.json + styles.json + assets.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--context", type=Path, required=True,
                    help="the verbatim get_design_context response, saved to a file")
    ap.add_argument("--texts", type=Path, required=True)
    ap.add_argument("--styles", type=Path, required=True)
    ap.add_argument("--assets", type=Path, required=True)
    ap.add_argument("--min-texts", type=int, default=1,
                    help="refuse if fewer strings than this were recovered (default 1)")
    args = ap.parse_args()

    if not args.context.exists():
        print(f"error: {args.context} does not exist", file=sys.stderr)
        return 2
    src = args.context.read_text(encoding="utf-8")

    consts = {name: url for name, url in ASSET_CONST.findall(src)}
    last_owner: str | None = None
    texts: dict[str, str] = {}
    styles: dict[str, dict] = {}
    assets: list[dict] = []

    for tag, attrs, body in scan_tags(src):
        ids = [norm_node(x) for x in DATA_NODE_ID.findall(attrs)]
        variant_ids: list[tuple[str, str]] = []  # (condition, nodeId)

        if id_expr := attr_expr(attrs, "id"):
            arms, default = ternary_chain(id_expr)
            for cond, val in arms:
                if m := re.fullmatch(r"node-([0-9I]+)_([0-9]+)", val):
                    variant_ids.append((cond, norm_node(f"{m.group(1)}_{m.group(2)}")))
            if default and (m := re.fullmatch(r"node-([0-9I]+)_([0-9]+)", default)):
                variant_ids.append(("__default__", norm_node(f"{m.group(1)}_{m.group(2)}")))
        for a, b in NODE_TOKEN.findall(attrs):
            nid = norm_node(f"{a}_{b}")
            if nid not in ids and all(nid != v for _, v in variant_ids):
                ids.append(nid)

        class_text = attr_expr(attrs, "className") or ""
        slots = template_slots(class_text)
        literal = class_text
        for slot in slots:
            literal = literal.replace("${" + slot + "}", " ")
        base_style = parse_styles(literal)

        # Per-variant colours: join the className ternary onto the id ternary by condition.
        variant_styles: dict[str, dict] = {}
        for chunk in slots:
            arms, default = ternary_chain(chunk)
            for cond, val in arms:
                variant_styles.setdefault(cond, {}).update(parse_styles(val))
            if default:
                variant_styles.setdefault("__default__", {}).update(parse_styles(default))

        for cond, nid in variant_ids:
            merged = dict(base_style)
            merged.update(variant_styles.get(cond, {}))
            if merged:
                styles.setdefault(nid, {}).update(merged)
        for nid in ids:
            if base_style:
                styles.setdefault(nid, {}).update(base_style)

        if content := extract_text(body):
            for nid in ids:
                texts.setdefault(nid, content)
        elif body.strip().startswith("{") and variant_ids:
            arms, default = ternary_chain(body.strip())
            per_cond = dict(arms)
            if default:
                per_cond["__default__"] = default
            for cond, nid in variant_ids:
                if cond in per_cond:
                    texts.setdefault(nid, per_cond[cond])

        owner = ids[0] if ids else (variant_ids[0][1] if variant_ids else None)
        if owner:
            last_owner = owner

        if src_m := SRC_REF.search(attrs):
            url = consts.get(src_m.group(1))
            if url:
                # An <img> carries no node id of its own; it belongs to the element that
                # wraps it. Without this attribution an asset cannot be checked against the
                # node that is supposed to render it.
                assets.append({
                    "id": owner or last_owner,
                    "const": src_m.group(1),
                    "url": url,
                    "ext": "svg" if url.endswith(".svg") else "png",
                })

    if len(texts) < args.min_texts:
        print(
            f"error: recovered {len(texts)} strings from {args.context} — expected at least "
            f"{args.min_texts}.\n"
            "       Either the file is not a get_design_context response, or it was saved\n"
            "       truncated. Do not continue: an IR with no text produces a screen with no\n"
            "       copy, and nothing downstream will tell you.",
            file=sys.stderr,
        )
        return 1

    args.texts.parent.mkdir(parents=True, exist_ok=True)
    args.texts.write_text(json.dumps(texts, ensure_ascii=False, indent=2), encoding="utf-8")
    args.styles.write_text(json.dumps(styles, ensure_ascii=False, indent=2), encoding="utf-8")
    args.assets.write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")

    distinct_fills = len({s["fill"] for s in styles.values() if "fill" in s})
    print(f"wrote {args.texts}  {len(texts)} strings")
    print(f"wrote {args.styles}  {len(styles)} styled nodes, {distinct_fills} distinct fills")
    print(f"wrote {args.assets}  {len(assets)} asset references, {len(consts)} constants")
    if distinct_fills <= 1 and len(styles) > 4:
        print("  note: every styled node shares one fill — check the variant ternaries parsed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
