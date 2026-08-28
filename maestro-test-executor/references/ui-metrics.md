# UI Metrics: what a screenshot can prove, and how precisely

This is the contract every 🎨 UI test case runs on. Read it before authoring or judging one.

A UI test only earns the name if it can come back **FAIL** on its own. For a long time this skill's UI cases mostly couldn't: spacing was an impression, typography was declared unmeasurable, and text was whatever the model thought it read off the image. Everything landed in 🔍 REVIEW, a human looked at it anyway, and the automation added nothing.

The fix is not "look harder". It is to stop asking the screenshot questions it can't answer and start asking the ones it can — and to ask the *view hierarchy* the rest. That gives two classes of property with two completely different rules.

**These two classes are not all of UI.** They are the part this skill *instruments*. Colour and contrast, corner radius, shadows, icon shape, image cropping, z-order, and whether a control is actually tappable are none of the above: no script here measures them, and a clean run says nothing about any of them. They stay with the cell-by-cell visual scan (`visual-review.md`) and with functional testing. Knowing where the instruments stop is what keeps a PASS honest.

## The contract

| | **Class A — exact** | **Class B — relative** |
|---|---|---|
| **Properties** | Text content; element presence/absence; reading order | Spacing and padding; element sizes; side margins; font size; font weight |
| **Tolerance** | **None.** One character off is a defect | A ratio band (8–14% by default, widened when the inputs can't support it) |
| **Compared as** | String equality | actual ÷ design, plus each element ÷ its own screen's baseline |
| **Read from** | The **view hierarchy** — the strings the app actually renders. Falls back to OCR when there is no device, at reduced authority (below) | **Rendered pixels**, normalized by width |
| **Tool** | `scripts/text_audit.py` | `scripts/spacing_audit.py`, `scripts/typography_audit.py` |
| **Outside the rule** | ❌ FAIL | ❌ FAIL |

Both classes fail hard. That is the point — a measured deviation is not a matter of taste, and filing it as a soft note is how a real single-token layout bug ships.

## Why the split

**Text has no tolerance, so it must not be measured — it must be read.** "Đăng nhập" and "Dang nhap" differ by diacritics and mean different things to a user. "Save" where the design says "Save draft" is a different product. There is no percentage that makes these acceptable, so the only correct comparison is character-for-character equality — and that means reading the actual string from the framework, not recognizing it from pixels. Vision is the wrong instrument here: it silently normalizes what it half-recognizes, and it is least reliable on exactly the small marks that matter most in Vietnamese copy.

**Geometry and typography have no absolute truth in a screenshot, so they must not be read — they must be measured, relatively.** A screenshot has no dp in it. The same screen is 1080 px wide on one device and 1284 on another; a design frame is 390 px at 1x and 1170 at 3x. Every absolute pixel number is an artefact of which device and which export you happened to have. What survives all of that is a **ratio**, and a ratio is exactly what a design parity question is actually asking: *is this gap the size the design says, proportionally? is the title still 1.8× body?* So never claim `24dp` from an image. Claim `1.33× the design's gap` and quote the design px behind it.

### Two ratios, because they fail differently

Every Class B check computes both, and either one going out of band is a finding:

- **Cross-image** — actual ÷ design, after normalizing both to the design's width. Catches *"every gap on this screen is 30% bigger than design"* and *"the whole type scale renders 15% small"*.
- **Intra-screen** — each element ÷ the median of its own screen. Catches *"the heading is supposed to be 1.8× body and renders 1.1×"*. This one never compares a pixel in one image to a pixel in the other, so it is immune to density and export scale entirely.

A screen with a uniformly shrunk type scale passes the intra-screen check and fails the cross-image one. A screen where only the heading lost its style does the reverse. Reporting one without the other misses half the bugs.

### Why width is the shared unit

Both geometry scripts normalize by **width only**. Mobile layouts pin horizontal metrics (side padding, card width, gutters) and let content flow vertically, so width is the honest shared dimension. Forcing the heights to match as well — which is what a naive side-by-side resize does — rescales the design's vertical rhythm onto the device's and normalizes the spacing error out of existence. That is precisely how a 30%-too-loose screen passes a "design comparison" (see the note on `pair_view.py` below).

## Class A — text content, exactly

**Expected strings, best source first:**

1. **Figma MCP, when a `node-id` URL exists.** `get_design_context` on the node returns the frame's structure including its text; `get_variable_defs` returns the tokens behind it. This is the strongest source because the strings are *data*, not something re-read from an image. Save them as a JSON array to `report/figma/TC-XXX_expected.json`.
2. **The test plan / PRD.** When the tester wrote the expected copy into the case, that is authoritative — use it verbatim.
3. **A design PNG, read carefully.** Last resort. You are transcribing, so transcribe conservatively and say in the report that the expected copy came from an image. If a string's diacritics or casing are not legible at the export's resolution, ask rather than guess — a wrong expectation produces a false FAIL that costs more than the question.

**Actual strings: the view hierarchy whenever a device exists.**

```bash
maestro hierarchy > /tmp/screen.json          # or: adb exec-out uiautomator dump /dev/tty > /tmp/screen.xml
python3 scripts/text_audit.py \
    --expected report/figma/TC-010_expected.json \
    --actual /tmp/screen.json \
    --ignore '^\d' --ignore 'đ$' \
    --out report/text/TC-010_default.json
```

Redirect the dump to a file — never let a raw hierarchy into context (see `selectors-and-inspection.md`). The script reads it, compares exactly, and exits 1 on any mismatch.

**Read the result by field:**

| Field | What it means for the verdict |
|---|---|
| `mismatched[].difference` | The *kind* of difference — `diacritics`, `casing`, `whitespace`, `punctuation`, `truncated`, `wording`. Lead the finding with this; "missing Vietnamese diacritics on the login title" is a one-line bug, "expected X got Y" is a puzzle. |
| `missing[]` | Expected copy that isn't on screen at all. Check first whether the flow actually reached the right state — a missing string is often a navigation problem, not a copy problem. |
| `defects[]` | Found without needing an expected list: `truncated` (the string itself ends in an ellipsis), `untranslated_key` (an i18n key leaked to the UI), `off_screen`, `collapsed_bounds`. All Critical. |
| `extra_on_screen[]` | Text the expected list doesn't mention. Informational by default — most of it is live data. Pass `--strict-extra` only on a screen whose copy is fully specified. |
| `ignored_as_dynamic[]` | What your `--ignore` patterns absorbed. Skim it: if a *static* label got ignored, the pattern is too broad and the check has a hole. |

### No device? OCR, with its authority stated

A tester comparing a Figma export against a build screenshot often has two images and nothing else. Under a hierarchy-only rule that review could not check text at all — leaving the one property with *no* tolerance as the only one nobody verified. So `text_audit.py` accepts an image on either side and reads it with tesseract:

```bash
python3 scripts/text_audit.py \
    --expected report/figma/TC-010.png --actual report/screenshots/TC-010.png \
    --ocr-lang vie --out report/text/TC-010_default.json
```

What makes this usable is not the recognizer's accuracy but knowing **which mistakes it can make**. Misreading a whole word takes a gross failure and is rare; misreading an accent, a capital, or a comma takes a few pixels and is routine. So the result splits accordingly, in `mismatched[].decidable`:

| Difference | From OCR | Why |
|---|---|---|
| A missing, extra, or changed **word**; a string absent entirely | **Decidable → ❌ FAIL** | Word-level shapes are what OCR gets right, and this is the defect a device-less review most needs |
| `diacritics`, `casing`, `punctuation`, `whitespace`, `truncated` | **Undecidable → 🔍 REVIEW** | These are exactly OCR's own error modes. Reporting one as a defect spends a developer's afternoon disproving the instrument |
| `line_wrap` — one line holding a neighbour's words | **Undecidable, and usually not a defect** | The design frame and the device are different widths, so the same sentence breaks in different places |

Set `--ocr-lang` to the screen's real language and install the pack; the result carries an `ocr_language_warning` when you didn't, because an English recognizer on Vietnamese copy reports every accent as missing. When the pairing is a close call, `alternative_match` names the runner-up — a guessed pairing files a real defect against the wrong element, which is worse than saying it is ambiguous.

This mode is a lead generator, not a gate. Say in the report that the text came from OCR, and settle anything marked undecidable on a device before filing it.

**The one thing this cannot prove: visibility.** A label ellipsized to `Monstera Delici…` on screen still reports its full text in the hierarchy, because truncation happens at draw time. Text correctness and visual review are two different checks and a UI TC needs both — this settles the content, the screenshot settles whether the user can read it. Say which one proved what.

## Start here: anchor on text, then measure

`scripts/layout_audit.py` is the first thing to run on a design-vs-build comparison. It is not the last: it measures the parts of a screen that carry text, which on a typical screen is most of the copy and none of the pictures.

```bash
# a device is running — exact text, exact boxes
maestro hierarchy > /tmp/screen.json
python3 scripts/layout_audit.py --design report/figma/TC-010.png \
    --actual /tmp/screen.json --actual-image report/screenshots/TC-010.png \
    --design-width-dp 390 --out report/text/TC-010_layout.json

# no device — both sides read from images
python3 scripts/layout_audit.py --design report/figma/TC-010.png \
    --actual report/screenshots/TC-010.png --design-width-dp 390
```

It finds elements by **what they say**, not by what they look like, and that one change removes the entire class of problem the band-based scripts spend their parameters on. "Popular Plants" in the design is the same element as "Popular Plants" in the build — at any size, any position, with any amount of unrelated data around it. So there is no `--roi` to tune, no `--min-gap` to sweep, no chrome to crop: text that has no counterpart simply does not pair, and says so.

Two consequences worth planning around:

- **It is fast, and that is the point.** One run on a real screen takes under a second and needs no follow-up. The band scripts are equally quick to *execute* — the cost was never CPU, it was the human loop of run → read JSON → open a 2 MB composite → adjust a parameter → repeat, which is where a single-screen review used to spend half an hour.
- **Every number names its element.** `gap "Search for plants" -> "Popular Plants": 40 → 61.4 design px (1.53x)` can be checked by reading it. `gap B2-B3` could only be checked by opening a picture.

**What it does not see: anything without text.** An icon row, an image card, a divider, a spacer, a floating action button, a debug overlay — no string, no anchor, not measured. OCR also reads light text on a coloured fill poorly, so a white label on a primary button may not anchor at all. On a real content screen that is a large fraction of the pixels, so treat a clean `layout_audit` run as covering the copy and its spacing, not the screen.

The band scripts stay in the workflow for exactly that remainder, because a band does not care whether a shape is a word: run `layout_audit.py` first for the anchored measurements, then `spacing_audit.py` and `typography_audit.py` over the regions it reports as `unpaired_*`, then the visual scan for what neither measures — clipping, overlap, colour, wrong state.

**Read the `evidence_grade` before filing anything.** From a hierarchy the numbers are framework-exact. From images they are recognizer-grade, and the two do not degrade the same way: a *gap* survives OCR well, because both sides are measured the same way and the error largely cancels, while a typography ratio or a single-character text difference does not. The verdict says which grade produced it, each finding repeats it, and text differences carry the same `decidable` rule `text_audit.py` uses — a missing word fails at any grade, a shifted line break or a stray comma does not.

**Pass the screenshot even when you have the hierarchy.** `--actual-image` is not optional decoration: a hierarchy box is the widget including its line-height padding, while a design export's box is the recognizer's line. Compared directly, a pixel-perfect screen reports a ~25% deficit on every gap — a confident number produced entirely by the two sources disagreeing about where a line of text ends. Given an image for each side, both are reduced to the ink the glyphs actually occupy, which is the one definition they can agree on. `box_semantics` in the result says what each side ended up measuring; when they differ, gaps are demoted to advisory rather than quietly mismeasured.

**Read `authority` before quoting anything.** `exact` means both sides came from a hierarchy. `actual exact, design from OCR` means the build's geometry is exact and the design's is recognized. `both from OCR` means every box traces ink rather than widgets — which is why, in that mode, element heights and side margins are downgraded to advisory: an ink box grows and shrinks with whether the line happens to contain a descender, and failing a build on that would be failing it on the recognizer's habits. Gaps survive, because both sides are measured the same way and the error cancels.

## Class B — spacing, size, weight, relatively

```bash
# geometry: gaps between elements, element heights, side margins
python3 scripts/spacing_audit.py report/figma/TC-010.png report/screenshots/TC-010.png \
    --crop-design-top 6% --crop-actual-top 4% --design-width-dp 390 \
    --out report/grid/TC-010-spacing.png

# typography: font size and font weight, per text band
python3 scripts/typography_audit.py report/figma/TC-010.png report/screenshots/TC-010.png \
    --crop-design-top 6% --crop-actual-top 4% --design-width-dp 390 \
    --out report/grid/TC-010-type.png
```

Both print JSON to stdout and write an annotated PNG. **Read the JSON before the image** — the numbers usually settle the question, and the image is then only needed to name which band is which.

### Tolerances, and why they move

| Property | Default band | Reasoning |
|---|---|---|
| Gap between elements | **±18% *and* ±4 design px** — both must be exceeded | A 2 px slip on a 12 px gap is 17% and still just rounding; a 20% slip on a 90 px gap is 18 px and obvious. Neither threshold alone separates those, so a gap is flagged only when it fails both |
| Element height | Same dual rule, ±18% and ±4 px | A flagged *height* means the element is the wrong size; a flagged *gap* means the space around it is. Different fixes, so they are measured and reported separately |
| Side margin | ±4 design px | Absolute only: side padding is a fixed value in every layout system, so a percentage of it means nothing |
| Font size | ±8% | Type scales step in discrete sizes — 16→18 is +12.5% — so 8% separates adjacent steps while staying above the measurement floor |
| Font weight | ±14% | Stroke thickness is a real but noisier signal than height; anti-aliasing and sub-pixel rendering move it a few percent |
| Systematic ratio | The same band, applied to the median | One number for the whole screen |

Every one of these is a default the script prints back in its own `tolerances` block. When a report quotes a threshold, quote it from that block rather than from this table — a number copied out of prose is the first thing to go stale.

`typography_audit.py` **widens these per band** when the inputs can't support them, and reports the widened value as `size_tolerance_used` / `weight_tolerance_used`. Two things force a widening, and both are worth understanding because both are fixable:

- **The text is too small to read precisely.** An x-height is only as precise as the glyph edges it is measured between, and anti-aliasing smears each edge across about a pixel. On a 1x design export a body-text x-height spans ~7 px, so one pixel per side is already ~14% — wider than any font-size bug worth reporting. The band cannot answer the question.
- **The two images are at different scales.** A 1x design export beside a 3x screenshot is not one measurement repeated; the low-resolution side reads systematically larger and heavier because proportionally more of each glyph is antialiased edge. That bias is not noise and does not average out.

Both vanish when the design is exported near the device's scale. **So export the design at 2x or 3x** (Figma MCP `get_screenshot` / `download_assets` take a scale; a tester-supplied export can be re-exported). `resolution_note` in the JSON says when this is costing you sensitivity, and the difference is real: at 1x-vs-3x a one-step font-size bug is undetectable; at matched scale it flags.

### Reading the geometry result

| Field | How to read it |
|---|---|
| `verdict` | Already phrased for the report. `INCONCLUSIVE` means fix the inputs before quoting anything. |
| `systematic_gap_ratio` / `systematic_size_ratio` | Median across the screen. `1.29` = every gap ~29% too big → **one** finding with one root cause (a wrong spacing token), not fifteen. |
| `gaps[]`, `band_heights[]`, `margin_deviations[]` | Per-element numbers, each carrying its own `flagged` — this is what a developer acts on. All three feed the verdict: a wrong element size fails the case the same way a wrong gap does. |
| `flagged_gap_count` / `flagged_height_count` / `flagged_margin_count` | The quick read. A gap and a height failing on the same band are two different bugs, not one. |
| `tolerances` | The thresholds actually applied. Quote the finding's numbers from here. |
| `bands[].reasons` | Cross-image failures — this element against its own counterpart in the design. Authoritative; quote them. |
| `bands[].secondary_reasons` | Intra-screen failures — this element against the screen's own body text. A lead worth checking, **not** a failure on its own: it depends on a baseline the screen defines, so another element's defect can move it. |
| `bands[].style_run` / `mixed_style_band` | `2/2` means this was the second type style inside one ink band — a caption under its heading, measured on its own. When a band holds more than one style, a single reading would describe neither, and a caption that grew would surface as a phantom *weight* change on the heading. |
| `intra_screen_baseline` | `used`, or declined with a reason. Below four text bands the screen's "body text" median rests on too few readings to judge anything against, so the intra-screen half is skipped rather than guessed. |
| `bands[].weight_confidence` | `high` on a paragraph, `low` on a two-word label. A low-confidence weight finding is an estimate; say so. |
| `unmatched_design` / `unmatched_actual` | Elements with no counterpart. Almost always a **data** difference (empty state vs three cards) — judge from the image, never report as a spacing or typography defect. |
| `matched_bands` / `matched_text_bands` | Under 3 → the verdict says INCONCLUSIVE. Fix the inputs first. |

### When the segmentation is wrong, fix the input — don't quote the number

Both scripts split the screen into horizontal bands of ink separated by empty gaps. When the band boxes in the annotated PNG don't land on elements you'd name out loud, every number downstream is meaningless. Fix in this order:

1. **Crop the chrome.** `--crop-design-*` too — a 390×844 iPhone frame draws its own status bar (~6% top, ~2% bottom).
2. **Mask what bridges a gap.** A FAB, a debug overlay, or a full-bleed photo merges two bands into one: `--mask-actual "60%,88%,100%,100%"`.
3. **Narrow the region.** `--roi-top` / `--roi-bottom` to audit only the part of the screen that has visible separation.
4. **Set the design's logical width.** `--design-width-dp 390` when the export isn't 1x, so the report reads in real dp.
5. **Adjust band merging.** `--min-gap` (spacing_audit defaults to `auto` and prints `min_gap_used`) when a paragraph split per line, or two sections merged.

If it stays inconclusive after that, say so and fall back to visual review. **Never quote a number you don't trust** — a fabricated measurement destroys the report's credibility faster than an honest "couldn't measure".

### What `pair_view.py` does and does not cover

`pair_view.py` answers *"is the right element here, with the right content and style?"* — it crops chrome so cell addresses align, diffs pixels, and flags cells over threshold. It is genuinely useful and its flags are a can't-skip list.

It is also structurally blind to Class B. Aligning cells requires resizing the design on **both** axes, which normalizes uniformly-inflated padding away, and when the two aspect ratios differ (an iOS export vs an Android screen — the normal case) it suppresses its own flags as unreliable. A screen with every gap 30% too big diffs clean and reports nothing. So: a clean `pair_view.py` diff is **not** evidence that spacing or typography is fine. Say "content/style diff clean" and cite the measurements separately.

## What still goes to 🔍 REVIEW

The point of measuring is to shrink this list, not to abolish it. Something belongs in REVIEW when it genuinely wasn't measured:

- A `verdict` of `INCONCLUSIVE`, or a band whose segmentation you don't trust.
- A weight finding at `low` confidence — a two-word label doesn't give enough stems for a stable reading.
- Colour and shade impressions. Nothing here measures colour; `pair_view.py` flags a cell as *different*, not as *the wrong blue*.
- Aesthetic judgement — "the density reads inconsistent but legible", "a designer might tweak this".
- A difference you genuinely can't classify as design or data. Treat it as data (don't FAIL) and note it.

