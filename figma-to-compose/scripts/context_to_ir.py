#!/usr/bin/env python3
"""Parse a `get_design_context` response into a node tree — layout, style and text intact.

`get_design_context` returns React + Tailwind, and that code *is* the design's structure:
`flex flex-col gap-[16px] px-[20px] items-center` is Figma auto-layout written down
exactly, `font-['Inter:Semi_Bold'] leading-[24px] tracking-[-0.36px]` is the text style,
`shadow-[0px_4px_12px_0px_rgba(…)]` is the effect. This script reads all of it into a
tree keyed by Figma node id, so nothing downstream has to re-derive layout from x/y or
guess a style the design already stated.

    python3 context_to_ir.py --context raw/context.json --tree raw/context-tree.json \\
        --texts raw/texts.json --styles raw/styles.json --assets raw/assets.json

`--context` takes the MCP response verbatim — either the JSON envelope
(`{"content": ["<code>", …]}`) or the bare code saved to a .tsx/.jsx file.

What the tree recovers that a flat regex pass loses:

* **Structure.** Elements nest; an `<img>` belongs to the nearest ancestor with a node id;
  an id-less `<p>`/`<span>` inside a text node is part of that node's string.
* **Inherited text style.** CSS inherits `font-*`, `text-*`, `leading-*` from ancestors —
  Figma's code often puts the font on a wrapper `<div>` and the string in a `<p>` below.
* **Mixed-style text.** `<p leading-[0]><span>Size: </span><span text-[#00dc82]>3.6 MB</span></p>`
  becomes one text node with two `runs`, instead of a node with no text at all.
* **Component instances.** A helper `function Card({variant = "A"})` used as
  `<Card variant="B" />` is expanded with its props, and the `isB ? … : …` ternaries in its
  ids, classes and text resolve to the instance's own arm. Ternaries that cannot be resolved
  fall back to the default arm and are listed under the node's `variants`.

The flat `--texts/--styles/--assets` maps are still written, for `figma_to_ir.py` without
`--tree` and for `ir_coverage_check.py`.
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ============================================================== input


def load_source(path: Path) -> str:
    """The code part of a get_design_context response, whatever it was saved as."""
    raw = path.read_text(encoding="utf-8")
    if raw.lstrip()[:1] not in ("{", "["):
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    parts: list[str] = []

    def collect(value) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for key in ("content", "text", "code"):
                if key in value:
                    collect(value[key])

    collect(data)
    code = [p for p in parts if "data-node-id" in p or "className" in p]
    return "\n".join(code or parts)


# ============================================================== JSX parsing


@dataclass
class Expr:
    code: str


@dataclass
class El:
    tag: str
    attrs: dict[str, tuple[str, str]]  # name -> ("str" | "expr" | "bool", value)
    children: list = field(default_factory=list)  # El | Expr | str


def match_brace(src: str, open_idx: int) -> int:
    """Index of the brace closing `src[open_idx]`, skipping quoted and template text."""
    depth, quote, i = 0, None, open_idx
    while i < len(src):
        c = src[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(src) - 1


def parse_attrs(text: str) -> dict[str, tuple[str, str]]:
    attrs: dict[str, tuple[str, str]] = {}
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        if text[i] == "{":  # {...spread}
            i = match_brace(text, i) + 1
            continue
        m = re.match(r"[\w:.-]+", text[i:])
        if not m:
            i += 1
            continue
        name = m.group(0)
        i += len(name)
        if i < n and text[i] == "=":
            i += 1
            if i < n and text[i] in "\"'":
                q = text[i]
                end = text.find(q, i + 1)
                end = n if end == -1 else end
                attrs[name] = ("str", text[i + 1 : end])
                i = end + 1
            elif i < n and text[i] == "{":
                end = match_brace(text, i)
                attrs[name] = ("expr", text[i + 1 : end].strip())
                i = end + 1
        else:
            attrs[name] = ("bool", "true")
    return attrs


def parse_element(src: str, i: int) -> tuple[El, int]:
    """Parse the element starting at `src[i] == '<'`; return it and the index after it."""
    n = len(src)
    j = i + 1
    while j < n and (src[j].isalnum() or src[j] in "._-:"):
        j += 1
    tag = src[i + 1 : j]
    depth, quote, k = 0, None, j
    while k < n:
        c = src[k]
        if quote:
            if c == "\\":
                k += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`" and (depth > 0 or c != "`"):
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ">" and depth == 0:
            break
        k += 1
    attr_text = src[j:k]
    self_closing = attr_text.rstrip().endswith("/")
    if self_closing:
        attr_text = attr_text.rstrip()[:-1]
    el = El(tag, parse_attrs(attr_text))
    i = k + 1
    if self_closing:
        return el, i
    while i < n:
        if src.startswith("</", i):
            end = src.find(">", i)
            return el, (n if end == -1 else end + 1)
        c = src[i]
        if c == "<" and i + 1 < n and (src[i + 1].isalpha() or src[i + 1] == ">"):
            child, i = parse_element(src, i)
            el.children.append(child)
        elif c == "{":
            end = match_brace(src, i)
            code = src[i + 1 : end].strip()
            if code and not code.startswith("/*"):
                el.children.append(Expr(code))
            i = end + 1
        else:
            stops = [p for p in (src.find("<", i + 1), src.find("{", i + 1)) if p != -1]
            nxt = min(stops) if stops else n
            el.children.append(src[i:nxt])
            i = nxt
    return el, i


def jsx_text(raw: str) -> str:
    """JSX whitespace rules: lines are trimmed, blank lines dropped, the rest joined by a space."""
    if "\n" not in raw:
        return html.unescape(raw)
    lines = raw.replace("\t", " ").split("\n")
    out = []
    for idx, line in enumerate(lines):
        if idx:
            line = line.lstrip()
        if idx < len(lines) - 1:
            line = line.rstrip()
        if line:
            out.append(line)
    return html.unescape(" ".join(out))


# ============================================================== expressions


class Unresolved(Exception):
    pass


def literal(code: str) -> str | None:
    """The value of a string literal or a template literal without interpolation."""
    code = code.strip()
    m = re.fullmatch(r'"((?:[^"\\]|\\.)*)"', code, re.S)
    if m:
        try:
            return json.loads(code)
        except json.JSONDecodeError:
            return m.group(1)
    m = re.fullmatch(r"'((?:[^'\\]|\\.)*)'", code, re.S)
    if m:
        body = m.group(1).replace("\\'", "'").replace('"', '\\"')
        try:
            return json.loads('"' + body + '"')
        except json.JSONDecodeError:
            return m.group(1)
    m = re.fullmatch(r"(?:String\.raw)?`((?:[^`\\]|\\.)*)`", code, re.S)
    if m and "${" not in m.group(1):
        return m.group(1).replace("\\`", "`").replace("\\n", "\n")
    return None


def split_ternary(code: str) -> tuple[str, str, str] | None:
    """Split `cond ? a : b` at the top level, nested ternaries left in `b`."""
    depth, quote, q_at, nest = 0, None, -1, 0
    i = 0
    while i < len(code):
        c = code[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and c == "?" and code[i + 1 : i + 2] not in ("?", "."):
            if q_at < 0:
                q_at = i
            nest += 1
        elif depth == 0 and c == ":" and q_at >= 0:
            nest -= 1
            if nest == 0:
                return code[:q_at].strip(), code[q_at + 1 : i].strip(), code[i + 1 :].strip()
        i += 1
    return None


def split_top_level(code: str, op: str) -> tuple[str, str] | None:
    """Split `a || b` at the first top-level occurrence of `op`, quotes and brackets respected."""
    depth, quote, i = 0, None, 0
    while i < len(code):
        c = code[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and code.startswith(op, i):
            return code[:i].strip(), code[i + len(op):].strip()
        i += 1
    return None


_ALLOWED = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.Compare,
            ast.Eq, ast.NotEq, ast.Name, ast.Load, ast.Constant)


def eval_condition(code: str, env: dict) -> bool:
    py = (code.replace("===", "==").replace("!==", "!=").replace("&&", " and ")
          .replace("||", " or "))
    py = re.sub(r"!(?!=)", " not ", py)
    py = py.replace("true", "True").replace("false", "False")
    try:
        tree = ast.parse(py.strip(), mode="eval")
    except SyntaxError as exc:
        raise Unresolved(code) from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise Unresolved(code)
        if isinstance(node, ast.Name) and node.id not in env and node.id not in ("True", "False"):
            raise Unresolved(code)
    return bool(eval(compile(tree, "<cond>", "eval"), {"__builtins__": {}}, dict(env)))  # noqa: S307


def eval_value(code: str, env: dict, notes: list[str]) -> str | None:
    """Evaluate a JSX attribute/child expression to a string. Unknown conditions take the
    default (last) arm and are recorded in `notes`."""
    code = code.strip()
    if not code:
        return None
    lit = literal(code)
    if lit is not None:
        return lit
    if code.startswith("(") and code.endswith(")"):
        return eval_value(code[1:-1], env, notes)
    if (alt := split_top_level(code, "||")):
        left = eval_value(alt[0], env, notes)
        return left if left else eval_value(alt[1], env, notes)
    parts = split_ternary(code)
    if parts:
        cond, yes, no = parts
        try:
            return eval_value(yes if eval_condition(cond, env) else no, env, notes)
        except Unresolved:
            notes.append(cond)
            return eval_value(no, env, notes)
    m = re.fullmatch(r"(?:String\.raw)?`(.*)`", code, re.S)
    if m:
        out, body, i = [], m.group(1), 0
        while (j := body.find("${", i)) != -1:
            out.append(body[i:j])
            end = match_brace(body, j + 1)
            out.append(eval_value(body[j + 2 : end], env, notes) or "")
            i = end + 1
        out.append(body[i:])
        return "".join(out)
    if re.fullmatch(r"[A-Za-z_]\w*", code):
        value = env.get(code)
        return value if isinstance(value, str) else None
    return None


# ============================================================== components


@dataclass
class Component:
    name: str
    defaults: dict
    consts: list[tuple[str, str]]
    root: El | None


FUNC = re.compile(r"(export\s+default\s+)?function\s+([A-Z]\w*)\s*\(")


def parse_components(src: str) -> tuple[dict[str, Component], str | None, dict[str, str]]:
    comps: dict[str, Component] = {}
    default_name = None
    for m in FUNC.finditer(src):
        name = m.group(2)
        paren_end = src.find(")", m.end())
        params = src[m.end() : paren_end]
        body_open = src.find("{", paren_end)
        if body_open == -1:
            continue
        # skip a return-type annotation like `: JSX.Element`
        body_end = match_brace(src, body_open)
        body = src[body_open + 1 : body_end]
        defaults: dict = {}
        if pm := re.search(r"\{(.*)\}", params, re.S):
            for part in pm.group(1).split(","):
                if "=" in part:
                    key, _, val = part.partition("=")
                    lit = literal(val.strip())
                    if lit is not None:
                        defaults[key.strip()] = lit
                    elif val.strip() in ("true", "false"):
                        defaults[key.strip()] = val.strip() == "true"
        consts = re.findall(r"const\s+(\w+)\s*=\s*([^;\n]+);", body)
        root = None
        if rm := re.search(r"return\s*\(?\s*<", body):
            start = body_open + 1 + rm.end() - 1
            root, _ = parse_element(src, start)
        comps[name] = Component(name, defaults, consts, root)
        if m.group(1):
            default_name = name
    assets = dict(re.findall(r'const\s+(\w+)\s*=\s*"(https://[^"]+)"', src))
    return comps, default_name, assets


# ============================================================== Tailwind → properties

NAMED_COLORS = {"white": ("#FFFFFF", 1.0), "black": ("#000000", 1.0), "transparent": ("#000000", 0.0)}
STYLE_WEIGHT = {
    "thin": 100, "hairline": 100, "extralight": 200, "ultralight": 200, "light": 300,
    "regular": 400, "normal": 400, "book": 400, "roman": 400, "medium": 500,
    "semibold": 600, "demibold": 600, "bold": 700, "extrabold": 800, "ultrabold": 800,
    "heavy": 900, "black": 900,
}
WEIGHT_CLASS = {"thin": 100, "extralight": 200, "light": 300, "normal": 400, "medium": 500,
                "semibold": 600, "bold": 700, "extrabold": 800, "black": 900}
GRADIENT_DIR = {"t": 0, "tr": 45, "r": 90, "br": 135, "b": 180, "bl": 225, "l": 270, "tl": 315}
NOISE = {
    "relative", "block", "content-stretch", "pointer-events-none", "max-w-none", "min-w-px",
    "min-h-px", "not-italic", "border-solid", "inline-block", "inline", "contents",
    "content-start", "box-border", "cursor-pointer", "mb-0", "min-w-full", "min-h-full",
}
TEXT_KEYS = ("family", "fontStyle", "weight", "italic", "size", "color", "lineHeight",
             "letterSpacing", "align", "textCase", "decoration", "singleLine", "ellipsis",
             "maxLines", "preserveWhitespace")


def num(value: str) -> float | None:
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)(px)?", value.strip())
    if not m:
        return None
    f = float(m.group(1))
    return int(f) if f.is_integer() else f


def hex_alpha(h: str) -> tuple[str, float]:
    h = h.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(ch * 2 for ch in h)
    alpha = 1.0
    if len(h) == 8:  # CSS order: RRGGBBAA
        alpha = round(int(h[6:], 16) / 255, 3)
        h = h[:6]
    return "#" + h.upper(), alpha


def parse_color(value: str) -> tuple[str, float] | None:
    v = value.replace("\\/", "/").replace("_", " ").strip()
    if v.startswith("color:"):
        v = v[6:]
    if v.startswith("var("):
        m = re.search(r",\s*(.+)\)\s*$", v)
        if not m:
            return None
        v = m.group(1).strip()
    if v in NAMED_COLORS:
        return NAMED_COLORS[v]
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", v):
        return hex_alpha(v)
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)", v)
    if m:
        r, g, b = (round(float(x)) for x in m.groups()[:3])
        a = m.group(4)
        alpha = 1.0 if a is None else (float(a[:-1]) / 100 if a.endswith("%") else float(a))
        return f"#{r:02X}{g:02X}{b:02X}", round(alpha, 3)
    return None


def color_entry(c: tuple[str, float]) -> dict:
    out = {"hex": c[0]}
    if c[1] < 1:
        out["alpha"] = c[1]
    return out


def split_top(value: str, sep: str = ",") -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def parse_shadows(value: str) -> list[dict]:
    out = []
    for part in split_top(value.replace("_", " ")):
        inset = part.startswith("inset ")
        part = part.removeprefix("inset ").strip()
        cm = re.search(r"(rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}|var\([^)]*\))", part)
        color = parse_color(cm.group(1)) if cm else ("#000000", 1.0)
        lengths = [num(x) for x in (part.replace(cm.group(1), "") if cm else part).split()]
        lengths = [x for x in lengths if x is not None] + [0, 0, 0, 0]
        shadow = {"x": lengths[0], "y": lengths[1], "blur": lengths[2], "spread": lengths[3],
                  **color_entry(color or ("#000000", 1.0))}
        if inset:
            shadow["inset"] = True
        out.append(shadow)
    return out


def parse_gradient(value: str) -> dict | None:
    v = value.replace("_", " ").strip()
    m = re.match(r"(linear|radial|conic)-gradient\((.*)\)\s*$", v)
    if not m:
        return None
    args = split_top(m.group(2))
    grad: dict = {"type": m.group(1), "stops": []}
    if args and (am := re.fullmatch(r"(-?[\d.]+)deg", args[0])):
        grad["angle"] = round(float(am.group(1)), 2)
        args = args[1:]
    elif args and args[0].startswith("to "):
        key = "".join(w[0] for w in args[0][3:].split())
        grad["angle"] = GRADIENT_DIR.get(key, 180)
        args = args[1:]
    elif m.group(1) == "linear":
        grad["angle"] = 180
    for arg in args:
        cm = re.match(r"(rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}|var\([^)]*\)|\w+)\s*([\d.]+%)?", arg)
        if cm and (color := parse_color(cm.group(1))):
            stop = color_entry(color)
            if cm.group(2):
                stop["position"] = round(float(cm.group(2)[:-1]) / 100, 4)
            grad["stops"].append(stop)
    return grad if grad["stops"] else None


def parse_font(value: str) -> dict:
    v = value.replace("\\/", "/")
    q = re.search(r"'([^']+)'|\"([^\"]+)\"", v)
    name = (q.group(1) or q.group(2)) if q else v.split(",")[0]
    family, _, style = name.partition(":")
    style = style.replace("_", " ").strip()
    out = {"family": family.replace("_", " ").strip()}
    if style:
        out["fontStyle"] = style
        key = style.lower().replace(" ", "").replace("italic", "") or "regular"
        if key in STYLE_WEIGHT:
            out["weight"] = STYLE_WEIGHT[key]
        if "italic" in style.lower():
            out["italic"] = True
    return out


def parse_classes(classes: str, inline_style: dict[str, str]) -> dict:
    """One element's className + style={{…}} → {"layout", "style", "text", "unparsed"}."""
    layout: dict = {}
    style: dict = {}
    text: dict = {}
    unparsed: list[str] = []
    pad: dict = {}
    pos: dict = {}
    corners: dict = {}
    grad_stops: dict = {}
    border: dict = {}

    for tok in classes.split():
        neg = tok.startswith("-")
        t = tok[1:] if neg else tok
        m = re.fullmatch(r"([a-z][a-z0-9-]*?)-\[(.+)\]", t)
        prefix, val = (m.group(1), m.group(2)) if m else (None, None)

        # ---- arbitrary property: [word-break:break-word], [text-shadow:…]
        if t.startswith("[") and t.endswith("]"):
            prop, _, pval = t[1:-1].partition(":")
            if prop == "text-shadow":
                text["shadows"] = parse_shadows(pval)
            elif prop not in ("word-break", "grid-area"):
                unparsed.append(tok)
            continue

        # ---- layout
        if t in ("flex", "inline-flex"):
            layout.setdefault("direction", "row")
        elif t == "flex-col":
            layout["direction"] = "column"
        elif t == "flex-row":
            layout["direction"] = "row"
        elif t == "grid":
            layout["direction"] = "grid"
        elif t == "flex-wrap":
            layout["wrap"] = True
        elif prefix == "grid-cols" and (gm := re.match(r"repeat\((\d+)", val)):
            layout["columns"] = int(gm.group(1))
        elif prefix == "grid-rows" and (gm := re.match(r"repeat\((\d+)", val)):
            layout["rows"] = int(gm.group(1))
        elif (gm := re.fullmatch(r"(col|row)-(\d+)", t)):
            layout.setdefault("cell", {})[gm.group(1)] = int(gm.group(2))
        elif prefix in ("gap", "gap-x", "gap-y") and num(val) is not None:
            layout[{"gap": "gap", "gap-x": "gapX", "gap-y": "gapY"}[prefix]] = num(val)
        elif t in ("gap-0", "p-0"):
            pass
        elif prefix in ("p", "px", "py", "pt", "pr", "pb", "pl") or t in ("px-px", "py-px", "p-px"):
            v = 1 if val is None else num(val)
            if v is None:
                unparsed.append(tok)
                continue
            key = prefix or t.split("-")[0]
            sides = {"p": ("top", "end", "bottom", "start"), "px": ("start", "end"),
                     "py": ("top", "bottom"), "pt": ("top",), "pr": ("end",),
                     "pb": ("bottom",), "pl": ("start",)}[key]
            for s in sides:
                pad[s] = v
        elif t.startswith("items-"):
            layout.setdefault("align", {})["cross"] = t[6:]
        elif t.startswith("justify-self-") or t.startswith("self-"):
            layout["selfAlign"] = t.rsplit("-", 1)[-1]
        elif t.startswith("justify-"):
            main = t[8:]
            layout.setdefault("align", {})["main"] = {
                "between": "spaceBetween", "around": "spaceAround", "evenly": "spaceEvenly"
            }.get(main, main)
        elif t.startswith("content-") and t != "content-stretch":
            pass
        # ---- sizing
        elif t in ("w-full", "h-full", "size-full"):
            if t != "h-full":
                layout["width"] = "fill"
            if t != "w-full":
                layout["height"] = "fill"
        elif prefix in ("w", "h", "size", "min-w", "min-h", "max-w", "max-h") or t in ("w-px", "h-px", "h-0", "w-0"):
            v = num(val) if val is not None else {"px": 1, "0": 0}[t.split("-")[1]]
            key = prefix or t.split("-")[0]
            if v is None:
                if val in ("min-content", "max-content", "fit-content"):
                    if key in ("w", "h", "size"):
                        layout["width" if key == "w" else "height"] = "wrap"
                    continue
                # percentages: the image-crop wrapper Figma emits, h-[208%]
                if val and val.endswith("%"):
                    layout[{"w": "widthPercent", "h": "heightPercent"}.get(key, key)] = float(val[:-1])
                else:
                    unparsed.append(tok)
                continue
            if key == "size":
                layout["width"] = layout["height"] = v
            elif key in ("w", "h"):
                layout["width" if key == "w" else "height"] = v
            else:
                layout[{"min-w": "minWidth", "min-h": "minHeight",
                        "max-w": "maxWidth", "max-h": "maxHeight"}[key]] = v
        elif prefix == "flex" or t in ("flex-1", "grow", "flex-auto"):
            weight = 1.0
            if val:
                first = val.split("_")[0]
                weight = float(first) if re.fullmatch(r"[\d.]+", first) else 1.0
            layout["weight"] = int(weight) if weight.is_integer() else weight
        elif t in ("shrink-0", "grow-0", "flex-none"):
            layout["noShrink"] = True
        elif t == "shrink":
            pass
        elif t == "aspect-square":
            layout["aspectRatio"] = 1
        elif prefix == "aspect":
            a, _, b = val.partition("/")
            if num(a) and num(b):
                layout["aspectRatio"] = round(num(a) / num(b), 4)
        # ---- position
        elif t == "absolute":
            pos["absolute"] = True
        elif t in ("fixed", "sticky"):
            pos["absolute"] = True
            pos["mode"] = t
        elif t == "inset-0":
            pos.update(top=0, end=0, bottom=0, start=0)
        elif prefix == "inset":
            vals = [num(x) for x in val.split("_")]
            if all(x is not None for x in vals):
                top, end, bottom, start = (vals * 4)[:4] if len(vals) == 1 else (
                    vals + vals)[:4] if len(vals) == 2 else (vals + [vals[1]])[:4]
                pos.update(top=top, end=end, bottom=bottom, start=start)
            else:
                pos["inset"] = val
        elif (pm := re.fullmatch(r"(top|left|right|bottom)-(0|px|\[(.+)\])", t)):
            side = {"left": "start", "right": "end"}.get(pm.group(1), pm.group(1))
            raw = pm.group(3)
            v = 0 if pm.group(2) == "0" else 1 if pm.group(2) == "px" else num(raw)
            if v is None and raw and raw.endswith("%"):
                v = raw
            if v is None:
                unparsed.append(tok)
                continue
            pos[side] = -v if (neg and isinstance(v, (int, float))) else v
        elif prefix in ("translate-x", "translate-y"):
            pos["translate" + prefix[-1].upper()] = val
        elif t.startswith("z-"):
            pos["z"] = t[2:]
        elif t in ("overflow-clip", "overflow-hidden"):
            layout["clip"] = True
        elif t.startswith("overflow-"):
            pass
        # ---- fills
        elif prefix == "bg":
            if (g := parse_gradient(val)):
                style["gradient"] = g
            elif (c := parse_color(val)):
                style["fill"] = color_entry(c)
            elif val.startswith("url("):
                style["backgroundImage"] = val
            else:
                unparsed.append(tok)
        elif t.startswith("bg-gradient-to-") or t.startswith("bg-linear-to-"):
            grad_stops["angle"] = GRADIENT_DIR.get(t.rsplit("-", 1)[-1], 180)
        elif prefix in ("from", "via", "to") and (c := parse_color(val)):
            grad_stops[prefix] = color_entry(c)
        elif t.startswith("bg-") and t[3:] in NAMED_COLORS:
            style["fill"] = color_entry(NAMED_COLORS[t[3:]])
        elif t.startswith("bg-") and t[3:] in ("clip-padding", "clip-border", "no-repeat", "cover", "center", "contain"):
            pass
        # ---- border
        elif t == "border" or (bm := re.fullmatch(r"border(?:-([trblxy]))?(?:-(\d+))?", t)):
            bm = re.fullmatch(r"border(?:-([trblxy]))?(?:-(\d+))?", t)
            side, width = bm.group(1), bm.group(2)
            border.setdefault("width", int(width) if width else 1)
            if side:
                border.setdefault("sides", []).extend(
                    {"t": ["top"], "r": ["end"], "b": ["bottom"], "l": ["start"],
                     "x": ["start", "end"], "y": ["top", "bottom"]}[side])
        elif prefix == "border" and num(val) is not None:
            border["width"] = num(val)
        elif prefix == "border" and (c := parse_color(val)):
            border.update(color_entry(c))
        elif t.startswith("border-") and t[7:] in NAMED_COLORS:
            border.update(color_entry(NAMED_COLORS[t[7:]]))
        elif t in ("border-dashed", "border-dotted"):
            border["style"] = t[7:]
        # ---- radius
        elif t == "rounded-full":
            style["radius"] = 9999
        elif (rm := re.fullmatch(r"rounded(?:-(t|r|b|l|tl|tr|br|bl))?-\[(.+)\]", t)):
            v = num(rm.group(2))
            if v is None:
                unparsed.append(tok)
                continue
            which = rm.group(1)
            if not which:
                style["radius"] = v
            else:
                for c in {"t": ("tl", "tr"), "r": ("tr", "br"), "b": ("br", "bl"),
                          "l": ("tl", "bl")}.get(which, (which,)):
                    corners[c] = v
        # ---- effects
        elif prefix == "shadow":
            style.setdefault("shadows", []).extend(parse_shadows(val))
        elif prefix == "drop-shadow":
            style.setdefault("dropShadows", []).extend(parse_shadows(val))
        elif (om := re.fullmatch(r"opacity-(\d+)", t)):
            style["opacity"] = round(int(om.group(1)) / 100, 3)
        elif prefix == "opacity" and num(val) is not None:
            style["opacity"] = num(val)
        elif prefix in ("blur", "backdrop-blur"):
            style["blur" if prefix == "blur" else "backgroundBlur"] = num(val)
        elif t.startswith("mix-blend-"):
            style["blend"] = t[10:]
        elif prefix == "rotate" or t.startswith("rotate-"):
            style["rotation"] = val or t[7:]
        elif t.startswith("-scale-") or t.startswith("scale-"):
            style["scale"] = t
        elif t in ("object-cover", "object-contain", "object-fill"):
            style["contentScale"] = {"object-cover": "Crop", "object-contain": "Fit",
                                     "object-fill": "FillBounds"}[t]
        # ---- text
        elif prefix == "font":
            text.update(parse_font(val))
        elif t.startswith("font-") and t[5:] in WEIGHT_CLASS:
            text["weight"] = WEIGHT_CLASS[t[5:]]
        elif prefix == "text" and num(val) is not None:
            text["size"] = num(val)
        elif prefix == "text" and (c := parse_color(val)):
            text["color"] = color_entry(c)
        elif t.startswith("text-") and t[5:] in NAMED_COLORS:
            text["color"] = color_entry(NAMED_COLORS[t[5:]])
        elif t in ("text-left", "text-center", "text-right", "text-justify", "text-start", "text-end"):
            text["align"] = t[5:]
        elif t in ("text-ellipsis", "truncate"):
            text["ellipsis"] = True
            if t == "truncate":
                text["singleLine"] = True
        elif prefix == "leading" or t in ("leading-none", "leading-normal"):
            v = val if val is not None else t[8:]
            if v == "normal":
                text["lineHeight"] = "auto"
            elif v == "none":
                text["lineHeight"] = {"multiplier": 1}
            elif v.endswith("px") and num(v) is not None:
                text["lineHeight"] = num(v)
            elif num(v) == 0:
                text["lineHeight"] = "wrapper"   # leading-[0]: the runs carry the real value
            elif num(v) is not None:
                text["lineHeight"] = {"multiplier": num(v)}
            elif v.endswith("%"):
                text["lineHeight"] = {"multiplier": float(v[:-1]) / 100}
            else:
                unparsed.append(tok)
        elif prefix == "tracking":
            if v := num(val):
                text["letterSpacing"] = {"px": v}
            elif (em := re.fullmatch(r"(-?[\d.]+)em", val)):
                text["letterSpacing"] = {"em": float(em.group(1))}
            elif val in ("0", "0px"):
                pass
            else:
                unparsed.append(tok)
        elif t in ("uppercase", "lowercase", "capitalize"):
            text["textCase"] = {"uppercase": "upper", "lowercase": "lower", "capitalize": "title"}[t]
        elif t in ("underline", "line-through"):
            text["decoration"] = t
        elif t == "italic":
            text["italic"] = True
        elif t == "whitespace-nowrap":
            text["singleLine"] = True
        elif t in ("whitespace-pre", "whitespace-pre-wrap"):
            text["preserveWhitespace"] = True
            if t == "whitespace-pre":
                text["singleLine"] = True
        elif (lm := re.fullmatch(r"line-clamp-(\d+)", t)):
            text["maxLines"] = int(lm.group(1))
        elif t in NOISE or t.startswith("whitespace-") or t.startswith("decoration-"):
            pass
        else:
            unparsed.append(tok)

    if pad:
        layout["padding"] = {s: pad.get(s, 0) for s in ("top", "end", "bottom", "start")}
    if pos:
        layout["position"] = pos
    if corners:
        base = style.get("radius", 0)
        style["corners"] = {c: corners.get(c, base) for c in ("tl", "tr", "br", "bl")}
    if border:
        style["border"] = border
    if "from" in grad_stops or "to" in grad_stops:
        stops = [grad_stops[k] for k in ("from", "via", "to") if k in grad_stops]
        style["gradient"] = {"type": "linear", "angle": grad_stops.get("angle", 180), "stops": stops}

    for key, value in inline_style.items():
        if key == "backgroundImage":
            for part in split_top(value):
                if (g := parse_gradient(part)):
                    style.setdefault("gradientLayers", []).append(g)
                else:
                    style["backgroundImage"] = part
            if style.get("gradientLayers") and "gradient" not in style:
                style["gradient"] = style["gradientLayers"][0]
            if len(style.get("gradientLayers", [])) <= 1:
                style.pop("gradientLayers", None)
        elif key in ("backgroundColor", "color") and (c := parse_color(value)):
            (style.__setitem__("fill", color_entry(c)) if key == "backgroundColor"
             else text.__setitem__("color", color_entry(c)))
        elif key not in ("fontVariationSettings",):
            unparsed.append(f"style.{key}")

    return {"layout": layout, "style": style, "text": text, "unparsed": unparsed}


