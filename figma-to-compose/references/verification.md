# Phase 4 — Verification

Four checks. The order matters: each one answers a question the next cannot.

| | Check | Cost | Answers |
|---|---|---|---|
| 1 | **Literal summary** (static) | ~1s | tokens vs raw values, component reuse — *advisory* |
| 2 | **Layout assertion** (`layout_assert.py`) | seconds | *exactly* where each node landed, in dp |
| 3 | **Material check** (human, magnified) | minutes | glow, font, thin accents — what no script sees |
| 4 | **Ink-band audits** (`spacing_audit`, `typography_audit`) | seconds | fallback for untagged screens, and a cross-check |
| — | **Device run** (emulator) | minutes | real state, navigation, insets — **once, at the end** |

**Check 2 replaced check 4 as the primary measurement**, and the reason is worth knowing:
the ink-band audits find element boundaries by scanning pixels, so they cannot name the
composable at fault, and they are fooled by content differences — a design row with a photo
thumbnail against a rendered row with an icon reads as a 20dp layout bug with nothing wrong
in the code. Layout assertion compares dp to dp, straight from `LayoutCoordinates`. It is
exact where the pixel audits are approximate, and it sees a 3dp accent bar that renders at
zero height — which every ratio in a real run reported as green.

Use the ink-band audits when the screen has no tags (legacy code, or a screen this pipeline
did not generate), or as a second opinion.

Full method, the tagging convention, and the limits: `references/pixel-fidelity.md`. The
tagging helper, the collector, and the dump-test harness itself ship as copy-in templates at
`assets/layout-audit/` — read its README before the first run; it exists precisely because a
real run reported success with every gate green while check 2 never executed at all (next
section explains why that is no longer a quiet outcome).

## Verdict state machine

A run that passes every static gate and never executes check 2 is not a passing run. A real
run did exactly that: `layout_rules_check.py` clean, the quality gate clean, the material
review done on a real device — and `layout_assert.py` never ran, because the tagging helper
and dump harness it needs did not exist in that project. The report said so honestly in a
footnote. The verdict at the top of the same report did not reflect it. That gap is the
defect this section closes.

Every run ends in exactly one of three verdicts. They are not degrees of the same thing —
they answer different questions, and conflating them is how an unmeasured screen ships under
a verdict that sounds like it was checked.

| Verdict | Means | How you get here |
|---|---|---|
| **PASS** | Check 2 ran, every tagged node is within tolerance, and tagging covered the screen. | `layout_assert.py` exits 0 with `"verdict": "PASS"` in its JSON. |
| **STOPPED UNCONVERGED** | Check 2 ran and measured real deviation that the repair loop (`references/repair-loop.md`) did not fully close within its 4-iteration bound. | `layout_assert.py` reports `"verdict": "FINDINGS"` at the end of the loop. This is an **honest result** — something was measured, the number is real, and the report says exactly what remains out of band. |
| **UNMEASURED** | Check 2 (and, if it was unavailable, the mandatory fallback below) did not produce a numeric comparison at all. | `layout_assert.py` exits **3** with `"verdict": "UNMEASURED"` — either nothing was tagged, or tagging covered too little of the screen (`--min-coverage`) — **or** the script could not be run at all and no ink-band audit was run in its place. |

**UNMEASURED is not a weaker PASS and not a kind of STOPPED UNCONVERGED — it is the absence of
evidence, not evidence of absence.** STOPPED UNCONVERGED means "we measured the gap between
the design and the screen, and it is N dp on these nodes." UNMEASURED means no such number
exists, for any node, so there is nothing to report as converged, close, or even roughly
right. A report may not use the words *convergence*, *fidelity*, *matches the design*, or
*passing* while its verdict is UNMEASURED — only the vocabulary a static gate earns: "the
layout contract is clean," "the quality gate is clean," neither of which is a claim about
whether the screen looks like the design.

