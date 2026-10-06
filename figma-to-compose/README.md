# figma-to-compose

Figma frame → Jetpack Compose that reuses the project's design system, with the difference
measured rather than eyeballed.

```text
Adapter  ──► IR ──► Compose ──► Render ──► Measure ──► Repair
(tokens +    (narrow,  (reuse      (JVM,     (ratios,    (bounded)
 components) typed)  components)  seconds)   not pixels)
```

## Why this shape

- **Works with no setup.** Point it at a Figma node and a Compose project. The adapter,
  token resolution and the literal summary are all optional; they make the output reuse a
  project's design system when there is one worth reusing.
- **Design-system conformance is review's job, not a gate here.** Every raw value the
  generator emits is listed with its Figma node in `ir/mapping-report.json` — never in a
  code comment (rule R7) — so review sees the question with its evidence. An earlier version blocked generation until every value
  resolved to a project token, and on the first real redesign it produced zero lines of
  Compose — a new visual direction by definition does not match the current theme.
- **HTML preview is not in the pipeline.** It cannot model what Figma→Compose actually gets
  wrong — text metrics, `includeFontPadding`, baseline alignment — and it costs a whole
  renderer to maintain. A JVM Compose render is the same speed and proves the real thing.
- **Layout is read, not guessed.** `get_design_context` *is* the auto-layout (`flex-col
  gap-[16px] px-[20px]`), plus every font, line height, gradient and shadow.
  `context_to_ir.py` parses it into a tree; geometry inference is only the fallback for
  hand-positioned frames.
- **The repair loop eats ratios, not pixel diffs.** `gap is 1.33× design on node 20:12` is
  one edit. "3.2% of pixels differ" is an infinite guess, and it is how these loops die.

## Layout

```
figma-to-compose/
├── SKILL.md                     orchestrator: phases, gates, stop conditions
├── references/
│   ├── adapter-spec.md          per-project token + component map
│   ├── extraction.md            Figma MCP → raw/
│   ├── ui-ir-schema.md          UI IR v1 (narrow by design)
│   ├── generation.md            IR → Compose rules
│   ├── verification.md          quality gate → JVM render → device
│   └── repair-loop.md           bounded repair, escalation
├── scripts/
│   ├── context_to_ir.py         get_design_context → node tree (layout, style, text runs)
│   ├── figma_to_ir.py           metadata geometry + context tree → screen.ui.json (IR v2)
│   ├── ir_coverage_check.py     did the IR carry the design? (blocking)
│   ├── layout_rules_check.py    layout contract R1–R7 (blocking)
│   ├── layout_assert.py         real node bounds vs design, in dp
│   ├── state_distinct_check.py  each captured state really is different
│   ├── scan_design_system.py    Kotlin theme + composables → adapter skeleton
│   ├── resolve_tokens.py        raw values → project tokens (advisory)
│   └── compose_quality_gate.py  literal + reuse summary on generated Kotlin
├── tests/                       python3 -m unittest discover -s tests
├── assets/layout-audit/         Kotlin templates for layout_assert.py
└── agents/
    └── figma-compose-worker.md  task brief for a coding agent (codex / claude)
```

## Quick start

```bash
# 1 · extract (agent, via Figma MCP) → raw/metadata.xml, raw/context.json, raw/design.png
python3 scripts/context_to_ir.py --context raw/context.json --tree raw/context-tree.json \
    --texts raw/texts.json --styles raw/styles.json --assets raw/assets.json

# 2 · IR — then read the tree and check it looks like the screen
python3 scripts/figma_to_ir.py --metadata raw/metadata.xml --tree raw/context-tree.json \
    --texts raw/texts.json --styles raw/styles.json --assets raw/assets.json \
    --out ir/screen.ui.json
python3 scripts/ir_coverage_check.py --ir ir/screen.ui.json --texts raw/texts.json \
    --styles raw/styles.json --assets raw/assets.json

# 3 · generate (agent, following references/generation.md)

# 4 · render and measure against raw/design.png
./gradlew :app:validateDebugScreenshotTest
```

Optional, when the project has a design system worth reusing:

```bash
python3 scripts/scan_design_system.py --project $APP --out $APP/.figma/adapter.json  # once
#   then curate figmaHints by hand — auto-generated hints are guesses

python3 scripts/resolve_tokens.py --ir ir/screen.ui.json --adapter $APP/.figma/adapter.json \
                                  --out ir/screen.ui.json --report ir/mapping-report.json
#   exits 0 with unmapped values; --strict turns it into a CI gate

python3 scripts/compose_quality_gate.py --project $APP --adapter $APP/.figma/adapter.json \
                                        --files <generated .kt> --baseline HEAD
#   a literal/reuse summary to paste into the PR
```

## Measurement is not duplicated here

Spacing, typography and text audits live in `../maestro-test-executor/scripts/` and run on
the ratio contract in `../maestro-test-executor/references/ui-metrics.md`. Phase 4 calls
them. Read that contract before judging any measurement — in particular, that text is
compared exactly from the view hierarchy while geometry is compared as a ratio, and that
neither says anything about gradients, shadows, icon shape, or whether a control is
tappable.

## Requirements

- Figma MCP configured for the agent doing the extraction
- Python 3.10+ (stdlib only; Pillow only for the measurement scripts)
- AGP 8.5+ for `screenshotTest`, or an existing Roborazzi/Paparazzi setup
