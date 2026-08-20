# Vision-based UI testing (grid-assisted screenshot review)

Use this when the goal is to judge how a screen **looks and lays out**, not just
whether an element is technically present. Maestro can prove `assertVisible`
passed; it cannot tell you the title is clipped, two labels overlap, a button
runs off the edge, or the empty state is misaligned. Those are visual defects a
person notices instantly but `assertVisible` sails right past. This method feeds
the screenshot to Claude's vision so that judgment happens automatically — and
overlays a **labeled grid** so the review is systematic and every finding has a
locatable address.

This is the automated layer that replaces the old "capture screenshot →
`NEEDS_REVIEW` → wait for a human" gap. Vision does the first pass; a human still
adjudicates the subjective, low-severity findings (see the verdict table below).

## What vision can and cannot prove — read this first

Vision **estimates**; it does not **measure**. Be honest about the boundary or
the report loses trust:

- **It reliably catches** gross layout defects: overlapping elements, text
  truncated/clipped by its container, content running off-screen, obvious
  misalignment, an element missing or in the wrong region, wrong/instructed
  state (loading spinner stuck, error banner where success expected), unreadable
  contrast, image not loaded / broken placeholder, RTL/locale overflow.
- **It cannot measure — so don't ask it to.** "Is that gap 24dp?" or "is the
  font 16sp?" are not answerable by looking. Asked anyway, vision produces an
  impression ("spacing feels a little loose") that is both unactionable and
  unreliable: a screen whose every padding is 30% too big reads as merely
  "fine, maybe slightly airy". Geometry belongs to `spacing_audit.py`, which
  measures it in design px/dp — see the next section. Framework *values*
  (`SizedBox(height: 24)`, `16.sp`) still need source inspection or
  Paparazzi/Roborazzi tests (see `visual-design-qa.md`); the measured render is
  the evidence that sends someone to look.
- **It only sees what rendered.** Off-screen content below the fold, and states
  gated behind data/permission, must be driven into view by the Maestro flow
  first (scroll, seed data) or they cannot be reviewed.
- **Rendering context colors perception.** Status bar, system font scaling,
  locale, dynamic content, and device density all change pixels. Note the device
  profile with every verdict so a "defect" isn't just a different emulator.

Keep this boundary explicit in findings: an overlap is a **CONFIRMED** visual
bug; "spacing feels tight" is an **estimate** for human review — and an estimate
is never the right output when a measurement was available.

## Measure the geometry, then look — the order matters

Design parity splits into two questions that need two different tools, and
collapsing them is what makes a "design comparison" quietly useless:

| Question | Tool | Why it must be this one |
|----------|------|-------------------------|
| Is the right element here, with the right content, colour, and style? | `pair_view.py` | Aligns both images to one grid and pixel-diffs, so no changed cell can be skipped and no unchanged cell can be imagined into a finding. |
| Is it the right size, in the right place, with the right space around it? | `spacing_audit.py` | Measures element bands and the gaps between them in design px/dp. Gaps are *differences* between positions, so the result survives a different status-bar height, screen size, and pixel density. |

**Why `pair_view.py` alone cannot answer the second question — the false
negative this section exists to prevent.** To align cells, `pair_view.py` resizes
the design onto the screenshot's width **and** height. Force-fitting both axes
rescales the design's vertical rhythm onto the device's, so if every padding on
the screen is inflated by the same factor, the resize normalizes it away and the
diff comes back clean. When the two aspect ratios differ (an iOS 390×844 mockup
vs a 1080×2424 Android screen — routine), it goes further and suppresses the
per-cell flags as unreliable, reporting nothing. A screen whose spacing is 30%
off passes both stages. So:

- Never conclude "spacing matches" from a clean `pair_view.py` diff. It did not
  look. Say "content/style diff clean" and cite `spacing_audit.py` separately.
- When `pair_view.py` prints the aspect-mismatch warning, that is **not** a dead
  end — it is the cue that geometry has to come from `spacing_audit.py`.

Run both in design mode. They are cheap, and each covers the other's blind spot.

## Data-state vs design-state — the most common false FAIL