**This is binding the same way the layout contract is.** `layout_rules_check.py` exits 1 and
that blocks; `layout_assert.py` now exits 3 under the same principle — a distinct exit code
from "measured and found issues" (which does not, by itself, block — see `--strict`) because
*not measured* and *measured and wrong* are different failures needing different next steps.
Treat exit 3 the way you treat exit 1 from the layout contract: stop, fix the cause (wire the
instrumentation, or run the mandatory fallback below), and re-run — do not report the run's
outcome from whatever gates did execute.

**Clearing UNMEASURED takes a real measurement, not a retry.** Running
`compose_quality_gate.py` again, re-reading the material check, or simply restating the
static gates as "all green" does not change the verdict — none of them measure geometry
against the design. Only one of two things clears it:

1. `layout_assert.py` runs with real tagged coverage and reports `PASS` or `FINDINGS`, or
2. tagging genuinely cannot be added this run, and the mandatory fallback below is run
   instead and its numbers are reported in the same place check 2's would have gone.

A report whose verdict is UNMEASURED still names every gate that **did** run clean — that
information is real and worth keeping — it just cannot borrow their color for the one
question none of them answer: does the screen match the design.

## 1 · Literal summary — advisory

```bash
python3 scripts/compose_quality_gate.py \
    --project <ANDROID_ROOT> \
    --files app/src/main/java/.../HomeScreen.kt \
    --adapter <ANDROID_ROOT>/.figma/adapter.json \
    --baseline HEAD
```

Counts dp/sp/color literals and literal user-facing strings in the generated file, lists the
design-system components it reuses and the composables it declares, and reports the delta
against a git ref.

**It is a reviewer's summary, not a stop sign.** Paste it into the PR description: "18 dp
literals, 12 colours (each listed with its node in mapping-report.json); reuses ComposerCard and IconTile;
declares StatsHero, ToolTile, RecentOutputRow." That is the input a reviewer needs to ask
the right question. Whether those numbers are acceptable depends on the codebase, and that
judgement belongs to whoever owns it.

A literal user-facing string is the one finding worth acting on without discussion — that is
a localisation bug, not a style preference.

## 2 · Layout assertion — the primary measurement

```bash
# tags on, run the dump test, pull the result
./gradlew :app:connectedDebugAndroidTest --tests '*HomeLayoutDumpTest'
adb pull /sdcard/Download/nodes.json render/nodes.json

python3 scripts/layout_assert.py --ir ir/screen.ui.json --actual render/nodes.json \
        --out audit/layout.json --tolerance 1.0
```

Reports three deltas per node — `size`, `offset` within its parent, `gap` to the previous
sibling — each naming the Figma node and the composable. Fix in that order: a wrong size
moves everything after it. Nodes in the IR with no tag are counted as **unverified**, never
as passing.

`--tolerance 0.5 --strict` for a pixel-perfect run. The method, the tagging convention, and
the limits are all in `references/pixel-fidelity.md`. If the project has no tagging helper or
dump test yet, copy them in from `assets/layout-audit/` rather than improvising one — that
directory's README states the AGP/dependency assumptions and exactly where each file goes.

**Read `"verdict"` in `audit/layout.json` before anything else in it**, and check the exit
code: `0` = `PASS`, `0` or `1` (depending on `--strict`) = `FINDINGS`, `3` = `UNMEASURED`.
Exit `3` fires regardless of `--strict` — an unmeasured run is never a pass — and means
`--min-coverage` was not met (default: zero nodes were tagged and compared at all). See
"Verdict state machine" above before reporting anything from a run that hit it.

## 3 · Fast render

Compose Preview screenshot testing on the JVM. No emulator, no APK.

**AGP 8.5+** ships `screenshotTest` (`com.android.compose.screenshot`); AGP is 8.13 here,
so prefer it. Roborazzi or Paparazzi are equivalent for this purpose — if the project
already has one, use that rather than adding a second.

```kotlin
// app/src/screenshotTest/kotlin/.../HomeScreenPreviews.kt
@Preview(name = "home", device = "spec:width=390dp,height=1315dp,dpi=320")
@Composable
private fun HomePreview() {
    VideoComposerTheme { HomeScreen(state = HomeUiState(/* fixture */), /* no-op lambdas */) }
}
```