def parse_inline_style(code: str) -> dict[str, str]:
    """`{ backgroundImage: "linear-gradient(…)", maskSize: "…" }` → dict."""
    code = code.strip()
    if code.startswith("{") and code.endswith("}"):
        code = code[1:-1]
    out = {}
    for m in re.finditer(r"(\w+)\s*:\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|`[^`]*`|[\w.#-]+)", code):
        out[m.group(1)] = literal(m.group(2)) or m.group(2)
    return out


# ============================================================== tree building


NODE_ID = re.compile(r"(?:node-)?(I?[0-9]+[:_][0-9]+(?:;[0-9]+[:_][0-9]+)*)")


def norm_node(raw: str) -> str:
    return raw.replace("_", ":")


@dataclass
class Frag:
    nodes: list = field(default_factory=list)
    runs: list = field(default_factory=list)
    images: list = field(default_factory=list)


class Builder:
    def __init__(self, comps: dict[str, Component], consts: dict[str, str]):
        self.comps = comps
        self.consts = consts
        self.expanded: list[str] = []
        self.unparsed: dict[str, int] = {}
        self.unresolved: set[str] = set()

    # ---------------------------------------------------------------- helpers

    def attr(self, el: El, name: str, env: dict, notes: list[str]) -> str | None:
        kind, value = el.attrs.get(name, (None, None))
        if kind == "str":
            return value
        if kind == "expr":
            return eval_value(value, env, notes)
        return None

    def node_id(self, el: El, env: dict, notes: list[str]) -> str | None:
        raw = self.attr(el, "data-node-id", env, notes) or self.attr(el, "id", env, notes)
        if raw and (m := NODE_ID.fullmatch(raw.strip())):
            return norm_node(m.group(1))
        return None

    def variants(self, el: El) -> list[dict]:
        """Every arm of a ternary `id={…}`, joined with the matching className arm."""
        kind, id_expr = el.attrs.get("id", (None, None))
        if kind != "expr" or not split_ternary(id_expr):
            return []
        arms = ternary_arms(id_expr)
        class_expr = el.attrs.get("className", (None, ""))[1]
        out = []
        for cond, value in arms:
            if not (m := NODE_ID.fullmatch(value)):
                continue
            env = {c: (c == cond) for c, _ in arms if c != "__default__"}
            notes: list[str] = []
            classes = eval_value(class_expr, env, notes) if class_expr else ""
            props = parse_classes(classes or "", {})
            out.append({"when": cond, "id": norm_node(m.group(1)),
                        **{k: v for k, v in props.items() if v and k != "unparsed"}})
        return out

    # ---------------------------------------------------------------- conversion

    def convert(self, el, env: dict, inherited: dict) -> Frag:
        if isinstance(el, str):
            text = jsx_text(el)
            return Frag(runs=[{"text": text, **inherited}]) if text.strip() or (text and "\n" not in el) else Frag()
        if isinstance(el, Expr):
            notes: list[str] = []
            if "<" in el.code:   # {cond && <X/>}, {cond ? <A/> : <B/>}
                return self.conditional_jsx(el.code, env, inherited)
            value = eval_value(el.code, env, notes)
            self.unresolved.update(notes)
            return Frag(runs=[{"text": value, **inherited}]) if value else Frag()

        if el.tag in self.comps and el.tag[:1].isupper():
            return self.instantiate(el, env, inherited)
        if el.tag == "br":
            return Frag(runs=[{"text": "\n", **inherited}])

        notes: list[str] = []
        classes = self.attr(el, "className", env, notes) or ""
        inline = parse_inline_style(el.attrs["style"][1]) if el.attrs.get("style", ("",))[0] == "expr" else {}
        props = parse_classes(classes, inline)
        for tok in props["unparsed"]:
            key = re.sub(r"\[.*\]", "[…]", tok)
            self.unparsed[key] = self.unparsed.get(key, 0) + 1
        text_here = {**inherited, **{k: v for k, v in props["text"].items() if k in TEXT_KEYS}}

        if el.tag == "img":
            src = self.attr(el, "src", env, notes)
            const = el.attrs.get("src", ("", ""))[1]
            url = self.consts.get(const, src if src and src.startswith("http") else None)
            if not url:
                return Frag()
            image = {"const": const if const in self.consts else None, "url": url,
                     "ext": "svg" if url.split("?")[0].endswith(".svg") else "png",
                     "layout": props["layout"], "style": props["style"]}
            nid = self.node_id(el, env, notes)
            if nid:
                return Frag(nodes=[{"id": nid, "name": self.attr(el, "data-name", env, notes) or "",
                                    "tag": "img", "asset": strip_none(image)}])
            return Frag(images=[strip_none(image)])

        frag = Frag()
        prev_block = False
        for child in el.children:
            sub = self.convert(child, env, text_here)
            is_block = isinstance(child, El) and child.tag in ("p", "div") and sub.runs and not sub.nodes
            if is_block and prev_block and frag.runs:
                frag.runs.append({"text": "\n", **text_here})
            prev_block = is_block
            frag.nodes.extend(sub.nodes)
            frag.runs.extend(sub.runs)
            frag.images.extend(sub.images)

        nid = self.node_id(el, env, notes)
        self.unresolved.update(notes)
        if nid is None:
            return frag   # id-less wrapper: transparent

        node: dict = {"id": nid, "name": self.attr(el, "data-name", env, notes) or "", "tag": el.tag}
        if props["layout"]:
            node["layout"] = props["layout"]
        if props["style"]:
            node["style"] = props["style"]
        runs = [r for r in frag.runs if r.get("text")]
        if runs and "".join(r["text"] for r in runs).strip():
            node["text"] = text_node(runs, text_here)
        if frag.images:
            if frag.nodes or runs:
                node.setdefault("style", {})["image"] = frag.images[0]
            else:
                node["asset"] = frag.images[0]
                if len(frag.images) > 1:
                    node["assetLayers"] = frag.images[1:]
        if frag.nodes:
            node["children"] = frag.nodes
        if notes and (vs := self.variants(el)):
            node["variants"] = vs
        if notes:
            node["unresolvedConditions"] = sorted(set(notes))
        return Frag(nodes=[node])

    def conditional_jsx(self, code: str, env: dict, inherited: dict) -> Frag:
        """`{cond ? <A/> : <B/>}` and `{cond && <A/>}` — render the arm this instance takes."""
        code = code.strip()
        while code.startswith("(") and code.endswith(")"):
            code = code[1:-1].strip()
        chosen = None
        if (parts := split_ternary(code)):
            cond, yes, no = parts
            try:
                chosen = yes if eval_condition(cond, env) else no
            except Unresolved:
                self.unresolved.add(cond)
                chosen = no
        elif (m := re.match(r"(.+?)&&\s*(\(?\s*<.*)", code, re.S)):
            try:
                chosen = m.group(2) if eval_condition(m.group(1), env) else None
            except Unresolved:
                self.unresolved.add(m.group(1).strip())
                chosen = m.group(2)   # show it: a hidden branch is invisible in review
        if not chosen:
            return Frag()
        chosen = chosen.strip()
        while chosen.startswith("(") and chosen.endswith(")"):
            chosen = chosen[1:-1].strip()
        if chosen.startswith("<"):
            el, _ = parse_element(chosen, 0)
            return self.convert(el, env, inherited)
        return self.convert(Expr(chosen), env, inherited) if chosen not in ("null", "undefined") else Frag()

    def instantiate(self, el: El, env: dict, inherited: dict) -> Frag:
        comp = self.comps[el.tag]
        if comp.root is None:
            return Frag()
        notes: list[str] = []
        inner = dict(comp.defaults)
        for name, (kind, value) in el.attrs.items():
            if kind == "str":
                inner[name] = value
            elif kind == "bool":
                inner[name] = True
            else:
                v = eval_value(value, env, notes)
                inner[name] = v if v is not None else (value == "true" if value in ("true", "false") else None)
        props = {k: v for k, v in inner.items()
                 if k not in ("className", "data-node-id", "data-name") and isinstance(v, (str, bool))}
        for name, expr in comp.consts:
            lit = literal(expr)
            if lit is not None:
                inner[name] = lit
                continue
            try:
                inner[name] = eval_condition(expr, inner)
            except Unresolved:
                pass
        self.expanded.append(el.tag)
        frag = self.convert(comp.root, inner, inherited)
        usage_id = self.node_id(el, env, notes)
        if usage_id and frag.nodes:
            root = frag.nodes[0]
            root["componentId"] = root["id"]
            root["id"] = usage_id
            root["component"] = el.tag
            root["props"] = props
            if name := self.attr(el, "data-name", env, notes):
                root["name"] = name
        return frag


