---
name: maestro-test-executor
description: Execute QA test plans by generating Maestro YAML flows one test case at a time, running each immediately, optionally comparing UI screenshots against Figma designs, and producing a consolidated test report. Designed for non-technical testers — no source code reading required. Use this skill whenever the user wants to automate test cases with Maestro, convert a manual test plan into Maestro flows, run E2E tests on mobile apps, or validate app UI against Figma design screenshots. Also trigger when the user mentions Maestro flows, YAML test generation, mobile UI testing, simulator screenshots, or wants to validate app behavior against a test plan — even if they don't explicitly say "maestro-test-executor".
---

# Maestro Test Executor

Converts a QA test plan into executable Maestro YAML flows, runs each case immediately after writing it, optionally validates UI against Figma designs, and produces a consolidated test report.

**Designed for non-technical testers.** There is no source code reading at any step. Selectors come from existing YAML flows, Maestro MCP live inspection, and what's visible on screen.

> **Scope rule:** This skill works exclusively within the `.maestro/<app-id>/` directory of the current workspace. All flow discovery, selector learning, and YAML generation happen inside this single boundary.

> **Token rule (read this first):** Large artifacts — raw view-hierarchy dumps (~250k tokens/screen), screenshots, and command logs — must never flood the main context. Route hierarchies through `scripts/filter_hierarchy.py` or a subagent, read failure screenshots only when needed, and `grep` logs instead of reading them whole. Details in `references/selectors-and-inspection.md`.

> **Resume rule:** A large plan is run across **multiple sessions** (e.g. session 1 = all P0 cases, session 2 = P1, …). There is exactly **one living report** and **one YAML file per TC id** per feature — every session **updates them in place**, never replaces or re-timestamps them. On starting a session, read the existing `report.md` first to see what's already done and continue from there. The full resume/upsert model is in `references/reporting.md` — read it before Phase 4 whenever a report already exists.

## Prerequisites

- **Maestro CLI** installed and on PATH (`maestro --version`)
- A running **emulator/simulator** or connected device
- **Test plan** — a list of test cases from the user (or output from `qa-test-planner`)
- **Supporting documents** (optional) — PRD, feature spec, or Figma URL to clarify expected behavior and UI
- **Pillow** (optional) — only for Tier 2 visual baseline diff (`pip install Pillow`); Tier 1 assertion-based UI checks don't need it

## Reference map

This SKILL.md is the orchestrator. Each phase points to a focused reference — read the reference when you reach that phase, not before.

| Topic | Reference | Read when |
|-------|-----------|-----------|
| Finding selectors cheaply, live inspection, selector catalog | `references/selectors-and-inspection.md` | You need a selector you don't already have |
| YAML structure, templates, execution command, failure handling | `references/yaml-flows.md` | Writing or fixing flows (Phase 4) |
| Authoring durable UI checks (Tier 1 assertions + Tier 2 baseline diff), dynamic-UI reasoning | `references/ui-validation.md` | Validating UI appearance (Phase 5) |
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
│ Phase 5: UI VALIDATION (if UI TCs exist)             │
│   Authoring (Agent, once): Figma → Tier 1 assertions │
│     in YAML + optional Tier 2 approved baseline       │
│   Regression (no Agent): Maestro asserts + diff script│
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
**Optional:** device name (auto-detect by default), **Figma file URL** (needed for UI validation), app-state setup (`clearState: true` by default).
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
- 🎨 **UI validation** — a screen's *appearance* matches the Figma design. Requires a Figma URL. The Agent reads the design **once at authoring time** and turns it into durable checks that run forever without an Agent: **Tier 1** Maestro assertions (static labels, button text, elements present/absent) baked into the YAML, and optional **Tier 2** baseline screenshot diff via `scripts/compare_screenshots.py`. See `references/ui-validation.md`.

**Automatability:** ✅ automatable · ⚠️ partially automatable (external setup / subjective) · ❌ skip (performance, manual-only, hardware sensor).

A UI-validation TC reads like any other plan entry — e.g. *"TC-010: Edit Recipe screen matches Figma design"* — and earns a row in the same Test Results table as functional TCs.

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

A 🎨 UI-validation TC runs through the **same loop**. Its YAML navigates to the screen, then asserts the **Tier 1** static facts extracted from the design (`assertVisible`/`assertNotVisible`/property checks) and takes a screenshot. Those assertions are pure Maestro — they pass/fail deterministically here with no Agent. If a Tier 2 baseline diff was set up, run `scripts/compare_screenshots.py` against the approved baseline after capture. If navigation fails, the TC is already a FAIL.

Templates, directory layout, the execution command, failure handling, and key YAML patterns are all in `references/yaml-flows.md`.

## Phase 5: UI Validation (authoring vs. regression)

Maestro has no native "compare to Figma" or pixel-diff command, so UI validation is designed to keep the **Agent out of the regression loop**. The Agent's vision is an *authoring* tool used once per TC; every later run is pure Maestro + a deterministic diff script.

