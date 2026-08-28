# Tier 3 — Visual Review from Screenshots (grid-assisted vision)

Tier 1 assertions prove an element is *technically present*. Tier 2 proves the pixels didn't *drift from an approved baseline*. Neither can tell you that a title is clipped, two labels overlap, a button runs off the screen edge, or the empty state is misaligned — defects a person spots in half a second but `assertVisible` sails straight past, and that a first-ever run has no baseline to diff against.

Tier 3 closes that gap: the Agent **looks at the screenshot** and judges the layout. To keep that judgment systematic instead of one impressionistic glance, `scripts/grid_overlay.py` stamps a labeled grid over the image first, so the review walks the screen cell by cell and every finding carries an address (`C3`, `A6:F8`) that a reviewer — or the bug-logging phase — can find again.

## When to reach for Tier 3 (and when not to)

Tier 3 needs the Agent, so it is deliberately **not** in the automated regression loop. Use it when:

- **The tester asks for a visual/design QA pass** — *"kiểm tra giao diện từng màn hình"*, *"test UI bằng ảnh chụp"*, *"xem có tràn chữ / lệch layout không"*, "review this screen against the design". This is the main case: they want eyes on the screen, not a green checkmark.
- **There is no baseline yet** — the very first UI run for a screen. Tier 2 needs an approved baseline; Tier 3 needs nothing but the screenshot.
- **Authoring a UI TC** — the same pass that extracts Tier 1 assertions is also the moment to catch layout defects, and to decide whether the screenshot is clean enough to promote to a Tier 2 baseline.
- **Tier 2 reported drift and you need to know *why*.** The heatmap says *where* pixels changed; vision says *what* changed and whether it matters.
- **The screen is too dynamic to baseline.** A feed whose content changes every run can't be pixel-diffed, but it can still be judged for overlap, truncation, and alignment.

Don't run Tier 3 on functional TCs that already passed — a clean `assertVisible` doesn't need eyes on it, and every screenshot read costs thousands of tokens. Don't re-run it each session on a UI TC that already passed and hasn't changed; the recorded verdict stands (see "Across sessions" below).

## What vision is for here — and what it must not be asked

Vision **estimates**; it does not **measure**, and it does not **read**. Both of those jobs belong to instruments, and handing them to vision is what used to make UI cases unfailable. Split the screen's properties three ways before you judge anything (`ui-metrics.md` is the full contract):

| Question | Instrument | Vision's role |
|---|---|---|
| Is this the right text? | `text_audit.py` against the **view hierarchy** — exact string equality | none: never transcribe copy from pixels |
| Is this gap / size / weight right? | `spacing_audit.py`, `typography_audit.py` — **ratios**, measured | none: never estimate a value a script measured |
| Does it *look* right on screen? | **Vision**, cell by cell | all of it — this is the part only eyes can do |

What's left for vision is the part it's genuinely good at, and it is a large part:

- **It reliably catches** gross layout defects: overlapping elements, text truncated or clipped by its container, content running off-screen, obvious misalignment, an element missing or in the wrong region, the wrong screen state (a stuck spinner where loaded content was expected, an error banner instead of success), unreadable contrast, a broken/unloaded image placeholder.
- **It is the only check for whether text is *visible*.** The hierarchy proves a string is correct; it cannot prove the user can read it, because a label ellipsized on screen still reports its full text. That defect is visible only in the image.
- **It only sees what rendered.** Content below the fold, and states gated behind data or permissions, must be driven into view by the Maestro flow first (scroll, seed data) or they simply cannot be reviewed.
- **Rendering context colours perception.** Status bar, system font scaling, locale, dynamic data, and device density all change pixels. Record the device profile with every verdict so a "defect" isn't just a different emulator.
- **It cannot claim a value.** No `dp`, no `sp`, no hex. Where a script measured it, quote the script. Where nothing measured it — colour shade, overall density — say "estimate" and mark it 🔍 REVIEW.

Say which is which in the finding: an overlap is a **confirmed** defect; a quoted ratio is a **measurement**; "this blue reads darker" is an **estimate**.

## The biggest false FAIL: data state vs. design state

A design mockup shows the screen in **one chosen, ideal data state** — a grid packed with items, curated studio photos, tidy short names. The real app renders whatever the **API and this user's data** currently provide: maybe one item instead of six, real user photos, longer names, a different badge count. **Those differences are data, not design defects.** Failing a case on them is the single most common way a visual comparison goes wrong, and it burns developer trust fast.

