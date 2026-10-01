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
| 3b · Layout contract | `references/layout-contract.md` | **Before writing a screen** — the rules the gate enforces |
| 4 · Verify | `references/verification.md` | Rendering and measuring |
| 4b · Pixel fidelity | `references/pixel-fidelity.md` | **Before the first layout assertion**, and for any pixel-perfect run |
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

**A stale adapter exits 3, and there is no override.** The adapter carries a per-file hash of
the theme sources it was built from; `resolve_tokens.py` recomputes them first and refuses if
anything was added, removed or edited. This is the one place in the token path that is strict,
because the failure is not a judgement call: in a real run the adapter was built at 21:57, the
same task legitimately added a brand palette at 22:0x, and the 22:27 mapping report called
`#FD75A7` unmapped when `PairPulsePink500` had existed for half an hour. An advisory warning
is precisely what went unread. Regenerating costs one second.

Component hints in the adapter are guesses until a human curates them. Prefer under-mapping:
a missed match costs one hint, a wrong match costs a rewrite.

### Pixel-perfect mode — declared, not default

Snapping 15dp to `spacing.md`(16) is a deliberate 1dp loss, and a real run spent it **85**
times. You cannot snap 85 times and be pixel-perfect, so this is a per-screen decision:

```bash
python3 scripts/resolve_tokens.py … --pixel-perfect
```

In that mode a snap is reported as **fidelity lost** with the exact dp cost, not as a
resolution — which forces the theme to carry the design's real values rather than rounding
the design to the theme. Pair it with `layout_assert.py --tolerance 0.5 --strict`.

Worth it for a surface where the designer's exact rhythm is the product. Not worth it for an
internal settings list. The precondition and the honest limits — the device is 411.4dp wide
and the frame is 390dp, so "pixel-perfect" can only mean *at the design's width* — are in
`references/pixel-fidelity.md`.

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

Five checks, in this order — each answers something the next cannot:

| | Check | Cost | Answers |
|---|---|---|---|
| **0** | **Layout contract** — `layout_rules_check.py` | ~1s | **exits 1**: fixed dims around text, text with no overflow or no colour, rows that push their own icons out or stretch their own pill, images losing their ratio |
| 1 | Literal summary (static) | ~1s | tokens vs raw values vs invented alpha — advisory |
| 2 | **Layout assertion** — `layout_assert.py` | seconds | *exactly* where each node landed, in dp — **exits 3 if nothing was measured** |
| 3 | **Material check** — human, magnified | minutes | glow, font, thin accents |
| 4 | Ink-band audits | seconds | **mandatory** when check 2 cannot run |
| — | Device run (emulator) | minutes | real state, navigation, insets — **once, at the end** |

**Two checks block, and they block for opposite reasons.** Check 0 blocks on a *wrong
answer*; check 2 blocks on *no answer*. The token gate and the literal summary stay advisory
because they are judgement calls about a codebase.

The layout contract is correctness: a screen that fails it matches the design at one width
with one string length and breaks outside that. Measured on freshly generated screens: rows
that push their own icons off screen, texts that clip with no ellipsis, and — the two newest
rules — **six texts with no declared colour** (a `#141414` title rendering pale grey because
it inherited `LocalContentColor` from a theme built for another product) and a `weight()` on
a pill's label that turned a 160dp button into a full-width bar. Both of those shipped
through a green run before R5 and R6 existed.

**Check 2 is the primary measurement, not the pixel audits.** Tag each generated composable
with its Figma node, read the real bounds back from `LayoutCoordinates`, compare dp to dp.
It names the composable at fault and it sees a 3dp accent bar rendering at zero height —
which every pixel ratio in a real run reported as green. Ink-band audits guess boundaries
from pixels, cannot attribute a finding to a node, and are fooled by content differences.

**The skill ships the instrumentation — `assets/layout-audit/`.** Earlier versions described
check 2 as primary while requiring a tag helper and test fixture the skill did not provide,
so on a fresh project it simply never ran, which is exactly the project it exists for. Copy
the templates in, per that directory's README.

**`UNMEASURED` is a verdict, not a footnote.** If no node was tagged and compared,
`layout_assert.py` exits 3 — unconditionally, even without `--strict` — and the run may not
use the words *converged*, *fidelity*, or *passing*. `STOPPED UNCONVERGED` means a real
number exists and repair did not close it; that is an honest result. `UNMEASURED` is an
absence of evidence, and a run that reports success from static gates alone has measured
nothing. When tagging genuinely cannot be added, check 4 becomes **mandatory** rather than a
fallback — commands in `references/verification.md`.

The repair loop runs on check 2 plus the JVM render; the emulator never goes inside it.

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
| `scripts/figma_to_ir.py` | Figma metadata → `screen.ui.json` (incl. each node's design `rect`) | yes |
| `scripts/layout_rules_check.py` | Layout contract gate — R1–R6, **exits 1** | **yes** |
| `scripts/layout_assert.py` | Real node bounds vs design, per node, in dp — **exits 3 if nothing measured** | **yes**; `UNMEASURED` otherwise |
| `assets/layout-audit/` | Kotlin templates that make `layout_assert.py` runnable on a bare project | with check 2 |
| `scripts/scan_design_system.py` | Kotlin theme + composables → adapter, with a theme-source fingerprint | no |
| `scripts/resolve_tokens.py` | Annotates IR with project tokens; **exits 3 on a stale adapter** | no |
| `scripts/compose_quality_gate.py` | Literal, alpha and reuse summary on generated Kotlin | no |

Measurement scripts are **not** duplicated here — `maestro-test-executor/scripts/`
(`spacing_audit.py`, `typography_audit.py`, `text_audit.py`, `pair_view.py`,
`grid_overlay.py`, `compare_screenshots.py`) already implement the ratio contract in
`maestro-test-executor/references/ui-metrics.md`. Phase 4 calls them; read that contract
before judging any measurement.
