# Layout contract

A Figma frame is **one width, one font scale, one string of one length**. Code generated to
match it exactly will match it exactly — and break the moment any of those three changes,
which is not an edge case but Tuesday: a longer filename, a user at 1.3× text, a 411dp
device instead of a 390dp frame.

These rules close that gap. They are enforced by `scripts/layout_rules_check.py`, which
**exits 1** — unlike the token and literal checks, which deliberately only report. The
difference is that those are judgement calls about a codebase, and these are correctness.

## The dimension ladder

Pick the **highest** rung that works. Rung 4 is a last resort, not a default.

```
1. No dimension modifier at all          ← the default; content measures itself
2. heightIn / widthIn / sizeIn(min = …)  ← when a minimum matters
3. aspectRatio · fillMaxWidth · weight   ← when the dimension comes from the parent
4. height / width / size(NamedVal)       ← ONLY a geometric box with no text in it
```

**Anything containing text uses rung 2, never rung 4.** A design's "54dp tall button"
becomes `heightIn(min = 54.dp)`: identical at font scale 1.0, and it grows instead of
clipping when the label wraps or the locale is German.

Rung 4 stays legitimate for icons, dividers, accent bars, thumbnail boxes, skeletons — real
geometry with no text beneath it. That is why the gate needs no exemption comment: the rule
is narrow enough that correct code passes untouched. **If something legitimate trips a rule,
the rule is wrong and gets fixed** — exemption comments are how a gate quietly stops meaning
anything.

Width deserves its own warning. A `width(350.dp)` that matches a 390dp frame is 350dp on a
411dp device where it should be 371dp. Card and container widths come from
`fillMaxWidth()` and padding, never from the design's measured number.

## Every Text declares what happens when it doesn't fit

`maxLines` **and** `overflow`, on every `Text`. No exceptions.

```kotlin
Text(
    text = output.fileName,
    maxLines = 1,
    overflow = TextOverflow.Ellipsis,
)
```

`maxLines = 1` without `overflow` clips mid-glyph with no ellipsis: the string is truncated
and nothing tells the reader it was. That is the most common form of this defect, and it
measured 9 occurrences in a freshly generated screen.

The design cannot answer this question. It drew one string. Whether a long one should
ellipsise, wrap to two lines, or shrink the type is a **product decision**, and it must
surface rather than be chosen silently — see *Decisions* below.

## Every Text declares its own colour

A `Text` with no `color` argument is a raw-value decision made silently, exactly like a bare
hex literal — except the token/literal checks only report, and this one renders invisible.

```kotlin
// WRONG — real code from a generated screen, PairPulse's theme is a different product's
Text(
    text = stringResource(R.string.connect_title),
    style = LocalAppTypography.current.headingH3,
    maxLines = 1,
    overflow = TextOverflow.Ellipsis,
)

// RIGHT — the design's #141414 resolved to a token and passed explicitly
Text(
    text = stringResource(R.string.connect_title),
    style = LocalAppTypography.current.headingH3,
    color = PairPulseTextPrimary,
    maxLines = 1,
    overflow = TextOverflow.Ellipsis,
)
```

With no `color`, the `Text` falls back to whatever `LocalContentColor` the surrounding theme
happens to provide. On a real run this rendered a `#141414` title as pale grey on a pink
background, and rendered a card's own body copy white-on-white — both on a device, both past
a gate that reported every file clean, because nothing was checking for an *absent* value.

**What this rule can and cannot prove.** `androidx.compose.ui.text.TextStyle` has its own
`color` field, so `style = someToken` legitimately carrying a baked-in colour is a real
pattern, not a hypothetical. This checker has no cross-file resolution — it never opens the
file that defines `LocalAppTypography` or any other token — so whether `headingH3` bakes in a
colour is **not statically provable** from the Kotlin source under analysis. Rather than
guess silently, it picks the defensible side: a `style =` that is a *property access*
(`LocalAppTypography.current.headingH3`, any other design-token reference) is treated as not
providing a colour, and the rule fires unless `color =` is also present. The one case it
can verify is an **inline** `style = TextStyle(…, color = …, …)` literal, because the colour
argument is sitting right there in the same call — that passes without a separate `color =`.

If your design system's typography tokens really do bake in colour per variant, this will
over-fire on code that is actually correct. The fix is still to pass `color =` explicitly at
the call site — redundant in that case, but explicit and provably correct — not to carve out
an exemption. A duplicated colour argument costs nothing at runtime; a silently inherited one
costs a pale-grey heading on a pink background.

Does not fire on `Icon(` or `Image(` — they take `tint`, not a text colour, and are a
different rule's concern (see *Images keep the design's ratio* below).

## Rows: exactly one child may shrink

The `<icon> text <icon>` row is where Compose layouts fail most reliably. A `Row` gives each
child its intrinsic width in order; a long string takes everything it asks for and the
trailing icon is simply pushed past the edge. Nothing clips, nothing warns.