Before comparing, sort each difference:

| Data-driven — **not** a defect | Design defect — **still counts** |
|---|---|
| Number of items shown | Overlap, clipping, truncation of a label that fits in the design |
| One column vs. two *because there are fewer items* | An element in the wrong place or wrong order |
| Specific names, text, photos, avatars | A **static** element present in the design but missing on device (a header illustration, a control) |
| Counts, badges, prices, dates | Broken spacing or alignment; wrong color/typography treatment |
| A section empty because the user has no data there | Content running off-screen; unreadable contrast |

Two ways to keep the comparison fair, best first:

1. **Match the data state** — have the flow seed the app into the state the design depicts, so remaining differences are real. Note the seeded state in the TC.
2. **Compare state-agnostic properties only** — when you can't match it, explicitly ignore count/content/columns-from-count and judge only the data-independent properties. Say so in the report: *"compared layout and style only; item count differs due to user data, excluded."*

When you genuinely can't tell whether a difference is data or design, **treat it as data (don't FAIL)** and note it for review. The design may also simply be an older iteration than the shipped screen.

**The app being *more* complete than the design usually means a stale baseline, not a bug.** If the app shows a real element the design lacks (a hero image, a new control), the likely cause is that the export or Figma node predates the shipped screen — verdict **PASS**, and recommend refreshing the baseline. The reverse (design has something the app is missing) is the one that usually is a real defect.

The three-band chrome rule from `ui-validation.md` applies here too: ignore the status bar and the OS navigation bar; an **app-owned** tab bar that appears in the design *is* design and gets compared.

## Where the files live

Everything stays under the feature's `report/` folder — `takeScreenshot: <bare-name>` writes to wherever Maestro was launched from (usually the repo root), so either point the flow at the `screenshots/` path or move the file there right after the run, before gridding.

```
.maestro/<app-id>/<feature>/report/
├── screenshots/   ← clean device captures from takeScreenshot
├── figma/         ← design references (export at 2x/3x) + TC-XXX_expected.json copy lists
├── text/          ← text_audit.py results: the exact-string comparison JSON
├── grid/          ← what the review reads: <stem>-grid.png (heuristic), or
│                    <stem>-pair.png / -spacing.png / -type.png (design mode)
└── vision/        ← annotated result images, defect cells washed red — the deliverable
```

Pair files by the same `TC-XXX_<state>` stem across folders so the set is obvious at a glance:
`figma/TC-010_default.png` ↔ `screenshots/TC-010_default.png` ↔ `text/TC-010_default.json` ↔ `grid/TC-010_default-pair.png` ↔ `vision/TC-010_default-report.png`.

## Getting the design reference (design mode)

Two sources, both ending as a PNG in `report/figma/`, after which the comparison is identical:

- **Tester-supplied export.** They drop design PNGs somewhere in the workspace. Record each screen's reference path in the TC so the pairing is explicit — don't force a rename; the plan carries the mapping (`TC-010 → figma/Home iOS - default.png`).
- **Figma node.** Given a Figma URL with a `node-id`, render it with the Figma MCP `get_screenshot` and save into `report/figma/`. Pull `get_design_context` too when you need exact copy/text detail. Keep the node id in the TC for traceability. If the URL has **no** `node-id`, ask for the node-specific URL before claiming design parity — a whole-file URL doesn't identify which frame to compare.

**No reference available? Run in heuristic mode** — judge the screen on its own against the checklist below. Never invent a design to compare against.

## The pipeline

