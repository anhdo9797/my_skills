# Reporting

How to consolidate results into the final report (Phase 6). Read this after processing the test cases in the **current session** — functional and UI-validation alike.

This report is not a throwaway summary. It is the **single source of truth** that (a) survives across multiple runs/sessions so you can resume, and (b) carries enough detail for the **next phase — bug logging** (`notion-bug-logger`) to file a real bug without re-investigating. Two design rules follow from that: never replace the report or the YAML on a re-run (always update in place), and always record **full, resolvable screenshot paths** — a relative link that only works from the report's own folder is useless the moment the bug-logging phase tries to attach the image.

## One canonical report per feature (not one per run)

```
.maestro/<app-id>/<feature>/report/report.md      ← THE living report, updated in place
.maestro/<app-id>/<feature>/report/<timestamp>/    ← raw maestro --test-output-dir logs (one per run, accumulate)
```

There is exactly **one** `report.md` per feature/module. Every session — the P0 session, the P1 session, and so on — opens this same file and **updates** it. It is never renamed with a timestamp and never overwritten from scratch. The timestamped `<timestamp>/` directories (raw Maestro logs + auto failure screenshots) still accumulate one per run; only the human-facing `report.md` is singular and living.

> **Migrating an old report:** if a feature still has `report_<date>_<time>.md` files from an older run, treat the most recent one as the seed, copy it to `report.md`, and continue from there. Don't start a fresh file.

## Resume model — how sessions share one report

A plan is often too large for one sitting (e.g. 60 cases across P0→P4). The tester runs it in slices — **session 1 = P0, session 2 = P1, …** — and expects each session to pick up where the last stopped, not to clobber it. The report's own **Test Results table is the progress board** that makes this work. No separate state file: the table *is* the state.

**Status vocabulary** (the resume anchor):

| Status | Meaning |
|--------|---------|
| ⬜ PENDING | Planned, not run yet (seeded but untouched) |
| ✅ PASS | Ran and passed |
| ❌ FAIL | Ran and failed (has a Failed Test Details entry) |
| 🔍 REVIEW | Ran; evidence captured, but the verdict needs a human — only **Minor** Tier 3 visual findings, or exact typography/spacing parity vision can't measure. Not a pass, not a failure. |
| ⏭️ SKIP | Not automatable (manual/hardware/performance) |
| 🔄 RETRY | Previously failed, re-run this session — update the same row |

> 🔍 REVIEW exists so a soft visual observation doesn't get force-fit into PASS (hiding it) or FAIL (crying wolf). It counts as *executed* in the Summary, and it belongs in Recommendations so the tester actually acts on it. Once the human decides, the row flips to ✅ or ❌ in a later session.

**Session 0 — seed the board (once, right after Phase 3 classification):**
Write every planned TC — the *whole* plan, all priorities — into the Test Results table as `⬜ PENDING`, with its priority filled in. This turns `report.md` into a master board that shows the full scope up front, so anyone can see at a glance that P2–P4 are still outstanding. Seeding is cheap (no runs happen yet) and it's what lets later sessions know what's left.

**Every session start — read before you write:**
1. Read `report.md` if it exists. The table tells you what's already ✅/❌ and what's still ⬜.
2. Confirm the session scope (which priority or which TC ids this session covers — ask in Phase 1 if unstated).
3. Work only the in-scope TCs that are still ⬜ PENDING (or 🔄 RETRY targets). Skip anything already ✅ unless the user explicitly asks to re-run it.

**Every session end — update in place (upsert), never rewrite:**
- **Upsert by TC id.** For each TC you ran, find its existing row and update Status / Evidence / Session in place. Rows for other priorities stay exactly as they were.
- **Append**, don't replace, in Failed Test Details and the Session Log.
- **Recompute the Summary** from the current table (it reflects cumulative progress across all sessions, plus a "this session" line).

> **Golden rule:** a session touches only its own rows. If the P1 session ever deletes, reorders, or blanks the P0 results, the resume contract is broken. Read → upsert → recompute. Never regenerate the file from memory.

## YAML reuse across sessions

Test case YAML is also reused, not replaced (details in `yaml-flows.md`). The filename is keyed to the **TC id** (`testcase/TC-017_add_ingredient.yaml`), so:
- If the file already exists, run it as-is (or edit it in place if the step logic genuinely changed). Never create `TC-017_add_ingredient_v2.yaml` or a re-slugged duplicate — that splits history and breaks the id→row→file mapping the report relies on.
- Tag each TC with its priority (`tags: [<feature>, P1]`) so a session can select its slice with `maestro test --include-tags P1`.

