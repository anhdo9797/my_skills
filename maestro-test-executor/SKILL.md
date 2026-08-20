---
name: maestro-test-executor
description: Execute QA test plans by generating Maestro YAML flows one test case at a time, running each immediately, reviewing UI appearance from screenshots, and producing a consolidated test report. Designed for non-technical testers — no source code reading required. Use this skill whenever the user wants to automate test cases with Maestro, convert a manual test plan into Maestro flows, run E2E tests on mobile apps, or validate app UI against Figma design screenshots. Also use it for visual/UI checking from screenshots — requests that mention design review, screenshot comparison, layout defects, text overflow, overlapping elements, clipped or truncated text, misaligned UI, wrong spacing or padding vs the design, "kiểm tra giao diện", "test visual", "test UI bằng ảnh chụp", "so sánh với Figma", "spacing/padding sai so với design", "phát hiện lỗi hiển thị / tràn chữ / lệch layout": it captures a screenshot per screen, overlays a labeled grid, scans it cell-by-cell with vision, **measures** gaps, element sizes, and margins against the design in dp so a spacing deviation is reported as a number instead of an impression, and auto-fails on serious defects with an annotated image marking exactly which cells are wrong. Also trigger when the user mentions Maestro flows, YAML test generation, mobile UI testing, simulator screenshots, or wants to validate app behavior against a test plan — even if they don't explicitly say "maestro-test-executor".
---

# Maestro Test Executor

Converts a QA test plan into executable Maestro YAML flows, runs each case immediately after writing it, validates how the UI looks (against a Figma design, or from the screenshot alone), and produces a consolidated test report.

**Designed for non-technical testers.** There is no source code reading at any step. Selectors come from existing YAML flows, Maestro MCP live inspection, and what's visible on screen.

> **Scope rule:** This skill works exclusively within the `.maestro/<app-id>/` directory of the current workspace. All flow discovery, selector learning, and YAML generation happen inside this single boundary.

> **Token rule (read this first):** Large artifacts — raw view-hierarchy dumps (~250k tokens/screen), screenshots, and command logs — must never flood the main context. Route hierarchies through `scripts/filter_hierarchy.py` or a subagent, read failure screenshots only when needed, and `grep` logs instead of reading them whole. Details in `references/selectors-and-inspection.md`. **The one deliberate exception is a Tier 3 visual review**, where reading the screenshot *is* the test — even there, read only the composite(s) that already contain both sides (`-grid.png`, or `-pair.png` + `-spacing.png`), one set per screen state, and read `spacing_audit.py`'s JSON before its image.

> **Resume rule:** A large plan is run across **multiple sessions** (e.g. session 1 = all P0 cases, session 2 = P1, …). There is exactly **one living report** and **one YAML file per TC id** per feature — every session **updates them in place**, never replaces or re-timestamps them. On starting a session, read the existing `report.md` first to see what's already done and continue from there. The full resume/upsert model is in `references/reporting.md` — read it before Phase 4 whenever a report already exists.

## Prerequisites

- **Maestro CLI** installed and on PATH (`maestro --version`)
- A running **emulator/simulator** or connected device
- **Test plan** — a list of test cases from the user (or output from `qa-test-planner`)
- **Supporting documents** (optional) — PRD, feature spec, or Figma URL to clarify expected behavior and UI
- **Pillow** — needed for Tier 2 baseline diff and Tier 3 grid overlay / design pairing / spacing measurement (`pip3 install Pillow`, one time). Tier 1 assertion-based UI checks don't need it

## Reference map

This SKILL.md is the orchestrator. Each phase points to a focused reference — read the reference when you reach that phase, not before.

| Topic | Reference | Read when |
|-------|-----------|-----------|
| Finding selectors cheaply, live inspection, selector catalog | `references/selectors-and-inspection.md` | You need a selector you don't already have |
| YAML structure, templates, execution command, failure handling | `references/yaml-flows.md` | Writing or fixing flows (Phase 4) |
| The three UI tiers, choosing between them, dynamic-UI reasoning | `references/ui-validation.md` | Validating UI appearance (Phase 5) |
| Tier 3 visual review: chrome-aligned design pairing, cell-by-cell scan, severity → verdict, annotated image | `references/visual-review.md` | Judging a screen from its screenshot (Phase 5, Tier 3) |
| Report template, resume/upsert across sessions, full screenshot paths, failed-case repro for bug logging | `references/reporting.md` | Producing/updating the report (Phase 6), or resuming a prior session |
| Full Maestro command-to-action mapping | `references/maestro_commands.md` | Mapping a step to the right command |