Everything else — a measured ratio outside its tolerance, on sound segmentation, with the data state accounted for — is **Critical → ❌ FAIL**, stated as a number. "Spacing complaints are subjective" was true only while spacing couldn't be measured.

## Before any of this is trustworthy: match the data state

A design mockup shows one chosen, ideal data state. The real app renders whatever this user's data provides. **Those differences are data, not defects**, and failing on them is the fastest way to lose developer trust — the full table is in `visual-review.md` and it governs every measurement here too.

Concretely for Class B: an empty state where the design shows three cards shifts the whole band sequence. The scripts report those as `unmatched_*` rather than as findings, but you still have to read them and confirm that's what happened. Best is to have the flow seed the app into the state the design depicts; second best is to compare only the bands that did match and say so in the report.

## The full UI TC recipe

```text
Maestro flow drives to the screen
   → maestro hierarchy > /tmp/screen.json        (exact text, exact presence)
   → takeScreenshot into report/screenshots/     (geometry + how it renders)
   │
   ├─ text_audit.py        → Class A: any mismatch or defect = FAIL
   ├─ spacing_audit.py     → Class B: gaps / heights / margins outside band = FAIL
   ├─ typography_audit.py  → Class B: size / weight outside band = FAIL
   └─ pair_view.py         → content & style diff, flagged cells to account for
   │
   → account for every flagged item, exclude data-driven differences
   → grid_overlay.py --highlight <cells> → report/vision/<stem>-report.png
   → row in report.md + findings in UI Validation Details
```

