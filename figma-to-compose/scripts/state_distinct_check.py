#!/usr/bin/env python3
"""Prove each captured state is actually a different state.

A screen with four tabs needs four captures that differ. In a real run two of them came
back **byte-identical** — a tab tap had missed, the app never left the previous state, and
the report counted them as two states anyway. Nothing in the pipeline noticed; the only
reason it surfaced was someone running `md5` by hand afterwards.

That is the cheapest possible defect to detect and it reached a final report, so it belongs
in the process rather than in someone's habits.

    python3 state_distinct_check.py --dir device/
    python3 state_distinct_check.py --dir device/ --expect for-you your-turn answered completed

Two failures are reported, and they are different problems:

* **identical** — the same bytes twice. The navigation did not happen at all.
* **near-identical** — different bytes, visually the same frame. Usually the clock or a
  battery pixel moved while the UI underneath never changed. A byte comparison alone calls
  this a pass, which is how a missed tap hides behind a status-bar tick.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is optional
    Image = None

THUMB = 64


def digest(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> list[int] | None:
    """A 64x64 grayscale thumbnail, as a flat list — enough to see 'same frame'."""
    if Image is None:
        return None
    with Image.open(path) as im:
        return list(im.convert("L").resize((THUMB, THUMB), Image.BILINEAR).getdata())


def mean_abs_diff(a: list[int], b: list[int]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fail when two captured states are the same screen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--dir", type=Path, help="directory of capture PNGs")
    ap.add_argument("--files", type=Path, nargs="*", default=[], help="explicit capture list")
    ap.add_argument("--expect", nargs="*", default=[],
                    help="state names that must each have a capture (stem match)")
    ap.add_argument("--map", nargs="*", default=[], metavar="STATE=DESIGN.PNG",
                    help="pair each state with its Figma baseline, e.g. "
                         "for-you=raw/5_8469/design.png your-turn=raw/5_8536/design.png. "
                         "With this, difference is judged as a ratio against what the design "
                         "itself demands — the only judgement that holds when two states are "
                         "meant to look similar.")
    ap.add_argument("--min-ratio", type=float, default=0.30,
                    help="fail when the device shows less than this fraction of the "
                         "difference the design draws between two states (default 0.30)")
    ap.add_argument("--near-threshold", type=float, default=1.5,
                    help="fallback only, used when --map is absent: mean 0-255 grey "
                         "difference below which two captures are called the same frame. "
                         "Absolute thresholds cannot tell a failed tap from two states the "
                         "design genuinely draws alike, so this reports as advisory.")
    args = ap.parse_args()

    files = sorted(args.files)
    if args.dir:
        files += sorted(p for p in args.dir.glob("*.png"))
    files = sorted(set(files))

    if not files:
        print("error: no capture files found — pass --dir or --files", file=sys.stderr)
        return 2

    failures: list[str] = []

    missing = [name for name in args.expect
               if not any(name == f.stem or f.stem.startswith(name) for f in files)]
    if missing:
        failures.append(f"no capture for: {', '.join(missing)}")

    digests: dict[str, list[Path]] = {}
    for f in files:
        digests.setdefault(digest(f), []).append(f)

    print(f"{len(files)} captures in {args.dir or 'the given list'}")
    for d, group in sorted(digests.items(), key=lambda kv: kv[1][0].name):
        names = ", ".join(p.name for p in group)
        print(f"  {d[:12]}  {names}")
        if len(group) > 1:
            failures.append(
                f"identical bytes: {names} — these are one screen, not {len(group)}. "
                f"The navigation between them did not happen."
            )

    if Image is None:
        print("  note: Pillow not installed — near-identical detection skipped")
    else:
        prints = {f: fingerprint(f) for f in files}
        mapping = {}
        for pair in args.map:
            state, _, design = pair.partition("=")
            p = Path(design)
            if p.exists():
                mapping[state] = fingerprint(p)
            else:
                failures.append(f"--map baseline not found: {design}")

        def state_of(path: Path) -> str | None:
            return next((s for s in mapping if path.stem == s or path.stem.startswith(s)), None)

        if mapping:
            print("\n  state difference, device vs what the design demands:")
        seen: set[tuple[str, str]] = set()
        for i, a in enumerate(files):
            for b in files[i + 1:]:
                if digest(a) == digest(b):
                    continue  # already reported as identical
                key = tuple(sorted((a.name, b.name)))
                if key in seen:
                    continue
                seen.add(key)
                diff = mean_abs_diff(prints[a], prints[b])

                sa, sb = state_of(a), state_of(b)
                if mapping and sa and sb:
                    want = mean_abs_diff(mapping[sa], mapping[sb])
                    ratio = diff / want if want > 0.01 else 1.0
                    print(f"    {a.name:22} vs {b.name:22} device {diff:5.2f} · "
                          f"design {want:5.2f} · ratio {ratio:.2f}")
                    if ratio < args.min_ratio:
                        failures.append(
                            f"{a.name} vs {b.name}: the design draws these {want:.2f} apart and "
                            f"the device shows {diff:.2f} — {ratio:.0%} of the expected "
                            f"difference. The transition between them did not fully happen."
                        )
                elif not mapping and diff < args.near_threshold:
                    print(
                        f"  advisory: {a.name} vs {b.name} differ by {diff:.2f}/255 mean grey. "
                        f"Different bytes, nearly the same frame — but without --map this "
                        f"cannot tell a failed tap from two states the design draws alike. "
                        f"Re-run with --map before believing or dismissing it."
                    )

    if failures:
        print("\nSTATE DISTINCTNESS FAILED")
        for f in failures:
            print(f"  · {f}")
        print(
            "\nRe-drive the navigation and re-capture. Do not raise the threshold, and do not\n"
            "report a state you did not actually reach."
        )
        return 1

    print("\nSTATE DISTINCTNESS PASSED — every capture is a different screen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