## Full screenshot paths — the rule

Every screenshot reference in the report — passing evidence, the auto-captured failure image, Figma-vs-actual pairs — must be recorded as a **full, resolvable path**, not a bare filename or a report-relative link. The bug-logging phase runs later, from a different working directory, and needs to open the actual image file to attach it.

Record **both** forms so the report is clickable *and* the path is copy-pasteable downstream:

- **Absolute path** (primary — what bug logging consumes). Compute the workspace root once at the start of Phase 6 and prefix it:
  ```bash
  REPORT_ABS="$(pwd)/.maestro/<app-id>/<feature>/report"
  # e.g. /Users/you/proj/.maestro/com.example.app/edit-recipe/report/screenshots/TC-001_result.png
  ```
- **Workspace-relative link** (for clicking inside the repo): `[img](.maestro/<app-id>/<feature>/report/screenshots/TC-001_result.png)`

In the Evidence column, put the clickable relative link. In **Failed Test Details**, always list the **absolute** path(s) explicitly under a `Screenshots:` line — that block is the bug-logging handoff and must stand on its own.

Where the images come from:
1. **`report/screenshots/`** — `takeScreenshot` output (name each `TC-XXX_result`, or `TC-XXX_step<N>` for intermediate captures)
2. **`report/<timestamp>/screenshot-❌-*.png`** — auto-captured by Maestro on failure
3. **`report/figma/`** — design references (Figma renders or tester-supplied exports)
4. **`report/diff/`** — `compare_screenshots.py` heatmaps (Tier 2 failures)
5. **`report/grid/`** — gridded screenshots (Tier 3 working images; usually not linked in the report)
6. **`report/vision/`** — Tier 3 annotated results with defect cells washed red — **this is the evidence to link for a visual finding**, not the raw screenshot

> **Capture the path to the failing state, not just the crash frame.** For a failed TC, the auto `screenshot-❌` shows the end state. To make the bug reproducible, also ensure a `takeScreenshot` runs on the **screen just before the failing action** where practical, so the report can show the setup and the failure. See "Failed Test Details" below.

## Data sources