## Workflow Overview

```
Input: Test Case List + Documents (optional)
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ Phase 1: GATHER INPUT                                │
│   • Receive test case list and optional documents    │
│   • Ask for app ID, platform, feature name           │
│   • Clarify ambiguous steps from test descriptions   │
├──────────────────────────────────────────────────────┤
│ Phase 2: SCAN EXISTING FLOWS                         │
│   • Scan .maestro/<app-id>/ for existing YAML flows  │
│   • Build selector catalog from proven flows         │
│   • Identify reusable shared flows                   │
├──────────────────────────────────────────────────────┤
│ Phase 3: ANALYZE TEST CASES                          │
│   • Break each TC into discrete Maestro steps        │
│   • Classify by type (functional / UI) + automatable │
│   • Map steps → Maestro commands                     │
├──────────────────────────────────────────────────────┤
│ Phase 4: GENERATE → EXECUTE (per test case loop)     │
│   For each automatable TC:                           │
│   ① Write YAML  ② Create file  ③ Run                 │
│   ④ Record result  ⑤ Fix if failed → re-run → next  │
├──────────────────────────────────────────────────────┤
│ Phase 5: UI VALIDATION (if 🎨 UI TCs exist)          │
│   Tier 1  assertions in YAML      → no Agent, CI-safe │
│   Tier 2  baseline pixel diff     → no Agent, CI-safe │
│   Tier 3  VISUAL REVIEW (on demand, Agent):           │
│     screenshot → grid → scan cell-by-cell →           │
│     Critical/Minor → FAIL / 🔍 REVIEW / PASS →        │
│     annotated image with defect cells washed red      │
├──────────────────────────────────────────────────────┤
│ Phase 6: REPORT (resumable, one living report)       │
│   • Upsert this session's rows into report.md        │
│   • Full screenshot paths + failed-case repro steps  │
│   • Recompute summary; log the session; announce     │
└──────────────────────────────────────────────────────┘
```

## Phase 1: Gather Input

Collect the inputs needed to organize and target flows.

**Required:** test case list (pasted or a file path), **App ID** (e.g. `com.example.app`), **platform** (Android/iOS), **feature name** (used to organize flows, e.g. `edit-recipe`).
**Optional:** device name (auto-detect by default), **design reference** for UI TCs — a Figma URL (node-specific, so it identifies which frame) or exported design images; without one, UI TCs still run as a Tier 3 defect scan — app-state setup (`clearState: true` by default).
**Session scope (for large plans):** which subset this session runs — typically a priority slice (**P0**, then **P1**, …) or an explicit TC-id range. If the user is running the plan in slices and doesn't say, ask which slice this session covers.

