# Test Planning

A test plan is the contract between the requirement and the flows you write. Spend
a few minutes here and the flows almost write themselves; skip it and you get a pile
of taps that assert nothing meaningful.

## When to plan vs. just write

- **Plan** for any feature, screen, or user journey ("test the favorites feature",
  "add tests for onboarding"). The user should confirm coverage before you author.
- **Skip straight to authoring** only for a trivial, fully-specified single check
  the user dictated ("assert the Home title says X").

## Source of truth — read before deriving scenarios

Testcases derived from assumptions are the main cause of shallow, unreliable suites.
Before enumerating scenarios, always read (in order):

1. **`.agent-kb/Readme.md`** — find which BRD + Development docs cover this feature.
2. **BRD doc** — the acceptance criteria are the testcase source. Every scenario must
   trace back to a specific BRD criterion; quote it in the `Criterion` field.
3. **Development doc** — the real navigation path, UI states, and data dependencies.
   A testcase with a guessed navigation path fails for the wrong reason.
4. **Compose source `features/<feature>/presentation/`** — `Modifier.testTag(...)`,
   `contentDescription`, `Text(...)` values are the only selectors you may use in steps
   and expected results. If no testTag exists for an element, flag it as a gap.

If any of these docs are missing, derive from source + app observation — but note the
gap explicitly in the plan.

## How to derive scenarios

For the target feature, enumerate scenarios across these categories. You won't need
every category every time — pick the ones that carry real risk for **this** feature
according to the BRD.

| Category | Question it answers | Example (a "favorite recipe" feature) |
|----------|--------------------|----------------------------------------|
| Happy path | Does the main BRD flow work end-to-end? | Tap heart on "Rice Egg Pork" → assertVisible id:favorites_item_title text:"Rice Egg Pork" |
| Alternate | Other valid routes to the same goal | Favorite from detail screen → same assertion |
| Negative / validation | Does it reject bad input/state gracefully? | Favoriting while offline → assertVisible id:retry_banner |
| Edge | Boundaries, empty/large states | Empty favorites → assertVisible id:empty_state_message |
| State / persistence | Does it survive navigation/relaunch? | Favorite set → relaunch warm → still assertVisible |
| Permission / system | OS dialogs, connectivity | Permission deny mid-flow → assertVisible id:permission_rationale |

Prioritize: **happy path first** (smoke suite), then negatives and edges from the BRD's
explicit error/edge criteria.

### Cache state — pick one per scenario

This app persists data, session, and the onboarding-completed flag, so every
scenario must declare which cache mode it runs under, because the same steps behave
differently cold vs warm:

- **Clear-cache (cold):** start from `launch_clear_state.yaml` (`clearState: true`).
  Deterministic; use for onboarding/first-run and anything that must not depend on
  leftover state. Most happy-path and edge scenarios are clear-cache.
- **With-cache (warm):** start from `launch_keep_state.yaml` (plain `launchApp`).
  Use for persistence — "favorite survives relaunch", "onboarding skipped on 2nd
  launch", cached list shows offline, login session kept. A warm scenario usually
  needs a clear-cache step first to *establish* the state, then a warm relaunch to
  assert it survived. Note this dependency in the plan's preconditions.

## Plan format

**Write the plan to a `TESTCASES.md` file, then ask the user to confirm it before
writing any YAML** — do not keep it only in chat. Location:

- Per-feature → `.maestro/flows/features/<feature>/TESTCASES.md`
- Smoke suite → `.maestro/flows/smoke/TESTCASES.md`
- Top-level index → `.maestro/TESTCASES.md` (links each feature plan; lists the build
  variant/appId and the run command). Create/update it alongside the feature plan.

Each `TESTCASES.md` carries a summary table plus a per-scenario section, and ends with
a short "Known fragility / recommendations" note (e.g. missing testTags, data
dependencies, scenarios expected to FAIL). Structure:

```
## Test plan: <feature>

Preconditions (global): <e.g. dev build installed, emulator running, locale=en>

| ID    | File                     | Scenario              | Priority | Cache       | Tags            |
|-------|--------------------------|-----------------------|----------|-------------|-----------------|
| TC-01 | favorite_from_list.yaml  | Favorite from list    | P0       | clear       | smoke, favorite |
| TC-02 | unfavorite_from_list.yaml| Unfavorite from list  | P1       | clear       | favorite        |
| TC-03 | favorite_persists.yaml   | Favorite persists     | P1       | clear→warm  | favorite        |
| TC-04 | favorites_empty.yaml     | Empty favorites state | P2       | clear       | favorite, edge  |

### TC-01 — Favorite from list
- Preconditions: on Recipes tab, recipe "Rice Egg Pork" visible
- Steps:
  1. Tap the favorite (heart) icon on "Rice Egg Pork"
  2. Open Favorites
- Expected: "Rice Egg Pork" appears in Favorites; heart shows filled state
```

Keep each scenario's steps in the order a user performs them.

### Testcase quality checklist — every scenario must pass all of these

A testcase fails the quality bar if any item is missing:

| Check | Bad (reject) | Good (accept) |
|-------|-------------|---------------|
| **BRD link** | "Favorite should work" | "BRD §3.2: tapping the heart adds the recipe to Favorites" |
| **Navigation path** | "Open Favorites" | "runFlow: open_recipes_tab.yaml → tap id:recipe_item_Rice_Egg_Pork" |
| **Step selectors** | "Tap the heart icon" | "tapOn id:favorite_button" (testTag confirmed in RecipeCard.kt:42) |
| **Expected result** | "Recipe appears in Favorites" | "assertVisible id:favorites_item_title text:'Rice Egg Pork'" |
| **Precondition data** | "A recipe exists" | "recipe 'Rice Egg Pork' seeded by clear-cache launch" |
| **Cache mode declared** | (missing) | "clear" or "warm" or "clear→warm" |

A step that says "tap the X button" without an `id:` or `text:` selector is not
acceptable — find the real testTag or contentDescription from the source, or flag it
as a gap with `# TODO: missing testTag on <element>`.

An expected result that cannot be written as a Maestro `assertVisible` / `assertNotVisible`
/ `assertTrue` command is not acceptable — rewrite it as one, or flag it as
`NEEDS_REVIEW` with the reason.

## Mapping plan → flows

- One scenario (TC-xx) → one flow file, named for the scenario
  (`favorite_from_list.yaml`), placed under `flows/features/<feature>/`.
- P0/happy-path scenarios also belong in `flows/smoke/` (or tagged `smoke`).
- Shared preconditions (launch with clean state, log in, navigate to a tab) become
  a subflow in `flows/common/` referenced via `runFlow:` — write setup once.
- Carry the plan's tags into each flow's `tags:` so `--include-tags` selection works.

## Scaffolding a new `.maestro/` setup

If the repo has no Maestro setup, create this layout:

```
.maestro/
├── config.yaml
└── flows/
    ├── common/        # shared subflows (launch, login, navigate)
    ├── smoke/         # P0 happy-path journeys
    └── features/
        └── <feature>/ # per-feature scenarios
```

`config.yaml`:

```yaml
flows:
  - flows/smoke/**/*.yaml
  - flows/features/**/*.yaml
testOutputDir: ../build/maestro
executionOrder:
  continueOnFailure: false   # stop the suite on first failure; set true to run all
```

Use `appId: ${APP_ID}` in flows and pass the real id at run time
(`-e APP_ID=com.example.app`) so the same flows work across flavors/build types.