def ternary_arms(code: str) -> list[tuple[str, str]]:
    arms = []
    while (parts := split_ternary(code)):
        cond, yes, code = parts
        if (lit := literal(yes)) is not None:
            arms.append((cond.strip("() "), lit))
    if (lit := literal(code)) is not None:
        arms.append(("__default__", lit))
    return arms


def strip_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, {}, [])}


def text_node(runs: list[dict], base: dict) -> dict:
    """Merge text runs into one text node; keep per-run overrides only where they differ."""
    merged: list[dict] = []
    for run in runs:
        if merged and all(merged[-1].get(k) == run.get(k) for k in TEXT_KEYS):
            merged[-1]["text"] += run["text"]
        else:
            merged.append(dict(run))
    content = "".join(r["text"] for r in merged)
    lead = len(content) - len(content.lstrip())
    content = content.strip()
    first = merged[0]
    style = {k: first[k] for k in TEXT_KEYS if k in first}
    if style.get("lineHeight") == "wrapper" or base.get("lineHeight") == "wrapper":
        inner = [r.get("lineHeight") for r in merged if r.get("lineHeight") not in (None, "wrapper")]
        style["lineHeight"] = inner[0] if inner else "auto"
    lh = style.get("lineHeight")
    if isinstance(lh, dict) and "multiplier" in lh and style.get("size"):
        style["lineHeight"] = round(lh["multiplier"] * style["size"], 2)
    ls = style.get("letterSpacing")
    if isinstance(ls, dict) and "em" in ls and style.get("size"):
        style["letterSpacing"] = {"px": round(ls["em"] * style["size"], 3), "em": ls["em"]}
    out: dict = {"content": content, **style}
    if len(merged) > 1:
        merged[0]["text"] = merged[0]["text"][lead:]
        merged[-1]["text"] = merged[-1]["text"].rstrip()
        out["runs"] = [
            {"text": r["text"],
             **{k: r[k] for k in TEXT_KEYS if k in r and r[k] != first.get(k) and r[k] != "wrapper"}}
            for r in merged
        ]
    return out