```text
[design mode]
Maestro drives to the screen
   → maestro hierarchy > /tmp/screen.json      (the exact strings the app renders)
   → takeScreenshot into report/screenshots/   (clean, no grid)

   → text_audit.py --expected …_expected.json --actual /tmp/screen.json
        (EXACT string equality; names each difference: diacritics / casing /
         truncated / wording)                       → report/text/<stem>.json
   → spacing_audit.py design.png actual.png …
        (scales by WIDTH only, segments both into element bands, MEASURES every
         gap / height / margin in design px-dp)     → report/grid/<stem>-spacing.png + JSON
   → typography_audit.py design.png actual.png …
        (MEASURES font size and stroke weight per text band, as ratios — both
         against the design and against the screen's own body text)
                                                    → report/grid/<stem>-type.png + JSON
   → pair_view.py design.png actual.png --crop-actual-top/--bottom …
        (crops chrome so cell addresses align, diffs pixels, flags cells over
         threshold, composes ONE side-by-side image)  → report/grid/<stem>-pair.png

   → read the three JSONs FIRST (they are numbers, not images, and they settle
     most of the verdict), then the composites: account for every flagged gap,
     band, and cell, then finish the checklist scan on the rest
   → classify each finding Critical / Minor, naming the exact cell(s)
   → severity → verdict (❌ FAIL / 🔍 REVIEW / ✅ PASS)
   → if any defect: grid_overlay.py --highlight <cells> → report/vision/<stem>-report.png
   → one row in report.md + findings in UI Validation Details (+ Failed Test Details if FAIL)

[heuristic mode — no design reference]
Maestro drives to the screen → maestro hierarchy (text_audit still applies whenever
   the plan or PRD specifies the copy) → takeScreenshot → grid_overlay.py
   → report/grid/<stem>-grid.png
   → read the gridded image, scan cell by cell against the checklist below
   → same classify → verdict → highlight → report steps as above
```

The measured checks run **before** the image is read, and that ordering is deliberate: they are cheap, deterministic, and they usually decide the verdict on their own. Reading a screenshot to form an impression of something a script already measured is both the most expensive step and the least reliable one.

### Step 1 — Capture the screen twice: pixels and strings

The TC's YAML already ends on `takeScreenshot` after the screen settles (`waitForAnimationToEnd` / `extendedWaitUntil`). Capture the exact state under test. For a long screen, take one shot per scroll position (`TC-010_top`, `TC-010_mid`, `TC-010_bottom`) — vision only sees what's in frame, so anything below the fold has to be scrolled into view by the flow.

At the same moment, dump the **view hierarchy** to a file:

```bash
maestro hierarchy > /tmp/TC-010_default.json     # iOS + Android
# Android alternative: adb exec-out uiautomator dump /dev/tty > /tmp/TC-010_default.xml
```

Redirect it — never let a raw dump into context (`selectors-and-inspection.md`). The screenshot and the hierarchy are the same screen seen two ways, and the review needs both: the hierarchy carries the exact strings, the screenshot carries how they render. Capture them together so they can't drift out of sync.

### Step 1b — Settle the text content first (exact, no tolerance)

Text is the one property with no tolerance, and it is also the cheapest thing to check, so do it before any image is read.

```bash
python3 scripts/text_audit.py \
    --expected report/figma/TC-010_expected.json \
    --actual /tmp/TC-010_default.json \
    --ignore '^\d' --ignore 'đ$' \
    --out report/text/TC-010_default.json
```

Build the expected list from the Figma node (`get_design_context`), the test plan, or — last resort — by transcribing the design export, in that order of trust. Skip this only when nothing specifies the copy; then the hierarchy still earns its keep, because `defects[]` catches a leaked i18n key, a string that arrives already ellipsized, and an element with collapsed or off-screen bounds without needing any expected list at all.

Every entry in `mismatched[]`, `missing[]`, or `defects[]` is **Critical**. There is no percentage of a wrong string that is acceptable, so none of these belong in 🔍 REVIEW. Lead the finding with the `difference` field — "missing Vietnamese diacritics" points straight at an encoding or resource problem, while "expected X, got Y" makes the developer diff two strings by eye.

One thing this cannot prove: **that the text is visible**. A label ellipsized on screen still reports its full string here. That defect belongs to the image, and it is one of the things the cell-by-cell scan is looking for.

### Step 2 — Align and grid

**No design reference (heuristic mode):**

```bash
python3 scripts/grid_overlay.py report/screenshots/TC-010_default.png \
    --out report/grid/TC-010_default-grid.png
```

Output defaults to `<name>-grid.png` next to the input if you omit `--out`. The script auto-picks ~6 columns for a phone portrait and derives rows so cells stay roughly square — square cells are what make "is this centered / aligned?" reliable. Cells are addressed spreadsheet-style: columns `A,B,C…` left→right, rows `1,2,3…` top→bottom, so `C4` is column 3, row 4.

**Comparing to a design reference (design mode) — use `pair_view.py`, not `grid_overlay.py` twice.** A Figma export almost never includes a real status bar or OS nav, but the device screenshot always does. Gridding the two images independently with the same `--cols/--rows` (the old approach) puts cell `C4` over *different* content in each — any comparison built on that is silently comparing the wrong regions. `pair_view.py` fixes this at the source: it crops the screenshot's chrome bands off first, so the two images' content occupies the same fractional area, *then* grids both, *then* measures a real pixel diff between them and flags every cell whose diff exceeds a threshold — so the review isn't just two independent glances, it's a guided comparison against a computed fact.