```bash
./gradlew :app:updateDebugScreenshotTest    # record
./gradlew :app:validateDebugScreenshotTest  # compare against recorded
```

Set the preview device to the **Figma frame's dp size** so the render and the design share
a coordinate space. Then the render is directly comparable to `raw/design.png` and
ratio measurement means something.

Fixtures must be **deterministic** — fixed strings, fixed dates, fixed sizes. A render
whose content changes between runs cannot be compared to anything.

### Prepare the baseline before you measure anything

The design PNG and the render are not comparable as they come out. Three mismatches will
each produce a full screen of confident, specific, completely wrong findings — and they
look exactly like layout bugs, which is what makes them expensive.

**1 · Strip the platform chrome from the design.** The frame carries a fake status bar and
home indicator; the code renders neither (it uses `statusBarsPadding()`). That one extra
band at the top shifts every subsequent pairing by one, so the audit compares the nav bar
to the hero, the hero to the button, and so on down the screen.

```bash
# heights come from the IR's platformChrome[] — here 44dp status bar, 34dp home indicator
python3 $M/spacing_audit.py design.png render.png --design-width-dp 390 \
        --crop-design-top 44 --crop-design-bottom 34 --out audit/spacing.png
```

Measured on a real run: uncropped, 9 gaps and 8 band heights flagged with nonsense pairings
(a 150dp hero "matched" to a 43dp stats row). Cropped, the band sequences aligned 14-to-14
and the findings became real.

**2 · Export the design at the render's scale.** Ask `get_screenshot` for a `maxDimension`
that yields the frame's natural size or a clean multiple of it, and render the preview at
the frame's dp size (`spec:width=390dp,height=1315dp,dpi=160`). A 232px-wide design beside
a 390px render measures nothing.

**3 · Expect the bottom to diverge, and ignore it.** The design frame is exactly as tall as
its content. The render fills the device, so any content that comes up short pools as empty
space above the bottom bar. On the same run this showed as a final gap of 88dp against the
design's 37dp — a 2.4× "finding" that is neither a bug nor fixable. **Trailing space is not
a measurement.** Read the gaps between content bands and ignore the last one.

### Ink-band audits — mandatory when layout assertion is unavailable, a fallback otherwise

Two different situations reach this section, and only one of them is optional:

- **Layout assertion couldn't run at all** — `layout_assert.py` exited 3 (UNMEASURED), or the
  tagging helper genuinely cannot be added this run. Here these audits are **mandatory, not
  optional.** Skipping them is exactly the gap this file exists to close: every static gate
  green, the real screen never measured against the design, and a report that cannot
  honestly say either way. Run them and report their numbers in place of `audit/layout.json`.
- **Layout assertion ran.** Here they are what the table above says — a second opinion, or
  the tool for a screen this pipeline didn't tag (legacy code).

Either way, reuse the ratio contract already implemented in this repo — do not write a new
one. Read `maestro-test-executor/references/ui-metrics.md` before judging any output, and
**prepare the baseline first.** The precondition is the same as "Prepare the baseline before
you measure anything" above, with one difference worth naming: when layout assertion is
unavailable there is often no JVM `screenshotTest` render either, so `actual` here is commonly
a **real device/emulator screenshot** instead of a chrome-less preview render — which means
**both** sides need their chrome cropped, not just the design's:

```bash
M=../maestro-test-executor/scripts

# heights come from the IR's platformChrome[] (design side); the device side is percentage-based
# because its exact px depends on resolution — these are Android gesture-nav defaults, verified
# against pair_view.py's own --help; use 4%/5% for 3-button nav instead
DESIGN_TOP=44 DESIGN_BOTTOM=34   # dp, from platformChrome[] — design.png is a 1x export
ACTUAL_TOP=4% ACTUAL_BOTTOM=3%   # device screenshot — status bar / gesture nav

# geometry: gaps between elements, element heights, side margins
python3 $M/spacing_audit.py raw/design.png device/home.png \
    --crop-design-top $DESIGN_TOP --crop-design-bottom $DESIGN_BOTTOM \
    --crop-actual-top $ACTUAL_TOP --crop-actual-bottom $ACTUAL_BOTTOM \
    --design-width-dp 390 --out audit/spacing.png > audit/spacing.json

# typography: font size and weight, per text band — read resolution_note first (below)
python3 $M/typography_audit.py raw/design.png device/home.png \
    --crop-design-top $DESIGN_TOP --crop-design-bottom $DESIGN_BOTTOM \
    --crop-actual-top $ACTUAL_TOP --crop-actual-bottom $ACTUAL_BOTTOM \
    --design-width-dp 390 --out audit/type.png > audit/type.json

# text content: exact, no tolerance — needs the real view hierarchy, not a screenshot
maestro hierarchy > render/hierarchy.json   # or: adb exec-out uiautomator dump /dev/tty > render/hierarchy.xml
python3 $M/text_audit.py --expected ir/expected-strings.json --actual render/hierarchy.json \
    --out audit/text.json

# content & style diff, chrome-aligned — a can't-skip list of flagged cells, not a geometry measurement
python3 $M/pair_view.py raw/design.png device/home.png \
    --crop-actual-top $ACTUAL_TOP --crop-actual-bottom $ACTUAL_BOTTOM \
    --out audit/pair.png > audit/pair.json
```