Order matters: settle Class A first (it's deterministic and cheap), then the measurements, then read the composite images for what none of them cover — clipping, overlap, wrong state, broken images.

## Writing the finding

Lead with the number, name the location, say which instrument proved it.

```
[Critical] Login title renders without Vietnamese diacritics: expected "Đăng nhập",
  hierarchy reports "Dang nhap" (element id login_title). Text content is exact-match;
  this is a copy/encoding defect, not a rendering one.
  Evidence: report/text/TC-010_default.json

[Critical] All section gaps render ~29% larger than the design (spacing_audit
  systematic_gap_ratio 1.29 over 5 comparable gaps): search→"Popular Plants" 28→36,
  card row→"Your Garden" 24→32 design px. Likely one root cause — a single
  vertical-spacing token. Evidence: report/grid/TC-010-spacing.png

[Critical] B2–C2: screen title renders at 0.67x the design's size and at body weight
  (typography_audit band 0: x-height 14.5→10.1 design px; stroke ratio 0.66,
  confidence high). Relative to body text it is 1.25x where the design uses 1.88x —
  the heading style is not being applied. Evidence: report/grid/TC-010-type.png

[Minor]    Search field renders 4 design px shorter than the design (48→44) —
  measured, inside the noticeable range but not a usability issue.

[Review]   Primary button blue reads slightly darker than the design. Not measured —
  nothing here measures colour. Estimate, for a human to judge.
```

Always include: severity, the location (cell address, or the band/gap id), the measurement, and the evidence path. A developer can act on "gap 24→32 design px (+33%)" in one read; "spacing looks off" sends them back to measure it themselves.