**Check for a prior session first.** If `.maestro/<app-id>/<feature>/report/report.md` already exists, this is a **resume**: read it (its Test Results table shows what's ✅/❌/⬜), record the device/OS/build already noted there, and run only the in-scope TCs still ⬜ PENDING. Do not regenerate the report or re-run passed cases unless asked. See the resume model in `references/reporting.md`.

If anything required is missing, ask for it all in one message. If a supporting document (PRD, spec, Figma) is provided, read it to extract UI labels, screen names, expected text, and navigation flows, and use that to clarify ambiguous steps — but **never read app source code**. If a step is still ambiguous, ask the user or inspect the live UI via the cheap path in `references/selectors-and-inspection.md`.

## Phase 2: Scan Existing Flows

Before generating any new YAML, scan `.maestro/<app-id>/` to learn from flows that already work — they contain selectors proven against the running app, the most reliable source of selector truth.

1. **List directories** under `.maestro/<app-id>/` to see what's already automated (`common/`, existing features, etc.).
2. **Read related YAML** — same feature first, then features sharing navigation paths, then `common/`/`shared/`.
3. **Build a selector catalog** (element → selector → source flow) and persist it to `.maestro/<app-id>/selectors.md`.
4. **Identify reusable shared flows** you can chain with `runFlow`.

Reuse aggressively — chain existing navigation flows instead of rewriting them. See `references/yaml-flows.md` for the reuse pattern and `references/selectors-and-inspection.md` for what to scan and what never to read.

## Phase 3: Analyze Test Cases

Break each test case into a concrete sequence of Maestro steps, and classify it along **two axes**.

**Type — what the test verifies:**
- 🔧 **Functional** (default) — behavior via UI actions + assertions (taps, inputs, text/state checks). Executed end-to-end in Phase 4.
- 🎨 **UI validation** — a screen's *appearance* is correct: matching a Figma design where one exists, and free of layout defects either way. Three tiers, chosen per TC in Phase 5: **Tier 1** Maestro assertions and **Tier 2** baseline pixel diff run forever without an Agent; **Tier 3** visual review has the Agent read the screenshot. See `references/ui-validation.md`.

**Automatability:** ✅ automatable · ⚠️ partially automatable (external setup / subjective) · ❌ skip (performance, manual-only, hardware sensor).

A UI-validation TC reads like any other plan entry — e.g. *"TC-010: Edit Recipe screen matches Figma design"* or *"TC-011: Home screen has no layout defects"* — and earns a row in the same Test Results table as functional TCs. **A UI TC needs no Figma URL:** with a design it's a parity check, without one it's a defect scan (Tier 3 heuristic mode). Don't turn a *"kiểm tra giao diện"* request away for lack of a design — the screenshot alone catches clipped text, overlap, and misalignment.

Then for each automatable step, determine **what action**, **which element** (from the selector catalog), **what to assert**, and **which Maestro command** (`references/maestro_commands.md`). For unknown selectors, follow the resolution order in `references/selectors-and-inspection.md`. **Present a classification summary (with each TC's type and priority) to the user before generating any YAML.**

**Seed the report board (once, if no report exists yet).** For a multi-session plan, write *every* planned TC — the whole plan, all priorities — into `report.md`'s Test Results table as `⬜ PENDING` with its priority filled in, before running anything. This makes the report a master progress board from the start, so later sessions (and the user) can see what's still outstanding. No runs happen during seeding, so it's cheap. See `references/reporting.md`.

## Phase 4: Generate → Execute (Per Test Case Loop)

**Do not write all test cases first.** Process one TC at a time — write the YAML, create the file, run it, record the result, then move on. This catches selector issues early and avoids debugging ten failed flows at once.

```
For each in-scope TC still ⬜ PENDING:
  ① Analyze steps   ② Reuse-or-write YAML: testcase/TC-XXX_<name>.yaml (tag its priority)
  ③ Run: maestro test --test-output-dir=... testcase/TC-XXX_<name>.yaml
  ④ PASS → upsert ✅ row (+ full screenshot path), next TC
     FAIL → read error, fix YAML, re-run → upsert final row + write Failed Test Details → next TC
```

**Reuse YAML by TC id — don't duplicate across sessions.** The filename is keyed to the TC id (`TC-017_add_ingredient.yaml`). If it already exists (seeded plan, or a prior session), run it as-is; edit it in place only if the step logic genuinely changed. Never create `TC-017_..._v2.yaml` or a re-slugged copy — that splits history and breaks the id→row→file mapping the report depends on. Tag every TC with its priority (`tags: [<feature>, P1]`) so a session can select its slice with `maestro test --include-tags P1`.

**Capture the path to the failure, not only the crash frame.** Where practical, add a `takeScreenshot` on the screen just *before* the failing action so the report can show both the setup and the failure — this is what makes a failed case reproducible enough to file as a bug next phase.

A 🎨 UI-validation TC runs through the **same loop**, with one extra sub-step after ③. Its YAML navigates to the screen, asserts the **Tier 1** static facts (`assertVisible`/`assertNotVisible`/property checks), and takes a screenshot into `report/screenshots/`. Those assertions are pure Maestro — they pass/fail deterministically with no Agent. Then:

- **Tier 2**, if a baseline exists: run `scripts/compare_screenshots.py` against it and read the JSON verdict.
- **Tier 3**, when this TC calls for a visual review (no baseline yet, an explicit design-QA request, or Tier 2 reported drift you need explained): with no design reference, grid the screenshot with `scripts/grid_overlay.py`. With a Figma/design image, run **both** `scripts/pair_view.py` (crops the screenshot's chrome so cell addresses actually align with the chrome-less design, then diffs pixels and flags every measurably-different cell → content/style) **and** `scripts/spacing_audit.py` (scales by width only and **measures** gaps, element heights, and margins in design px/dp → geometry). Never read spacing off `pair_view.py`: it resizes the design on both axes, so uniformly inflated padding diffs clean, and it suppresses its own flags whenever the aspect ratios differ — which is how a screen with every gap 30% too big passes a "design comparison". Scan the results cell by cell and turn the findings into a verdict + an annotated image. This is the one place the loop reads a screenshot into context — that *is* the test. Read `references/visual-review.md` before doing it.

If navigation fails, the TC is already a FAIL and there's nothing to review — fix the flow first.

Templates, directory layout, the execution command, failure handling, and key YAML patterns are all in `references/yaml-flows.md`.

## Phase 5: UI Validation (three tiers)

Maestro has no native "compare to Figma" or pixel-diff command, so UI validation is built from three complementary checks. The first two are designed to keep the **Agent out of the regression loop** — they run forever, unattended, in CI. The third is the pass that *creates* them and catches what they can't express.

| Tier | Checks | Runs with | Read |
|------|--------|-----------|------|
| **1 — Assertions** (always) | Static facts you can name: titles, button labels, elements present/absent | Maestro `assertVisible`/`assertNotVisible` baked into the YAML | `ui-validation.md` |
| **2 — Baseline diff** (optional) | Pixel *drift* from an approved capture, with chrome and dynamic regions masked | `scripts/compare_screenshots.py` — exit 0 pass / 1 drift | `ui-validation.md` |
| **3 — Visual review** (on demand) | How the screen *looks*: clipping, overlap, truncation, misalignment, wrong state — plus **measured** spacing/size/margin parity vs the design | No design: `scripts/grid_overlay.py`. With a design: `scripts/pair_view.py` (chrome-aligned, diff-flagged side-by-side) **+** `scripts/spacing_audit.py` (measures gaps/heights/margins in dp) — then the Agent scans the results | `visual-review.md` |

**Reach for Tier 3** when the tester asks for a visual/design QA pass, when there's no baseline yet (a first run has nothing to diff against), while authoring a UI TC (it's how you confirm the screen is actually right before encoding assertions), or when Tier 2 reports drift and someone needs to know *what* changed. Don't run it on functional TCs that already passed — a clean `assertVisible` doesn't need eyes on it, and each screenshot read costs real tokens.

**Tier 3 in one line:** capture → `grid_overlay.py` → scan cell by cell → classify each finding **Critical** (a user would notice and be blocked) or **Minor** (subjective polish) → any Critical = **❌ FAIL**, only Minor = **🔍 REVIEW**, clean = **✅ PASS** → re-run with `--highlight` to wash the defective cells red into `report/vision/`. That annotated image is the deliverable — a reviewer opens one file and sees exactly where the problems are.

Two judgment calls decide whether any of this is trustworthy, and both are in the references:

- **A design and a screenshot are never pixel-identical.** Mask system chrome (the three-band model), treat API/dynamic content as expected, and only turn *static/structural* elements into assertions. → `ui-validation.md`
- **Data state is not design state.** The app showing three items where the design shows six is the *user's data*, not a defect — failing on that is the most common way a visual comparison goes wrong and the fastest way to lose the developers' trust. → `visual-review.md`

Read the relevant reference before authoring or reviewing any UI TC. When you genuinely can't tell whether a difference is a real defect or expected variation, say so and ask — a confidently-wrong FAIL wastes developer time; a confidently-wrong PASS hides a bug.

A clean Tier 3 pass is the natural moment to **promote the screenshot to a Tier 2 baseline**: vision just confirmed it's correct, so it's a baseline worth diffing against. That's the graduation path — Tier 3 finds and confirms, Tiers 1 and 2 lock it in.

## Phase 6: Update the Report (resumable)

There is **one living report per feature** at `.maestro/<app-id>/<feature>/report/report.md` — not one per run. Every session updates it in place; it is never re-timestamped or overwritten. Read `references/reporting.md` for the full template and the resume/upsert rules. The essentials:

- **Upsert by TC id.** For each TC you ran this session, update its existing row (Status, Evidence, Session) in place. Rows for other priorities/sessions stay untouched. Then recompute the Summary from the whole table.
- **Full screenshot paths.** Every evidence reference is a resolvable path — clickable workspace-relative link in the table, plus the **absolute** path listed in Failed Test Details. The next phase (bug logging) opens these files from a different directory, so a bare filename or report-relative link won't do.
- **Failed Test Details = bug-logging handoff.** For each ❌ FAIL, write a detailed entry: priority, suggested severity, environment, **numbered Steps to Reproduce from a clean state**, Expected vs Actual, and absolute screenshot paths. These fields map 1:1 onto `notion-bug-logger`, so the next phase files the bug with no re-investigation. Append entries; never drop earlier sessions'.
- **Visual findings are evidence, not prose.** For a Tier 3 TC, the Evidence link is the annotated `report/vision/…-report.png` (not the raw screenshot), and each finding is recorded with its **severity + cell address** in UI Validation Details. "Title clipped in C3–D3" is actionable; "the title looks wrong" isn't. Also note what you excluded as data-driven, so the same difference isn't re-raised next session as new.
- **Session Log + announcement.** Append one Session Log row, then tell the user plainly: what ran, cumulative progress, which cases failed (with severity), **which cases need their call (🔍 REVIEW)**, and what the next session covers — so they never have to open the file to know the state.

Functional and UI-validation TCs share the single **Test Results** table (columns `Name | Priority | Step | Status | Evidence | Session`, type marked 🔧/🎨), which doubles as the cross-session progress board. Status vocabulary is ⬜ PENDING / ✅ PASS / ❌ FAIL / 🔍 REVIEW / ⏭️ SKIP / 🔄 RETRY — **🔍 REVIEW** exists so a soft visual observation isn't force-fit into PASS (hiding it) or FAIL (crying wolf); it counts as executed and waits for the human's decision.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Reading app source code (Kotlin/Swift) | Testers don't have access; flows must work without it | Existing YAML flows + MCP inspect + documents |
| Writing all YAML first, then running | Selector errors cascade — all flows fail | Write 1 TC → run → fix → next TC |
| Hardcoded waits (`sleep: 5000`) | Slow and flaky | `waitForAnimationToEnd` or `extendedWaitUntil` |
| Skipping the Phase 2 scan | Misses proven selectors, reinvents the wheel | Always scan existing flows first |
| Deeply nested flow chains | Hard to debug failures | Max 2 levels of `runFlow` |
| Testing multiple scenarios in one flow | Hard to pinpoint which step failed | One TC = one YAML file |
| Relying on element index | Fragile across releases | `id`, `testId`, or `text` |
| Guessing selectors without evidence | Flows fail on first run | Filtered inspection path, or ask the user |
| `--debug-output` instead of `--test-output-dir` | Confusing nested structure | Always `--test-output-dir` |
| Reading a raw hierarchy dump into context | ~250k tokens, ~95% noise | `scripts/filter_hierarchy.py` or a subagent |
| Re-inspecting the same screen each TC | Repeats the most expensive operation | Persist + read the selector catalog |
| Reading passing-TC screenshots into context | Each image costs thousands of tokens for no gain | Save as evidence (path only); read on failure, or for a Tier 3 review where the image *is* the test |
| `Read`-ing whole `commands-*.json` | Logs are large; you need one step | `grep` the failing step |
| Flagging UI diffs from status bar / OS nav / API content | False positives bury real issues | Mask chrome, treat dynamic content as expected (`ui-validation.md`) |
| Failing a visual TC because the app shows fewer items than the design | That's the user's data, not a design defect — the fastest way to lose developer trust | Match the data state, or compare state-agnostic properties only and say so (`visual-review.md`) |
| Putting the Agent in the regression loop for UI checks | Slow, token-heavy, can't run headless in CI | Tier 1 + Tier 2 for every run; Tier 3 on demand |
| Refusing a "kiểm tra giao diện" request because there's no Figma link | Layout defects don't need a design to be wrong | Tier 3 heuristic mode — the screenshot alone catches clipping, overlap, misalignment |
| Reading a raw screenshot for a visual review | One gestalt glance skips quiet corners; findings have no address | Grid it first, scan cell by cell, cite cells (`grid_overlay.py`) |
| Reading both the raw and the gridded version of the same shot | Doubles the image cost for zero extra information | Read only the gridded one — it carries everything |
| Gridding a design export and a device screenshot independently with the same `--cols/--rows` | The design has no status bar/OS nav but the screenshot does, so cell `C4` covers different content in each — the "comparison" is silently wrong | `pair_view.py` crops the screenshot's chrome bands first so cell addresses actually line up, then diffs and flags |
| Judging design-vs-actual as two separately-read images | Diffuse, low-precision task — real differences quietly get missed, and it degrades into two independent heuristic glances instead of an actual comparison | `pair_view.py`'s one composite image + measured per-cell diff flags — account for every flagged cell first |
| Concluding "spacing matches the design" from a clean `pair_view.py` diff | It never looked: aligning cells requires resizing the design on **both** axes, which normalizes uniformly-inflated padding away — and it suppresses its flags entirely when the aspect ratios differ. A 30%-too-loose screen passes silently | `spacing_audit.py` measures gaps/heights/margins in design px-dp (width-only scaling), and `systematic_gap_ratio` names a whole-screen deviation as one finding |
| Reporting a spacing deviation as "looks a bit tight/loose" for a human to judge | An adjective is unactionable and unfalsifiable; it's also how a real single-token layout bug gets filed as polish and shipped | Quote the measurement — "gap 24→32 design px (+33%)" — and file a measured, out-of-tolerance deviation as **Critical**, not 🔍 REVIEW |
| Washing cells red on a hunch ("feels tight here") | An image that highlights everything points at nothing | Highlight only cells with visible evidence; estimates stay text notes |
| Claiming a `dp`/`sp` value from a screenshot | Vision estimates, it doesn't measure — a fabricated number destroys the report's credibility | Say "looks about half the design's gap (estimate)" and mark it 🔍 REVIEW |
| Forcing a Minor visual finding into PASS or FAIL | PASS hides it; FAIL cries wolf and gets the whole report ignored | 🔍 REVIEW — evidence captured, human decides |
| Creating a new timestamped report each session | Splits results; no cumulative view; breaks resume | One living `report.md`; upsert rows in place |
| Overwriting/regenerating the report from memory on a resume | Wipes other sessions' P0–P4 results | Read existing report → upsert only this session's rows → recompute summary |
| Duplicating YAML per session (`TC-017_v2.yaml`) | Splits history; breaks id→row→file mapping | One YAML per TC id; edit in place, tag by priority |
| Bare filename / report-relative screenshot link | Bug-logging phase can't resolve it from its own dir | Record full absolute paths in Failed Test Details |
| Failure row with just "element not found" | Not enough to file a bug next phase | Failed Test Details with repro steps + expected/actual + screenshot paths |

## References

- `references/selectors-and-inspection.md` — finding selectors cheaply, live inspection, selector catalog, what not to read
- `references/yaml-flows.md` — directory structure, YAML templates, execution command, failure handling, patterns
- `references/ui-validation.md` — the three UI tiers, choosing between them, and dynamic-UI reasoning
- `references/visual-review.md` — Tier 3: chrome-aligned design pairing, cell-by-cell scan, severity → verdict, annotated result image, data-vs-design rule
- `references/reporting.md` — report location, template, and the Test Results table
- `references/maestro_commands.md` — full command-to-action mapping
- `scripts/filter_hierarchy.py` — collapse a raw hierarchy dump into a compact selector table (~1–5k tokens instead of ~250k)
- `scripts/compare_screenshots.py` — deterministic baseline-vs-actual visual diff with masking (Tier 2 UI regression, no Agent)
- `scripts/grid_overlay.py` — stamp a labeled grid on a screenshot for cell-by-cell review; `--highlight` washes defect cells red for the report image (Tier 3, heuristic mode and final report image)
- `scripts/pair_view.py` — Tier 3 design mode, content/style: crops chrome so cell addresses align, diffs the design against the screenshot, and composes one side-by-side image with measurably-different cells flagged
- `scripts/spacing_audit.py` — Tier 3 design mode, geometry: scales by width only, segments both images into element bands, and measures every gap, element height, and side margin in design px/dp, with a `systematic_gap_ratio` that names a whole-screen spacing deviation as one finding
- [Maestro Docs](https://docs.maestro.dev/) · [Maestro MCP](https://docs.maestro.dev/get-started/maestro-mcp) · [Figma MCP](https://www.figma.com/developers/mcp)
```