```bash
python3 scripts/pair_view.py report/figma/TC-010_default.png report/screenshots/TC-010_default.png \
    --cols 6 --rows 13 \
    --crop-actual-top 6% --crop-actual-bottom 4% \
    --out report/grid/TC-010_default-pair.png
```

Starting crop values (verify against the output — if content still looks offset between the two halves, adjust and regenerate before trusting any cell citation):

| Chrome | `--crop-actual-top` | `--crop-actual-bottom` |
|--------|---------------------|-------------------------|
| iOS, notch/Dynamic Island | ~7% | ~4% |
| iOS, home button | ~5% | ~1% |
| Android, gesture nav | ~4% | ~3% |
| Android, 3-button nav | ~4% | ~5% |

If the design export itself includes a device mockup frame (uncommon — most Figma node exports are content-only), crop it too with `--crop-design-top`/`--crop-design-bottom`. Mask known-dynamic regions (a live photo, a list of real rows) with `--mask x1,y1,x2,y2` (percentages recommended, since they survive the resize) so they don't get flagged as "different" for containing different — expected — content.

The script prints a JSON summary with every cell's measured diff ratio and which cells crossed `--cell-threshold` (default 8%). Read that JSON for the exact numbers; it's what lets a finding cite a measured percentage instead of an eyeballed guess.

### Step 2b — Measure the geometry (design mode: always, not optional)

`pair_view.py` answers *"is the right element here, with the right content and style?"*. It cannot answer *"is this gap 16dp like the design, or 28dp?"* — and it will not tell you it didn't try. To align cell addresses it resizes the design onto the screenshot's width **and** height; force-fitting both axes rescales the design's vertical rhythm onto the device's, so a screen whose every padding is inflated by the same factor diffs **clean**. When the two aspect ratios differ (an iOS 390×844 export vs a 1080×2424 Android screen — the normal case), it goes further and suppresses its own flags as unreliable, reporting nothing at all. A 30%-too-loose screen sails through both stages. That is the single most common design-parity defect and the easiest one to miss.

So spacing is a **measurement**, and `spacing_audit.py` measures it:

```bash
python3 scripts/spacing_audit.py report/figma/TC-010_default.png report/screenshots/TC-010_default.png \
    --crop-design-top 6% --crop-design-bottom 2% --crop-actual-top 4% \
    --mask-actual "60%,88%,100%,100%" \
    --out report/grid/TC-010_default-spacing.png
```

It scales by **width only** — mobile layouts pin horizontal metrics and let content flow vertically, so width is the honest shared unit, and not touching the height is what keeps vertical error in the data. It then segments both images into horizontal content bands separated by empty gaps, aligns the two band sequences (skips allowed, since real data ≠ mockup data), and reports gap by gap. Because gaps are *differences* between positions, the result is immune to a taller/shorter status bar, screen size, and pixel density.

Read the JSON first:

| Field | How to read it |
|-------|----------------|
| `verdict` | Plain-language conclusion, already phrased for the report. |
| `systematic_gap_ratio` | Median actual/design gap ratio. `1.29` = every gap ~29% too big → **one** finding with one root cause (a wrong spacing token), not fifteen separate ones. |
| `gaps[]` | Per-gap `design` / `actual` / `delta` / `delta_pct` / `flagged`. This is what a developer acts on. |
| `band_heights[]` | Element heights — separates "the space around it is wrong" from "the element is the wrong size". |
| `margin_deviations[]` | Left/right ink extent per band — catches side-padding and width bugs. |
| `unmatched_design` / `unmatched_actual` | Bands with no counterpart, and `comparable: false` gaps. Almost always a **data** difference (empty state vs three cards) — judge from the image, never report as a spacing defect. |
| `matched_bands` | Under 3 → `verdict` says INCONCLUSIVE. Fix the inputs before quoting anything. |

