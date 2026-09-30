---
name: figma-to-compose
description: Turn a Figma frame into Jetpack Compose, then prove it matches by rendering the real Compose and measuring the difference as ratios instead of eyeballing it. Use whenever the user wants to implement a Figma design as Compose, port a screen from Figma to Android, redesign an existing Compose screen against a new Figma frame, or build a Figma→code pipeline. Also trigger on "implement design này", "làm màn hình theo Figma", "figma sang compose", "code màn hình từ design", "so sánh UI với Figma", or when a figma.com/design URL appears next to an Android/Compose project. Works on any Compose project with no setup; when the project has a design system, point it at one optional adapter file and the generated code reuses that project's components and tokens instead of raw values.
---

# Figma → Compose

Produce Compose that matches the Figma frame, and prove it with measurements rather than
impressions.

```text
Figma ──► IR ──► Compose ──► Render ──► Measure ──► Repair
        (narrow,           (JVM,      (ratios,    (bounded)
         typed)            seconds)   not pixels)
                 ▲
         adapter ┘  optional: reuse this project's components and tokens
```

## The two rules that make this work

**1. The IR is narrow on purpose.** It covers the Figma subset that maps cleanly onto
Compose and refuses the rest into `unsupported[]`, with the node id intact, for a human. A
generator that approximates a mask or a mixed-style text run produces code nobody can trace
back to the design.

**2. Differences are measured as ratios, never as pixels.** A screenshot has no dp in it.
`1.33× the design's gap on node 20:12` is a finding an agent can act on; `3.2% of pixels
differ` is a number that sends the repair loop into an infinite guess. Pixel diff is a
*regression* gate after approval — never the repair signal.

## What this skill does not own

**Design-system conformance is a review concern, not a gate here.** Whether a value should
have been a token, whether a new composable duplicates an existing one, whether the palette
should migrate — those are judgement calls about a codebase, and they belong in code review
(`/code-review`, `review-bitbucket-pr`) where a human is already looking. This skill's job
is to make them *easy to see*: every raw value it emits carries a marker comment naming its
Figma node, and `mapping-report.json` lists them all. It does not stop work over them.

An earlier version blocked generation until every value resolved to a project token. On the
first real redesign it produced zero lines of Compose, because a new visual direction by
definition does not match the current theme. A tool that refuses to work on the case you
built it for is not a gate, it is a bug.

## Reference map

Read the reference when you reach its phase, not before.

| Phase | Reference | Read when |
|---|---|---|
| 1 · Extract | `references/extraction.md` | Pulling a frame out of Figma |
| 2 · IR | `references/ui-ir-schema.md` | Building or reading `screen.ui.json` |
| 2b · Tokens | `references/adapter-spec.md` | **Optional** — the project has a design system |
| 3 · Generate | `references/generation.md` | Writing Compose from IR |
| 4 · Verify | `references/verification.md` | Rendering and measuring |
| 5 · Repair | `references/repair-loop.md` | A measurement came back out of band |

## Phase 1 — Extract

Figma MCP only. Never screen-scrape, never guess geometry.

```
get_metadata(fileKey, nodeId)       → structure, names, x/y/w/h      → raw/metadata.xml
get_design_context(fileKey, nodeId) → fills, typography, text        → raw/context.json
get_variable_defs(fileKey, nodeId)  → design tokens, if the file has any
get_screenshot(fileKey, nodeId)     → raw/design.png  (the measurement baseline)
```

`get_variable_defs` returning `{}` is normal — most real files carry no variables. Derive
`raw/texts.json` and `raw/styles.json` from the design context. Details:
`references/extraction.md`.

## Phase 2 — IR

```bash
python3 scripts/figma_to_ir.py --metadata raw/metadata.xml --texts raw/texts.json \
                               --styles raw/styles.json --out ir/screen.ui.json
```

**Check the tree before trusting it.** Every section of the design should appear as a
container with a sensible `direction` and `gap`; platform chrome should be in
`platformChrome[]`; `unsupported[]` should be short. Layout is *derived from geometry*, so a
tree that does not look like the screen means the extractor guessed wrong — fix that before
generating, not after.

### Phase 2b — Tokens (optional)

Only when the project has a design system worth reusing:

