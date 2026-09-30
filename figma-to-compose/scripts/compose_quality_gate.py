#!/usr/bin/env python3
"""Static gate on generated Compose: tokens instead of literals, reuse instead of rewrite.

This runs *before* any screenshot. A hardcoded colour renders perfectly and is invisible to
every visual check in the pipeline — it only shows up when the theme changes or dark mode
ships, and to a human reviewer in five seconds. Catching it costs a second here.

Scope matters: the gate judges the files this pipeline produced, not the whole codebase. A
mature project carries literals the pipeline did not write, and failing on those teaches
people to pass --no-verify. With --baseline it additionally reports the delta against git,
which answers the question review actually asks — did this change make it worse?

Exit codes: 0 pass, 1 gate failed, 2 usage error.

Usage:
    python3 compose_quality_gate.py --project <ROOT> --adapter <ROOT>/.figma/adapter.json \\
            --files app/src/main/java/.../HomeScreen.kt [--baseline HEAD] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DP_LITERAL = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\.dp\b")
SP_LITERAL = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\.sp\b")
COLOR_LITERAL = re.compile(r"Color\(\s*0x[0-9A-Fa-f]{6,8}")
RAW_VALUE_MARKER = re.compile(r"//\s*figma\s+[\w:-]+\s+—\s+no matching token\b")
# A user-facing string is one handed to a text-rendering parameter, not any string at all:
# content descriptions go through stringResource too, but tags, keys and routes do not.
TEXT_LITERAL = re.compile(r'\b(?:Text|BasicText)\s*\(\s*(?:text\s*=\s*)?"([^"]{2,})"')
COMPOSABLE_DECL = re.compile(r"@Composable[^\n]*\n(?:@\w+[^\n]*\n)*\s*(?:internal\s+|private\s+|public\s+)?fun\s+([A-Z]\w*)\s*\(")

DEFAULT_BUDGET = {"dp": 4, "sp": 0, "color": 0, "string": 0}


def strip_noise(source: str) -> str:
    """Blank out comments so their contents are not scanned.

    Replaced with spaces rather than deleted so every offset still maps to the same line in
    the original file — a gate that reports the wrong line number wastes more time than it
    saves.
    """
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    source = re.sub(r"/\*.*?\*/", blank, source, flags=re.S)
    return re.sub(r"//[^\n]*", blank, source)


def scan(path: Path, whitelist: set[str]) -> dict:
    source = path.read_text(encoding="utf-8", errors="replace")
    source_lines = source.splitlines()
    text = strip_noise(source)
    line_at = lambda idx: text[:idx].count("\n") + 1  # noqa: E731

    def is_marked_raw(idx: int) -> bool:
        """Return whether a literal is explicitly traceable to an unmapped Figma node."""
        line_number = line_at(idx)
        return bool(RAW_VALUE_MARKER.search(source_lines[line_number - 1]))

    dp = [
        (m.group(0), line_at(m.start()))
        for m in DP_LITERAL.finditer(text)
        if m.group(0) not in whitelist and not is_marked_raw(m.start())
    ]
    sp = [
        (m.group(0), line_at(m.start()))
        for m in SP_LITERAL.finditer(text)
        if m.group(0) not in whitelist and not is_marked_raw(m.start())
    ]
    colors = [
        (m.group(0), line_at(m.start()))
        for m in COLOR_LITERAL.finditer(text)
        if not is_marked_raw(m.start())
    ]
    strings = [(m.group(1), line_at(m.start())) for m in TEXT_LITERAL.finditer(text)]

    return {
        "file": str(path),
        "dp": dp,
        "sp": sp,
        "color": colors,
        "string": strings,
        "declares": COMPOSABLE_DECL.findall(text),
        "text": text,
    }


def reuse_ratio(text: str, declared: list[str], components: list[dict]) -> dict:
    """How much of this file leans on the design system versus rebuilding it."""
    names = [c["name"] for c in components]
    used = sorted({n for n in names if re.search(rf"\b{re.escape(n)}\s*\(", text)})
    new = [d for d in declared if d not in names]
    # A newly declared composable whose name collides with an adapter component by shape
    # is the duplication this check exists to find.
    shadowed = [d for d in new if any(d.lower().rstrip("0123456789") in n.lower() or n.lower() in d.lower() for n in names)]
    return {"componentsUsed": used, "newComposables": new, "shadowing": shadowed}


def git_baseline(project: Path, rel: str, ref: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(project), "show", f"{ref}:{rel}"],
            capture_output=True, text=True, timeout=20,
        )
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, type=Path)
    ap.add_argument("--adapter", required=True, type=Path)
    ap.add_argument("--files", required=True, nargs="+", help="generated/modified .kt files")
    ap.add_argument("--baseline", help="git ref to compare literal counts against, e.g. HEAD")
    ap.add_argument("--json", type=Path, help="write the full result here")
    args = ap.parse_args()

    project = args.project.resolve()
    try:
        adapter = json.loads(args.adapter.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read adapter: {exc}", file=sys.stderr)
        return 2

    whitelist = set(adapter.get("literalWhitelist", []))
    budget = {**DEFAULT_BUDGET, **adapter.get("literalBudget", {})}
    components = adapter.get("components", [])
    theme_package_path = "/theme/"

    results, failures = [], []
    for name in args.files:
        path = Path(name)
        if not path.is_absolute():
            path = project / name
        if not path.exists():
            print(f"error: {path} does not exist", file=sys.stderr)
            return 2
        if theme_package_path in str(path):
            print(f"skip  {path.name} — theme package is where literals belong")
            continue

        scanned = scan(path, whitelist)
        rel = str(path.relative_to(project))
        entry = {
            "file": rel,
            "counts": {k: len(scanned[k]) for k in ("dp", "sp", "color", "string")},
            "reuse": reuse_ratio(scanned["text"], scanned["declares"], components),
            "violations": {},
        }

        for kind in ("dp", "sp", "color", "string"):
            over = len(scanned[kind]) - budget[kind]
            if over > 0:
                entry["violations"][kind] = [
                    {"value": v, "line": ln} for v, ln in scanned[kind][: budget[kind] + 10]
                ]
                failures.append((rel, kind, len(scanned[kind]), budget[kind]))

        if args.baseline:
            before = git_baseline(project, rel, args.baseline)
            if before is None:
                entry["delta"] = None  # new file, or not tracked at that ref
            else:
                prior = strip_noise(before)
                entry["delta"] = {
                    kind: len(scanned[kind]) - len(pattern.findall(prior))
                    for kind, pattern in (("dp", DP_LITERAL), ("sp", SP_LITERAL), ("color", COLOR_LITERAL), ("string", TEXT_LITERAL))
                }

        results.append(entry)

    for entry in results:
        counts, reuse = entry["counts"], entry["reuse"]
        status = "FAIL" if entry["violations"] else "pass"
        print(f"\n{status}  {entry['file']}")
        print(f"      literals  dp={counts['dp']} sp={counts['sp']} color={counts['color']} string={counts['string']}"
              f"   (budget dp={budget['dp']} sp={budget['sp']} color={budget['color']} string={budget['string']})")
        if "delta" in entry:
            if entry["delta"] is None:
                print(f"      vs {args.baseline}  new file — no baseline to compare")
            else:
                deltas = " ".join(f"{k}{v:+d}" for k, v in entry["delta"].items() if v)
                print(f"      vs {args.baseline}  {deltas or 'no change'}")
        print(f"      reuses    {', '.join(reuse['componentsUsed']) or '(none)'}")
        if reuse["newComposables"]:
            print(f"      declares  {', '.join(reuse['newComposables'])}")
        if reuse["shadowing"]:
            print(f"      ⚠ may duplicate an existing component: {', '.join(reuse['shadowing'])}")
        for kind, items in entry["violations"].items():
            for item in items[:6]:
                print(f"      {kind:6} line {item['line']}: {item['value']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"budget": budget, "files": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if failures:
        print(f"\nGATE FAILED — {len(failures)} budget overruns")
        print("Replace literals with tokens: composerTokens.spacing.*, MaterialTheme.colorScheme.*,")
        print("MaterialTheme.typography.*, stringResource(R.string.*). See references/generation.md.")
        return 1

    print("\nGATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
