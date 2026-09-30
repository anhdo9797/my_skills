# Agent brief — figma-compose-worker

A task brief for a coding agent (codex, claude) executing this pipeline on one screen.
Fill the placeholders, hand it over whole. The agent starts cold — everything it needs is
either here or behind a path named here.

---

## Inputs

| | |
|---|---|
| Android project | `{{PROJECT_ROOT}}` |
| Skill root | `{{SKILL_ROOT}}` (read `SKILL.md` first, then the reference for each phase) |
| Figma file key | `{{FILE_KEY}}` |
| Figma node | `{{NODE_ID}}` — `{{SCREEN_NAME}}` |
| Target file | `{{TARGET_KT}}` |
| Adapter | `{{PROJECT_ROOT}}/.figma/adapter.json` (already generated; component map is unreviewed) |
| Work dir | `{{WORK_DIR}}` — put `raw/`, `ir/`, `render/`, `audit/` here |

## Ground rules

1. **Build the screen.** Unmapped tokens do not stop you — emit the design's own value with
   a marker comment naming the Figma node (`// figma 17:34 — no matching token`) and keep
   going. The deliverable is a working screen plus an honest account of what is raw in it.
2. **Never an unexplained literal, and never an invented token.** A bare `Color(0xFF00DC82)`
   hides the finding; the same literal with its node id hands review the question. Do not
   name a token that does not exist in the project.
3. **Do not edit the theme.** Not `Color.kt`, not the theme composable. If whole families of
   colours are unmatched, say so in the report — migrating the palette is a decision for the
   people who own the codebase, made with the working screen in front of them.
4. **Scope is the screen file.** No ViewModel, repository, navigation, DI, or dependency
   changes. If the design needs data the current UI state does not carry, add the field to
   the state class, leave a `TODO` with the Figma node id, and say so in the report.
5. **Report what happened, including what failed.** A half-converged repair loop and a
   screen that is 80% off-palette are normal outcomes. A report that hides them is worse
   than no report.

> **Steps 3b and 5's summary are optional.** Run them when `{{PROJECT_ROOT}}/.figma/adapter.json`
> exists. Without it, go straight from the IR to generation — the output is idiomatic
> Compose with the design's own values, which is the right answer for a project with no
> design system to reuse.

## Steps

### 1 · Verify the toolchain

Run each script with `--help`. Then confirm `python3 --version` ≥ 3.10 and that
`{{PROJECT_ROOT}}/.figma/adapter.json` parses. **If a script has a bug, fix the script in
`{{SKILL_ROOT}}/scripts/` and say what you changed** — these are new and this run is their
first real exercise.

### 2 · Extract from Figma

Via Figma MCP, into `{{WORK_DIR}}/raw/`:

```
get_metadata(fileKey, nodeId)       → raw/metadata.xml   (verbatim, including any prefix lines)
get_variable_defs(fileKey, nodeId)  → raw/variables.json ({} is normal — most files have no variables)
get_design_context(fileKey, nodeId) → raw/context.json
get_screenshot(fileKey, nodeId, maxDimension = 2 × frame width) → raw/design.png (curl the URL)
```

Then derive two files the extractor needs, from `context.json`:

- `raw/texts.json` — `{"<nodeId>": "<exact string>"}` for every text node. Copy the
  characters exactly, diacritics included. A string you cannot read is `null`, never a guess.
- `raw/styles.json` — `{"<nodeId>": {"fill": "#RRGGBB", "radius": 22, "size": 16,
  "weight": 600, "color": "#RRGGBB", "border": "#RRGGBB"}}` for every node that has them.

### 3 · IR

```bash
python3 {{SKILL_ROOT}}/scripts/figma_to_ir.py \
    --metadata raw/metadata.xml --texts raw/texts.json --styles raw/styles.json \
    --file-key {{FILE_KEY}} --out ir/screen.ui.json
```

**Check the IR by hand before trusting it** — this is the step that decides whether the
generated screen is right, because layout is derived from geometry rather than read from
Figma. Every section of the design should appear as a container with a sensible `direction`
and `gap`, platform chrome should be in `platformChrome[]`, and `unsupported[]` should be
short. A tree that does not look like the screen means the extractor guessed wrong — fix it
now, not after generating from it.

### 3b · Tokens — only if `.figma/adapter.json` exists

```bash
python3 {{SKILL_ROOT}}/scripts/resolve_tokens.py \
    --ir ir/screen.ui.json --adapter {{PROJECT_ROOT}}/.figma/adapter.json \
    --out ir/screen.ui.json --report ir/mapping-report.json
```

Exits 0 even with unmapped values. Read `ir/mapping-report.json` for what stayed raw — it
goes in the report and in the PR description, not in a stop decision.

### 4 · Generate

Follow `{{SKILL_ROOT}}/references/generation.md`. Reuse before writing; token where the IR
resolved one and a marked raw value where it did not; strings to `res/values/strings.xml`;
existing adaptive behaviour preserved.

### 5 · Verify

```bash
python3 {{SKILL_ROOT}}/scripts/compose_quality_gate.py \
    --project {{PROJECT_ROOT}} --adapter {{PROJECT_ROOT}}/.figma/adapter.json \
    --files {{TARGET_KT}} --baseline HEAD --json audit/quality.json
```

Fix what it flags, then render. Prefer the project's existing screenshot-test setup; if
there is none, add the `screenshotTest` source set (AGP 8.5+) with a deterministic preview
at the Figma frame's dp size. Then measure with `maestro-test-executor/scripts/` against
`raw/design.png` and read the JSON before any image.

### 6 · Repair, bounded

`{{SKILL_ROOT}}/references/repair-loop.md`. Max 4 iterations, deviation must decrease, one
finding family per iteration, layout and style only. Stopping without converging is a
result — report the remaining findings as numbers.

## Deliverable — `{{WORK_DIR}}/REPORT.md`

```markdown
## Verdict
GENERATED | CONVERGED | STOPPED UNCONVERGED | EXTRACTION FAILED

## Raw values in the generated screen
resolved N · snapped N · raw N · components reused N
<what stayed raw, grouped — "38 of 41 colours are new; this frame is a dark redesign"
beats 38 separate lines. This paragraph belongs in the PR description too.>

## Changes
<files touched, and why each>

## Script fixes
<any change made under scripts/, with the reason>

## Measurements
<the audit numbers, per finding, with node ids>

## Open
<what a human has to decide, stated as a question with options>
```
