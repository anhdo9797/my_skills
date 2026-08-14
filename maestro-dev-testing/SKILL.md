---
name: maestro-dev-testing
description: >-
  Plan, author, run, and report mobile UI tests for an Android app using the
  Maestro CLI, working in the project's .maestro/ directory. Use this skill
  whenever the user wants to write end-to-end / UI / integration tests, create
  automated test flows, build a smoke or regression suite, verify a screen or
  user journey works, test clear-cache vs warm-cache (with-cache) behavior, or
  "run the app tests and tell me what passes" — even when they don't say
  "Maestro" by name. Triggers on requests like "write a test for the recipe
  screen", "add UI tests for the favorites flow", "create a smoke test", "test
  the debug build on dev", "automate testing this feature", or "run the smoke
  suite and report pass/fail". Also use it for visual/design QA and vision-based
  UI testing — requests that mention Figma, responsive layout, font size,
  spacing, screenshot comparison, design review, "kiểm tra giao diện từng màn
  hình", "test UI bằng ảnh chụp", "phát hiện lỗi hiển thị / tràn chữ / overlap /
  lệch layout", or "chia lưới màn hình để soi": it captures a screenshot per
  screen, overlays a labeled grid, and uses vision to scan each screen cell-by-
  cell, auto-failing on serious defects. This is the dev-side skill: it reads the app's source for
  real selectors and writes a test plan first. It detects the app's build
  variant and applicationId from the project (never hardcoded), produces a
  TESTCASES.md plan, then authors and runs Maestro flows one case at a time —
  updating the run report after each case — and reports PASS, FAIL, SKIP,
  ERROR, NEEDS_REVIEW, or PENDING for every case.
---

# Maestro UI Testing

Turn a feature or requirement into automated UI tests you can actually run and trust.
The loop is **Plan → (per case: Author → Run → Record) → Summarize**, working in the
project's `.maestro/` directory. A good plan prevents shallow tests; matching the repo's
conventions keeps the suite maintainable; running each case as you write it catches selector
errors early instead of debugging ten broken flows at once; and parsing real run output is the
only honest way to say a test passed.

This is the **dev-side** skill — it reads the app's source to find real selectors and writes a
plan before any YAML. (A sibling skill, `maestro-test-executor`, covers the tester who can't
read code.)

**Match the user's language in human-facing prose** — chat replies, and the prose inside
`TESTCASES.md` / `RUN_REPORT.md` / `report.md`. If they wrote in Vietnamese, answer and document
in Vietnamese. Everything that is code or a stable identifier stays in English: flow filenames,
`appId`, tags, selectors, `testTag`s, YAML keys, Maestro commands — translating those breaks the
suite. So a `TESTCASES.md` can carry Vietnamese descriptions next to English ids and selectors.

## Token discipline (read first — keeps runs cheap)

Large artifacts must never flood context; they are the main cost of a run:

- **Never read a raw `inspect_screen` / hierarchy dump into context** (~250k tokens, ~95% noise).
  Route it through `scripts/filter_hierarchy.py` (compact selector table, ~1–5k tokens) or let a
  subagent inspect and return only the selector. See `references/flow-investigation.md`.
- **`grep` run logs for the failing step** — don't `Read` whole `commands-*.json` files.
- **Read failure screenshots only when the error text isn't enough.** Never read passing-case
  screenshots; save them as evidence (path only). The exception is a **vision/UI case**, where
  reading the screenshot *is* the test — but read only the **gridded** version, one image per
  screen state (see `references/vision-ui-testing.md`), never raw + gridded of the same shot.
- Read each `references/*.md` **only when you reach the phase that needs it**, not upfront.

## Phase 0 — Detect the environment (always first)

Learn how *this* repo tests so your output drops in cleanly instead of forking a parallel
convention.

1. **Maestro installed?** `maestro -v`. If missing, tell the user to install
   (`curl -fsSL https://get.maestro.mobile.dev | bash`); you can still author flows.
2. **Read the existing `.maestro/` setup** (the working dir): `config.yaml` (flow globs,
   `testOutputDir`, `continueOnFailure`), the folder layout (`flows/smoke/`,
   `flows/features/<feature>/`, shared subflows in `flows/common/`), the shared launch subflows
   (clear-state vs keep-state), and the tag vocabulary. Flows reference the app as `appId: ${APP_ID}`
   (env-injected) — never hardcode an id in a flow. Follow what you find; don't "improve" it. If
   `.maestro/` doesn't exist, scaffold it per `references/test-planning.md`.
