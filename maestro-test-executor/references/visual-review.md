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

## What vision can and cannot prove — read this before judging

Vision **estimates**; it does not **measure**. Being honest about that boundary is what keeps the report trustworthy:

- **It reliably catches** gross layout defects: overlapping elements, text truncated or clipped by its container, content running off-screen, obvious misalignment, an element missing or in the wrong region, the wrong screen state (a stuck spinner where loaded content was expected, an error banner instead of success), unreadable contrast, a broken/unloaded image placeholder, an untranslated key like `home.title` leaking to the UI.
- **It cannot measure exact values.** "Is the padding 24dp?" or "is this font 16sp?" cannot be answered from a screenshot. Vision may say "this looks cramped compared to the design" — it may not claim a `dp`/`sp` number. Exact typography and spacing parity stays a **🔍 REVIEW** note for a human or a developer.
- **It only sees what rendered.** Content below the fold, and states gated behind data or permissions, must be driven into view by the Maestro flow first (scroll, seed data) or they simply cannot be reviewed.
- **Rendering context colors perception.** Status bar, system font scaling, locale, dynamic data, and device density all change pixels. Record the device profile with every verdict so a "defect" isn't just a different emulator.

Say which is which in the finding: an overlap is a **confirmed** defect; "spacing feels tight" is an **estimate**.

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
├── figma/         ← design references: Figma renders or tester-supplied exports
├── grid/          ← gridded versions of the above (what vision actually reads)
└── vision/        ← annotated result images, defect cells washed red — the deliverable
```

Pair files by the same `TC-XXX_<state>` stem across folders so the set is obvious at a glance:
`figma/TC-010_default.png` ↔ `screenshots/TC-010_default.png` ↔ `grid/TC-010_default-grid.png` ↔ `vision/TC-010_default-report.png`.

## Getting the design reference (design mode)

Two sources, both ending as a PNG in `report/figma/`, after which the comparison is identical:

- **Tester-supplied export.** They drop design PNGs somewhere in the workspace. Record each screen's reference path in the TC so the pairing is explicit — don't force a rename; the plan carries the mapping (`TC-010 → figma/Home iOS - default.png`).
- **Figma node.** Given a Figma URL with a `node-id`, render it with the Figma MCP `get_screenshot` and save into `report/figma/`. Pull `get_design_context` too when you need exact copy/text detail. Keep the node id in the TC for traceability. If the URL has **no** `node-id`, ask for the node-specific URL before claiming design parity — a whole-file URL doesn't identify which frame to compare.

**No reference available? Run in heuristic mode** — judge the screen on its own against the checklist below. Never invent a design to compare against.

## The pipeline

```text
[design mode] design reference → grid it with the SAME --cols/--rows
Maestro drives to the screen → takeScreenshot into report/screenshots/  (clean, no grid)
   → grid_overlay.py           → report/grid/<stem>-grid.png
   → read the gridded image, scan cell by cell (heuristic, or vs. the gridded design)
   → classify each finding Critical / Minor, naming the exact cell(s)
   → severity → verdict (❌ FAIL / 🔍 REVIEW / ✅ PASS)
   → if any defect: grid_overlay.py --highlight <cells> → report/vision/<stem>-report.png
   → one row in report.md + findings in UI Validation Details (+ Failed Test Details if FAIL)
```

### Step 1 — Capture a clean screenshot

The TC's YAML already ends on `takeScreenshot` after the screen settles (`waitForAnimationToEnd` / `extendedWaitUntil`). Capture the exact state under test. For a long screen, take one shot per scroll position (`TC-010_top`, `TC-010_mid`, `TC-010_bottom`) — vision only sees what's in frame, so anything below the fold has to be scrolled into view by the flow.

### Step 2 — Overlay the grid

```bash
python3 scripts/grid_overlay.py report/screenshots/TC-010_default.png \
    --out report/grid/TC-010_default-grid.png
```

Output defaults to `<name>-grid.png` next to the input if you omit `--out`. The script auto-picks ~6 columns for a phone portrait and derives rows so cells stay roughly square — square cells are what make "is this centered / aligned?" reliable. Cells are addressed spreadsheet-style: columns `A,B,C…` left→right, rows `1,2,3…` top→bottom, so `C4` is column 3, row 4.

**Dependency:** Pillow. If it errors with "Pillow is required", run `pip3 install Pillow` once — a one-time setup, not a per-case cost.

**Comparing to a design reference?** Grid **both** images with the **same** `--cols`/`--rows` so `C4` means the same region in both:

```bash
python3 scripts/grid_overlay.py report/screenshots/TC-010_default.png --cols 6 --rows 13 --out report/grid/TC-010_default-grid.png
python3 scripts/grid_overlay.py report/figma/TC-010_default.png       --cols 6 --rows 13 --out report/grid/TC-010_design-grid.png
```

The two images may differ in resolution — the grid normalizes them to the same addresses. Use `--emit-legend` only when you need the cell→pixel map (e.g. to hand a defect location to a follow-up `tapOn: point`); for a pure review the labels on the image are enough and the legend just adds JSON to stdout.

### Step 3 — Scan cell by cell (don't glance)

Read the **gridded** image and walk the checklist **region by region**, naming the cell(s) each observation falls in. Scanning by cell is the whole point — it forces coverage of the quiet corners a gestalt glance skips. Go top band → content → bottom band. In design mode, read the actual-grid and design-grid together and compare the **same cell** in each.

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

- Same elements present, in the same regions (map each design region to a cell range).
- Text content matches — copy, casing, no untranslated keys.
- Relative layout matches: order, grouping, alignment, proportions.
- Color and emphasis match intent (the primary button actually looks primary).
- Flag anything present in the design but missing on device (and vice versa) **that is not data-driven**.
- **Exclude data-driven differences** per the table above — don't FAIL on them.

Compare **relative** layout and presence, not pixel-exact positions: device density and system chrome legitimately differ from a design frame. That's what Tier 2 is for, and even there the chrome is masked.

### Step 4 — Classify each finding by severity

| Severity | Definition | Examples |
|----------|------------|----------|
| **Critical** | Breaks usability or is unambiguously wrong; a user would report it. | A control's text fully clipped or unreadable; two interactive elements overlapping; content running off-screen; a required element missing; an untranslated key on screen; a broken image where content was expected. |
| **Minor** | Subjective or low-impact polish; needs human judgment. | Spacing feels tight; slightly off-center; a colour shade looks a touch off vs. the design; inconsistent but legible density. |

If you're unsure whether something is Critical, ask: *would a normal user notice and be blocked or confused?* Yes → Critical. Merely "a designer might tweak it" → Minor. **Bias Minor when genuinely uncertain** — a false Critical erodes trust faster than a missed nitpick.

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
[Minor]    A11–F11: bottom nav icons sit tight against the top divider; gap looks
  about half the design's (estimate). Figma node 123:456.
```

Always include: severity, cell address(es), what's wrong, and the annotated image path (plus the Figma node id in design mode). The cell address is what makes a finding actionable — "title is clipped" is vague; "title clipped in C3–D3" points straight at it.

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
- In design mode, read the **actual-grid and design-grid** pair — that pair *is* the comparison. Don't also read the ungridded originals.
- Add scroll-position shots (`-top/-mid/-bottom`) only when content genuinely extends beyond the fold; each is another image in context.
- Reserve vision for 🎨 UI TCs and explicit design-QA requests. A functional TC with a clean `assertVisible` doesn't need eyes on it.
- Skip `--emit-legend` unless you need the coordinate map.
