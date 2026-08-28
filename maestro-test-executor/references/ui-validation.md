# UI Validation: Three Tiers of Visual Check

The goal of UI validation is to verify that the app screen looks the way it should — matching the Figma design where one exists, and free of layout defects either way.

> **Read `ui-metrics.md` first.** It defines what a UI case may assert and how precisely: text content is **exact** (no tolerance, read from the view hierarchy), while spacing, element size, font size, and font weight are **relative** (ratios against the design and against the screen's own baseline, with a tolerance band). Outside its rule, either class fails the case outright. Everything below is the machinery; that document is the contract, and without it a UI case degrades into impressions that can never fail.

The naive way — have the Agent eyeball Figma vs. a screenshot on every run — works, but it puts the Agent in the regression loop forever: slow, token-heavy, impossible to run headless in CI. So the durable checks are built the other way around: **the Agent's vision is an authoring tool, not a runtime dependency.** It looks at the design *once*, while writing the test, and turns it into checks that Maestro (and a tiny diff script) can run forever without any Agent.

But some things genuinely need eyes — a clipped title, two overlapping labels, a first-ever run with no baseline to diff against. That's a separate, deliberately on-demand tier. Three tiers total:

| Tier | What it checks | Mechanism | Needs the Agent? |
|------|----------------|-----------|------------------|
| **1 — Assertions** (always) | Specific, nameable facts from the design: static labels, button text, key elements present/absent, counts, states | Maestro `assertVisible` / `assertNotVisible` / property assertions baked into the TC YAML | **No** — pure Maestro, CI-safe |
| **2 — Baseline diff** (optional) | Layout / color / spacing *drift* from an approved capture, which assertions can't name | `scripts/compare_screenshots.py` diffs the fresh screenshot against the baseline, with dynamic regions masked | **No** — deterministic script, CI-safe |
| **3 — Visual review** (on demand) | Two things at once: **measured parity** with the design (text exact; spacing / size / weight as ratios) and how the screen *looks* — overlap, truncation, clipping, misalignment, wrong state | `text_audit.py` + `spacing_audit.py` + `typography_audit.py` measure; then `pair_view.py` / `grid_overlay.py` and the Agent scan cell by cell → severity → verdict | **Partly** — the measurements are scripts and run without one; the cell scan is the Agent's job. See `visual-review.md` |

Tiers 1 and 2 are the regression contract: they run every time, forever, unattended. Tier 3 is the pass that *creates* that contract and catches what it can't express. The Agent re-enters only when the design changes, a baseline must be re-approved, or the tester explicitly asks for a visual QA pass — not on every run.

**Which tier for the request in front of you:**

- *"Verify the Edit Recipe screen matches Figma, and keep checking it every release"* → Tier 1 (+ Tier 2 if drift matters), authored with a Tier 3 pass to get it right once.
- *"Kiểm tra giao diện từng màn hình xem có lỗi hiển thị không"* / *"test UI bằng ảnh chụp"* / no design provided → **Tier 3**, heuristic mode. There's nothing to assert against yet; the screenshot is the test.
- *"Tier 2 says 3% drift — is that a bug?"* → **Tier 3** on the same capture to say *what* changed and whether it matters.

Maestro itself has no native "compare to Figma" or pixel-diff command, which is exactly why this split exists.

---

## Why a design and a screenshot are never pixel-identical

Both tiers depend on reasoning about *difference*. A Figma frame and a real device screenshot of "the same screen" always differ in ways that are **not bugs**. If you treat every difference as a defect, Tier 1 produces brittle assertions and Tier 2 produces false positives on every run. Three sources of expected, never-a-bug difference:

1. **System chrome differs.** The Figma frame carries a *mock* status bar (often "9:41", full battery/signal) and a mock bottom system bar / home indicator. The real screenshot carries the *device's actual* status bar (real clock, battery %, Wi-Fi/cellular, notch/cutout) and the real OS navigation (Android gesture pill or 3-button nav; iOS home indicator). These never match.

2. **API / dynamic content differs.** An `Image` showing a placeholder photo in Figma shows a *different, real photo from the API* in the app. Lists show real rows; counts, prices, dates, names, avatars, badges reflect live data. The *content* legitimately differs; only its *treatment* (position, shape, aspect ratio, fallback) is designed.

3. **Rendering environment differs.** Font hinting, anti-aliasing, shadow blur, sub-pixel spacing, minor color-profile shifts. Noise, not defects.

So the question is never "are these two images the same?" It is: **"does the app render the *designed structure and style* correctly, given that content and chrome will differ?"**

### The three-band model: mask the chrome

Every mobile screen splits into three horizontal bands. Decide everything using only the middle band.

```
┌─────────────────────────────┐
│  ▓▓ STATUS BAR ▓▓           │  ← IGNORE (clock, battery, signal, notch)
├─────────────────────────────┤
│      CONTENT AREA           │  ← the only band that decides pass/fail
│   (the subject under test)  │
├─────────────────────────────┤
│  ▓▓ SYSTEM NAV ▓▓          │  ← IGNORE OS bar; compare only an APP-owned tab bar
└─────────────────────────────┘
```

- **Top band:** always ignore. → In Tier 2, this is `--ignore-top`.
- **Bottom band:** ignore the OS navigation. But an **app-owned** bottom/tab bar that appears in the design *is* design — compare it. → In Tier 2, `--ignore-bottom` for the OS strip only.
- **Middle band:** where the verdict lives.

### Static vs. dynamic: the classification both tiers run on

Within the content area, sort what you see into two buckets:

| | **Static / structural** — MUST match design | **Dynamic / data-driven** — content WILL differ |
|---|---|---|
| Examples | Layout & spacing, component shape/size, colors & theme, fonts/weights, icons, static labels & headings, button text, tab labels, empty/error/loading designs | Photos from API/CDN, user text, list rows, counts/badges, prices, dates & times, avatars, search results |
| Tier 1 → | Becomes an **assertion** (`assertVisible: "Save Recipe"`) | Do **not** assert exact content; at most assert the container/placeholder exists |
| Tier 2 → | Part of the **compared** area | **Mask** it (`--mask x1,y1,x2,y2`) so it never trips the diff |

**Worked example — image element.** Figma: recipe card with a placeholder photo, 16:9, rounded, at top. App: a *different* real photo. → content differs = expected. Tier 1: don't assert the photo; assert the title/button around it. Tier 2: mask the photo rectangle, then diff the rest. Only flag if the app renders the image square/un-rounded/misplaced.

**Worked example — system chrome.** Figma status bar "9:41" full battery; app "14:32" 47%. → top band, ignore. Tier 2: `--ignore-top`.

**Worked example — static label.** Figma button "Save Recipe"; app "Save". → static = real defect. Tier 1: `assertVisible: "Save Recipe"` would have caught this deterministically, forever.

---

## Tier 1 — Author durable assertions from the design (always do this)

This is the primary, CI-friendly form of UI validation. While looking at the Figma design once, extract every **static** fact and bake it into the TC's YAML as an assertion. These run on every future regression with zero Agent involvement.

```yaml
# TC-010: Edit Recipe screen matches Figma  (Tier 1 — assertions live in the flow)
appId: ${APP_ID}
name: "TC-010: Edit Recipe screen matches Figma"
tags: [ui-validation, edit-recipe]
env:
  APP_ID: <app-id>
---
- runFlow: ../../common/launch_clear_state.yaml
- runFlow: ../flow/navigate_to_edit_recipe.yaml
- waitForAnimationToEnd

# --- Static facts extracted from the Figma design ---
- assertVisible: "Edit Recipe"            # screen title
- assertVisible: "Save Recipe"            # primary button label (NOT "Save")
- assertVisible:
    id: "recipe_photo"                    # the image container exists (don't assert WHICH photo)
- assertVisible: "Ingredients"            # section header
- assertNotVisible: "Delete"             # design has no delete button on this screen

- takeScreenshot: "TC-010_result"         # evidence + Tier 2 baseline input
```

What makes a good Tier 1 assertion: it names a **static** element (from the table above), it's specific (exact label text, a stable `id`), and it would still be true tomorrow regardless of API data. Don't assert dynamic content (a specific recipe name, a count, a date) — that makes the test flaky.

**Maestro's `text:` is a regular expression, not a literal.** So `assertVisible: "Save"` can match a button reading "Save draft", and copy containing `.`, `(`, `?`, `+`, or `*` matches more loosely than it looks. When the exact string is the point, anchor it and escape the metacharacters — `text: "^Save Recipe$"`, `text: "^Quên mật khẩu\?$"`. This is a real source of assertions that pass on the wrong string.

Even anchored, an assertion set is a *sample* of the copy — you write the handful of labels you thought to write. For a screen whose copy is specified (a Figma node, a PRD, a plan that quotes the strings), run `scripts/text_audit.py` as well: it compares **every** rendered string against the expected list, exactly, and catches the leaked i18n key and the diacritic-stripped label that nobody thought to assert. Tier 1 is the CI-safe subset; `text_audit.py` is the complete check at authoring time. See `ui-metrics.md`.

If you can't reach a screen or an element selector is unknown, follow `selectors-and-inspection.md`.

## Tier 2 — Visual baseline diff (optional, for drift assertions can't name)

Assertions catch *named* facts. They can't catch "the card got 20px shorter" or "the accent color shifted". For that, capture an **approved baseline** once and diff future runs against it deterministically.

**Authoring (once, Agent-assisted):**
1. Run the capture flow; confirm the screenshot genuinely matches the design (this is where Agent vision is used).
2. Decide the masks: the status bar band, the OS nav band, and every **dynamic** region (API images, live lists). Record them so regression reuses them — save a sidecar next to the baseline:

   ```json
   // report/baseline/TC-010.masks.json
   {
     "ignore_top": "6%",
     "ignore_bottom": "5%",
     "masks": ["0,180,1080,780", "0,820,1080,1400"]
   }
   ```
3. Promote the approved screenshot to the baseline: `report/baseline/TC-010.png`.

**Regression (every run, no Agent):**
```bash
python3 scripts/compare_screenshots.py \
  .maestro/<app-id>/<feature>/report/baseline/TC-010.png \
  .maestro/<app-id>/<feature>/report/screenshots/TC-010_result.png \
  --masks-file .maestro/<app-id>/<feature>/report/baseline/TC-010.masks.json \
  --threshold 0.01 \
  --out .maestro/<app-id>/<feature>/report/diff/TC-010_diff.png
```

The script prints a JSON summary and exits `0` (within threshold → PASS) or `1` (drift exceeds threshold → FAIL); `--out` writes a heatmap of where it drifted. Read the JSON, not the images — only open the heatmap (one image) if it failed and you need to see where.

Tuning: `--tolerance` is the per-channel intensity delta below which a pixel counts as unchanged (default 24, absorbs anti-aliasing); `--threshold` is the allowed changed-pixel ratio (default 0.01 = 1%). If a run fails only because of a newly-dynamic region, add a mask to the sidecar rather than loosening the threshold.

## Tier 3 — Measured parity + visual review (on demand)

Tiers 1 and 2 both need something to compare against: a named fact, or an approved baseline. Tier 3 needs neither — it works from the design reference (or from nothing at all), which is the only way to judge a screen nobody has baselined yet.

Two things happen in this tier, and keeping them distinct is what makes it able to fail. **Measured parity** compares the screen to the design in numbers: exact strings from the hierarchy, and spacing / size / weight as ratios. Those are scripts, they are deterministic, and a result outside tolerance fails the case on its own. **Visual review** is the Agent reading the composite image for what no script measured — a clipped title, two overlapping labels, a stuck spinner, an unreadable contrast.

To keep that judgment systematic rather than one impressionistic glance, the screenshot is gridded first so every finding carries an address (`C3`, `A6:F8`) a reviewer can find again. There are two entry points, depending on whether a design reference exists:

- **No design reference (heuristic mode):** `scripts/grid_overlay.py` grids the screenshot alone; the review walks it cell by cell against a defect checklist.
- **A design reference exists (design mode):** run **four** checks, because they answer four different questions and each is blind to the others'. The first three are measurements and produce numbers; only the last needs eyes.
  - `scripts/pair_view.py` — **content, presence, style.** It first **crops the screenshot's chrome bands** (status bar, OS nav) so its content lines up with the chrome-less design export, **then** grids both at the same coordinates, computes a real pixel diff, and composes them into one side-by-side image with every cell whose diff exceeds a threshold flagged in amber. Skip straight to `grid_overlay.py` on two independently-gridded images and cell `C4` in one is very likely a different region than `C4` in the other — the chrome heights don't match, so nothing built on that alignment is trustworthy.
  - `scripts/text_audit.py` — **content: the exact strings, from the view hierarchy.** Not from the image: reading copy off a screenshot is OCR by another name, and it is least reliable on the small diacritics that matter most. Every mismatch is Critical; there is no tolerance on text.
  - `scripts/typography_audit.py` — **type: font size and font weight, as ratios.** It measures each text band's x-height and stroke-thickness-over-x-height, both against the design and against its own screen's body text. It never claims an `sp` value — that isn't in a screenshot — but "the heading renders at 0.67× the design's size and at body weight" is measured, and it fails the case.
  - `scripts/spacing_audit.py` — **geometry: gaps, element heights, side margins, measured in design px/dp.** This is not optional on a spacing question, because `pair_view.py` structurally cannot answer it: to align cells it resizes the design onto the screenshot's width *and* height, which rescales the design's vertical rhythm onto the device's — so a screen whose every padding is inflated by one factor diffs **clean**, and when the aspect ratios differ (an iOS export vs an Android screen: routine) it suppresses its own flags entirely. `spacing_audit.py` scales by **width only**, segments both images into element bands, and compares gap by gap; since gaps are differences between positions, the result survives different chrome, screen size, and density.

Findings are classified **Critical** (a user would notice and be blocked — overlap, clipping, off-screen content, missing element — or a *measured* deviation outside tolerance) or **Minor** (subjective, or measured but small and localized), and the severity decides the verdict: any Critical → ❌ FAIL, only Minor → 🔍 REVIEW, clean → ✅ PASS. The deliverable is an annotated image with the defective cells washed red, plus the measured numbers in the finding text.

```bash
# Heuristic mode
python3 scripts/grid_overlay.py report/screenshots/TC-010_default.png \
    --cols 6 --rows 13 --out report/grid/TC-010_default-grid.png

# Design mode, part 1 — content/style: crops chrome, aligns, diffs, and flags in one step
python3 scripts/pair_view.py report/figma/TC-010_default.png report/screenshots/TC-010_default.png \
    --cols 6 --rows 13 --crop-actual-top 6% --crop-actual-bottom 4% \
    --out report/grid/TC-010_default-pair.png

# Design mode, part 2 — content: EXACT text, from the hierarchy (never from pixels)
maestro hierarchy > /tmp/TC-010.json
python3 scripts/text_audit.py --expected report/figma/TC-010_expected.json \
    --actual /tmp/TC-010.json --out report/text/TC-010_default.json

# Design mode, part 3 — geometry: MEASURES gaps / heights / margins in design px-dp
python3 scripts/spacing_audit.py report/figma/TC-010_default.png report/screenshots/TC-010_default.png \
    --crop-design-top 6% --crop-design-bottom 2% --crop-actual-top 4% \
    --out report/grid/TC-010_default-spacing.png

# Design mode, part 4 — type: MEASURES font size and weight as ratios
python3 scripts/typography_audit.py report/figma/TC-010_default.png report/screenshots/TC-010_default.png \
    --crop-design-top 6% --crop-design-bottom 2% --crop-actual-top 4% --design-width-dp 390 \
    --out report/grid/TC-010_default-type.png

# …scan the gridded/paired image cell by cell (accounting for every flagged
# cell first in design mode), then mark only the cells with visible evidence
# on the FINAL report image — always from the plain screenshot via grid_overlay.py:
python3 scripts/grid_overlay.py report/screenshots/TC-010_default.png \
    --cols 6 --rows 13 --highlight "E2:F3" --out report/vision/TC-010_default-report.png
```

**Read `ui-metrics.md` and `visual-review.md` before running a Tier 3 pass.** Between them they carry the two judgment calls that decide whether the result is trustworthy: which properties are measured versus estimated (and therefore which findings may fail a case and which must stay 🔍 REVIEW), and the **data-state vs. design-state** rule that stops the most common false FAIL — the app showing three items where the design shows six is *data*, not a defect.

A clean Tier 3 pass is also the natural moment to **promote the screenshot to a Tier 2 baseline** — vision just confirmed it's correct, so it's a baseline you can trust. That's the intended graduation: Tier 3 finds and confirms; Tiers 1 and 2 lock it in for every future run.

---

## Procedure summary

**At authoring time (Agent in the loop, once per TC):**
1. Name the **subject under test** — the region this TC is about; focus there.
2. Mask the chrome bands; classify content-area elements static vs. dynamic.
3. **Tier 3 pass:** run the measurements (`text_audit.py`, `spacing_audit.py`, `typography_audit.py`) and read their JSON, then grid the capture and scan it cell by cell. This is what tells you the screen is actually correct before you encode anything — the measurements settle parity, the scan catches the layout defects no assertion and no ratio would name.
4. **Tier 1:** turn every static fact into an `assertVisible`/`assertNotVisible`/property assertion in the YAML.
5. **Tier 2 (if requested):** promote the vision-approved screenshot to the baseline and record its masks sidecar.

**At regression time (no Agent):**
- Maestro runs the flow → Tier 1 assertions pass/fail deterministically.
- `compare_screenshots.py` runs → Tier 2 pass/fail deterministically.
- The TC's status is PASS only if both tiers pass. A Tier 2 failure links the heatmap as evidence.

**On demand (Agent, when asked or when Tier 2 drift needs explaining):** Tier 3 as above.

## Mapping verdict → TC status

- All Tier 1 assertions pass (and Tier 2 within threshold, if used; Tier 3 clean, if run) → **✅ PASS**
- A cosmetic-only Tier 2 drift the user accepts → **✅ PASS** with a note (and update the baseline)
- A failed Tier 1 assertion, Tier 2 drift over threshold on a static region, **any text mismatch or text defect**, **any measured spacing / size / weight ratio outside tolerance**, or any other **Critical** Tier 3 finding → **❌ FAIL**
- Only **Minor** Tier 3 findings, or an observation nothing measured — a colour impression, a `low`-confidence weight reading, an `INCONCLUSIVE` audit — → **🔍 REVIEW** (evidence captured, a human decides)

When you report a FAIL, state the reasoning so a developer can trust it — name the element, say why it's static (not chrome or API content), and quote design vs. actual. For a Tier 3 FAIL, name the cell(s). Evidence links the Figma design, the app capture, and whichever artifact proved it: the Tier 2 heatmap or the Tier 3 annotated image.

## When in doubt

If you can't confidently tell whether a difference is a real defect or expected dynamic/chrome variation, **say so and ask the user** rather than guessing. A confidently-wrong FAIL wastes developer time; a confidently-wrong PASS hides a bug. This judgment is exactly the part that belongs at authoring time — get it right once, encode it as an assertion or a mask, and regression stays trustworthy without you.
