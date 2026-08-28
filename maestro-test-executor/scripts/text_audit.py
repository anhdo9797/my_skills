#!/usr/bin/env python3
"""Compare on-screen text against the exact strings the design specifies.

WHY THIS EXISTS — the failure it fixes
--------------------------------------
Everything else in this skill's UI validation is a tolerance: spacing within
18%, type size within 8%, "close enough to the design". Text content is the one
property with no tolerance at all. "Đăng nhập" and "Đang nhập" differ by one
diacritic and mean different things. "Save" where the design says "Save draft"
is a different product. A missing accent, a stray capital, a leaked i18n key —
each is a shipped bug, and none of them is a judgement call.

Vision is the wrong instrument for it. Reading strings off a screenshot by eye
is OCR by another name: it silently normalizes what it half-recognizes, it is
least reliable on exactly the small diacritics that matter most in Vietnamese,
and it gives no way to tell "the app renders the wrong string" from "the model
misread the pixels". So the primary source here is the **view hierarchy** — the
strings the app is actually rendering, character for character, straight from
the framework — compared to the expected list with exact equality.

When there is no device, an image can be supplied on either side and is read
with tesseract. That is a deliberate degrade, not an equivalent: the result
marks each difference `decidable` according to whether OCR can settle that kind
of difference at all — a missing word it can, a missing accent it cannot. See
"NO DEVICE" below.

WHAT THIS PROVES, AND WHAT IT DOESN'T
-------------------------------------
The hierarchy proves the string is *correct*. It does not prove the string is
*visible*: a label ellipsized to "Monstera Delici…" on screen still reports its
full text in the hierarchy, because truncation happens at draw time. That is
why text correctness and visual review are two different checks and both are
required — this script settles the content, the screenshot settles whether the
user can actually read it. Neither substitutes for the other, and saying so in
the report is what keeps the verdict honest.

NAMING THE DIFFERENCE, NOT JUST FINDING IT
------------------------------------------
A mismatch reported as "expected X, got Y" makes a developer diff two strings by
eye — and the differences that matter here are the ones the eye is worst at.
So every mismatch is classified by *what kind* of difference it is, by
normalizing both sides one step at a time and reporting the first step that
makes them equal: whitespace, casing, diacritics, truncation, punctuation, or a
genuine wording change. "Missing Vietnamese diacritics" is a one-line bug report
with an obvious cause; "expected 'Đăng nhập', got 'Dang nhap'" is a puzzle.

USAGE
-----
  # capture the hierarchy without it ever entering the agent's context
  maestro hierarchy > /tmp/screen.json
  python3 text_audit.py --expected expected.json --actual /tmp/screen.json

  # Android, via uiautomator
  adb exec-out uiautomator dump /dev/tty > /tmp/screen.xml
  python3 text_audit.py --expected expected.txt --actual /tmp/screen.xml

  # let dynamic content through (prices, counts, timestamps, user names)
  python3 text_audit.py --expected expected.json --actual /tmp/screen.json \\
      --ignore '^\\d+' --ignore 'đ$' --ignore '^@'

`--expected` accepts a JSON array of strings (or of objects with a "text" key —
the shape Figma text nodes come in), or a plain-text file with one string per
line, blank lines and `#` comments skipped.

NO DEVICE
---------
  python3 text_audit.py --expected DESIGN.png --actual SCREENSHOT.png --ocr-lang vie

Word-level differences stay hard failures; character-level ones (accents,
casing, punctuation, whitespace, truncation) are held as undecidable, because
those are precisely OCR's own error modes and reporting one as a defect spends a
developer's afternoon disproving the instrument.

Exit code 0 when every expected string matched exactly, 1 otherwise, so the
check can gate a run. Dependencies: none for the hierarchy path; Pillow and
tesseract only when an input is an image.
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from filter_hierarchy import parse as parse_hierarchy  # noqa: E402


ELLIPSIS = ("…", "...")
# A key that leaked to the UI instead of its translation: dotted, no spaces,
# lowercase — 'home.title', 'errors.network.retry'. Real copy essentially never
# looks like this, and when it does the false positive is one line to dismiss.
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


# ------------------------------------------------------------- normalization

def _strip_diacritics(text):
    """Drop combining marks: 'Đăng nhập' -> 'Dang nhap'.

    Vietnamese needs the Đ/đ special case because it is a distinct letter rather
    than D plus a combining mark, so NFD leaves it untouched and the comparison
    would miss the single most common way Vietnamese copy gets mangled.
    """
    text = text.replace("Đ", "D").replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if not unicodedata.combining(c))


def _collapse_space(text):
    return re.sub(r"\s+", " ", text).strip()


def _strip_ellipsis(text):
    text = text.strip()
    for suffix in ELLIPSIS:
        if text.endswith(suffix):
            return text[: -len(suffix)].strip()
    return text


def _strip_punct(text):
    """Remove punctuation, then re-collapse: dropping the '?' from 'khẩu ?'
    leaves a trailing space that would otherwise make the two sides unequal and
    push a punctuation-spacing difference all the way down to 'wording'."""
    return _collapse_space(re.sub(r"[^\w\s]", "", text, flags=re.UNICODE))


# Ordered from most benign to most substantive. The first rung that makes the
# two strings equal names the defect, which is why the order matters: a string
# that differs in both casing and diacritics is reported as a casing problem
# only if casing alone explains it.
LADDER = [
    ("whitespace", lambda s: _collapse_space(s)),
    ("casing", lambda s: _collapse_space(s).casefold()),
    ("diacritics", lambda s: _strip_diacritics(_collapse_space(s)).casefold()),
    ("truncated", lambda s: _strip_ellipsis(_collapse_space(s)).casefold()),
    ("punctuation", lambda s: _strip_punct(_collapse_space(s)).casefold()),
    ("diacritics+punctuation",
     lambda s: _strip_punct(_strip_diacritics(_collapse_space(s))).casefold()),
]


def _norm_words(text):
    return _strip_diacritics(_collapse_space(text)).casefold()


def _is_wrap(expected, actual, prev_expected="", next_expected="",
             prev_actual="", next_actual=""):
    """True when the two lines hold the same words, split in different places.

    Both sides are read line by line, but a design frame and a device are
    different widths, so the same sentence breaks differently. Compared
    line-for-line that invents two findings — a line that "lost" its tail and
    the next that "gained" it — out of a paragraph whose words are identical.

    The obvious test, "is one string contained in the other", is wrong in the
    most damaging possible way: it also matches a line that simply lost a word.
    `Your Garden` -> `Garden` and `Save draft` -> `Save` both pass containment,
    and both are exactly the copy defects this whole check exists to catch. So
    containment is only the entry condition. The words that differ must then be
    shown to have *moved*, by turning up at the touching edge of the
    neighbouring line on the other side — the tail of a wrapped line reappears
    at the START of the next one, and a word pulled upward reappears at the END
    of the previous one. Words that moved are a wrap; words that vanished are a
    defect.
    """
    e, a = _norm_words(expected), _norm_words(actual)
    if not e or not a or e == a:
        return False

    if e in a:
        # The actual line carries extra words; they must have come from a
        # neighbouring EXPECTED line.
        longer, shorter, others = a, e, (prev_expected, next_expected)
    elif a in e:
        longer, shorter, others = e, a, (prev_actual, next_actual)
    else:
        return False

    before, after = longer.split(shorter, 1)
    before, after = before.strip(), after.strip()
    prev_line, next_line = (_norm_words(others[0]), _norm_words(others[1]))

    # Trailing extra words wrap forward: the neighbour below should begin with
    # them. Leading extra words were pulled up: the neighbour above should end
    # with them.
    if after and next_line.startswith(after):
        return True
    if before and prev_line.endswith(before):
        return True
    return False


def classify(expected, actual, context=None):
    """Name the kind of difference between two strings, or None if identical.

    `context` carries the neighbouring lines on both sides; without it the wrap
    test cannot be made and is skipped rather than guessed, because guessing it
    wrong silently downgrades a missing word to a layout note.
    """
    if expected == actual:
        return None
    if context and _is_wrap(expected, actual, **context):
        return "line_wrap"
    for name, norm in LADDER:
        if norm(expected) == norm(actual):
            if name == "truncated":
                # Only the actual side losing a tail is truncation; the reverse
                # means the app is rendering *more* than the design asked for,
                # which is a copy change, not a clipped label.
                shorter = len(_collapse_space(actual)) < len(_collapse_space(expected))
                return "truncated" if shorter else "wording"
            return name
    return "wording"


def similarity(a, b, lenient=True):
    """How alike two strings are.

    Matching uses the lenient form — accent-blind and case-blind — because the
    whole point is to pair an expected string with its mangled counterpart. The
    number *reported* uses the raw strings, so a diacritic-stripped label does
    not get filed at similarity 1.0 and read as a perfect match.
    """
    if lenient:
        a = _strip_diacritics(_collapse_space(a)).casefold()
        b = _strip_diacritics(_collapse_space(b)).casefold()
    return difflib.SequenceMatcher(None, a, b).ratio()


# -------------------------------------------------------------------- inputs

def load_expected(path, lang="eng", psm=4):
    """Read the expected strings from JSON, a one-per-line text file, or a design image.

    Accepting the design PNG here is what makes a device-less review possible at
    all: with a Figma export and a screenshot and nothing else, both sides go
    through the same recognizer, so the same reading errors land on both and
    largely cancel. What does not cancel is a word the design has and the build
    does not — which is the difference worth catching.
    """
    if path.lower().endswith(IMAGE_SUFFIXES):
        return [item["text"] for item in ocr_image(path, lang, psm)], "ocr"
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()
    stripped = raw.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        data = json.loads(stripped)
        if isinstance(data, dict):
            data = data.get("texts") or data.get("expected") or []
        out = []
        for item in data:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                value = item.get("text") or item.get("characters") or item.get("value")
                if value:
                    out.append(str(value))
        return out, "list"
    return ([line.strip() for line in raw.splitlines()
             if line.strip() and not line.lstrip().startswith("#")], "list")


def _bounds(node):
    """Parse '[x1,y1][x2,y2]' into a tuple, or None when unavailable."""
    match = re.findall(r"-?\d+", node.bounds or "")
    return tuple(int(v) for v in match[:4]) if len(match) >= 4 else None


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

# OCR reads shapes; the hierarchy reads data. That difference is not a matter of
# accuracy but of *which mistakes are possible*, and the split below is the
# whole reason an image-sourced comparison can be trusted at all. Getting a word
# wrong requires misreading a whole shape and is rare; getting an accent, a
# capital, or a comma wrong requires misreading a few pixels and is routine —
# and on a Vietnamese screen without the matching language pack it is close to
# guaranteed. So a word-level difference from OCR is evidence, and a
# character-level one is a question for the hierarchy.
OCR_DECIDABLE = {"wording"}
OCR_UNDECIDABLE = {"diacritics", "casing", "punctuation", "whitespace",
                   "truncated", "line_wrap"}


def _looks_like_text(line):
    """Filter OCR noise: icons and textures come back as short symbol soup."""
    stripped = line.strip()
    if len(stripped) < 3:
        return False
    letters = sum(1 for c in stripped if c.isalpha())
    return letters >= 2 and letters / len(stripped) >= 0.5


def ocr_image(path, lang, psm=4, min_width=1000):
    """Read on-screen strings from an image with tesseract.

    This exists for the review that has a design export and a screenshot and no
    device — the common case when a tester is checking a build against Figma.
    Under the hierarchy-only rule that comparison had no way to check text at
    all, which left the one property with *no* tolerance as the only one nobody
    verified. A degraded check that says how far it can be trusted beats no
    check.

    Small exports are upscaled first: a 1x mobile frame renders body copy at
    ~11 px, below what the recognizer resolves reliably, and feeding it anyway
    produces confident nonsense rather than an honest failure.
    """
    binary = shutil.which("tesseract")
    if not binary:
        raise ValueError(
            "reading text from an image needs tesseract, which is not on PATH.\n"
            "Install it (macOS: brew install tesseract, plus tesseract-lang for "
            "non-English screens), or supply a view hierarchy instead — that is "
            "the exact source and needs no OCR."
        )
    try:
        from PIL import Image
    except ImportError:
        raise ValueError("reading text from an image needs Pillow (pip3 install Pillow)")

    with Image.open(path) as img:
        source = path
        if img.size[0] < min_width:
            scale = min_width / float(img.size[0])
            upscaled = img.convert("RGB").resize(
                (min_width, int(round(img.size[1] * scale))), Image.LANCZOS)
            source = os.path.join(
                tempfile.gettempdir(),
                f"text_audit_{os.path.basename(path)}_{min_width}.png")
            upscaled.save(source)

    result = subprocess.run(
        [binary, source, "stdout", "--psm", str(psm), "-l", lang],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(f"tesseract failed: {result.stderr.strip()[:300]}")

    return [{"text": line.strip(), "bounds": None, "source": "ocr", "id": ""}
            for line in result.stdout.splitlines() if _looks_like_text(line)]


def installed_ocr_languages():
    binary = shutil.which("tesseract")
    if not binary:
        return []
    result = subprocess.run([binary, "--list-langs"], capture_output=True, text=True)
    return [l.strip() for l in result.stdout.splitlines()[1:] if l.strip()]


def load_actual(path, include_accessibility, lang="eng", psm=4):
    """Read on-screen strings from a hierarchy dump, or from an image via OCR.

    Accessibility labels are excluded by default. They are a parallel string
    that screen readers announce, often deliberately worded differently from the
    visible label, so folding them into the same list produces "extra text on
    screen" findings for text nobody can see.
    """
    if path != "-" and path.lower().endswith(IMAGE_SUFFIXES):
        return ocr_image(path, lang, psm), (0, 0)

    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    if not raw.strip():
        raise ValueError("empty hierarchy dump")
    try:
        nodes = parse_hierarchy(raw)
    except (json.JSONDecodeError, ET.ParseError) as exc:
        raise ValueError(f"could not parse hierarchy (not valid JSON or XML): {exc}")

    items, screen = [], [0, 0]
    for node in nodes:
        box = _bounds(node)
        if box:
            screen[0] = max(screen[0], box[2])
            screen[1] = max(screen[1], box[3])
        value = node.text or (node.desc if include_accessibility else "")
        if value and value.strip():
            items.append({
                "text": value,
                "bounds": box,
                "source": "text" if node.text else "accessibility",
                "id": node.rid,
            })
    return items, tuple(screen)


# ------------------------------------------------------------------ matching

def _context(expected, on_screen, idx, node_idx):
    """Neighbouring lines on both sides, in reading order.

    Reading order is what makes the wrap test meaningful: a wrapped tail lands
    on the line immediately below, nowhere else. OCR emits lines top to bottom,
    and the expected list is written in the same order, so plain list adjacency
    is the right notion of neighbour on both sides.
    """
    def at(seq, i, key=None):
        if 0 <= i < len(seq):
            return seq[i][key] if key else seq[i]
        return ""
    return {
        "prev_expected": at(expected, idx - 1),
        "next_expected": at(expected, idx + 1),
        "prev_actual": at(on_screen, node_idx - 1, "text"),
        "next_actual": at(on_screen, node_idx + 1, "text"),
    }


def match(expected, on_screen, ignore_patterns):
    """Pair each expected string with an on-screen string, exact matches first.

    Two passes, and the order is the whole point. Claiming exact matches before
    looking for approximate ones stops a correctly-rendered "Lưu" from being
    consumed as the fuzzy partner of an expected "Luu" while the *actually*
    broken "Luu" elsewhere on screen reports as merely missing — which would
    point the developer at the wrong widget.
    """
    remaining = list(range(len(on_screen)))
    results = [None] * len(expected)

    for idx, want in enumerate(expected):
        for slot, node_idx in enumerate(remaining):
            if on_screen[node_idx]["text"] == want:
                results[idx] = {"status": "exact", "node": node_idx}
                remaining.pop(slot)
                break

    for idx, want in enumerate(expected):
        if results[idx] is not None:
            continue
        scored = sorted(
            ((similarity(want, on_screen[n]["text"]), slot, n)
             for slot, n in enumerate(remaining)),
            key=lambda t: t[0], reverse=True)
        best_score, best, _ = scored[0] if scored else (0.0, None, None)
        runner_up = scored[1] if len(scored) > 1 else None
        # Below ~0.6 the "closest" string is unrelated, and quoting it as a near
        # miss sends the reader chasing a coincidence instead of the real gap.
        if best is not None and best_score >= 0.6:
            node_idx = remaining.pop(best)
            # A near-tie means the pairing is a guess, and a guessed pairing
            # produces a finding filed against the wrong element — the most
            # expensive kind of wrong, because it sends someone to inspect a
            # widget that is fine. Naming the alternative lets the reader settle
            # it at a glance instead of trusting the sort order.
            alternative = None
            if runner_up and best_score - runner_up[0] < 0.12:
                alternative = on_screen[runner_up[2]]["text"]
            results[idx] = {
                "status": "mismatch",
                "node": node_idx,
                "similarity": round(
                    similarity(want, on_screen[node_idx]["text"], lenient=False), 3),
                "difference": classify(
                    want, on_screen[node_idx]["text"],
                    _context(expected, on_screen, idx, node_idx)),
                "alternative_match": alternative,
            }
        else:
            results[idx] = {"status": "missing", "node": None}

    ignored = []
    extra = []
    for node_idx in remaining:
        text = on_screen[node_idx]["text"]
        if any(p.search(text) for p in ignore_patterns):
            ignored.append(text)
        else:
            extra.append(text)
    return results, extra, ignored


def find_defects(on_screen, screen_size, degraded=False):
    """Content defects visible in the source itself, expected list or not.

    `degraded` marks the whole set as OCR-sourced. It matters most for the
    truncation check: an ellipsis is a handful of dark pixels, so a recognizer
    both invents them and misses them, and an OCR-read `...` is the same class
    of evidence the policy already refuses to decide on elsewhere. Counting it
    as a hard defect anyway is how a live, deliberately-truncated plant name
    fails a build.
    """
    defects = []
    width, height = screen_size
    for item in on_screen:
        text = item["text"]
        if text.strip().endswith(ELLIPSIS):
            defects.append({
                "type": "truncated",
                "text": text,
                "decidable": not degraded,
                "note": ("the rendered string itself ends in an ellipsis, so the "
                         "content is cut before it reaches the view")
                        if not degraded else
                        ("read from an image: an ellipsis is a few pixels, which "
                         "OCR both invents and misses, and truncated text is "
                         "routinely intentional on a live list. Confirm on the "
                         "device before filing"),
            })
        if KEY_PATTERN.match(text.strip()):
            defects.append({
                "type": "untranslated_key",
                "text": text,
                "decidable": not degraded,
                "note": "looks like a translation key that leaked to the UI",
            })
        box = item["bounds"]
        if box:
            x1, y1, x2, y2 = box
            if x2 <= x1 or y2 <= y1:
                defects.append({
                    "type": "collapsed_bounds", "text": text, "decidable": True,
                    "note": f"element has zero area at {box} — present in the tree "
                            f"but nothing is drawn",
                })
            elif width and height and (x2 > width + 1 or y2 > height + 1 or x1 < -1):
                defects.append({
                    "type": "off_screen", "text": text, "decidable": True,
                    "note": f"box {box} extends past the {width}x{height} screen",
                })
    return defects


def check_order(expected, results, on_screen):
    """Report expected strings that render out of their specified order.

    Reading order is content: a screen that shows the price above the product
    name says something different from one that shows it below, even though both
    contain the same strings. Only strings that were matched can be ordered, and
    the check is skipped rather than guessed at when fewer than three were.
    """
    placed = [
        (idx, on_screen[r["node"]]["bounds"])
        for idx, r in enumerate(results)
        if r and r["node"] is not None and on_screen[r["node"]]["bounds"]
    ]
    if len(placed) < 3:
        return []
    # Sort by rendered position, top to bottom then left to right.
    rendered = sorted(placed, key=lambda p: (p[1][1], p[1][0]))
    rendered_order = [idx for idx, _ in rendered]
    expected_order = sorted(rendered_order)
    if rendered_order == expected_order:
        return []
    out = []
    for position, idx in enumerate(rendered_order):
        if expected_order[position] != idx:
            out.append({
                "text": expected[idx],
                "expected_position": idx + 1,
                "rendered_position": position + 1,
            })
    return out


# ---------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(
        description="Compare on-screen text against the exact expected strings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--expected", required=True,
                   help="JSON array of strings/objects, one string per line, or a "
                        "design image (read with OCR — see --ocr-lang)")
    p.add_argument("--actual", required=True,
                   help="view-hierarchy dump (Maestro JSON or uiautomator XML), "
                        "'-' to read stdin, or a screenshot (read with OCR). The "
                        "hierarchy is exact; an image is a degraded fallback for "
                        "when there is no device")
    p.add_argument("--ocr-lang", default="eng",
                   help="tesseract language for image inputs (default eng). Use the "
                        "screen's real language — 'vie' for Vietnamese — and install "
                        "the pack, or accents will be misread as defects")
    p.add_argument("--ocr-psm", type=int, default=4,
                   help="tesseract page-segmentation mode for image inputs "
                        "(default 4, one column of variable-size text)")
    p.add_argument("--ignore", action="append", default=[], metavar="REGEX",
                   help="on-screen text matching this is dynamic, not unexpected "
                        "(repeatable)")
    p.add_argument("--strict-extra", action="store_true",
                   help="fail when the screen shows text the expected list omits")
    p.add_argument("--check-order", action="store_true",
                   help="also verify the expected strings render in order")
    p.add_argument("--include-accessibility", action="store_true",
                   help="also compare accessibility labels, not just visible text")
    p.add_argument("--out", default=None, help="write the JSON result here too")
    args = p.parse_args()

    try:
        expected, expected_source = load_expected(
            args.expected, args.ocr_lang, args.ocr_psm)
        on_screen, screen_size = load_actual(
            args.actual, args.include_accessibility, args.ocr_lang, args.ocr_psm)
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2
    if not expected:
        sys.stderr.write("ERROR: the expected list is empty — nothing to verify.\n")
        return 2

    actual_source = "ocr" if any(i["source"] == "ocr" for i in on_screen) else "hierarchy"
    degraded = "ocr" in (expected_source, actual_source)

    patterns = [re.compile(pat) for pat in args.ignore]
    results, extra, ignored = match(expected, on_screen, patterns)
    defects = find_defects(on_screen, screen_size, degraded)
    order_issues = check_order(expected, results, on_screen) if args.check_order else []

    mismatches, missing = [], []
    for idx, result in enumerate(results):
        if result["status"] == "mismatch":
            node = on_screen[result["node"]]
            kind = result["difference"]
            # An OCR-sourced difference is only trustworthy when it is a whole
            # word: the recognizer's own errors live in accents, capitals, and
            # punctuation, so a character-level "defect" read off pixels is at
            # least as likely to be the tool misreading as the app misbehaving.
            # Reporting it as a failure would spend a developer's afternoon
            # disproving the instrument.
            decidable = (not degraded) or kind in OCR_DECIDABLE
            mismatches.append({
                "expected": expected[idx],
                "actual": node["text"],
                "difference": kind,
                "similarity": result["similarity"],
                "element_id": node["id"] or None,
                "bounds": node["bounds"],
                "source": node["source"],
                "alternative_match": result.get("alternative_match"),
                "decidable": decidable,
                "note": None if decidable else
                        f"a {kind} difference cannot be decided from OCR — capture "
                        f"the view hierarchy on the device to settle it",
            })
        elif result["status"] == "missing":
            missing.append({"expected": expected[idx]})

    exact = sum(1 for r in results if r["status"] == "exact")
    decided = [m for m in mismatches if m["decidable"]]
    undecided = [m for m in mismatches if not m["decidable"]]

    # `missing` survives the degrade: a whole string the recognizer never saw is
    # a word-level observation, and it is the very defect a device-less review
    # most needs to catch.
    hard_defects = [d for d in defects if d.get("decidable", True)]
    soft_defects = [d for d in defects if not d.get("decidable", True)]
    failed = bool(decided or missing or hard_defects or order_issues
                  or (args.strict_extra and extra))

    if not failed and not undecided and not soft_defects:
        verdict = (f"PASS — all {exact} expected strings render exactly, "
                   f"character for character.")
    elif not failed:
        held = sorted({m["difference"] for m in undecided}
                      | {d["type"] for d in soft_defects})
        verdict = (f"REVIEW — {exact} strings match; "
                   f"{len(undecided) + len(soft_defects)} observation(s) OCR cannot "
                   f"decide ({', '.join(held)}). Capture the view hierarchy to "
                   f"settle them.")
    else:
        parts = []
        if decided:
            kinds = sorted({m["difference"] for m in decided})
            parts.append(f"{len(decided)} wrong ({', '.join(kinds)})")
        if missing:
            parts.append(f"{len(missing)} not on screen")
        if hard_defects:
            parts.append(f"{len(hard_defects)} content defect(s)")
        if order_issues:
            parts.append(f"{len(order_issues)} out of order")
        if args.strict_extra and extra:
            parts.append(f"{len(extra)} unexpected")
        verdict = (f"FAIL — {'; '.join(parts)}. Text content has no tolerance: "
                   f"every one of these is a defect, not a judgement call.")
        if undecided or soft_defects:
            verdict += (f" A further {len(undecided) + len(soft_defects)} "
                        f"observation(s) need the view hierarchy — see "
                        f"mismatched[].decidable and defects[].decidable.")

    result = {
        "verdict": verdict,
        "exact": exact,
        "expected_count": len(expected),
        "mismatched": mismatches,
        "missing": missing,
        "defects": defects,
        "out_of_order": order_issues,
        "extra_on_screen": extra,
        "ignored_as_dynamic": ignored,
        "screen_size": list(screen_size),
        "sources": {"expected": expected_source, "actual": actual_source},
        "note": "The hierarchy proves the string is correct, not that it is "
                "visible — a label ellipsized on screen still reports its full "
                "text here. Pair this with the visual review.",
    }

    if degraded:
        langs = installed_ocr_languages()
        result["ocr_note"] = (
            "At least one side was read from an image, so this is a degraded "
            "check: word-level differences (a missing or changed word) are "
            "reported as defects, while character-level ones (accents, casing, "
            "punctuation, whitespace, truncation) are held as undecided because "
            "they are also what OCR gets wrong. Capture the view hierarchy on "
            f"the device for an exact answer. Language used: {args.ocr_lang}; "
            f"installed: {', '.join(langs) or 'unknown'}."
        )
        if args.ocr_lang not in langs:
            result["ocr_language_warning"] = (
                f"'{args.ocr_lang}' is not installed, so tesseract fell back and "
                f"every reading is suspect. Install the pack (macOS: brew install "
                f"tesseract-lang) before trusting any of this."
            )

    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload)
    print(payload)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