**At authoring time (Agent reads the Figma design once):** fetch the design via Figma MCP (`get_screenshot`), then produce durable checks:
- **Tier 1 — assertions (always):** extract every *static* fact from the design (titles, button labels, elements present/absent) and bake them into the TC YAML as `assertVisible`/`assertNotVisible`. These run forever with no Agent.
- **Tier 2 — baseline diff (optional):** approve a baseline screenshot and record which regions to mask (status bar, OS nav, and dynamic API/data regions). Regression then runs `scripts/compare_screenshots.py` against that baseline.

**At regression time (no Agent):** Maestro evaluates the Tier 1 assertions; `compare_screenshots.py` evaluates Tier 2 (exit 0 = within threshold, 1 = drift). The TC passes only if both pass.

The reasoning that makes this accurate — a design and a screenshot are **never pixel-identical**, so mask system chrome, treat API/dynamic content as expected (mask it / don't assert it), and only turn **static/structural** elements into assertions — plus the three-band model, the static-vs-dynamic table, and the baseline/masks workflow are all in `references/ui-validation.md`. Read it before authoring any UI TC.

## Phase 6: Update the Report (resumable)

There is **one living report per feature** at `.maestro/<app-id>/<feature>/report/report.md` — not one per run. Every session updates it in place; it is never re-timestamped or overwritten. Read `references/reporting.md` for the full template and the resume/upsert rules. The essentials:

- **Upsert by TC id.** For each TC you ran this session, update its existing row (Status, Evidence, Session) in place. Rows for other priorities/sessions stay untouched. Then recompute the Summary from the whole table.
- **Full screenshot paths.** Every evidence reference is a resolvable path — clickable workspace-relative link in the table, plus the **absolute** path listed in Failed Test Details. The next phase (bug logging) opens these files from a different directory, so a bare filename or report-relative link won't do.
- **Failed Test Details = bug-logging handoff.** For each ❌ FAIL, write a detailed entry: priority, suggested severity, environment, **numbered Steps to Reproduce from a clean state**, Expected vs Actual, and absolute screenshot paths. These fields map 1:1 onto `notion-bug-logger`, so the next phase files the bug with no re-investigation. Append entries; never drop earlier sessions'.
- **Session Log + announcement.** Append one Session Log row, then tell the user plainly: what ran, cumulative progress, which cases failed (with severity), and what the next session covers — so they never have to open the file to know the state.

Functional and UI-validation TCs share the single **Test Results** table (columns `Name | Priority | Step | Status | Evidence | Session`, type marked 🔧/🎨), which doubles as the cross-session progress board.

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
| Reading passing-TC screenshots into context | Each image costs thousands of tokens for no gain | Save as evidence (path only); read on failure/validation only |
| `Read`-ing whole `commands-*.json` | Logs are large; you need one step | `grep` the failing step |
| Flagging UI diffs from status bar / OS nav / API content | False positives bury real issues | Mask chrome, treat dynamic content as expected (`ui-validation.md`) |
| Putting the Agent in the regression loop for UI checks | Slow, token-heavy, can't run headless in CI | Author Tier 1 assertions + Tier 2 baseline once; regression runs Maestro + diff script with no Agent |
| Creating a new timestamped report each session | Splits results; no cumulative view; breaks resume | One living `report.md`; upsert rows in place |
| Overwriting/regenerating the report from memory on a resume | Wipes other sessions' P0–P4 results | Read existing report → upsert only this session's rows → recompute summary |
| Duplicating YAML per session (`TC-017_v2.yaml`) | Splits history; breaks id→row→file mapping | One YAML per TC id; edit in place, tag by priority |
| Bare filename / report-relative screenshot link | Bug-logging phase can't resolve it from its own dir | Record full absolute paths in Failed Test Details |
| Failure row with just "element not found" | Not enough to file a bug next phase | Failed Test Details with repro steps + expected/actual + screenshot paths |

## References

- `references/selectors-and-inspection.md` — finding selectors cheaply, live inspection, selector catalog, what not to read
- `references/yaml-flows.md` — directory structure, YAML templates, execution command, failure handling, patterns
- `references/ui-validation.md` — authoring durable UI checks (Tier 1 assertions + Tier 2 baseline diff) and dynamic-UI reasoning
- `references/reporting.md` — report location, template, and the Test Results table
- `references/maestro_commands.md` — full command-to-action mapping
- `scripts/filter_hierarchy.py` — collapse a raw hierarchy dump into a compact selector table (~1–5k tokens instead of ~250k)
- `scripts/compare_screenshots.py` — deterministic baseline-vs-actual visual diff with masking (Tier 2 UI regression, no Agent)
- [Maestro Docs](https://docs.maestro.dev/) · [Maestro MCP](https://docs.maestro.dev/get-started/maestro-mcp) · [Figma MCP](https://www.figma.com/developers/mcp)
```