When the verdict is INCONCLUSIVE or the band boxes in the PNG don't land on elements you'd name out loud, fix the inputs — in this order: crop the chrome (`--crop-design-*` too: a 390×844 iPhone frame draws its own status bar, ~6% top / ~2% bottom); `--mask-actual` a FAB or debug overlay that bridges a gap and merges two bands; `--roi-top`/`--roi-bottom` to audit only the part of the screen that has visible separation; `--design-width-dp 390` when the export isn't 1x so the report reads in real dp; `--min-gap` (default `auto`, prints `min_gap_used`) if a paragraph split per line or two sections merged. If it stays inconclusive, say so and fall back to visual review — never quote a number you don't trust.

### Step 2c — Measure the typography (design mode: always, not optional)

Font size and font weight used to be the two properties this skill declared untestable, and that declaration was what made 🎨 cases unfailable — a title rendering at body size produced a soft note and nothing else. The question was wrong, not the medium. "Is this 16sp?" is unanswerable from pixels; "is this the size the design says, proportionally, and is it still bigger than body text by the same factor?" is a ratio, and ratios measure cleanly.

```bash
python3 scripts/typography_audit.py report/figma/TC-010_default.png \
    report/screenshots/TC-010_default.png \
    --crop-design-top 6% --crop-design-bottom 2% --crop-actual-top 4% \
    --design-width-dp 390 \
    --out report/grid/TC-010_default-type.png
```

It segments both images into text bands the same way `spacing_audit.py` does, then measures each band's **x-height** (the size signal) and **stroke thickness ÷ x-height** (the weight signal — dimensionless, so it doesn't move with size). Every band gets four ratios: size and weight against the design, and size and weight against the median of its *own* screen. The pair matters because they fail differently — a uniformly shrunk type scale passes the intra-screen check and fails the cross-image one, while a heading that lost its style does the reverse.

Read the JSON first:

| Field | How to read it |
|-------|----------------|
| `verdict` | Already phrased for the report. `INCONCLUSIVE` (under 2 matched text bands) means fix the inputs before quoting anything. |
| `systematic_size_ratio` | Median size ratio across the screen. Outside tolerance = the whole type scale is wrong — **one** finding with one root cause, not one per band. |
| `bands[].reasons` | Plain-language statement of exactly which ratio failed and by how much. Quote it verbatim into the finding. |
| `bands[].weight_confidence` | `high` on a paragraph, `low` on a two-word label. A low-confidence weight finding is an estimate — mark it 🔍 REVIEW rather than failing on it. |
| `bands[].secondary_reasons` | Differences against the screen's own body text rather than against the design. Follow them up, but do not fail a case on them: the baseline they use is defined by the screen, so one real defect can nudge it and implicate an innocent element. |
| `bands[].style_run` | `2/2` = the second type style inside one ink band, measured separately. This is what lets a caption under a heading be judged on its own instead of being averaged into it. |
| `bands[].size_tolerance_used` | The tolerance actually applied. When it is well above the 8% floor, the inputs couldn't support finer — see below. |
| `resolution_note` | Present when the design export and the screenshot are at mismatched scales, or the text is too small to resolve a size step. **Act on it.** |
| `unmatched_design` / `unmatched_actual` | Bands with no counterpart — almost always a data difference. Judge from the image, never report as a typography defect. |

**Export the design at the device's scale.** A 1x Figma export beside a 3x screenshot is not one measurement repeated: the low-resolution side reads systematically larger and heavier, because proportionally more of each glyph is antialiased edge. The script detects the mismatch and widens its tolerances rather than reporting a bias as a bug — which is correct, but it costs real sensitivity: at 1x-vs-3x a single-step font-size change (16→14) is simply not detectable. Re-export at 2x/3x (Figma MCP `get_screenshot` / `download_assets` take a scale) and it flags. This is one export setting and it is the difference between a test that can fail and one that can't.

Bands that are photos, dividers, or filled shapes are detected and marked `comparable: false` rather than guessed at, so a hero image never becomes a typography finding.

**Dependency (all four scripts):** Pillow. If it errors with "Pillow is required", run `pip3 install Pillow` once — a one-time setup, not a per-case cost.

### Step 3 — Scan cell by cell (don't glance)

**Design mode:** work from the measurements outward, in this order:

0. **Settle everything measurable before you look at anything.** Three JSONs, in this order — they are numbers, they are cheap, and they usually decide the verdict on their own:
   - **`text_audit.py`** — every `mismatched`, `missing`, and `defects` entry is Critical. Exact, no tolerance.
   - **`spacing_audit.py`** — account for every `flagged: true` gap, and check `systematic_gap_ratio`. If it's outside tolerance, the honest finding is *one* finding ("all section spacing renders N% larger than design") with the per-gap table as evidence, not nine separate gap findings for one wrong token.
   - **`typography_audit.py`** — account for every flagged band, and check `systematic_size_ratio` the same way. Read `resolution_note` and `size_tolerance_used`: if the tolerance had to be widened a lot, a real one-step size bug may be sitting under it, and the fix is a higher-scale design export, not a softer conclusion.

   A clean `pair_view.py` diff is **not** evidence that spacing or typography is fine; it never measured either. Say "content/style diff clean" and cite the measurements separately.

Then read the **paired composite** (`report/grid/<stem>-pair.png`) — design left, actual right, same grid, amber-flagged cells on the right showing a measured diff percentage — and do two things, in order:

1. **Account for every flagged cell first.** A flag is a measured fact, not a suggestion — explain what actually differs in that cell (text, layout, color, missing/extra element) and whether it's a design defect or a data-driven difference (see the table below). A flagged cell can turn out to be data-driven (excluded, not a defect) or chrome-adjacent (crop was imperfect — say so and note the correct crop for next time), but it cannot be silently skipped.
2. **Finish the checklist scan on the rest of the grid**, flagged or not. The pixel diff is a **floor, not a ceiling** — it catches structural/positional/textual differences above the threshold, but a subtle color or font-weight difference can sit under `--cell-threshold` and never flag, so the full visual checklist below still applies everywhere.

**Heuristic mode:** read the single gridded image and walk the checklist **region by region**, naming the cell(s) each observation falls in. Scanning by cell is the whole point — it forces coverage of the quiet corners a gestalt glance skips. Go top band → content → bottom band.

**Heuristic checklist** (no design reference — judge the screen on its own):

- **Overflow / truncation** — text cut off, unexpectedly ellipsized, or spilling outside its container or the screen edge?
- **Overlap / collision** — two elements stacked on each other, a label over an icon or image?
- **Alignment** — do items that should share an edge or baseline actually align? Is a centered element off-center?
- **Spacing / density** — anything uncomfortably cramped or oddly far apart vs. its neighbours? (estimate, not a measurement)
- **Clipping** — descenders (g, y, p) or glyph tops cut by a tight box? images cropped wrong?
- **Contrast / legibility** — is text readable against its background? are disabled and enabled states distinguishable?
- **State correctness** — is the screen in the state the TC intends (loaded, not a spinner/skeleton/error/empty by mistake)? any placeholder or broken image?
- **Completeness** — is an element the screen should show missing from frame? any stray debug text, lorem ipsum, or untranslated key?

**Design-parity checklist** (a design reference was provided):

- **Text content — from `text_audit.py`, exact.** Every expected string accounted for, every `defects[]` entry raised. Never re-read copy off the screenshot to "confirm" it; the hierarchy already settled it, and re-reading only adds a chance to be wrong.
- **Spacing, element sizes, side margins — from `spacing_audit.py`, quoted as numbers.** Every flagged gap accounted for; `systematic_gap_ratio` reported when it's outside tolerance; `band_heights` and `margin_deviations` checked.
- **Font size and weight — from `typography_audit.py`, quoted as ratios.** Every flagged band accounted for; `systematic_size_ratio` reported when the whole scale is off; low-confidence weight findings marked as estimates.
- Every **amber-flagged cell** from `pair_view.py` explained first (see Step 3) — that's the measured, can't-skip list.
- Same elements present, in the same regions (map each design region to a cell range).
- **Is the text actually readable as rendered** — this is the half `text_audit.py` cannot see: a correct string ellipsized, clipped by its box, or overlapped by a neighbour.
- Relative layout matches: order, grouping, alignment, proportions.
- Color and emphasis match intent (the primary button actually looks primary).
- Flag anything present in the design but missing on device (and vice versa) **that is not data-driven**.
- **Exclude data-driven differences** per the table above — don't FAIL on them.

Compare **relative** layout and presence, not pixel-exact positions: device density and system chrome legitimately differ from a design frame. That's what Tier 2 is for, and even there the chrome is masked. The one exception is spacing and margins, which *are* compared numerically — `spacing_audit.py` normalizes by width and compares differences between element positions, so density and chrome drop out of the arithmetic. "Gap renders 32 design px where the design says 24" is a legitimate finding; "the elements look further apart" is not.

### Step 4 — Classify each finding by severity