# ============================================================== flat maps


def walk(node: dict):
    yield node
    for child in node.get("children", []):
        yield from walk(child)


def legacy_style(node: dict) -> dict:
    """The flat style dict figma_to_ir.py (without --tree) and ir_coverage_check.py read."""
    out: dict = {}
    style = node.get("style", {})
    text = node.get("text", {})
    if (fill := style.get("fill")) and fill.get("alpha", 1) > 0:
        out["fill"] = fill["hex"]
        if "alpha" in fill:
            out["fillAlpha"] = fill["alpha"]
    elif (grad := style.get("gradient")):
        out["fill"] = grad["stops"][0]["hex"]
        out["gradient"] = grad
    if "radius" in style:
        out["radius"] = style["radius"]
    if (border := style.get("border")) and "hex" in border:
        out["border"] = border["hex"]
        out["borderWidth"] = border.get("width", 1)
    for key in ("shadows", "dropShadows", "opacity", "corners"):
        if key in style:
            out[key] = style[key]
    if text:
        for key in ("size", "weight", "lineHeight", "letterSpacing", "family"):
            if key in text:
                out["fontFamily" if key == "family" else key] = text[key]
        if (color := text.get("color")):
            out["color"] = color["hex"]
    return out


# ============================================================== main


def main() -> int:
    ap = argparse.ArgumentParser(
        description="get_design_context → context-tree.json (+ texts/styles/assets maps)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--context", type=Path, required=True,
                    help="the get_design_context response, verbatim (.json envelope or .tsx code)")
    ap.add_argument("--tree", type=Path, help="write the node tree here (feed it to figma_to_ir.py --tree)")
    ap.add_argument("--texts", type=Path, required=True)
    ap.add_argument("--styles", type=Path, required=True)
    ap.add_argument("--assets", type=Path, required=True)
    ap.add_argument("--min-texts", type=int, default=1,
                    help="refuse if fewer strings than this were recovered (default 1)")
    args = ap.parse_args()

    if not args.context.exists():
        print(f"error: {args.context} does not exist", file=sys.stderr)
        return 2
    src = load_source(args.context)
    comps, default_name, consts = parse_components(src)
    root_comp = comps.get(default_name) if default_name else (list(comps.values())[-1] if comps else None)

    builder = Builder(comps, consts)
    if root_comp and root_comp.root is not None:
        frag = builder.instantiate(El(root_comp.name, {}), {}, {})
    else:   # bare JSX with no function wrapper
        start = src.find("<")
        if start == -1:
            print(f"error: no JSX found in {args.context}", file=sys.stderr)
            return 2
        el, _ = parse_element(src, start)
        frag = builder.convert(el, {}, {})
    if not frag.nodes:
        print(f"error: no element with a data-node-id in {args.context}", file=sys.stderr)
        return 2
    root = frag.nodes[0] if len(frag.nodes) == 1 else {"id": "", "name": "", "tag": "fragment", "children": frag.nodes}

    texts: dict[str, str] = {}
    styles: dict[str, dict] = {}
    assets: list[dict] = []
    for node in walk(root):
        nid = node["id"]
        ids = [nid] + ([node["componentId"]] if node.get("componentId") else [])
        if "text" in node:
            for i in ids:
                texts.setdefault(i, node["text"]["content"])
        if (st := legacy_style(node)):
            for i in ids:
                styles.setdefault(i, st)
        for v in node.get("variants", []):
            vs = legacy_style({"style": v.get("style", {}), "text": v.get("text", {})})
            if vs:
                styles.setdefault(v["id"], vs)
        for image in ([node["asset"]] if "asset" in node else []) + node.get("assetLayers", []) + (
                [node["style"]["image"]] if "image" in node.get("style", {}) else []):
            assets.append({"id": nid, "const": image.get("const"), "url": image["url"], "ext": image["ext"]})

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

    for path in (args.texts, args.styles, args.assets, args.tree):
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
    args.texts.write_text(json.dumps(texts, ensure_ascii=False, indent=2), encoding="utf-8")
    args.styles.write_text(json.dumps(styles, ensure_ascii=False, indent=2), encoding="utf-8")
    args.assets.write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")

    nodes = list(walk(root))
    auto_layout = sum(1 for n in nodes if n.get("layout", {}).get("direction"))
    mixed = sum(1 for n in nodes if "runs" in n.get("text", {}))
    effects = sum(1 for n in nodes if {"shadows", "dropShadows", "gradient", "blur"} & set(n.get("style", {})))
    families = sorted({n["text"]["family"] for n in nodes if n.get("text", {}).get("family")})
    if args.tree:
        args.tree.write_text(json.dumps({
            "schema": "figma-context-tree/v1",
            "root": root,
            "components": sorted(set(builder.expanded) - {root_comp.name if root_comp else ""}),
            "fonts": families,
            "unparsedClasses": dict(sorted(builder.unparsed.items(), key=lambda kv: -kv[1])),
            "unresolvedConditions": sorted(builder.unresolved),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.tree}  {len(nodes)} nodes, {auto_layout} auto-layout containers, "
              f"{mixed} mixed-style texts, {effects} with effects/gradients")
    distinct_fills = len({s["fill"] for s in styles.values() if "fill" in s})
    print(f"wrote {args.texts}  {len(texts)} strings")
    print(f"wrote {args.styles}  {len(styles)} styled nodes, {distinct_fills} distinct fills")
    print(f"wrote {args.assets}  {len(assets)} asset references, {len(consts)} constants")
    if families:
        print(f"  fonts: {', '.join(families)} — bundle these in res/font/, or say so in the report")
    if builder.unparsed:
        top = ", ".join(f"{k}×{v}" for k, v in sorted(builder.unparsed.items(), key=lambda kv: -kv[1])[:8])
        print(f"  unparsed classes: {top} — not carried into the IR; check whether any matter")
    if builder.unresolved:
        print(f"  unresolved variant conditions (default arm taken): {', '.join(sorted(builder.unresolved))}")
    if distinct_fills <= 1 and len(styles) > 4:
        print("  note: every styled node shares one fill — check the variant ternaries parsed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
