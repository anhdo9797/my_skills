#!/usr/bin/env python3
"""Shared unit handling for the geometry audits: everything in dp, one tolerance.

WHY THIS EXISTS
---------------
The audits used to state their tolerances in "design px" — the pixels of
whatever export the tester happened to supply. On a 1x export that is dp; on a
3x export the same "4 px" is 1.3 dp, below anti-aliasing noise, so every clean
screen flagged. The companion rule (±18% as well) then went the other way: on a
90 dp gap nothing under 16 dp could fail. The numbers were precise and the
verdicts were not.

The fix is to pick one unit a designer and a developer both read — dp, the
Figma 1x pixel — and one tolerance in that unit:

1. **Density-independent scaling.** Each side is converted to dp by its OWN
   density (design export scale, device density), so resolution cancels out
   and a 360 dp phone is not stretched to a 390 dp frame. Native and Flutter
   layouts keep spacing fixed in dp across phone widths, so stretching by width
   would turn a correct 100 dp gap into "108 dp" — a false failure.
   (`--scale-mode width` restores the old stretch for layouts that really do
   scale with the screen width.)
2. **Absolute band.** A gap, height or margin fails when it differs from the
   design by more than TOLERANCE dp (default 8). No percentage gate by default.

When the design's logical width is not given, it is inferred from the export
width (1170 px -> 3x of 390 dp) and the result says so, because a wrong
inference scales every number — check `design_width_dp` in the output.
"""

import re
import shutil
import subprocess

DEFAULT_TOLERANCE_DP = 8.0

# Logical widths of the frames Figma offers and phones actually report.
COMMON_FRAME_WIDTHS_DP = (320, 360, 375, 384, 390, 393, 400, 402, 411, 412,
                          414, 428, 430, 440)


DESIGN_SCALES = (1, 1.5, 2, 3, 4)
# Android densities that phones actually ship with (Pixel 2.625x, many 2.75x).
DEVICE_SCALES = (1, 1.5, 2, 2.625, 2.75, 3, 3.5, 4)


def infer_width_dp(px_width, scales=DESIGN_SCALES, what="design"):
    """Guess a logical width from a pixel width.

    Tries each scale and keeps the one whose logical width lands closest to a
    real phone frame. Returns (width_dp, scale, note). When two scales both fit
    (1080 px = 360 dp @3x or 411 dp @2.625x) the note says so — that choice
    moves every number by 14%, so it must be settled from the device.
    """
    fits = []
    for scale in scales:
        logical = px_width / scale
        nearest = min(COMMON_FRAME_WIDTHS_DP, key=lambda w: abs(w - logical))
        fits.append((abs(nearest - logical) / nearest, scale, logical))
    fits.sort(key=lambda f: (round(f[0], 3), f[1] != int(f[1]), f[1]))
    err, scale, logical = fits[0]
    if err > 0.03:
        return float(px_width), 1.0, (
            f"{what} width {px_width}px matches no phone frame; assumed 1x. "
            f"Pass --{what}-width-dp if that is wrong.")
    note = (f"{what} width inferred as {logical:g} dp ({px_width}px at {scale:g}x). "
            f"Pass --{what}-width-dp to override.")
    others = [f for f in fits[1:] if f[0] < 0.01 and abs(f[2] - logical) > 2]
    if others:
        alt = ", ".join(f"{f[2]:.0f} dp @{f[1]:g}x" for f in others)
        note += (f" AMBIGUOUS: also fits {alt}. Read the real value "
                 f"(Android: adb shell wm size + wm density -> px*160/density).")
    return round(logical, 1), float(scale), note


def infer_design_width_dp(px_width):
    """Design exports use integer-ish scales (1x/2x/3x)."""
    return infer_width_dp(px_width, DESIGN_SCALES, "design")


def resolve_design_width_dp(px_width, given):
    """Return (width_dp, source_note) using the explicit value when given."""
    if given:
        return float(given), "given"
    width_dp, _, note = infer_design_width_dp(px_width)
    return width_dp, note


def _adb_value(args, key):
    out = subprocess.run(["adb", "shell", "wm"] + args, capture_output=True,
                         text=True, timeout=5).stdout
    found = dict(re.findall(r"(Physical|Override) " + key + r": (\S+)", out))
    return found.get("Override") or found.get("Physical")


def adb_width_dp(px_width):
    """Read the connected Android device's real dp width, when it IS this screenshot.

    Only trusted when `adb` reaches exactly one device and that device's pixel
    width equals the screenshot's (either orientation) — otherwise the density
    belongs to some other screen. Returns (width_dp, note) or (None, None).
    """
    if not shutil.which("adb"):
        return None, None
    try:
        size = _adb_value(["size"], "size")
        density = _adb_value(["density"], "density")
    except (subprocess.SubprocessError, OSError):
        return None, None
    if not size or not density:
        return None, None
    try:
        w, h = (int(v) for v in size.split("x"))
        dpi = float(density)
    except ValueError:
        return None, None
    for dev_px in (w, h):
        if abs(dev_px - px_width) <= 2:
            width_dp = round(dev_px * 160.0 / dpi, 1)
            return width_dp, (f"actual width read from adb: {dev_px}px at "
                              f"{dpi:g} dpi = {width_dp:g} dp")
    return None, None


def resolve_actual_width_dp(px_width, given):
    """Same for the device screenshot, which may use fractional densities.

    Order: explicit value -> the connected Android device via adb (when its
    pixel width matches) -> inference from the pixel width (may be ambiguous).
    """
    if given:
        return float(given), "given"
    width_dp, note = adb_width_dp(px_width)
    if width_dp:
        return width_dp, note
    width_dp, _, note = infer_width_dp(px_width, DEVICE_SCALES, "actual")
    return width_dp, note


def out_of_tolerance(design_dp, actual_dp, tol_dp, tol_pct=0.0):
    """True when |actual - design| exceeds tol_dp (and tol_pct, if one is set).

    tol_pct defaults to 0 = off: the band is a fixed number of dp. Setting it
    restores the old dual rule (both must be exceeded) for anyone who wants it.
    """
    if design_dp is None or actual_dp is None:
        return False
    delta = abs(actual_dp - design_dp)
    if delta <= tol_dp:
        return False
    if tol_pct and design_dp:
        return delta / design_dp > tol_pct
    return True