```kotlin
// WRONG — a long name pushes the chevron off screen
Row {
    Icon(painterResource(R.drawable.file), null, Modifier.size(IconSize))
    Text(output.fileName, maxLines = 1, overflow = TextOverflow.Ellipsis)
    Icon(painterResource(R.drawable.chevron), null, Modifier.size(IconSize))
}

// RIGHT — the text is the one that gives way
Row(verticalAlignment = Alignment.CenterVertically) {
    Icon(painterResource(R.drawable.file), null, Modifier.size(IconSize))
    Text(
        output.fileName,
        modifier = Modifier.weight(1f),
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
    Icon(painterResource(R.drawable.chevron), null, Modifier.size(IconSize))
}
```

The rules:

- **Exactly one child takes `weight(1f)`** — the one allowed to shrink, normally the text.
- **Icons never take weight.** They keep their intrinsic size; that is the point of them.
- **Two texts that can both grow** need explicit weights summing to the space, and which one
  wins is a decision, not a default.

A real generated screen contained this, and it is exactly the shape above:

```kotlin
Row {                                   // ← no weight anywhere
    Text(originalSize, maxLines = 1)    // ← no overflow either
    Image(arrowRight, Modifier.size(12.dp))
    Text(outputSize, maxLines = 1)
}
```

A size string of `"1234.56 MB"` pushes the arrow and the second value out of the row.

## Self-painted rows hug their label, they don't stretch to it

R3 counts weighted children; it has no idea *which* child is correct to shrink. A `Row` that
clips itself and paints its own `background()` isn't a generic layout slot — it's drawn as a
button, pill, or chip, and a button hugs its label. Giving that label `weight(1f)` is still
exactly one weighted child, so R3 is satisfied, but `weight()` forces the `Row` to claim the
full width its parent offers regardless of what the `Row`'s own modifiers say. A ~160dp
hug-content pill becomes an edge-to-edge bar.

```kotlin
// WRONG — real code from ConnectEmptyState; this pill filled the screen width
Row(
    modifier = Modifier
        .padding(top = AppSpacing.space16)
        .clip(AppShapes.pill)
        .background(PairPulseBrandPink.copy(alpha = 0.2f))
        .clickable(onClick = onExplore)
        .padding(horizontal = AppSpacing.space16, vertical = AppSpacing.space12),
) {
    Text(
        text = stringResource(R.string.connect_explore_topics),
        modifier = Modifier.weight(1f),
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
    Image(painterResource(R.drawable.connect_arrow), contentDescription = null)
}

// RIGHT — no weight anywhere; the Row hugs the label, the pill measures ~160dp
Row(
    modifier = Modifier
        .padding(top = AppSpacing.space16)
        .clip(AppShapes.pill)
        .background(PairPulseBrandPink.copy(alpha = 0.2f))
        .clickable(onClick = onExplore)
        .padding(horizontal = AppSpacing.space16, vertical = AppSpacing.space12),
) {
    Text(
        text = stringResource(R.string.connect_explore_topics),
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
    )
    Image(painterResource(R.drawable.connect_arrow), contentDescription = null)
}
```

The rule: a `Row` whose own modifier chain contains both `.clip(` and `.background(`, and
*none* of `.fillMaxWidth()` / `.fillMaxSize()` / `.width(` — i.e. it never itself claims a
width — may not hand `weight()` to a direct `Text` child. `weight()` on a *container* child
(a `Box`, a `Column`) is unaffected; that is the correct shape for a progress bar that should
shrink while a `"72%"` label beside it keeps its intrinsic width.

**R3 and R6 on the same Row.** For exactly this shape, R3's fix ("give the text `weight(1f)`")
and R6's fix ("don't") are opposites. R3 therefore skips any Row that matches R6's
self-painted/no-own-width signature — R6 is the rule that governs it. If a Row of this shape
*is* meant to run edge-to-edge, say so on the Row itself with `fillMaxWidth()`: that both
satisfies R6 (the Row now honestly claims its own width) and hands the Row back to R3, which
will then correctly ask for `weight()` on the text to protect the trailing icon from a long
string.

**What this rule can and cannot prove.** Whether a given `Row` is *supposed* to hug its
content or fill its parent is a decision recorded in the Figma frame's own sizing mode — this
checker reads neither the IR nor any tag, by design, so it cannot see that decision. What it
*can* see is a contradiction: a Row that paints itself as a self-contained control, never
claims a width of its own, and then reaches for `weight()` on a label anyway — `weight()`
being the one modifier that silently overrides "never claimed a width" with "fills it after
all." That contradiction, not "this Row is the wrong size," is the enforceable signal, and it
is narrow on purpose: a full-width button that legitimately wants its label pinned to one
side and an icon to the other (`fillMaxWidth()` **and** `weight()` on the label) is excluded,
because the Row's own modifiers already say honestly what it's doing.

## Images keep the design's ratio

The IR carries every node's `rect`, so the ratio is known. Carry it:

```kotlin
Image(
    painter = …,
    contentDescription = …,
    modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f),
    contentScale = ContentScale.Crop,
)
```