```bash
python3 scripts/scan_design_system.py --project <APP> --out <APP>/.figma/adapter.json   # once
python3 scripts/resolve_tokens.py --ir ir/screen.ui.json --adapter <APP>/.figma/adapter.json \
                                  --out ir/screen.ui.json --report ir/mapping-report.json
```

This annotates values that match project tokens and lists the ones that don't. It **exits 0
either way** — `--strict` turns it into a CI gate for teams that have decided their screens
may not introduce raw values. Skip the whole step on a project with no design system, or
when the design is a visual direction the codebase has not adopted; the generator handles
raw values fine.

Component hints in the adapter are guesses until a human curates them. Prefer under-mapping:
a missed match costs one hint, a wrong match costs a rewrite.

## Phase 3 — Generate Compose

Rules in full: `references/generation.md`. The short version:

- **Reuse before you write** — anything with a `mapping.component` uses that composable.
- **Token when one exists, raw with a marker when it doesn't:**
  `Color(0xFF00DC82) // figma 17:34 — no matching token`. Never a bare unexplained literal.
- **Strings to resources.** Figma copy is the source of truth for the default locale.
- **Platform chrome is not content.** Use `statusBarsPadding()` / `navigationBarsPadding()`;
  never reproduce a mock's fake status bar as views.
- **Don't freeze the mock.** The frame is one width; the code runs on many. Keep `maxLines`,
  overflow, font-scale and width branching.

## Phase 4 — Verify

Two loops, and the fast one carries the repair cycle:

| Loop | Tool | Cost | Catches |
|---|---|---|---|
| **Fast** | Compose Preview screenshot test on the JVM (`screenshotTest`, Roborazzi, Paparazzi) | seconds | layout, spacing, typography, color |
| **Slow** | Build + emulator + Maestro | minutes, **run once at the end** | real state, navigation, dynamic data, insets |

Never put the emulator inside the repair loop. Measurement contract and commands:
`references/verification.md`.

**A clean measurement is not a passing grade.** The audits cover geometry and text; they are
blind to glow, shadow, font identity and thin accents — which is most of what makes a design
look like itself. Finish with the **material check** in `references/verification.md`:
magnify 3–4× and compare shadows, font, accents, gradients and radii by eye, and settle thin
accents by sampling pixels. A run that scored 0.962 on rhythm and 100% on structure was
still visibly wrong on all four.

**Prepare the baseline before measuring, or every number is wrong.** Crop the design's
platform chrome (it shifts every band by one), render the preview at the frame's dp size,
and ignore the final gap (the render fills the device; the frame stops at its content).
Then read each audit's `match_rate` / `resolution_note` **before** its findings — a pixel
typography audit on a 1× mobile frame resolves nothing and says so. Details and the numbers
from a real run: `references/verification.md`.

```bash
python3 scripts/compose_quality_gate.py --project <APP> --files <generated .kt> \
                                        --adapter <APP>/.figma/adapter.json --baseline HEAD
```

Advisory: it counts literals and component reuse in the generated file and reports the delta
against git. Useful as a summary to paste into a PR — it is a reviewer's input, not a stop
sign. Run it with `--strict` only if the team wants it enforced.

## Phase 5 — Repair

`references/repair-loop.md`. Bounded by construction: max **4** iterations, aggregate
deviation must decrease, one finding family per iteration, layout and style only. Stopping
without converging is a normal outcome — report what remains as numbers rather than hiding
it.

## Scripts

| Script | Does | Required |
|---|---|---|
| `scripts/figma_to_ir.py` | Figma metadata → `screen.ui.json` | yes |
| `scripts/scan_design_system.py` | Kotlin theme + composables → adapter skeleton | no |
| `scripts/resolve_tokens.py` | Annotates IR with project tokens; reports the rest | no |
| `scripts/compose_quality_gate.py` | Literal + reuse summary on generated Kotlin | no |

Measurement scripts are **not** duplicated here — `maestro-test-executor/scripts/`
(`spacing_audit.py`, `typography_audit.py`, `text_audit.py`, `pair_view.py`,
`grid_overlay.py`, `compare_screenshots.py`) already implement the ratio contract in
`maestro-test-executor/references/ui-metrics.md`. Phase 4 calls them; read that contract
before judging any measurement.