Comparing against a chrome-less JVM `screenshotTest` render instead (the "Prepare the
baseline" case above)? Drop `--crop-actual-top`/`--crop-actual-bottom` from all three — the
render has no status bar or nav bar to strip in the first place.

`spacing_audit.py`, `typography_audit.py`, and `pair_view.py` print their JSON result to
**stdout** and take `--out` only for the annotated/composite **PNG** — redirect stdout
yourself if you want the numbers on disk: `python3 $M/spacing_audit.py … > audit/spacing.json`.
`text_audit.py` is the exception: its `--out` writes the JSON result directly, as shown above.

Read **the JSON before the images**. Numbers settle most of the verdict at a fraction of
the cost; open `pair_view.py` / `grid_overlay.py` composites only for what the numbers
flag — `grid_overlay.py render/home.png --highlight <cells>` turns a numeric finding into an
annotated screenshot for a report.

The contract in one line: **text is exact, geometry is a ratio.** A gap reported as
`1.33× design` is actionable. "Looks a bit loose" is not, and neither is "3.2% of pixels
differ".

#### What this fallback can honestly claim, and what it cannot

This is weaker evidence than a clean `layout_assert.py` run, not an equivalent — say so in
whatever report cites it:

| | `layout_assert.py` | Ink-band fallback |
|---|---|---|
| Reads | `LayoutCoordinates`, exact dp | pixels, inferred bands |
| Names the composable at fault | yes — the Figma node id | no — a band index / cell address only |
| Sees a 3dp accent bar | yes | no — too thin to segment, reports nothing |
| Confused by a photo vs. an icon in the same slot | no | yes — a content difference reads as a layout bug |
| Proves | the real render's bounds vs. the design's | the render's **pixels** approximate the design's bands within a ratio band |

So: a clean fallback run means *"the measurable bands — mostly text and their surrounding
gaps — fall within the tolerance band, and `pair_view.py` found no flagged cell."* It does
not mean the screen's geometry matches the design the way a clean `layout_assert.py` run
would; it means the parts pixels can resolve didn't contradict the design, and the rest —
thin accents, elements with no ink to segment, which composable to blame for a flagged gap —
stayed unmeasured by this method too. State that distinction in the verdict, don't let a
clean fallback run upgrade a report past STOPPED UNCONVERGED into language that claims more
than it checked.

### Where the pixel audits stop, and what to use instead

**Read each audit's own confidence fields before its findings.** They are the first thing in
the JSON for a reason:

| Field | Believe the findings when |
|---|---|
| `match_rate`, `pairing_confidence` | rate is high and confidence is not `medium`/`low` |
| `resolution_note` | it is absent — its presence means the tolerance was widened to uselessness |
| `systematic_*_ratio` | it is near 1.0; far from 1.0 means **one** root cause, not N findings |

**Typography cannot be measured off a 1× mobile frame.** A 390pt Figma frame exports at
~390px, where body text is 9–13px tall — below what an x-height measurement can resolve to
a font-size step, and `get_screenshot` will not upscale past the frame's natural size. On a
real run the audit said so itself (`resolution_note`) and then flagged 12 of 15 bands.

**A substituted font flags nearly every band, in the same direction.** The design is drawn
in one typeface; a Compose preview renders in the platform default unless the font is
bundled and set. That showed up as `systematic_weight_ratio 1.21` with "stroke weight
renders heavier" on band after band. One cause, zero code defects.

So: **establish type parity at the IR stage, not the pixel stage.** The IR carries each text
node's exact size and weight from `get_design_context`, and `resolve_tokens.py` already
refuses to match a style whose weight differs — a 16sp regular never resolves to a 16sp
semibold. That comparison is exact, costs nothing, and does not care what font the preview
picked. Use the pixel typography audit only as a sanity check, and only when its own
confidence fields say it resolved anything.

## 4 · Material check — mandatory, and no script does it

**A clean geometry audit is not a passing grade.** Spacing, size and text can all measure
within band while the screen still looks obviously wrong to anyone who opens it, because
what makes a design look like itself is mostly *material*: glow, shadow, font identity,
thin accents, gradients. None of that is instrumented here.

This is not hypothetical. A real run scored `systematic gap ratio 0.962`, 100% structural
match and exact Vietnamese copy — and was reported as strong. The person who looked at it
said "khác nhiều quá" in one glance, and they were right: every neon glow was missing, the
font was Roboto instead of Inter, and a 3dp accent bar on twelve cards rendered at zero
height. The numbers had no opinion about any of it.

So before declaring a screen done, **crop and magnify 3–4× and compare these by eye**, one
element at a time:

| Check | The failure it catches |
|---|---|
| **Shadows and glows** | `Modifier.shadow()` draws a **black** shadow. On a dark UI it is invisible. A design with `rgba(0,219,130,0.35)` glows needs `ambientColor`/`spotColor` (API 28+) or a custom blur — elevation alone renders nothing |
| **Font identity** | The design names a family (`Inter`, `SF Pro`). `FontFamily.SansSerif` is Roboto. Every glyph differs in width and cap height even when the sp value is right — and the typography audit's `systematic_weight_ratio` will blame it on weight |
| **Thin accents** | A 3dp bar is 3px at 1× and vanishes in a scaled-down comparison. Check it by sampling pixels at its expected x, not by looking at a full-screen pair |
| **Gradients** | A flat fill where the design has a gradient reads as "wrong colour", and a colour audit that samples one pixel will not notice |
| **Corner radii** | Off-by-8dp on a card is obvious to a designer and invisible to every band measurement |

Sampling pixels is the reliable way to settle a thin accent:

```python
# design vs device at the accent's expected column
design.getpixel((20, 370))   # (0, 220, 130) — the bar is there
device.getpixel((20, 370))   # (26, 29, 34)  — card surface; the bar is not
```

That one comparison found a `fillMaxHeight()` inside a `LazyColumn` resolving to zero
height — a defect no ratio in this pipeline would ever have surfaced.

## 5 · Device run — once

```bash
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
# then drive to the screen and capture
```

This exists to catch what a JVM render cannot: real window insets, real system bars, real
data from the repository, navigation into and out of the screen, and dynamic text from the
actual locale. It is minutes per iteration, so it runs **once, after the fast loop has
converged** — never inside the repair loop.

If the project has `maestro-test-executor` available, drive and capture with it; its
hierarchy dump is also the only honest source for `text_audit.py`'s actual strings.

## What none of this proves

The measured checks cover spacing, element size, font size, font weight, text content, and
flat fills. They say nothing about: gradients and shadows, corner-radius correctness,
icon shape, image cropping, z-order, press/ripple states, animation, or whether a control
is actually tappable. Those stay with a human looking at the pair composite, and with
functional tests.

A clean audit is not "the screen is correct". It is "the instrumented properties are within
band". Saying which is which is what keeps a PASS worth anything.