A design mockup shows the screen in **one chosen data state** — usually full and
ideal: a 2-column grid packed with items, a garden with several plants, curated
studio photos. The real app renders whatever the **API and the user's data**
currently provide: maybe one column because the user has one saved plant, fewer
cards, real user photos, different names, a different count badge. **These
differences are data, not design defects** — failing the case on them is the
single most common way a vision comparison goes wrong.

Before comparing, decide which differences are data-driven and **exclude them**:

- **Data-driven (NOT a defect):** number of items shown, one-column vs multi-
  column *when it's driven by how many items exist*, specific text/names/images,
  counts and badges, empty vs populated sections, a carousel showing fewer cards
  because there are fewer to show.
- **Design defects (still count):** things that are wrong *regardless of data* —
  overlap, clipping, truncation of a label that does fit in the design, an
  element in the wrong place, a static element present/absent vs the design
  (e.g. a decorative header image, a mis-styled button), broken spacing or
  alignment, wrong colors/typography treatment.

Two ways to keep the comparison fair, best first:

1. **Match the data state.** Seed the app into the state the design depicts (a
   `runFlow` that saves N plants, or a fixture/mock) so both show the same
   content, then differences are real. Note the seeded state in the testcase.
2. **Compare state-agnostic properties only.** When you can't match the data,
   explicitly ignore count/content/column-from-count and judge only the
   data-independent properties above. Say so in the report: "compared layout/
   style only; item count differs due to user data, excluded."

When unsure whether a difference is data or design, **treat it as data (don't
FAIL)** and note it for human review — the design baseline may also simply be a
different or older iteration than the shipped screen.

**App more complete than the design usually means a stale baseline, not a bug.**
If the app shows a real element the baseline lacks (a header hero image, a new
control), the likely cause is that the export/Figma node is older than the
shipped screen. Verdict **PASS**, and recommend refreshing the baseline — don't
FAIL the app for being ahead of an outdated design. (The reverse — the design has
something the app is missing — is the one that usually is a real defect.)

## Design baseline sources

"Compare to the design" needs a baseline image to compare *against*. It can come
from either source — both end as a PNG in the feature's `baseline/` folder, after
which the comparison is identical:

- **Exported image folder.** The user drops design exports (PNG/JPG) somewhere
  under `.maestro/`. Record each screen's baseline path in `TESTCASES.md` so the
  pairing is explicit — don't force a rename; the plan carries the mapping
  (`VIS-HOME-01 → baseline: Home iOS - default.png`).
- **Figma node.** When the user gives a Figma URL with a `node-id`, render the
  node to an image with the Figma MCP `get_screenshot` and save it into the same
  `baseline/` folder (also pull `get_design_context` for text/token detail). Keep
  the node id in the testcase for traceability. If the URL has no `node-id`, ask
  for the node-specific URL before claiming parity — see `visual-design-qa.md`.

If **no baseline** is provided, run in heuristic mode (judge the screen on its
own, checklist below). Don't invent a design to compare against.

## Where the files live (keep them out of the repo root)

`takeScreenshot: <bare-name>` writes to the directory Maestro runs from — the
repo root — which clutters it and shows up as stray untracked files. Keep every
visual artifact under the feature's folder in `.maestro/`:

```
.maestro/artifacts/<feature>/
  baseline/   design references (exported image or Figma render), <TC-ID>-<state>.png
  actual/     device screenshots from Maestro takeScreenshot
  grid/       <stem>-grid.png (heuristic) or <stem>-pair.png + <stem>-spacing.png (design)
  report/     annotated result images (defect cells washed red) — the deliverable
```

Pair files by the same `<TC-ID>-<state>` stem across folders, e.g.
`baseline/VIS-HOME-01-default.png` ↔ `actual/VIS-HOME-01-default.png` ↔
`report/VIS-HOME-01-default-report.png`. Point `takeScreenshot` at the `actual/`
path (create the folder first), or move the file there right after the run before
gridding.

## The pipeline