3. **Resolve the build variant and APP_ID from the project** — do not assume any literal id.
   Read `references/build-variants.md` for the derivation method. In short: read
   `app/build.gradle.kts` to compute `applicationId` from `defaultConfig` + the flavor/build-type
   suffixes, and cross-check what's installed with `adb shell pm list packages`. Default to the
   debug build of the default/dev flavor unless the user names a variant. Map the chosen variant
   to both its `applicationId` (the `${APP_ID}` value) and its `./gradlew :app:install…` task.
4. **Device/emulator running?** `adb devices`. Maestro needs one. If none is up, author now and
   mark the run `PENDING` — say so rather than pretend.

## Phase 1 — Plan the tests (MANDATORY: user review before any YAML)

Never jump straight to YAML. The plan forces you to think about preconditions, negative cases, and
— for apps that persist state — **cache mode** (clear / warm); user review before authoring prevents
wasted YAML work on the wrong scenarios.

The input may be a **one-line requirement** ("test favorites"), a **visual/design QA request**
("compare this screen to Figma"), or a **document / PRD / acceptance criteria**. When a document is
provided, derive scenarios from *its* stated behaviors and **quote the criterion each scenario
verifies** so coverage is auditable. When you don't know how a user reaches the screen under test,
run Phase 1.5 before finalizing steps — a plan built on a guessed path is worth little.

### Phase 1a — Read docs + source to derive precise testcases (token-efficient)

Before writing anything, do these reads **in order** — each layer sharpens the testcases:

1. **Read `.agent-kb/Readme.md`** to find which BRD, Development, and Tracking docs cover this
   feature. Pick only the relevant ones (usually BRD + Development for the feature under test).
2. **Read the BRD doc** — extract the exact acceptance criteria, business rules, edge cases, and
   error states the feature must satisfy. These become the source of truth for what each testcase
   must verify. Quote the criterion in the testcase so coverage is auditable.
3. **Read the Development doc** — extract the real navigation path to reach the screen, actual
   state machine (what triggers each UI state), and any data dependencies (seed recipes, auth
   requirements). This prevents guessed navigation paths.
4. **Grep `.maestro/flows/`** for existing flows and `TESTCASES.md` — reuse proven selectors,
   anchor data, and `runFlow` entry points. Note which cases already exist so you don't duplicate.
5. **Scan `features/<feature>/presentation/`** for `Modifier.testTag(...)`, `contentDescription`,
   and `Text(...)` — collect real selectors in one pass into a compact table
   (`selector → element → screen`). These are the only selectors you may use in YAML.

From these reads, derive the candidate testcase list. Each candidate must already have a concrete
expected result tied to a real UI element — not "it works" but "assertVisible id:recipe_title".

### Phase 1b — Present testcase strings for user review (STOP HERE)

**Before writing `TESTCASES.md` or any YAML, present the candidate list in chat as a simple
numbered/bulleted list** — just the id, a one-line description, priority, and cache mode. Nothing
else. This is cheap to review and fast to edit.

