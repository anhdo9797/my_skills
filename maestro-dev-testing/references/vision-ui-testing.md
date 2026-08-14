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
- **It cannot measure exact values.** "Is the padding 24dp?" or "is the font
  16sp?" are not answerable from a screenshot — vision can say "this looks
  cramped vs the Figma render" but not assert a `dp`/`sp` number. Route exact
  typography/spacing to source inspection or Paparazzi/Roborazzi screenshot
  tests (see `visual-design-qa.md`).
- **It only sees what rendered.** Off-screen content below the fold, and states
  gated behind data/permission, must be driven into view by the Maestro flow
  first (scroll, seed data) or they cannot be reviewed.
- **Rendering context colors perception.** Status bar, system font scaling,
  locale, dynamic content, and device density all change pixels. Note the device
  profile with every verdict so a "defect" isn't just a different emulator.

Keep this boundary explicit in findings: an overlap is a **CONFIRMED** visual
bug; "spacing feels tight" is an **estimate** for human review.

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
  grid/       labeled-grid versions of actual (and baseline when comparing)
  report/     annotated result images (defect cells washed red) — the deliverable
```

Pair files by the same `<TC-ID>-<state>` stem across folders, e.g.
`baseline/VIS-HOME-01-default.png` ↔ `actual/VIS-HOME-01-default.png` ↔
`report/VIS-HOME-01-default-report.png`. Point `takeScreenshot` at the `actual/`
path (create the folder first), or move the file there right after the run before
gridding.

## The pipeline

```text
[design mode] baseline image (export or Figma render) → grid it, SAME cols/rows
Maestro drives to the screen  →  takeScreenshot into actual/  (clean, no grid)
        →  grid_overlay.py adds a labeled grid → grid/
        →  vision scans cell-by-cell: heuristic, or actual-grid vs baseline-grid
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

### Step 2 — Overlay the grid

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

**Comparing to a design baseline?** Grid **both** the actual screenshot **and**
the baseline with the **same** `--cols`/`--rows`, so cell `C4` means the same
region in both images:

```bash
python3 scripts/grid_overlay.py actual/VIS-HOME-01-default.png   --cols 6 --rows 13 --out grid/VIS-HOME-01-default-grid.png
python3 scripts/grid_overlay.py baseline/VIS-HOME-01-default.png --cols 6 --rows 13 --out grid/VIS-HOME-01-baseline-grid.png
```

Pick the column count from the phone aspect (6 is a good default) and let both
share it. The two images can differ in resolution — the grid normalizes them to
the same cell addresses. Chrome that legitimately differs (status bar, home
indicator, notch) is not a defect; compare the app content, not the OS frame.

### Step 3 — Scan cell-by-cell (don't glance)

Read the **gridded** image and walk the checklist **region by region**, naming
the cell(s) each observation falls in. Scanning by cell is the whole point: it
forces coverage of quiet corners a gestalt glance skips. Go top band → content
→ bottom band. In design mode, read the actual-grid and baseline-grid together
and compare the **same cell** in each.

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

- Same elements present, in the same regions (map each Figma frame region to a
  grid cell range).
- Text content matches (copy, casing, no untranslated keys).
- Relative layout matches: order, grouping, alignment, proportions.
- Color/emphasis matches intent (primary button actually looks primary).
- Flag anything present in Figma but missing on device (and vice-versa) **that is
  not data-driven** — a static illustration, a mis-styled control, wrong spacing.
- **Exclude data-driven differences** (item count, one-vs-two columns from how
  many items exist, specific names/photos, badges) per "Data-state vs
  design-state" above — don't FAIL on them.

Keep the Figma node id in each finding for traceability.

Compare **relative** layout and presence — not pixel-exact positions; device
density and system chrome legitimately differ from a Figma frame.

### Step 4 — Classify each finding by severity

| Severity | Definition | Examples |
|----------|------------|----------|
| **Critical** | Breaks usability or is unambiguously wrong; a user would report it. | Text of a control fully clipped/unreadable; two interactive elements overlapping; content runs off-screen; a required element missing; untranslated key shown; broken/failed image where content expected. |
| **Minor** | Subjective or low-impact polish; needs human judgment. | Spacing feels tight; slight off-center; a shade of color looks a touch off vs Figma; inconsistent but legible density. |

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
[Minor]    A11–F11: bottom nav icons sit tight against the top divider; spacing
  looks ~half the Figma gap (estimate). Figma node 123:456.
```

Always include: severity, cell address(es), what's wrong, and the gridded
screenshot path (plus Figma node id in parity mode). Cell addresses are what make
the finding actionable — "title is clipped" is vague; "title clipped in C3–D3"
points straight at it.

## Token discipline for vision

Vision review is the one place this skill *does* read a screenshot into context —
that's the test, not waste. Keep it disciplined:

- Read **one gridded image per screen state**. Do **not** read the raw + gridded
  versions of the same shot; the grid version carries everything.
- In design mode, read the **actual-grid and baseline-grid** for a screen — that
  pair is the comparison. Don't also read the ungridded originals.
- Only add scroll-position shots (`-top/-mid/-bottom`) when content actually
  extends beyond the fold — each is another image in context.
- Reserve vision for cases the plan marked as visual/UI (`VIS-*`, design-QA
  requests). Don't run a vision pass on every functional smoke test — a
  functional PASS with a clean `assertVisible` doesn't need eyes on it.
- Skip `--emit-legend` unless you need the coordinate map; it adds JSON to stdout.

## Integration with the run loop

A vision case slots into the Phase 2 loop as an extra step after the screenshot:

```text
[once] design mode: grid each baseline/ image with the shared --cols/--rows
2-A  Write <VIS-ID>.yaml  (drives to screen, ends on takeScreenshot into actual/)
2-B  Run the flow
2-C  grid_overlay.py actual/<shot>.png --cols N --rows M → grid/<shot>-grid.png
2-C' Read grid (+ baseline-grid in design mode) → cell-by-cell scan → findings
     → severity → verdict
2-C" If any defect: grid_overlay.py --highlight <cells> → report/<shot>-report.png
2-D  report.md row (Status from Step 5, evidence = report image) + findings in
     RUN_REPORT.md
2-E  Announce inline (e.g. "✗ VIS-01 FAIL — extra header image E2–F3; report/…")
```

Functional cases stay exactly as before (no grid, no vision unless they fail
ambiguously). Only visual/UI cases carry the grid+vision sub-step.