```text
Maestro drives to the screen  →  takeScreenshot into actual/  (clean, no grid)
        │
        ├─[design mode: a baseline exists]
        │     pair_view.py  design + actual → grid/<stem>-pair.png   (content/style)
        │     spacing_audit.py design + actual → grid/<stem>-spacing.png + JSON
        │     → read the two composites; account for every flagged cell and every
        │       flagged gap, then finish the parity checklist
        │
        └─[heuristic mode: no baseline]
              grid_overlay.py actual → grid/<stem>-grid.png
              → read it and walk the heuristic checklist cell by cell
        │
        →  classify each finding by severity, note the exact defect cell(s)
        →  severity → verdict (FAIL / NEEDS_REVIEW / PASS)
        →  if any defect: grid_overlay.py --highlight <cells> → report/ image
        →  one row in report.md, findings + report-image path in RUN_REPORT.md
```

### Step 1 — Capture a clean screenshot

The Maestro flow already ends on `takeScreenshot: <TC-ID>-<step>` after the
screen settles (`waitForAnimationToEnd` / `extendedWaitUntil`). Capture the
screen in the exact state under test. For long screens, take one screenshot per
scroll position (`<TC-ID>-top`, `<TC-ID>-mid`, `<TC-ID>-bottom`) — vision only
sees what's in frame.

### Step 2a — Heuristic mode: overlay the grid

```bash
python3 scripts/grid_overlay.py <shot>.png            # auto ~square cells
python3 scripts/grid_overlay.py <shot>.png --cols 6   # force column count
python3 scripts/grid_overlay.py <shot>.png --emit-legend   # also print cell→px map
```

Output is `<shot>-grid.png`. The script auto-picks a column count (~6 for phone
portrait) and derives rows so cells stay roughly square — square cells make
"is this centered / aligned?" reasoning reliable. Cells are addressed
spreadsheet-style: columns `A,B,C…` left→right, rows `1,2,3…` top→bottom, so
`C4` is column 3, row 4.

**Dependency:** the script needs Pillow. If it errors with "Pillow is required",
run `pip3 install Pillow` once, then re-run. This is a one-time setup, not a
per-case cost.

