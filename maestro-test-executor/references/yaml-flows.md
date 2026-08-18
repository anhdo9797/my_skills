# YAML Flows: Structure, Templates & Execution

Everything about writing, organizing, running, and debugging Maestro flows. Read this when generating or fixing YAML in Phase 4.

## Directory structure

```
.maestro/<app-id>/
├── config.yaml
├── selectors.md            ← persisted selector catalog (see selectors-and-inspection.md)
├── common/
│   ├── launch_clear_state.yaml
│   └── login.yaml
└── <feature-name>/
    ├── testcase/           ← individual TC files, created one by one
    │   ├── TC-001_<name>.yaml
    │   ├── TC-002_<name>.yaml
    │   └── ...
    ├── flow/               ← shared navigation flows
    │   └── navigate_to_screen.yaml
    └── report/             ← execution artifacts
        ├── report.md       ← THE one living report, updated in place every session (never re-timestamped)
        ├── screenshots/    ← takeScreenshot output (actual app captures)
        ├── figma/          ← design references: Figma renders or tester-supplied exports
        ├── baseline/       ← approved Tier 2 baselines + <TC>.masks.json sidecars
        ├── diff/           ← compare_screenshots.py heatmaps (on Tier 2 failure)
        ├── grid/           ← grid_overlay.py output — what Tier 3 vision actually reads
        ├── vision/         ← Tier 3 annotated results, defect cells washed red (the deliverable)
        └── <timestamp>/    ← maestro --test-output-dir logs + failure screenshots (one per run, accumulate)
```

**One TC id = one YAML file, reused across sessions.** The filename is keyed to the TC id (`TC-017_add_ingredient.yaml`). When a plan is run in slices (P0 session, then P1, …), a later session reruns or edits the *same* file in place — never create `TC-017_..._v2.yaml` or a re-slugged copy. Tag each TC with its priority so a session can run just its slice:

```yaml
tags: [<feature-name>, regression, P1]   # → maestro test --include-tags P1
```

## Reuse existing flows aggressively

Existing YAML flows are **mandatory reading** — they encode navigation paths that already work. When a new test case needs to reach "Edit Profile", and there's already a flow for "onboarding → home → profile", do not rewrite that path. Chain it:

```yaml
# TC-005: Edit profile name
- runFlow: ../../common/launch_clear_state.yaml          # reuse existing
- runFlow: ../../onboarding/flow/complete_onboarding.yaml # reuse existing
- runFlow: ../../home/flow/navigate_to_profile.yaml       # reuse existing
# Now write only the new steps specific to this TC
- tapOn: "Edit"
- eraseText: 30
- inputText: "New Name"
- assertVisible: "Profile updated"
```

The new YAML should only contain steps that are genuinely new. Everything before the new action should be a `runFlow` reference. Keep `runFlow` chains to **max 2 levels deep** — deeper nesting makes failures hard to trace.

## Functional TC template

```yaml
# --- Configuration ---
appId: ${APP_ID}
name: "TC-001: <Test case title>"
tags:
  - <feature-name>
  - regression
  - <priority>    # P0, P1, P2
env:
  APP_ID: <app-id>

---
# --- Preconditions ---
- runFlow: ../../common/launch_clear_state.yaml
- runFlow: ../flow/navigate_to_screen.yaml

# --- Steps ---
- tapOn:
    id: "element_id"
- inputText: "test value"

# --- Assertions ---
- assertVisible: "Expected Text"

# --- Evidence ---
- takeScreenshot: "TC-001_result"
```

## UI-validation template (Tier 1 assertions baked in)

A 🎨 UI-validation TC navigates to the screen, asserts the **static facts extracted from the Figma design** (these run forever with no Agent), then captures a screenshot for evidence and as the Tier 2 baseline input. See `ui-validation.md` for how to choose which facts become assertions vs. what to leave to a masked baseline diff.

```yaml
# TC-010: Edit Recipe screen matches Figma
appId: ${APP_ID}
name: "TC-010: Edit Recipe screen matches Figma"
tags: [ui-validation, <feature-name>]
env:
  APP_ID: <app-id>
---
- runFlow: ../../common/launch_clear_state.yaml
- runFlow: ../flow/navigate_to_edit_recipe.yaml
- waitForAnimationToEnd        # let the screen settle so the capture is stable

# --- Tier 1: static facts from the design (deterministic, no Agent) ---
- assertVisible: "Edit Recipe"            # screen title
- assertVisible: "Save Recipe"            # exact button label
- assertVisible:
    id: "recipe_photo"                    # image container exists (not WHICH photo)
- assertNotVisible: "Delete"             # design has no delete here

- takeScreenshot: "TC-010_result"
```

Assert only **static** elements (labels, headings, button text, element presence). Never assert dynamic content (a specific recipe name, count, or date) — that makes the test flaky. If navigation fails or a Tier 1 assertion fails, the TC is a FAIL.

**Tier 2 (optional) baseline diff** runs after capture, as a separate deterministic step — no Agent:

```bash
python3 scripts/compare_screenshots.py \
  report/baseline/TC-010.png report/screenshots/TC-010_result.png \
  --masks-file report/baseline/TC-010.masks.json --threshold 0.01 \
  --out report/diff/TC-010_diff.png   # exit 0 = pass, 1 = drift over threshold
```

## Execution command per TC

```bash
maestro test \
  --test-output-dir=.maestro/<app-id>/<feature>/report \
  .maestro/<app-id>/<feature>/testcase/TC-001_<name>.yaml
```

Always use `--test-output-dir` (not `--debug-output`, which creates a confusing nested structure).

## Handling failures

When a TC fails:

1. Read the error message — it identifies which command failed.
2. `grep` only the failing step out of the command log — don't `Read` the whole file:
   ```bash
   grep -A5 -i "error\|failed" report/<timestamp>/commands-*.json
   ```
3. Read `screenshot-❌-*.png` **only when the error message alone isn't enough** — an image costs thousands of tokens, so skip it for obvious failures (clear "element not found").
4. Common fixes:
   - **Element not found** → re-derive the selector via the cheap path (`selectors-and-inspection.md`) or existing flows
   - **Timeout** → add `waitForAnimationToEnd` or increase the `extendedWaitUntil` timeout
   - **Wrong screen** → fix the navigation flow
5. Fix YAML → re-run → record the final result.
6. Move to the next TC regardless of outcome (document failures for the report).

## Key YAML patterns

**Scroll to find element:**
```yaml
- scrollUntilVisible:
    element:
      text: "Save"
    direction: DOWN
    timeout: 10000
```

**Clear and re-enter text:**
```yaml
- tapOn:
    id: "input_field"
- eraseText: 50
- inputText: "New value"
```

**Optional element (won't fail if absent):**
```yaml
- tapOn:
    text: "Allow"
    optional: true
```

**Wait for async result (prefer over hardcoded `sleep`):**
```yaml
- extendedWaitUntil:
    visible:
      text: "Success"
    timeout: 15000
```

**Reuse shared flows with parameters:**
```yaml
- runFlow: ../../common/launch_clear_state.yaml
- runFlow: ../flow/navigate_to_screen.yaml
- runFlow:
    file: ../flow/setup_data.yaml
    env:
      USERNAME: "test@example.com"
```

For the full command-to-action mapping, see `maestro_commands.md`.
