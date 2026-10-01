#!/usr/bin/env python3
"""Scan a Compose project's theme and composable inventory into an adapter skeleton.

What it reads is what a human would read to answer "what tokens does this project have":
the Dp token data classes, the palette object, the color scheme wiring, the Typography
block, the Shapes block, and every @Composable declaration under the UI source tree.

What it produces is a *skeleton*. Token values are parsed and reliable; `figmaHints` and
`kind` on each component are guesses that a human must review before the pipeline trusts
them (see references/adapter-spec.md).

Usage:
    python3 scan_design_system.py --project /path/to/android/root \\
                                  --out /path/to/android/root/.figma/adapter.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- source discovery


def find_kotlin_sources(project: Path) -> list[Path]:
    """Every main-source .kt file, build dirs excluded."""
    return [
        p
        for p in project.rglob("*.kt")
        if "/build/" not in str(p) and "/src/test/" not in str(p) and "/src/androidTest/" not in str(p)
    ]


def find_theme_files(sources: list[Path]) -> list[Path]:
    """Files under a `theme` package, falling back to whatever declares MaterialTheme."""
    themed = [p for p in sources if "/theme/" in str(p)]
    if themed:
        return themed
    return [p for p in sources if "MaterialTheme(" in p.read_text(encoding="utf-8", errors="replace")]


def fingerprint_theme(theme_files: list[Path], project: Path) -> dict:
    """Content hash per theme source file, keyed by project-relative path.

    This is what lets resolve_tokens.py tell a current adapter from a stale one: a per-file
    hash catches an edit (same files, different hash), and the file list itself — the dict's
    keys, recomputed against the live theme the same way this scanner found it — catches a
    file added to or removed from the theme package, which an edit-only hash would miss.
    """
    return {
        "algorithm": "sha256",
        "files": {
            str(p.relative_to(project)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(theme_files)
        },
    }


def balanced_block(text: str, open_idx: int, pair: str = "()") -> str:
    """Return the substring inside the bracket pair opening at `open_idx`."""
    opener, closer = pair
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i]
    return ""


# ---------------------------------------------------------------- theme parsing

# `val md: Dp = 16.dp` and `val space16 = 16.dp` are the same token declared two ways.
DP_VAL = re.compile(r"val\s+(\w+)\s*(?::\s*Dp\s*)?=\s*([\d.]+)\.dp")
# Token groups live in a data class of defaults or in a plain object of constants.
DATA_CLASS = re.compile(r"data class\s+(\w+)\s*\(")
TOKEN_OBJECT = re.compile(r"\bobject\s+(\w+)\s*\{")
COLOR_DECL = re.compile(r"val\s+(\w+)\s*=\s*Color\(0x([0-9A-Fa-f]{8})\)")
# `val LightPrimary = ColorBrand` — a semantic name pointing at a raw one.
COLOR_ALIAS = re.compile(r"val\s+(\w+)\s*(?::\s*Color\s*)?=\s*(?:\w+\.)?(\w+)\s*$", re.MULTILINE)
SHAPE_DECL = re.compile(r"(\w+)\s*=\s*RoundedCornerShape\(([\d.]+)\.dp\)")
SCHEME_ROLE = re.compile(r"^\s*(\w+)\s*=\s*(?:\w+\.)?(\w+)\s*,?\s*$", re.MULTILINE)
THEME_FUN = re.compile(r"fun\s+(\w*Theme)\s*\(")
TOKEN_ACCESSOR = re.compile(r"val\s+(\w+)\s*:\s*\w+\s*\n?\s*@Composable")


def _group_name(class_name: str) -> str:
    """ComposerSpacing -> spacing, ComposerRadii -> radii."""
    name = re.sub(r"^[A-Z][a-z]+(?=[A-Z])", "", class_name)  # drop a leading brand prefix
    return (name or class_name).lower()


def parse_dp_groups(text: str) -> dict[str, dict[str, float]]:
    """Token groups, however the project declares them.

    Both shapes are common and mean the same thing:
        data class ComposerSpacing(val md: Dp = 16.dp, ...)
        object AppSpacing { val space16 = 16.dp; ... }
    """
    groups: dict[str, dict[str, float]] = {}
    for pattern, pair in ((DATA_CLASS, "()"), (TOKEN_OBJECT, "{}")):
        for m in pattern.finditer(text):
            block = balanced_block(text, m.end() - 1, pair)
            values = {name: float(val) for name, val in DP_VAL.findall(block)}
            if values:
                groups.setdefault(_group_name(m.group(1)), {}).update(values)
    return groups


def parse_palette(text: str) -> dict[str, str]:
    """`val Ink = Color(0xFFF8F7FB)` -> {"Ink": "#F8F7FB"}. Alpha is kept only when < FF.

    Then resolves alias chains — `val LightPrimary = ColorBrand` — because a project that
    names its ramp once and its roles separately is doing the right thing, and a scanner
    that only sees hex literals reports zero roles on it.
    """
    palette = {}
    for name, argb in COLOR_DECL.findall(text):
        alpha, rgb = argb[:2].upper(), argb[2:].upper()
        palette[name] = f"#{rgb}" if alpha == "FF" else f"#{argb.upper()}"

    for _ in range(4):  # depth-bounded; real chains are one or two links
        added = False
        for name, target in COLOR_ALIAS.findall(text):
            if name not in palette and target in palette:
                palette[name] = palette[target]
                added = True
        if not added:
            break
    return palette


def parse_color_scheme(text: str, palette: dict[str, str]) -> dict[str, dict[str, str]]:
    """Resolve both the light and dark scheme, kept apart.

    A single merged map cannot represent a project that ships both — collapsing them
    (whichever direction) means one of the two schemes is simply wrong in the adapter, and
    a Figma frame drawn against the scheme that lost gets resolved against the wrong
    numbers with nothing to say so. Generation picks light by default and dark on request
    (see resolve_tokens.py --dark); the adapter has to carry both for that to be a real
    choice instead of a guess.
    """
    schemes: dict[str, dict[str, str]] = {}
    for scheme_name, fn in (("light", "lightColorScheme("), ("dark", "darkColorScheme(")):
        idx = text.find(fn)
        if idx < 0:
            continue
        block = balanced_block(text, idx + len(fn) - 1)
        roles: dict[str, str] = {}
        for role, ref in SCHEME_ROLE.findall(block):
            if ref in palette:
                roles.setdefault(role, palette[ref])
        if roles:
            schemes[scheme_name] = roles
    return schemes


WEIGHTS = {
    "Thin": 100, "ExtraLight": 200, "Light": 300, "Normal": 400, "Medium": 500,
    "SemiBold": 600, "Bold": 700, "ExtraBold": 800, "Black": 900,
}


# `name = Callee(`, with the type annotation Kotlin allows in between:
#   titleMedium = appTextStyle(...)          a Typography slot
#   val captionSmall: TextStyle = TextStyle(...)   an explicitly typed property
ANY_CALL_DECL = re.compile(r"(\w+)\s*(?::\s*[\w.<>]+\s*)?=\s*(\w+)\s*\(")
# `val headingH1: TextStyle = AppHeadingH1` — a semantic name for a ramp entry.
TEXT_STYLE_ALIAS = re.compile(r"val\s+(\w+)\s*:\s*TextStyle\s*=\s*(\w+)\s*[,)\n]")
# `displayLarge = AppHeadingH1,` — a slot wired to an existing style rather than built inline.
ALIAS_ASSIGN = re.compile(r"(\w+)\s*=\s*(\w+)\s*[,)\n]")


def _style_values(block: str) -> dict | None:
    """Pull size / lineHeight / weight out of a text-style call, named or positional."""
    size = re.search(r"fontSize\s*=\s*([\d.]+)\.sp", block)
    line = re.search(r"lineHeight\s*=\s*([\d.]+)\.sp", block)
    if not size:
        # Positional helper, e.g. appTextStyle(FontWeight.Medium, 14.sp, 20.sp). Kotlin
        # convention puts size before line height, so read them in order.
        bare = re.findall(r"(?<![\w.])([\d.]+)\.sp", block)
        if not bare:
            return None
        entry = {"size": float(bare[0])}
        if len(bare) > 1:
            entry["lineHeight"] = float(bare[1])
    else:
        entry = {"size": float(size.group(1))}
        if line:
            entry["lineHeight"] = float(line.group(1))
    weight = re.search(r"FontWeight\.(\w+)", block)
    entry["weight"] = WEIGHTS.get(weight.group(1), 400) if weight else 400
    return entry


def style_factories(text: str) -> set[str]:
    """Functions declared to return a TextStyle.

    A real type ramp is often built through one — `private fun appTextStyle(weight, size,
    lineHeight): TextStyle = TextStyle(...)` and then twenty `val AppHeadingH1 =
    appTextStyle(SemiBold, 28.sp, 32.sp)`. Without this, a scanner sees twenty function
    calls and reports a project with no typography at all.
    """
    factories = set()
    for m in re.finditer(r"fun\s+(\w+)\s*\(", text):
        end = m.end() - 1 + len(balanced_block(text, m.end() - 1)) + 2
        if re.match(r"\s*:\s*TextStyle\b", text[end : end + 24]):
            factories.add(m.group(1))
    return factories


def _text_styles(text: str, any_callee: bool = False, factories: set[str] | None = None) -> dict[str, dict]:
    """Text styles declared in `text`.

    `any_callee` is for the inside of a Typography block, where the slot names are fixed
    and whatever builds them is a text style by definition. Outside it, the callee must be
    `TextStyle` itself or a known factory — otherwise every two-argument call with an `.sp`
    in it would be mistaken for a type token.
    """
    styles: dict[str, dict] = {}
    allowed = {"TextStyle", *(factories or set())}
    for m in ANY_CALL_DECL.finditer(text):
        name, callee = m.group(1), m.group(2)
        if not any_callee and callee not in allowed:
            continue
        if name in allowed:  # the factory's own `): TextStyle = TextStyle(` body
            continue
        entry = _style_values(balanced_block(text, m.end() - 1))
        if entry and entry["size"] > 0:
            styles[name] = entry
    return styles


# The Material 3 baseline. A project that writes `Typography()` with no arguments — or
# overrides only a few slots — still renders the rest, and the resolver has to be able to
# match against them. Without this, such a project reports "no typography" and every text
# node in the design comes back unmapped for no reason.
MATERIAL3_DEFAULTS: dict[str, dict] = {
    "displayLarge": {"size": 57.0, "lineHeight": 64.0, "weight": 400},
    "displayMedium": {"size": 45.0, "lineHeight": 52.0, "weight": 400},
    "displaySmall": {"size": 36.0, "lineHeight": 44.0, "weight": 400},
    "headlineLarge": {"size": 32.0, "lineHeight": 40.0, "weight": 400},
    "headlineMedium": {"size": 28.0, "lineHeight": 36.0, "weight": 400},
    "headlineSmall": {"size": 24.0, "lineHeight": 32.0, "weight": 400},
    "titleLarge": {"size": 22.0, "lineHeight": 28.0, "weight": 400},
    "titleMedium": {"size": 16.0, "lineHeight": 24.0, "weight": 500},
    "titleSmall": {"size": 14.0, "lineHeight": 20.0, "weight": 500},
    "bodyLarge": {"size": 16.0, "lineHeight": 24.0, "weight": 400},
    "bodyMedium": {"size": 14.0, "lineHeight": 20.0, "weight": 400},
    "bodySmall": {"size": 12.0, "lineHeight": 16.0, "weight": 400},
    "labelLarge": {"size": 14.0, "lineHeight": 20.0, "weight": 500},
    "labelMedium": {"size": 12.0, "lineHeight": 16.0, "weight": 500},
    "labelSmall": {"size": 11.0, "lineHeight": 16.0, "weight": 500},
}


def parse_typography(text: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """Split Material slots from any project-specific scale.

    They are not interchangeable in generated code — a Material slot is
    `MaterialTheme.typography.titleMedium`, a project style is reached through the token
    accessor — so the adapter has to keep them apart or the generator picks the wrong one.
    """
    factories = style_factories(text)

    custom = _text_styles(text, factories=factories)
    # A named scale usually aliases the raw ramp — `val headingH1: TextStyle = AppHeadingH1`.
    # The alias is the name a caller writes, so it is the one worth reporting.
    for name, target in TEXT_STYLE_ALIAS.findall(text):
        if name not in custom and target in custom:
            custom[name] = custom[target]

    # Word-anchored: `AppExtendedTypography(` also ends in "Typography(", and parsing that
    # data class as the Material block yields zero slots and hides the real one.
    m = re.search(r"\bTypography\s*\(", text)
    material_block = balanced_block(text, m.end() - 1) if m else ""
    material = _text_styles(material_block, any_callee=True)
    # Slots are just as often wired to the project's own ramp as built inline:
    #   Typography(displayLarge = AppHeadingH1, ...)
    for slot, target in ALIAS_ASSIGN.findall(material_block):
        if slot not in material and target in custom:
            material[slot] = custom[target]

    overridden = set(material)
    material = {**MATERIAL3_DEFAULTS, **material}
    for name in material:
        material[name] = {**material[name], "source": "project" if name in overridden else "material3-default"}

    return material, {k: v for k, v in custom.items() if k not in overridden}


def parse_shapes(text: str) -> dict[str, float]:
    idx = text.find("Shapes(")
    if idx < 0:
        return {}
    block = balanced_block(text, idx + len("Shapes(") - 1)
    return {name: float(val) for name, val in SHAPE_DECL.findall(block)}


# ---------------------------------------------------------------- composable inventory

COMPOSABLE = re.compile(
    r"@Composable[^\n]*\n(?:@\w+[^\n]*\n)*\s*(?:internal\s+|private\s+|public\s+)?fun\s+"
    r"(?:\w+\.)?([A-Z]\w*)\s*\(",
)

CONTAINER_HINTS = ("card", "surface", "scaffold", "section", "panel", "sheet", "container", "tile", "grid")
CONTROL_HINTS = ("button", "chip", "field", "switch", "stepper", "slider", "bar", "pill", "toggle")

# Destinations, not parts. A Figma layer never "reuses" a screen, and leaving these in the
# component list is what produces matches like tab-Settings -> SettingsScreen.
DESTINATION_SUFFIXES = ("Screen", "App", "Entry", "Route", "Host", "NavGraph")

# Words that describe *where a box sits*, not *what it is*. Every design has a dozen rows,
# bars and sections, so a hint made only of these matches everything and means nothing.
GENERIC_TOKENS = {
    "row", "column", "col", "bar", "group", "wrap", "inner", "outer", "content", "section",
    "item", "left", "right", "top", "bottom", "start", "end", "main", "container", "frame",
    "view", "screen", "app", "entry", "area", "block", "part", "box", "layout", "header",
    "footer", "body", "list", "grid", "stack", "panel", "info", "detail", "default",
}


def classify(name: str) -> str:
    lower = name.lower()
    if any(h in lower for h in CONTROL_HINTS):
        return "control"
    if any(h in lower for h in CONTAINER_HINTS):
        return "container"
    return "unknown"


def camel_tokens(name: str) -> list[str]:
    """Distinctive words in a composable name — the generic ones carry no signal."""
    return [t.lower() for t in re.findall(r"[A-Z][a-z0-9]*", name) if len(t) > 2 and t.lower() not in GENERIC_TOKENS]


# Where reusable parts live. A composable defined next to a feature's screen is that
# feature's business, not a design-system component, and listing 140 of them makes the
# adapter noise rather than a map.
SHARED_UI_MARKERS = ("/component", "/designsystem/", "/design_system/", "/widget", "/core/ui/", "/ui/common/", "/ds/")


def scan_components(sources: list[Path], project: Path) -> list[dict]:
    """Public/internal @Composables that look like shared design-system parts."""
    shared = [p for p in sources if any(m in str(p) for m in SHARED_UI_MARKERS)]
    # A project with no shared UI package still has components worth mapping; fall back to
    # everything rather than returning an empty map.
    candidates = shared or sources

    components: list[dict] = []
    seen: set[str] = set()
    for path in candidates:
        if "/theme/" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in COMPOSABLE.finditer(text):
            name = m.group(1)
            if name in seen or name.endswith(DESTINATION_SUFFIXES):
                continue
            # Private composables are screen-local; they are not reusable design-system parts.
            decl_start = text.rfind("\n", 0, m.start(1))
            if "private" in text[max(0, decl_start - 200) : m.start(1)].split("@Composable")[-1]:
                continue
            seen.add(name)
            params = [
                p.split(":")[0].strip()
                for p in balanced_block(text, m.end() - 1).split(",")
                if ":" in p
            ]
            hints = camel_tokens(name)
            components.append(
                {
                    "name": name,
                    "file": str(path.relative_to(project)),
                    "kind": classify(name),
                    "props": [p for p in params if p and p.isidentifier()],
                    "figmaHints": hints + [f"{h}-*" for h in hints],
                    "confidence": "review",
                }
            )
    return sorted(components, key=lambda c: c["name"])


# ---------------------------------------------------------------- assembly

DEFAULT_COMMANDS = {
    "build": "./gradlew :app:assembleDebug",
    "unitTest": "./gradlew :app:testDebugUnitTest",
    "screenshotTest": "./gradlew :app:validateDebugScreenshotTest",
    "screenshotUpdate": "./gradlew :app:updateDebugScreenshotTest",
    "lint": "./gradlew :app:lintDebug",
}

DEFAULT_TOLERANCE = {
    "spacingRatio": 0.12,
    "fontSizeRatio": 0.10,
    "colorDeltaE": 6,
    "snapDistance": {"spacing": 2, "radius": 3, "fontSize": 1},
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, type=Path, help="Android project root")
    ap.add_argument("--out", required=True, type=Path, help="adapter.json to write")
    ap.add_argument("--force", action="store_true", help="overwrite an existing adapter")
    args = ap.parse_args()

    project = args.project.resolve()
    if not project.is_dir():
        print(f"error: {project} is not a directory", file=sys.stderr)
        return 2
    if args.out.exists() and not args.force:
        print(f"error: {args.out} exists (pass --force to overwrite; it may hold reviewed mappings)", file=sys.stderr)
        return 2

    sources = find_kotlin_sources(project)
    theme_files = find_theme_files(sources)
    if not theme_files:
        print("error: no theme package found — pass a project with a Compose theme", file=sys.stderr)
        return 2

    theme_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in theme_files)

    palette = parse_palette(theme_text)
    dp_groups = parse_dp_groups(theme_text)
    theme_fun = THEME_FUN.search(theme_text)

    material_type, custom_type = parse_typography(theme_text)

    theme: dict = {
        "package": ".".join(theme_files[0].parts[theme_files[0].parts.index("java") + 1 :][:-1])
        if "java" in theme_files[0].parts
        else "",
        "themeComposable": theme_fun.group(1) if theme_fun else None,
        "files": [str(p.relative_to(project)) for p in theme_files],
        "palette": palette,
        "colors": parse_color_scheme(theme_text, palette),
        "typography": material_type,
        "typeScale": custom_type,
        "shapes": parse_shapes(theme_text),
        **dp_groups,
    }

    components = scan_components(sources, project)

    adapter = {
        "project": project.name,
        "root": str(project),
        "generatedBy": "scan_design_system.py",
        "fingerprint": fingerprint_theme(theme_files, project),
        "theme": theme,
        "components": components,
        "commands": DEFAULT_COMMANDS,
        "tolerance": DEFAULT_TOLERANCE,
        "literalWhitelist": ["0.dp", "1.dp", "0f", "1f"],
        "review": {
            "componentsNeedingReview": [c["name"] for c in components if c["confidence"] == "review"],
            "note": "figmaHints and kind are guesses. Confirm them before trusting mapping output.",
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(adapter, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"wrote {args.out}")
    for group, values in dp_groups.items():
        print(f"  {group:12} {len(values)} tokens")
    scheme_summary = ", ".join(f"{name}:{len(roles)}" for name, roles in theme["colors"].items()) or "none found"
    print(f"  {'palette':12} {len(palette)} colors -> {scheme_summary} scheme roles")
    overridden = sum(1 for s in theme["typography"].values() if s.get("source") == "project")
    print(f"  {'typography':12} {overridden}/{len(theme['typography'])} Material slots overridden "
          f"(rest are M3 defaults) + {len(theme['typeScale'])} project styles")
    print(f"  {'components':12} {len(components)} (all need review)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