Use `--emit-legend` when you want the cell→pixel/normalized-center map printed
(e.g. to hand a defect's location to a follow-up Maestro `tapOn: point`). For a
pure visual review the labels on the image are enough — skip the legend to keep
output small.

### Step 2b — Design mode: build the pair, then measure

Do **not** grid the baseline and the screenshot separately. A Figma export has no
status bar or OS nav baked in; a real screenshot always does. Gridding each on
its own puts cell `C4` over a different region of content in each image, and
every comparison built on that is measuring the wrong things without anyone
noticing. Both scripts below crop the chrome first, so the alignment is real.

**First — content and style (`pair_view.py`):**

```bash
python3 scripts/pair_view.py baseline/VIS-HOME-01-default.png actual/VIS-HOME-01-default.png \
    --cols 6 --rows 13 --crop-actual-top 4% --crop-actual-bottom 3% \
    --out grid/VIS-HOME-01-default-pair.png
```

One composite, design | actual, sharing a grid, with every cell whose measured
diff exceeds the threshold flagged amber. Mask genuinely dynamic regions
(`--mask 0%,20%,100%,55%`) so user photos and live lists don't flood the flags.

**Then — geometry (`spacing_audit.py`), and never skip this on a spacing
question:**

```bash
python3 scripts/spacing_audit.py baseline/VIS-HOME-01-default.png actual/VIS-HOME-01-default.png \
    --crop-design-top 6% --crop-design-bottom 2% --crop-actual-top 4% \
    --mask-actual "60%,88%,100%,100%" \
    --out grid/VIS-HOME-01-default-spacing.png
```

It scales by **width only** (so vertical error survives instead of being resized
away), segments both images into content bands separated by empty gaps, aligns
the two band sequences, and prints a gap-by-gap table plus an annotated
side-by-side PNG. Read the JSON first, then the PNG to see which band is which.

The numbers that matter in the JSON:

| Field | How to read it |
|-------|----------------|
| `verdict` | Plain-language conclusion, already written for the report. |
| `systematic_gap_ratio` | Median actual/design gap ratio. `1.29` = every gap is ~29% too big — **one** finding with one root cause (a wrong spacing token/theme value), not fifteen. |
| `gaps[]` | Per-gap `design` / `actual` / `delta` / `delta_pct`, and `flagged`. This is the evidence a developer acts on. |
| `band_heights[]` | Element heights — separates "the space around it is wrong" from "the thing itself is the wrong size". |
| `margin_deviations[]` | Left/right ink extent per band — catches side-padding and width bugs. |
| `unmatched_design` / `unmatched_actual` | Bands with no counterpart. Usually a **data** difference (empty state vs three cards) — judge from the image, never report as a spacing defect. |
| `matched_bands` | Fewer than 3 means the segmentation didn't get traction; the `verdict` says INCONCLUSIVE. Fix the inputs (below) or fall back to visual review — do not report a number you don't trust. |

Getting a trustworthy segmentation, in order of what usually goes wrong:

- **Crop the chrome.** Otherwise the status bar becomes band 1 and every gap
  shifts. Starting points: iOS notch `--crop-actual-top 7% --crop-actual-bottom 4%`;
  iOS home button `5%` / `1%`; Android gesture nav `4%` / `3%`; Android 3-button
  `4%` / `5%`. Most Figma exports need `--crop-design-*` too when the frame draws
  its own status bar (a 390×844 iPhone frame does: about `6%` top, `2%` bottom).
- **Mask what floats.** A FAB, a snackbar, or a debug overlay sitting in a gap
  bridges it and merges two bands into one: `--mask-actual "60%,88%,100%,100%"`.
- **`--roi-top` / `--roi-bottom`** to audit only the part of the screen that has
  visible separation — the right move on a screen that's half full-bleed photo.
- **`--design-width-dp 390`** when the export isn't 1x, so the report reads in
  real dp instead of export px.
- `--min-gap` defaults to `auto` and prints `min_gap_used`. Raise it if a
  paragraph got split into one band per line; lower it if two separate sections
  merged.

Sanity-check the annotated PNG before quoting any number: the band boxes should
land on the elements you'd name out loud ("header block", "search bar", "card
row"). If they don't, the numbers describe something else.

### Step 3 — Scan cell-by-cell (don't glance)

Read the composite and walk the checklist **region by region**, naming the
cell(s) each observation falls in. Scanning by cell is the whole point: it forces
coverage of quiet corners a gestalt glance skips. Go top band → content → bottom
band.

**In design mode, work from the measurements outward, in this order:**

1. **Account for every flagged gap and every `flagged: true` band metric from
   `spacing_audit.py`.** Each one is either a real finding or has a stated reason
   to dismiss (a data difference, an unmatched band inside it, a crop you can
   see is off). "I didn't mention it" is not one of those reasons.
2. **Check `systematic_gap_ratio` before writing anything up.** If it's outside
   tolerance, the honest finding is *one* finding — "all section spacing renders
   N% larger than design" — with the per-gap table as evidence. Filing nine
   separate gap findings for one wrong token buries the actual bug.
3. **Account for every amber cell in the `pair_view.py` composite.** Same rule:
   explained or dismissed with a reason.
4. **Then scan the rest of the checklist yourself.** The measurements are a
   floor, not a ceiling: a masked region, a difference below threshold, and
   anything colour- or content-related can still be a real defect that no flag
   marked.

**Heuristic checklist** (mode: no Figma reference — judge the screen on its own):

- **Overflow / truncation** — any text cut off, ellipsized unexpectedly, or
  spilling outside its container or the screen edge?
- **Overlap / collision** — do two elements sit on top of each other, or a label
  over an icon/image?
- **Alignment** — are items that should share an edge/baseline actually aligned?
  Is a centered element off-center?
- **Spacing / density** — are elements uncomfortably cramped or oddly far apart
  vs their neighbors? (estimate, not a measurement)
- **Clipping** — descenders (g, y, p) or top of glyphs cut by a tight box?
  images cropped wrong?
- **Contrast / legibility** — text readable against its background? disabled vs
  enabled states distinguishable?
- **State correctness** — is the screen in the state the test intends (loaded,
  not a spinner/skeleton/error/empty by mistake)? any placeholder or broken
  image?
- **Completeness** — is any element the screen should show missing from frame?
  any stray debug text, lorem ipsum, untranslated key (e.g. `home.title`)?

**Figma-parity checklist** (mode: a Figma node was provided — compare to the
baseline render from `get_screenshot`):

- **Spacing / size / margins — from `spacing_audit.py`, quoted as numbers.**
  Every flagged gap accounted for; `systematic_gap_ratio` reported when it's
  outside tolerance; `band_heights` and `margin_deviations` checked. Never leave
  this row as an impression when a measurement exists.
- Same elements present, in the same regions (map each Figma frame region to a
  grid cell range).
- Text content matches (copy, casing, no untranslated keys).
- Relative layout matches: order, grouping, alignment, proportions.
- Color/emphasis matches intent (primary button actually looks primary).
- Flag anything present in Figma but missing on device (and vice-versa) **that is
  not data-driven** — a static illustration, a mis-styled control.
- **Exclude data-driven differences** (item count, one-vs-two columns from how
  many items exist, specific names/photos, badges) per "Data-state vs
  design-state" above — don't FAIL on them. In the spacing table these surface as
  `unmatched_*` bands and `comparable: false` gaps; leave them out of the
  spacing verdict rather than explaining them away as defects.

Keep the Figma node id in each finding for traceability.

Compare **relative** layout and presence, not pixel-exact positions — with one
exception: spacing and margins *are* compared numerically, because
`spacing_audit.py` normalizes by width and compares differences between element
positions, which makes the comparison independent of density and chrome. A
measured "gap is 32 design px where the design says 24" is a legitimate finding;
"the elements look further apart" is not.

### Step 4 — Classify each finding by severity

| Severity | Definition | Examples |
|----------|------------|----------|
| **Critical** | Breaks usability, or is unambiguously wrong — including *measured* deviations from the design. | Text of a control fully clipped/unreadable; two interactive elements overlapping; content runs off-screen; a required element missing; untranslated key shown; broken/failed image where content expected; **`systematic_gap_ratio` outside tolerance** (the screen's whole vertical rhythm is wrong vs the design); **a single measured gap or margin far outside tolerance** (e.g. 13 → 42 design px). |
| **Minor** | Subjective, or measured but small and localized. | A gap 5–6 design px off in one place; slight off-center; a shade of colour a touch off vs Figma; density that reads inconsistent but legible. |

**A measured deviation is not an estimate.** The old rule — "spacing complaints
are subjective, so file them Minor and let a human decide" — was correct only
while spacing could not be measured. Now it can, and treating a measured 29%
inflation as a soft note is how a real, single-root-cause layout bug ships. If
the number is outside tolerance and the segmentation is sound (band boxes land on
real elements, gap `comparable: true`), it is a **Critical** finding: state the
measurement, don't hedge it. Keep hedging for what genuinely is an estimate — an
`INCONCLUSIVE` verdict, an unmatched band, a colour impression.

If unsure whether something is Critical, ask: *would a normal user notice and be
blocked/confused?* Yes → Critical. Merely "a designer might tweak it" → Minor.
Bias Minor when genuinely uncertain — a false Critical erodes trust faster than a
missed nitpick.

### Step 5 — Severity → verdict (the auto rule)

| Screen result | Verdict | Meaning in report |
|---------------|---------|-------------------|
| One or more **Critical** findings | **FAIL** | Automatically failed on visual evidence. List each Critical finding with its cell(s) and the annotated `report/…-report.png` path. |
| Only **Minor** findings | **NEEDS_REVIEW** | Evidence + findings captured; a human confirms whether to fix. |
| No findings, screen matches intent/Figma | **PASS** | Note "vision review clean" and keep the screenshot path as evidence. |
| Screen never reached / wrong state blocks review | **ERROR** or **PENDING** | Not a visual verdict — the flow failed before vision could judge. Fix and re-run. |

This is the "hybrid by severity" policy: hard defects fail the case on their own;
soft ones defer to a person. Never silently upgrade a Minor to FAIL or downgrade
a Critical to NEEDS_REVIEW — the whole point is that Criticals don't wait.

### Step 6 — Produce the annotated report image (the deliverable)

The result of a visual case is an **image**, not just text: the gridded
screenshot with each **defective cell washed faint red** so a reviewer sees at a
glance *where* the problems are. Generate it by re-running the grid script with
`--highlight` on the cells your scan flagged:

```bash
python3 scripts/grid_overlay.py actual/VIS-HOME-01-default.png \
    --cols 6 --rows 13 --highlight "E2:F3,A6:F8" \
    --out report/VIS-HOME-01-default-report.png
```

`--highlight` takes single cells (`E2`) and ranges (`A6:F8` = the whole block).
The wash defaults to ~10% opacity red with a thin red border, so it marks the
cell without hiding the pixels that are the evidence.

**Only highlight cells with clear, visible evidence.** A cell earns a red wash
when the defect is *in that cell and you can see it* — a clipped title, an
overlapping element, an image the design doesn't have. Do **not** wash a cell for
a vague or estimated concern ("this area feels a bit tight"); that stays a text
note in `RUN_REPORT.md`, not a mark on the image. A report image that highlights
everything tells the reviewer nothing; one that highlights only the real defects
is a map straight to them. On a clean PASS, there's nothing to highlight — the
plain grid (or even the raw screenshot) is the evidence.

The `report/…-report.png` path is what goes in `report.md`'s evidence column and
`RUN_REPORT.md`, alongside the per-cell findings text.

## Finding format

Write each finding so a reviewer can locate and judge it without re-deriving
context. One line per finding in `RUN_REPORT.md`:

```
[Critical] C3–D3: "Monstera Deliciosa" title clipped on the right edge, last
  characters cut by the card boundary. Evidence: VIS-01-detail-grid.png
[Critical] All section gaps render ~29% larger than design (spacing_audit
  systematic_gap_ratio 1.29, 5 comparable gaps): search→"Popular Plants" 28→36,
  card row→"Your Garden" 24→32, "Your Garden"→content 13→42 design px. One
  root cause likely — a single vertical-spacing token/theme value.
  Evidence: grid/VIS-HOME-01-default-spacing.png. Figma node 123:456.
[Minor]    B2: search field renders 4 design px shorter than design (48→44);
  within noticeable range but not a usability issue.
```

Always include: severity, the location (cell address, or the band/gap id from the
spacing audit), what's wrong, and the evidence image path (plus the Figma node id
in parity mode). **When a number exists, the finding leads with the number** —
"gap 24→32 design px (+33%)" is something a developer can act on in one read;
"spacing looks off" sends them back to measure it themselves. Reserve prose-only
findings for what genuinely wasn't measured, and say so ("estimate").

## Token discipline for vision

Vision review is the one place this skill *does* read a screenshot into context —
that's the test, not waste. Keep it disciplined:

- Heuristic mode: read **one gridded image per screen state**. Do **not** read the
  raw + gridded versions of the same shot; the grid version carries everything.
- Design mode: read the **`-pair.png`** and the **`-spacing.png`** composites —
  two images that each already contain both sides. Don't also read the ungridded
  originals or the baseline on its own. Read the spacing **JSON** before its PNG;
  often the numbers settle the question and the PNG is only needed to name which
  band is which.
- Only add scroll-position shots (`-top/-mid/-bottom`) when content actually
  extends beyond the fold — each is another image in context.
- Reserve vision for cases the plan marked as visual/UI (`VIS-*`, design-QA
  requests). Don't run a vision pass on every functional smoke test — a
  functional PASS with a clean `assertVisible` doesn't need eyes on it.
- Skip `--emit-legend` unless you need the coordinate map; it adds JSON to stdout.

## Integration with the run loop

A vision case slots into the Phase 2 loop as an extra step after the screenshot:

```text
2-A  Write <VIS-ID>.yaml  (drives to screen, ends on takeScreenshot into actual/)
2-B  Run the flow
2-C  design mode:  pair_view.py     baseline actual → grid/<shot>-pair.png
                   spacing_audit.py baseline actual → grid/<shot>-spacing.png + JSON
     heuristic:    grid_overlay.py  actual          → grid/<shot>-grid.png
2-C' Read the composite(s) → account for flagged gaps, then flagged cells, then
     finish the checklist → findings → severity → verdict
2-C" If any defect: grid_overlay.py --highlight <cells> → report/<shot>-report.png
2-D  report.md row (Status from Step 5, evidence = report image + spacing image)
     + findings with their measured numbers in RUN_REPORT.md
2-E  Announce inline (e.g. "✗ VIS-01 FAIL — section gaps +29% vs design; report/…")
```

Functional cases stay exactly as before (no grid, no vision unless they fail
ambiguously). Only visual/UI cases carry the grid+vision sub-step.