Never pin both width and height from the design's numbers — that is rung 4 applied to
something whose size depends on the screen.

**Square icons are not this case.** `Image(painterResource(...), modifier = Modifier.size(24.dp))`
pins a square box, and Compose's default `ContentScale.Fit` keeps the artwork's ratio inside
it. That is how icon drawables are drawn and it is correct. The rule fires only on an image
poured into a box of a different shape with no instruction, where it silently stretches.

Which `ContentScale` is a decision: `Crop` fills and trims the edges, `Fit` letterboxes.
The design shows one framing of one asset and cannot tell you which it meant.

## No Figma in comments or KDoc

**R7.** Generated Kotlin names neither Figma, a node id, a frame name, nor the design file —
in any `//`, `/* */` or KDoc.

```kotlin
/** The screen's own bottom navigation (figma 5:8501 "Nav Bar"). */   // ✗ R7
/** Bottom navigation for the Connect screen. Taps are inert. */      // ✓

.background(Color(0xFF00DC82))   // figma 17:34 — no matching token   // ✗ R7
.background(Color(0xFF00DC82))                                        // ✓

Modifier.figmaNode("5:8501")     // ✓ — code, not a comment; layout_assert.py reads it
```

An earlier version of this skill required the opposite and called the marker comment "the
whole point". That was wrong. Traceability belongs somewhere a script checks, and it already
has two such places:

| Where | What it holds | Who reads it |
|---|---|---|
| `Modifier.figmaNode("5:8501")` | the node a composable came from | `layout_assert.py`, at runtime |
| `ir/mapping-report.json` | every raw value, its node, why it stayed raw | review, the PR description |

A comment is checked by nobody. It is therefore the one copy that silently rots when the
design moves on, and the one copy every future reader of `features/connect/` has to scroll
past while debugging an app they are not importing. KDoc is for what the composable does and
what a caller must know.

**What the rule matches**, deliberately narrowly: the word `figma`; `node-5_8501`; and a node
id whose second component is three or more digits (`5:8501`, `I5:7853;19:1891`). An aspect
ratio (`16:9`), a clock (`10:30`) or a version (`2:1`) in ordinary prose does not trip it.

## Decisions: ask the risky ones, default the rest

Several of these choices are **undecidable from the design**. The rule for handling them
reuses the chrome/content split already in `generation.md`:

| | Source | Handling |
|---|---|---|
| **Safe — chrome** | a fixed string the design drew (`"NÉN & CHUYỂN ĐỔI"`, tool labels, headings) | choose the default, record it. The length is known |
| **Risky — content** | bound to state, length unknown (file names, sizes, dates, counts) | **stop and ask** when the default could hide something the reader needs |

"Could hide something" is the test, and it is concrete: a filename ellipsised to
`"VID_2026092…"` makes two files indistinguishable; a truncated size or price removes the
number the row exists to show. A section heading clipping does not — the user already knows
what the section is.

Defaults, when the choice is safe:

| Element | Default |
|---|---|
| Text in a Row beside anything else | `weight(1f)`, `maxLines = 1`, `overflow = Ellipsis` |
| Standalone body text | `maxLines = 2`, `overflow = Ellipsis` |
| Headings | `maxLines = 1`, `overflow = Ellipsis` |
| Image into a non-square box | `aspectRatio` from the design's rect, `ContentScale.Crop` |

### `decisions.md`

Every undecidable choice goes in the work dir, whether asked or defaulted:

```markdown
| Node | Element | Question | Chose | Why | Needs sign-off |
|---|---|---|---|---|---|
| 20:49 | item-name-1 | long filename: ellipsise or wrap? | maxLines 1 + Ellipsis | row height is fixed in the design | **yes** — two files can look identical |
| 17:37 | sec-title | heading overflow | maxLines 1 + Ellipsis | known copy, 14 chars | no |
| 20:47 | thumb-1 | Crop or Fit | Crop | design shows a filled 50×50 tile | no |
```

The `Needs sign-off` column is what the reader scans. A report with none is a report that
made no risky choices — or missed them.

## Running the gate

```bash
python3 scripts/layout_rules_check.py --files <generated .kt files>
```

| Rule | Fails when |
|---|---|
| **R1** | a fixed `height`/`width`/`size` on a node whose subtree contains text |
| **R2** | a `Text` missing `maxLines` or `overflow` |
| **R3** | a `Row` with text and ≥2 children where no child takes `weight` (skips rows R6 governs) |
| **R4** | an `Image` filling a non-square box with no `aspectRatio` or `ContentScale` |
| **R5** | a `Text` with no `color =` and no colour provable from an inline `TextStyle(color = …)` |
| **R6** | a self-painted `Row` (`.clip(` + `.background(`, no own `fillMaxWidth`/`fillMaxSize`/`width`) that hands `weight()` to a `Text` child |
| **R7** | a comment or KDoc naming Figma, a node id, a frame name, or the design file |

`--warn-only` exists for migrating an existing screen that predates the contract. It is not
for new code.