| Severity | Definition | Examples |
|----------|------------|----------|
| **Critical** | Breaks usability, is unambiguously wrong, or is a *measured* deviation outside tolerance. | **Any text mismatch or text defect at all** — wrong copy, missing diacritics, wrong casing, an untranslated key, a string that arrives truncated (exact-match property: there is no small version of this); a control's text fully clipped or unreadable; two interactive elements overlapping; content running off-screen; a required element missing; a broken image where content was expected; **`systematic_gap_ratio` or `systematic_size_ratio` outside tolerance** (the screen's whole rhythm or type scale is wrong); **one measured gap, margin, font size, or weight far outside tolerance** (e.g. a heading at 0.67× the design's size, or a gap 13 → 42 design px). |
| **Minor** | Measured but small and localized, or genuinely subjective. | A gap 5–6 design px off in one place; a font size just past tolerance on a single band; slightly off-center; a colour shade a touch off vs. the design; density that reads inconsistent but legible. |

If you're unsure whether something is Critical, ask: *would a normal user notice and be blocked or confused?* Yes → Critical. Merely "a designer might tweak it" → Minor. **Bias Minor when genuinely uncertain** — a false Critical erodes trust faster than a missed nitpick.

**But a measured deviation isn't uncertainty, and a wrong string isn't a matter of degree.** "Spacing and typography complaints are subjective, so file them Minor" was right only while neither could be measured. Both can now, and filing a measured 29% inflation or a heading rendering at 0.67× its intended size as a soft note is how a real single-root-cause bug ships. If the number is outside tolerance and the segmentation is sound (band boxes land on real elements, gap `comparable: true`, `weight_confidence` not `low`), it's **Critical**: state the measurement, don't hedge it.

Text is stricter still: it has no tolerance to be inside of, so a mismatch is Critical regardless of size. One missing diacritic is Critical.

Save the hedging for what genuinely is an estimate — an INCONCLUSIVE verdict, an unmatched band, a `low`-confidence weight reading, a colour impression.

### Step 5 — Severity → verdict

| Scan result | TC status | What the report says |
|-------------|-----------|----------------------|
| One or more **Critical** findings | **❌ FAIL** | Failed on visual evidence. List each Critical finding with its cell(s) and link the annotated `vision/…-report.png`. Also write a Failed Test Details entry — this is a filable bug. |
| Only **Minor** findings | **🔍 REVIEW** | Evidence and findings captured; a human decides whether to fix. Not a failure, not a clean pass. |
| No findings; screen matches intent / design | **✅ PASS** | Note "vision review clean" and keep the screenshot path as evidence. |
| Screen never reached, or the wrong state blocks review | **❌ FAIL** (navigation) | Not a visual verdict — the flow failed before vision could judge. Fix the flow and re-run. |

This is the point of the tier: hard defects fail the case on their own instead of waiting in a queue for a human; soft ones defer to a person. Never silently upgrade a Minor to FAIL or downgrade a Critical to REVIEW — that's exactly the judgment the tester is trusting you with.

### Step 6 — Produce the annotated report image (the deliverable)

The result of a visual case is an **image**, not just paragraphs: the gridded screenshot with each defective cell washed faint red, so a reviewer sees at a glance *where* the problems are. Re-run the grid script with `--highlight` on the cells your scan flagged:

```bash
python3 scripts/grid_overlay.py report/screenshots/TC-010_default.png \
    --cols 6 --rows 13 --highlight "E2:F3,A6:F8" \
    --out report/vision/TC-010_default-report.png
```

`--highlight` takes single cells (`E2`) and rectangular ranges (`A6:F8` = the whole block). The wash is ~10% opacity red with a thin red border, so it marks the cell without hiding the pixels that *are* the evidence.

**Only highlight cells with clear, visible evidence.** A cell earns a red wash when the defect is in that cell and you can see it — a clipped title, an overlapping element, a control the design doesn't have. Do **not** wash a cell for a vague concern ("this area feels a bit tight"); that stays a text note. A report image that highlights everything tells the reviewer nothing; one that highlights only real defects is a map straight to them. On a clean PASS there's nothing to highlight — the plain screenshot is the evidence.

The `vision/…-report.png` path is what goes in the report's Evidence column, and its **absolute** path goes in Failed Test Details for the bug-logging phase.

## Finding format

Write each finding so a reviewer can locate and judge it without re-deriving context. One line per finding:

```
[Critical] C3–D3: "Monstera Deliciosa" title clipped on the right edge, last
  characters cut by the card boundary. Evidence: report/vision/TC-010_default-report.png
[Critical] All section gaps render ~29% larger than the design (spacing_audit
  systematic_gap_ratio 1.29 over 5 comparable gaps): search→"Popular Plants"
  28→36, card row→"Your Garden" 24→32, "Your Garden"→content 13→42 design px.
  Likely one root cause — a single vertical-spacing token.
  Evidence: report/grid/TC-010_default-spacing.png. Figma node 123:456.
[Critical] B2–C2: screen title renders at 0.67x the design's size and at body
  weight (typography_audit band 0: x-height 14.5→10.1 design px; stroke ratio
  0.66, confidence high). Relative to body text it is 1.25x where the design
  uses 1.88x — the heading text style is not being applied.
  Evidence: report/grid/TC-010_default-type.png
[Critical] Login title renders without Vietnamese diacritics: expected
  "Đăng nhập", the hierarchy reports "Dang nhap" (element id login_title).
  Text content is exact-match, so this is Critical regardless of size.
  Evidence: report/text/TC-010_default.json
[Minor]    B2: search field renders 4 design px shorter than the design (48→44) —
  noticeable but not a usability issue.
```

Always include: severity, the location (cell address, or the band/gap id from the spacing audit), what's wrong, and the annotated image path (plus the Figma node id in design mode). The location is what makes a finding actionable — "title is clipped" is vague; "title clipped in C3–D3" points straight at it. **When a number exists, lead with the number:** the measured diff ratio from `pair_view.py` when a cell was flagged ("C3–D3 (18% pixel diff)"), and the measured px/dp from `spacing_audit.py` for anything about spacing, size, or margins. A developer can act on "gap 24→32 design px (+33%)" in one read; "spacing looks off" sends them back to measure it themselves. Reserve prose-only findings for what genuinely wasn't measured, and label those "estimate".

**Critical findings feed Failed Test Details** (see `reporting.md`). Map them onto the bug fields directly so the next phase files the bug without re-investigating:

- **Actual Result** ← the finding text, cells included ("title clipped at the right edge of the card, cells C3–D3")
- **Expected Result** ← what the design or normal layout implies ("full title visible, wrapping to a second line as in the design")
- **Screenshots (absolute paths)** ← the annotated `vision/…-report.png`, plus the design reference in design mode
- **Suggested severity** ← Critical finding → Major or higher, depending on how much it blocks the user

## Across sessions

Vision verdicts are recorded, not recomputed. On a resume session, a UI TC already marked ✅ PASS or 🔍 REVIEW is **not** re-scanned unless the tester asks or the screen has changed — re-reading screenshots is the most expensive thing this skill does. A ❌ FAIL that's being retried does get a fresh capture, grid, and scan, and its row is updated in place like any other 🔄 RETRY.

When a screen passes Tier 3 cleanly and the tester wants it protected in future automated runs, that's the moment to promote the screenshot to a **Tier 2 baseline** (`ui-validation.md`) — vision confirmed it's correct, so it's a trustworthy baseline. That's the intended graduation path: Tier 3 finds and confirms; Tier 1 and 2 lock it in.

## Token discipline for vision

Reading a screenshot is the one place this skill deliberately spends tokens on an image — that's the test, not waste. Keep it disciplined:

- Read **one gridded image per screen state**. Never read the raw *and* the gridded version of the same shot; the gridded one carries everything.
- **Read every JSON before any PNG.** `text_audit.py`, `spacing_audit.py`, and `typography_audit.py` all print numbers, and numbers cost a fraction of what an image costs while being strictly more reliable. In practice they settle most of the verdict, and the images are then only needed to name which band is which and to catch what nothing measured.
- In design mode, read the **`-pair.png`**, **`-spacing.png`**, and **`-type.png`** composites — each already contains both halves side by side. Don't also read the ungridded originals, the design on its own, or grid the two images separately. If the spacing and typography JSONs are clean and unambiguous, their PNGs can be skipped entirely; `-pair.png` is the one that still earns a read, because the checklist scan happens on it.
- Add scroll-position shots (`-top/-mid/-bottom`) only when content genuinely extends beyond the fold; each is another image in context.
- Reserve vision for 🎨 UI TCs and explicit design-QA requests. A functional TC with a clean `assertVisible` doesn't need eyes on it.
- Skip `--emit-legend` unless you need the coordinate map.
