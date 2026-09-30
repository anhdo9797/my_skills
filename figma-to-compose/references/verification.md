# Phase 4 — Verification

Three checks, cheapest first.

```text
1. Literal summary  static, ~1s     counts + delta vs git        (advisory)
2. Fast render      JVM, ~seconds   layout, spacing, typography  (the real check)
3. Device run       emulator, min   state, navigation, insets    ← once, at the end
```

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
literals, 12 colours, all marked with Figma node ids; reuses ComposerCard and IconTile;
declares StatsHero, ToolTile, RecentOutputRow." That is the input a reviewer needs to ask
the right question. Whether those numbers are acceptable depends on the codebase, and that
judgement belongs to whoever owns it.

A literal user-facing string is the one finding worth acting on without discussion — that is
a localisation bug, not a style preference.

## 2 · Fast render

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

### Measuring against Figma

Reuse the ratio contract already implemented in this repo. Read
`maestro-test-executor/references/ui-metrics.md` before judging any output.

```bash
M=../maestro-test-executor/scripts
python3 $M/spacing_audit.py    --design raw/design.png --actual render/home.png --out audit/spacing.json
python3 $M/typography_audit.py --design raw/design.png --actual render/home.png --out audit/type.json
python3 $M/text_audit.py       --expected ir/expected-strings.json --actual render/hierarchy.json --out audit/text.json
```

Read **the JSON before the images**. Numbers settle most of the verdict at a fraction of
the cost; open `pair_view.py` / `grid_overlay.py` composites only for what the numbers
flag.

The contract in one line: **text is exact, geometry is a ratio.** A gap reported as
`1.33× design` is actionable. "Looks a bit loose" is not, and neither is "3.2% of pixels
differ".

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

## 3 · Device run — once

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

## The material check — mandatory, and no script does it

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

## What none of this proves

The measured checks cover spacing, element size, font size, font weight, text content, and
flat fills. They say nothing about: gradients and shadows, corner-radius correctness,
icon shape, image cropping, z-order, press/ripple states, animation, or whether a control
is actually tappable. Those stay with a human looking at the pair composite, and with
functional tests.

A clean audit is not "the screen is correct". It is "the instrumented properties are within
band". Saying which is which is what keeps a PASS worth anything.