Example format (adapt language to user's):
```
Testcases đề xuất cho <feature>:

1. LIKE-01 [P0 / clear] — Like a recipe → recipe appears in Favorites tab
2. LIKE-02 [P1 / warm] — Unlike a recipe → recipe removed from Favorites
3. LIKE-03 [P1 / clear→warm] — Favorites persist after app relaunch
4. LIKE-04 [P1 / clear] — Empty Favorites state shown when no likes
⚠️ LIKE-05 [P2 / clear] — Like limit banner (feature not yet shipped)

Bạn có muốn thêm, bỏ, hoặc chỉnh sửa case nào không?
```

**Wait for explicit approval** (or edits) before proceeding. If the user says "ok" / "looks good" /
"add X", incorporate the feedback and confirm the final list. Only move to Phase 1c when the list
is agreed. If the user says "skip the plan", honor that — but this review is the default.

**As soon as the list is approved → go straight to Phase 1c then Phase 2 without pausing.**
Do not ask for another confirmation; the approval of the list is the green light to create scripts.

### Phase 1c — Write `TESTCASES.md` then immediately start Phase 2

Write the plan file **as a single uninterrupted step before Phase 2 begins** — do not present it
for another round of review; it is just the permanent record of what was already approved.

1. **`TESTCASES.md` location:** per-feature → `.maestro/flows/features/<feature>/TESTCASES.md`;
   smoke suite → `.maestro/flows/smoke/TESTCASES.md`. Keep a top-level `.maestro/TESTCASES.md`
   index linking each feature plan, listing the build variant/APP_ID and the run command.
2. **Each scenario row needs:** the stable id from Phase 1b, the eventual flow filename, priority,
   cache mode, tags, preconditions, ordered steps, and a concrete expected result. Mark ⚠️ on
   scenarios expected to FAIL against current code, with reason.
3. Once the file is written, **immediately begin Phase 2** — start the build-run-report loop for
   TC-01 without waiting for further input.

For visual/design QA (Figma, responsive, font/spacing, "kiểm tra giao diện từng màn hình"), read
`references/vision-ui-testing.md` (grid + vision method) and `references/visual-design-qa.md` (Figma
baseline, device matrix) before planning. Key limit: Maestro drives the app, asserts visible
hierarchy, sets orientation, and captures screenshots — the **vision pass** then judges layout from
those screenshots (overlap, truncation, alignment, clipping), auto-failing on serious defects. Vision
*estimates*; it still can't read exact `fontSize`/`dp` values, so treat exact typography/spacing as
review checks (`NEEDS_REVIEW`) or push them to source/screenshot-diff tests.

## Phase 1.5 — Investigate the flow when steps aren't obvious

Most requirements name a *destination* but not the *path* or the *selectors*. You can't write a
trustworthy flow from a guessed path — a tap on the wrong element fails for the wrong reason. So
recover each step deliberately. Read `references/flow-investigation.md` for the full method; the
order, cheapest first:

1. **Reuse what the suite already knows.** Grep `.maestro/` — `flows/common/` holds shared entry
   points; other features' flows and `TESTCASES.md` show proven selectors and anchor data. Reuse
   via `runFlow`.
2. **Read the app's Compose source** under `features/<feature>/presentation/` for
   `Modifier.testTag(...)` → `contentDescription` → `stringResource`/`Text(...)`, in that priority
   order. If a named screen/control isn't in the source at all, that's a finding (not yet built) —
   surface it, don't paper over it with a guess.
3. **Inspect a live screen** via the Maestro MCP (`inspect_screen`, `run`, `take_screenshot`) or
   `maestro studio` — but route any hierarchy through `filter_hierarchy.py` / a subagent (token rule).
4. **Ask the user a specific question** when reuse, source, and inspection still leave a gap — cite
   what you found and ask only for the missing piece.

**Definition of done:** for every step you can name the selector *and* its source (reused subflow /
`testTag` in file X / `inspect_screen` / confirmed by user). Anything unsourced becomes a
`# TODO: verify selector` comment or a question — never a confident guess. When you recover a
multi-step path, extract it to `flows/common/<navigate>.yaml` and `runFlow` it.

## Phase 2 — Build YAML → Run → Screenshot → Update (repeat for every case)

Author only after the plan is approved and selectors are sourced from the Phase 1a read pass.

**The loop is strict, self-driving, and runs until all TCs are done:**

```
[approval received from Phase 1b]
    ↓
write TESTCASES.md  (Phase 1c — no extra confirmation needed)
    ↓
for each TC in TESTCASES.md (TC-01 first, then TC-02, … until the last):
    2-A  Write <TC-ID>.yaml
    2-B  Run that single flow → read PASS/FAIL
    2-C  Functional TC: check screenshot ONLY on FAIL/ambiguous.
         Visual/UI TC (VIS-*): grid the screenshot + run the vision scan
         → severity → verdict (see references/vision-ui-testing.md)
    2-D  Write result row in report.md + detail in RUN_REPORT.md
    2-E  Announce result inline ("✓ TC-01 PASS" / "✗ TC-02 FAIL — <reason>")
    → automatically continue to next TC without asking permission
until every TC in the plan has a status (PASS/FAIL/ERROR/PENDING)
    ↓
Phase 3  Finalize totals, surface failures, done.
```

**Never break the loop mid-way to ask "should I continue?"** — keep going until all TCs have a
result. Only pause if the user explicitly interrupts, or if a blocking environment issue (e.g.
device disconnected, build failed) prevents every remaining case from running — in that case mark
the remaining TCs `PENDING` with the reason and report the partial result.

Each iteration is atomic: one new YAML file, one run, one report row — then the next.

Read `references/maestro-commands.md` for command syntax only when you reach a command you need — not upfront.

**Install the variant once before the first run:**

```bash
./gradlew :app:install<Variant>           # e.g. :app:installDevDebug — from Phase 0
```

Then for **each approved scenario**, follow this tight loop:

### 2-A: Build YAML

Start from `assets/flow-template.yaml`. Use the selectors already collected in Phase 1a — no
re-reading source files. One flow = one scenario; name it after the scenario id; carry the plan's
tags. Reuse setup via `runFlow:` instead of copy-pasting launch steps.

Selector priority: **`id` > `text` > `index`/`point`** — `testTag`/`semantics` ids survive locale
changes; coordinates are last resort and brittle. End on an `assertVisible` (or equivalent) that
proves the expected result — a flow that only taps passes vacuously.

**Cache mode** is a first-class dimension:
- **Clear-cache (cold):** reuse `flows/common/launch_clear_state.yaml` (`clearState: true`) via
  `runFlow`. Use for onboarding, first-run, anything that must not depend on prior state.
- **With-cache (warm):** use `launch_keep_state.yaml` (`assets/launch_keep_state.yaml`; create it
  in `flows/common/` if absent). A warm test usually needs a clear-cache flow to run first to
  establish the state.

Add a `takeScreenshot` after the key assertion — name it `<TC-ID>-<step>.png`. This screenshot is
the primary evidence for both PASS and FAIL; it costs nothing extra to collect.

### 2-B: Run the single flow

```bash
maestro test -e APP_ID=<applicationId> .maestro/flows/features/<feature>/<scenario>.yaml
```

Read only the final PASS/FAIL line and the failing assertion text (if any) from the output — don't
read whole log files. `grep` for errors if the summary is ambiguous.

### 2-C: Check screenshot (functional) / vision scan (visual)

**Functional cases:** open/read the screenshot **only if the test failed or the result is
ambiguous**. For a clean PASS with an expected `assertVisible`, trust the CLI output and move on —
never read passing screenshots, as they add token cost with no information gain.

**Visual/UI cases (`VIS-*`, design-QA requests):** the look of the screen *is* the assertion, so run
a vision pass — read `references/vision-ui-testing.md` for the full method. In short:

1. Capture into `.maestro/artifacts/<feature>/actual/`, then grid it:
   `python3 scripts/grid_overlay.py actual/<shot>.png --cols 6 --rows 13` → `grid/<shot>-grid.png`
   (needs Pillow once: `pip3 install Pillow`).
2. **Design mode:** the baseline is either a user-exported image or a Figma render (saved under
   `baseline/`). Grid it with the **same** `--cols/--rows` so cells line up, then compare
   actual-grid ↔ baseline-grid **cell-by-cell**. **Heuristic mode (no baseline):** scan the gridded
   screenshot against the checklist on its own.
3. Classify each finding **Critical** (breaks usability / unambiguously wrong / clear design
   deviation) or **Minor** (subjective polish), naming the exact cell(s).
4. Map to a verdict: any Critical → **FAIL**; only Minor → **NEEDS_REVIEW**; clean → **PASS**.
5. **Produce the report image:** if there are defects, re-run with `--highlight "<cells>"` to wash
   the defective cells red (~10% opacity) → `report/<shot>-report.png`. Only highlight cells with
   clear visible evidence — never mark a cell on a vague estimate.

This is the hybrid-by-severity policy: serious visual defects fail the case automatically; soft ones
defer to a human. The deliverable is the annotated `report/` image plus per-cell findings recorded
in Phase 2-D.

### 2-D: Update report immediately

Append/update this scenario's row in `report.md` and its detail in `RUN_REPORT.md` (see Phase 3)
before moving to the next case. On failure, classify it:
- `FAIL` — app reached the assertion and behaved wrong.
- `ERROR` — environment/setup failure (app not installed, invalid YAML, Maestro crash).
- `NEEDS_REVIEW` — visual evidence captured; parity needs Figma/human comparison.

On `ERROR`, fix the YAML or environment issue and re-run immediately; don't leave it broken and
move on. On `FAIL`, record the assertion text + screenshot path and move to the next case.

Once the whole approved set has run, do a short final pass over Phase 3's reporting rules to make
sure every planned scenario appears exactly once and totals are correct.

## Phase 3 — The report (written incrementally, finalized at the end)

A test you haven't run is a guess. **Confirm the run command with the user and surface it** before
running — they may want to run it themselves or on a specific device. Always give the copy-paste
command and expected output. If no device is up, hand over the command and mark cases `PENDING`.

Two files, next to the feature plan (`.maestro/flows/features/<feature>/` or `.maestro/flows/smoke/`),
**updated after each case** in Phase 2 rather than written all at once:

- **`report.md`** — table-first; reviewers scan it or paste it into task tracking. Every planned
  scenario from `TESTCASES.md` appears exactly once, including cases that didn't run.
- **`RUN_REPORT.md`** — narrative detail: failing assertions, screenshot paths, troubleshooting, the
  exact command used, the device matrix for visual QA.

`report.md` table columns:

| Testcase ID | Flow file | Priority | Cache mode | Device / viewport | Tags | Status | Result / evidence | Notes / next action |
|-------------|-----------|----------|------------|-------------------|------|--------|-------------------|---------------------|
| LIKE-01 | `like_recipe.yaml` | P0 | clear | Pixel_7 portrait | smoke, like | PASS | Expected recipe appears in Favorites | - |
| LIKE-02 | `unlike_recipe.yaml` | P1 | warm | Pixel_7 portrait | like | FAIL | `assertVisible` timed out; screenshot: `…/failure.png` | Check selector or app behavior |
| VIS-01 | `recipe_detail_visual.yaml` | P1 | clear | tablet landscape | visual | NEEDS_REVIEW | Screenshot: `…/VIS-01-tablet.png`; Figma node `123:456` | Compare spacing to Figma |
| LIKE-03 | `favorite_persists.yaml` | P1 | clear→warm | Pixel_7 portrait | like | PENDING | Not run: `adb devices` empty | Start emulator, install variant, rerun |

Allowed statuses: `PASS`, `FAIL`, `SKIP`, `PENDING`, `ERROR`, `NEEDS_REVIEW`. Use `ERROR` for
test/environment setup failures (app not installed, invalid YAML, Maestro crash); `FAIL` when the app
reached the assertion and behaved wrong; `NEEDS_REVIEW` for visual checks where evidence was captured
but parity needs Figma/human comparison; `PENDING` for cases that never executed.

**Reporting rules — be faithful (in the file and in chat):**
- Report what actually happened: "3 passed, 2 failed" with failing case names, the assertion error,
  and any screenshot path. Summarize total/passed/failed/skipped.
- **Never report a test as passing if it didn't run.** Say it was skipped/errored and why.
- Distinguish a real app bug from a flaky/wrong test or an environment problem ("Unable to launch
  app" = variant not installed → install it), and propose the fix.

## Quick reference

| Need | Go to |
|------|-------|
| Derive APP_ID + build variant / install task for any project | `references/build-variants.md` |
| Test plan structure, scenario & cache-state types | `references/test-planning.md` |
| Vision UI testing: grid overlay, cell-by-cell scan, severity→verdict | `references/vision-ui-testing.md` |
| Visual/design QA from Figma; responsive/font/spacing limits | `references/visual-design-qa.md` |
| Recover an unknown path / selectors (reuse → source → inspect → ask) | `references/flow-investigation.md` |
| Maestro command syntax, selectors, cache patterns | `references/maestro-commands.md` |
| Collapse a hierarchy dump into a compact selector table (token saver) | `scripts/filter_hierarchy.py` |
| Overlay a labeled grid / wash defect cells red for the report image | `scripts/grid_overlay.py` |
| Flow starting point | `assets/flow-template.yaml` |
| Warm-cache shared launch subflow | `assets/launch_keep_state.yaml` |

## Workflow summary (token-efficient)

```
Phase 0   Detect env (maestro -v, read .maestro/, resolve APP_ID, check adb)
Phase 1a  Read existing features + flows → collect selectors in one pass
Phase 1b  Present testcase string list → WAIT for user review/approval  ← only pause
Phase 1c  Write TESTCASES.md → immediately start Phase 2 (no extra confirmation)
Phase 1.5 Investigate unknown steps (only if gaps remain after 1a)

Phase 2 loop — self-driving until ALL TCs have a status:
  for each TC:
    Write <TC-ID>.yaml
    Run single flow
    Functional: check screenshot (FAIL/ambiguous only)
    Visual (VIS-*): grid actual (+baseline, same dims) → cell-by-cell scan →
      severity→verdict → --highlight defect cells into report/ image
    Update report.md + RUN_REPORT.md (evidence = report image)
    Announce result inline
    → next TC automatically

Phase 3   Finalize totals, surface failures, done.
```