1. **Recorded results** from Phase 4 — pass/fail per TC, execution time, the exact step that failed
2. **`commands-*.json`** in `report/<timestamp>/` — step-by-step details (grep, don't Read whole)
3. **Screenshots** — locations above (record full paths)
4. **UI comparison verdicts** from the UI-validation phase, if run (see `ui-validation.md`)
5. **The existing `report.md`** — prior sessions' rows you must preserve

## Report template

The template below is the *full* file. On a resume session you don't retype it — you update the rows and append to the detail/log sections. Shown whole here so you know the target shape.

```markdown
# Test Execution Report: <Feature Name>

**App:** <app-id>
**Platform:** <Android/iOS>
**Feature:** <feature-name>
**Device / OS:** <e.g. Pixel 7 emulator, Android 14>   ← needed by bug logging (Environment)
**Build / Version:** <app version or build no. if known>
**Last updated:** <YYYY-MM-DD HH:mm>

---

## Summary (cumulative across all sessions)

| Metric | Value |
|--------|-------|
| Total planned test cases | X |
| Functional / UI-validation | X / X |
| Executed so far | X |
| ⬜ Pending (not yet run) | X |
| ✅ Passed | X |
| ❌ Failed | X |
| 🔍 Needs review (visual, human decides) | X |
| ⏭️ Skipped (not automatable) | X |
| Pass rate (of executed) | X% |
| Progress (executed / planned) | X / 60 |

**This session:** covered <P1> · ran X · ✅ X · ❌ X.

---

## Test Results  (this table is the progress board — upsert by TC id, never rewrite)

| Name | Priority | Step | Status | Evidence | Session |
|------|----------|------|--------|----------|---------|
| 🔧 TC-001 Happy path | P0 | Launch → login → submit | ✅ PASS | [img](.maestro/com.x/edit-recipe/report/screenshots/TC-001_result.png) | S1 (2026-06-29) |
| 🔧 TC-002 Empty form validation | P0 | Submit empty → assert error | ❌ FAIL | [fail](.maestro/com.x/edit-recipe/report/2026-06-29_1200/screenshot-❌-TC-002.png) | S1 (2026-06-29) |
| 🔧 TC-017 Add ingredient | P1 | Tap add → input → save | ✅ PASS | [img](.maestro/com.x/edit-recipe/report/screenshots/TC-017_result.png) | S2 (2026-06-30) |
| 🎨 TC-010 Edit screen matches Figma | P1 | Navigate → compare vs Figma | ❌ FAIL | [design](.maestro/com.x/edit-recipe/report/figma/TC-010_default.png) vs [annotated](.maestro/com.x/edit-recipe/report/vision/TC-010_default-report.png) | S2 (2026-06-30) |
| 🎨 TC-011 Home layout review | P2 | Navigate → vision scan | 🔍 REVIEW | [annotated](.maestro/com.x/edit-recipe/report/vision/TC-011_default-report.png) — 2 Minor (spacing) | S2 (2026-06-30) |
| 🔧 TC-031 Bulk delete | P2 | — | ⬜ PENDING | — | — |
| 🔧 TC-045 Perf: scroll 1k rows | P3 | — | ⏭️ SKIP | Performance — manual only | — |

> **Column guide:**
> - **Name** — type icon (🔧 functional / 🎨 UI validation) + TC id + short title
> - **Priority** — P0…P4 (drives which session runs it)
> - **Step** — the action sequence; for a failure, name the exact step that failed
> - **Status** — ⬜ PENDING / ✅ PASS / ❌ FAIL / 🔍 REVIEW / ⏭️ SKIP / 🔄 RETRY
> - **Evidence** — clickable workspace-relative link (full absolute paths live in Failed Test Details)
> - **Session** — which session ran it (S1, S2 …) + date, so history is legible

### Optional: step-by-step breakdown
When a TC has many steps or failed mid-way, expand it into one row per step so the exact failure point is obvious:

| Name | Step | Status | Evidence |
|------|------|--------|----------|
| TC-002 Validation | 1. Launch + clear state | ✅ PASS | — |
| TC-002 Validation | 2. Tap "Submit" | ✅ PASS | [img](.../screenshots/TC-002_step2.png) |
| TC-002 Validation | 3. Assert "Error message" visible | ❌ FAIL | [fail](.../2026-06-29_1200/screenshot-❌-TC-002.png) |

---

## Failed Test Details

*One entry per ❌ FAIL. This is the bug-logging handoff — write it so `notion-bug-logger` can file the bug directly, with no re-investigation. Append new entries; keep entries from earlier sessions.*

*A visual (🎨) FAIL earns the same entry. A Tier 3 Critical finding maps straight onto these fields: the finding text with its cell address becomes **Actual Result**, what the design or normal layout implies becomes **Expected Result**, and the annotated `report/vision/…-report.png` (plus the design reference, in design mode) becomes the **Screenshots** — so the developer opens one image and sees exactly which cell is wrong. Steps to Reproduce are still needed: a screenshot without the path to reach that screen isn't a filable bug.*

### ❌ TC-002 — Empty form validation

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Suggested severity** | Major |
| **Type** | 🔧 Functional |
| **Session** | S1 (2026-06-29 12:00) |
| **Environment** | com.example.app · Android 14 · Pixel 7 emulator · build 1.4.0 |

**Failed at:** `assertVisible: "Please fill all fields"` (step 3) — element not visible after 5000ms.

**Steps to Reproduce** (from a clean state — this is what makes it a filable bug):
1. Launch the app with cleared state (`launch_clear_state.yaml`).
2. Navigate: Home → Recipes → tap "＋ Add Recipe".
3. Leave every field empty.
4. Tap **Save Recipe**.

**Expected Result:** An inline validation message "Please fill all fields" appears; the form is not submitted.

**Actual Result:** No validation message appears; the app navigates back to the recipe list as if the save succeeded, persisting an empty record.

**Screenshots (absolute paths):**
- Setup (empty form before Save): `/Users/you/proj/.maestro/com.example.app/edit-recipe/report/screenshots/TC-002_step2.png`
- Failure state: `/Users/you/proj/.maestro/com.example.app/edit-recipe/report/2026-06-29_1200/screenshot-❌-TC-002.png`

**Reproduction flow:** `.maestro/com.example.app/edit-recipe/testcase/TC-002_empty_form_validation.yaml`

**Likely cause (hypothesis, not fact):** Validation is not wired to the Save handler, or the message text differs from the plan.

---

## UI Validation Details

*(Only if a 🎨 UI-validation TC ran. Record which tiers ran and what each said — a "—" means that tier wasn't used for this TC, which is normal. Full screenshot paths for any failure also go into Failed Test Details above so bug logging has them.)*

| TC | Screen | Tier 1 (assertions) | Tier 2 (baseline diff) | Tier 3 (visual review) | Verdict |
|----|--------|---------------------|------------------------|------------------------|---------|
| TC-010 | Edit Form | ❌ `assertVisible: "Save Recipe"` failed — button reads "Save" | — | 1 Critical (C3–D3 title clipped) | ❌ FAIL (static label + clipping) |
| TC-011 | Home | ✅ all pass | ✅ diff 0.4% ≤ 1% ([heatmap](.../diff/TC-011_diff.png)) | 2 Minor (spacing A11–F11) | 🔍 REVIEW — Minor only |
| TC-012 | Detail | ✅ all pass | ❌ diff 3.2% > 1% ([heatmap](.../diff/TC-012_diff.png)) | confirms: card height drifted, B4–E6 | ❌ FAIL — card height drifted |
| TC-013 | Settings | ✅ all pass | — (no baseline yet) | ✅ clean — promoted to baseline | ✅ PASS |

> Tier 1 failures cite the exact assertion. Tier 2 failures cite the diff ratio vs. threshold and link the heatmap. Tier 3 findings cite **severity + cell address** and link the annotated `vision/…-report.png`.

### Tier 3 findings (one line per finding, per TC)

*The cell address is what makes a visual finding actionable — "title is clipped" is vague, "title clipped in C3–D3" points straight at it. Mark estimates as estimates: vision judges layout, it never measures `dp`/`sp`.*

```
TC-010 — Edit Form  (device: Pixel 7 emulator, Android 14 · design: Figma node 123:456)
  [Critical] C3–D3: recipe title clipped at the right edge of the card; last
             characters cut by the card boundary. → report/vision/TC-010_default-report.png
  [Minor]    A11–F11: bottom nav icons sit tight against the divider; gap looks
             about half the design's (estimate, not measured).
  Excluded as data-driven: only 3 recipe cards shown vs. 6 in the design (user's data).
```

Always note what you **excluded as data-driven** — it shows the comparison was fair and stops the same difference being re-raised next session as a "new" defect.

---

## Session Log  (append one row per session — the audit trail of the resume)

| Session | Date | Scope | Ran | ✅ | ❌ | 🔍 | ⏭️ | Notes |
|---------|------|-------|-----|----|----|----|----|-------|
| S1 | 2026-06-29 | P0 (12 cases) | 12 | 10 | 2 | 0 | 0 | TC-002, TC-008 failed → in Failed Details |
| S2 | 2026-06-30 | P1 (15 cases) | 15 | 12 | 2 | 1 | 0 | TC-010 (UI, clipped title), TC-023 failed; TC-011 needs review |

---

## Recommendations
- [ ] TC-002 (P0): confirm exact validation message text with dev, then log bug (severity Major).
- [ ] TC-010 (P1): fix "Save Recipe" button label to match design.
- [ ] Remaining: P2–P4 still ⬜ PENDING (33 cases) — next sessions.
```

## End-of-session announcement (report clearly)

After updating `report.md`, tell the user plainly — don't make them open the file to learn what happened. Keep it short and quantitative, and always surface the two things they act on next: what failed (→ bug logging) and what's left (→ next session). Example:

```
Session 2 (P1) done — report updated: .maestro/com.example.app/edit-recipe/report/report.md

  P1: ran 15 · ✅ 12 · ❌ 2 · 🔍 1
  Cumulative: 27/60 executed · ✅ 22 · ❌ 4 · 🔍 1 · ⬜ 33 pending (P2–P4)

  Failures this session (details + repro steps + screenshot paths in the report,
  ready for the bug-logging phase):
    • TC-010 (Major) — "Save Recipe" button label reads "Save"; title also clipped
      at C3–D3 → report/vision/TC-010_default-report.png
    • TC-023 (Medium) — ingredient count not updated after add

  Needs your call:
    • TC-011 (🔍) — 2 Minor spacing findings on Home; annotated image in the report.
      Tell me fix / accept and I'll flip the row next session.

  Next session → P2 (18 cases).
```

## Handoff to bug logging (next phase)

Each Failed Test Details entry is deliberately shaped to match what `notion-bug-logger` needs, so the next phase is a copy-through, not a re-investigation:

| Failed Test Details field | → notion-bug-logger field |
|---------------------------|---------------------------|
| TC id + short title | Bug ID (title) |
| Suggested severity | Severity (Critical/Major/Medium/Minor) |
| Priority | Priority (P0…P4) |
| Environment line | Environment |
| Steps to Reproduce | Steps to Reproduce |
| Expected Result | Expected Result |
| Actual Result | Actual Result |
| Screenshots (absolute paths) | Evidence (local file path) |

Because those paths are absolute, the bug-logging phase can open and attach the images regardless of its working directory.
