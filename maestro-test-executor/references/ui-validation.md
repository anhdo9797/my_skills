# UI Validation: Three Tiers of Visual Check

The goal of UI validation is to verify that the app screen looks the way it should — matching the Figma design where one exists, and free of layout defects either way.

The naive way — have the Agent eyeball Figma vs. a screenshot on every run — works, but it puts the Agent in the regression loop forever: slow, token-heavy, impossible to run headless in CI. So the durable checks are built the other way around: **the Agent's vision is an authoring tool, not a runtime dependency.** It looks at the design *once*, while writing the test, and turns it into checks that Maestro (and a tiny diff script) can run forever without any Agent.

But some things genuinely need eyes — a clipped title, two overlapping labels, a first-ever run with no baseline to diff against. That's a separate, deliberately on-demand tier. Three tiers total:

| Tier | What it checks | Mechanism | Needs the Agent? |
|------|----------------|-----------|------------------|
| **1 — Assertions** (always) | Specific, nameable facts from the design: static labels, button text, key elements present/absent, counts, states | Maestro `assertVisible` / `assertNotVisible` / property assertions baked into the TC YAML | **No** — pure Maestro, CI-safe |
| **2 — Baseline diff** (optional) | Layout / color / spacing *drift* from an approved capture, which assertions can't name | `scripts/compare_screenshots.py` diffs the fresh screenshot against the baseline, with dynamic regions masked | **No** — deterministic script, CI-safe |
| **3 — Visual review** (on demand) | How the screen *looks*: overlap, truncation, clipping, misalignment, wrong state — defects with no baseline and no name | `scripts/grid_overlay.py` + the Agent scanning the gridded screenshot cell by cell → severity → verdict | **Yes** — that's the point; see `visual-review.md` |

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

## Tier 3 — Visual review from the screenshot (on demand)

Tiers 1 and 2 both need something to compare against: a named fact, or an approved baseline. Tier 3 needs neither — the Agent reads the screenshot and judges the layout directly, which is the only way to catch a clipped title or two overlapping labels on a screen nobody has baselined yet.

To keep that judgment systematic rather than one impressionistic glance, `scripts/grid_overlay.py` stamps a labeled grid over the screenshot first; the review then walks it cell by cell and every finding carries an address (`C3`, `A6:F8`) a reviewer can find again. Findings are classified **Critical** (a user would notice and be blocked — overlap, clipping, off-screen content, missing element) or **Minor** (subjective polish), and the severity decides the verdict: any Critical → ❌ FAIL, only Minor → 🔍 REVIEW, clean → ✅ PASS. The deliverable is an annotated image with the defective cells washed red.

```bash
python3 scripts/grid_overlay.py report/screenshots/TC-010_default.png \
    --cols 6 --rows 13 --out report/grid/TC-010_default-grid.png
# …scan the gridded image cell by cell, then mark only the cells with visible evidence:
python3 scripts/grid_overlay.py report/screenshots/TC-010_default.png \
    --cols 6 --rows 13 --highlight "E2:F3" --out report/vision/TC-010_default-report.png
```

**Read `visual-review.md` before running a Tier 3 pass.** The full method is there, and so are the two judgment calls that decide whether the result is trustworthy: what vision can and cannot prove (it estimates, it does not measure — never claim a `dp`/`sp` value from a screenshot), and the **data-state vs. design-state** rule that stops the most common false FAIL (the app showing three items where the design shows six is *data*, not a defect).

A clean Tier 3 pass is also the natural moment to **promote the screenshot to a Tier 2 baseline** — vision just confirmed it's correct, so it's a baseline you can trust. That's the intended graduation: Tier 3 finds and confirms; Tiers 1 and 2 lock it in for every future run.

---

## Procedure summary

**At authoring time (Agent in the loop, once per TC):**
1. Name the **subject under test** — the region this TC is about; focus there.
2. Mask the chrome bands; classify content-area elements static vs. dynamic.
3. **Tier 3 pass:** grid the capture and scan it cell by cell — this is what tells you the screen is actually correct before you encode anything, and it catches layout defects no assertion would name.
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
- A failed Tier 1 assertion, Tier 2 drift over threshold on a static region, or a **Critical** Tier 3 finding → **❌ FAIL**
- Only **Minor** Tier 3 findings, or exact typography/spacing parity that vision can't measure → **🔍 REVIEW** (evidence captured, a human decides)

When you report a FAIL, state the reasoning so a developer can trust it — name the element, say why it's static (not chrome or API content), and quote design vs. actual. For a Tier 3 FAIL, name the cell(s). Evidence links the Figma design, the app capture, and whichever artifact proved it: the Tier 2 heatmap or the Tier 3 annotated image.

## When in doubt

If you can't confidently tell whether a difference is a real defect or expected dynamic/chrome variation, **say so and ask the user** rather than guessing. A confidently-wrong FAIL wastes developer time; a confidently-wrong PASS hides a bug. This judgment is exactly the part that belongs at authoring time — get it right once, encode it as an assertion or a mask, and regression stays trustworthy without you.
