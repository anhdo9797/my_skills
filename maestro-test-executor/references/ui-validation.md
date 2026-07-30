# UI Validation: Figma → Durable, Agent-Free Checks

The goal of UI validation is to verify that the app screen matches the Figma design. The naive way — have the Agent eyeball Figma vs. a screenshot on every run — works, but it puts the Agent in the regression loop forever: slow, token-heavy, and impossible to run headless in CI.

So this skill is built the other way around: **the Agent's vision is an authoring tool, not a runtime dependency.** The Agent looks at the design *once*, while writing the test, and turns it into checks that Maestro (and a tiny diff script) can run forever without any Agent involved.

Two tiers of durable check come out of that authoring pass:

| Tier | What it checks | Mechanism | Agent at regression time? |
|------|----------------|-----------|---------------------------|
| **1 — Assertions** (always) | Specific, nameable facts from the design: static labels, button text, key elements present/absent, counts, states | Maestro `assertVisible` / `assertNotVisible` / property assertions baked into the TC YAML | **No** — pure Maestro |
| **2 — Visual baseline diff** (optional) | Layout / color / spacing drift that assertions can't name | `scripts/compare_screenshots.py` compares the fresh screenshot against an approved baseline, with dynamic regions masked | **No** — deterministic script |

The Agent only re-enters when the **design changes** or the **baseline must be re-approved** — i.e. when authoring, not when running. Maestro itself has no native "compare to Figma" or pixel-diff command, which is exactly why this split exists.

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

---

## Procedure summary

**At authoring time (Agent in the loop, once per TC):**
1. Name the **subject under test** — the region this TC is about; focus there.
2. Mask the chrome bands; classify content-area elements static vs. dynamic.
3. **Tier 1:** turn every static fact into an `assertVisible`/`assertNotVisible`/property assertion in the YAML.
4. **Tier 2 (if requested):** approve the baseline screenshot and record its masks sidecar.

**At regression time (no Agent):**
- Maestro runs the flow → Tier 1 assertions pass/fail deterministically.
- `compare_screenshots.py` runs → Tier 2 pass/fail deterministically.
- The TC's status is PASS only if both tiers pass. A Tier 2 failure links the heatmap as evidence.

## Mapping verdict → TC status

- All Tier 1 assertions pass (and Tier 2 within threshold, if used) → **PASS**
- A cosmetic-only Tier 2 drift the user accepts → **PASS** with a note (and update the baseline)
- A failed Tier 1 assertion, or Tier 2 drift over threshold on a static region → **FAIL**

When you report a FAIL, state the reasoning so a developer can trust it — name the element, say why it's static (not chrome or API content), and quote design vs. actual. Evidence links the Figma design, the app capture, and (Tier 2) the diff heatmap.

## When in doubt

If you can't confidently tell whether a difference is a real defect or expected dynamic/chrome variation, **say so and ask the user** rather than guessing. A confidently-wrong FAIL wastes developer time; a confidently-wrong PASS hides a bug. This judgment is exactly the part that belongs at authoring time — get it right once, encode it as an assertion or a mask, and regression stays trustworthy without you.
