# Phase 3 — Generating Compose

Input: a token-resolved `screen.ui.json` with an empty (or human-cleared) `unmapped[]`.
Output: Kotlin that a reviewer would have written.

## Order of preference for every node

1. **A composable named in `mapping.component`** — use it, pass its props.
2. **A composable in the adapter that fits but wasn't auto-matched** — use it, and add the
   hint to the adapter so the next run matches it.
3. **A layout primitive** (`Column`/`Row`/`Box`) with modifiers.
4. **A new private composable in this file** — when the same shape repeats 3+ times in the
   screen, or when nothing in the project fits.

With no adapter, every node lands on 3 or 4, and that is a perfectly good outcome: the
result is idiomatic Compose that happens not to reuse anything, which is exactly right for
a project with no design system to reuse.

With an adapter, step 4 is the one to look twice at. A generated `ToolTile` sitting beside
an existing `ComposerCard` that does the same job is the most common thing a reviewer sends
back — so before writing a new composable, check the adapter's component list for the shape
you are about to build.

## Before you generate: check where the content actually is

Run `ir_coverage_check.py` and read its `tree N + sourceContext M` lines. If the tree's
share is small, the screen is built from component instances and the tree is a geometric
skeleton — the per-instance colours, icons and labels are in `sourceContext`, flat and keyed
by node id. Generating from the tree alone yields eleven identical cards where the design
has eleven tinted ones. `references/ui-ir-schema.md` explains how to rebuild the grouping.

## Comments and KDoc carry no Figma

**Nothing in the generated Kotlin may mention Figma, a node id, a frame name, or the design
file.** Not in `//`, not in `/* */`, not in KDoc. This is gated; see rule R7 in
`references/layout-contract.md`.

```kotlin
/** The screen's own bottom navigation (figma 5:8501 "Nav Bar"). */   // ✗
/** Bottom navigation for the Connect screen. Taps are inert. */      // ✓

.background(Color(0xFF00DC82))   // figma 17:34 — no matching token   // ✗
.background(Color(0xFF00DC82))                                        // ✓
```

An earlier version of this skill required the opposite — every raw value carried a marker
comment naming its node, and that was called "the whole point". It was wrong, for a reason
worth stating because it generalises.

**Traceability belongs in machine-readable places, and it already has two.**

| Where | What it holds | Who reads it |
|---|---|---|
| `Modifier.figmaNode("5:8501")` | the node a composable came from | `layout_assert.py`, at runtime |
| `ir/mapping-report.json` | every raw value, its node, why it stayed raw | review, the PR description |

Both are checked. A comment is checked by nobody, so it is the one copy that silently rots
when the design moves on — and it is the copy a reader has to scroll past on every line.
Reviewers get the same information from the mapping report, with better fidelity, without
the code carrying build-pipeline residue.

KDoc exists to say what a composable **does** and what a caller must know. A reader of
`features/connect/` is debugging an app, not auditing a design import. Write documentation
for them.

## Values: token when there is one, raw when there isn't

When the IR node carries a resolved `token`, use it:

| Raw | Emitted |
|---|---|
| `padding: 16` → `spacing.md` | `padding(composerTokens.spacing.md)` |
| `fill: #17141D` → `colorScheme.primary` | `MaterialTheme.colorScheme.primary` |
| `size 16 / weight 600` → `typography.titleMedium` | `style = MaterialTheme.typography.titleMedium` |
| `radius: 22` → `radii.card` | `RoundedCornerShape(composerTokens.radii.card)` |

When `token` is `null` — no adapter, or nothing matched — emit the raw value plainly:

```kotlin
.background(Color(0xFF00DC82))
.padding(horizontal = 20.dp)
```

Prefer a named file-local val (`private val CardRadius = 16.dp`) over a bare literal where
the project's conventions ask for one — that is readability, not traceability.

The question a reviewer needs to ask is still *should this be a token, or is this screen
genuinely off-palette?* `ir/mapping-report.json` hands them that question with every node id
attached, and `compose_quality_gate.py` counts what stayed raw. Neither needs the code to
carry the evidence inline.

Never invent a token name that does not exist in the project.

## Tag every generated composable with its Figma node

A composable that came from an IR node carries that node's id, so verification can compare
it to the design directly instead of guessing its boundary from pixels:

```kotlin
ToolCard(
    modifier = Modifier
        .figmaNode("17:39")
        .fillMaxWidth(),
)
```

**The tag must not ship.** `figmaNode` is a project-local helper that compiles to nothing
unless a layout audit is running — see `references/pixel-fidelity.md` for the two-file
pattern. Never leave a bare `testTag` in production composables for this purpose.

A node you cannot tag — text inside a design-system component, a shape drawn in a `Canvas` —
is **unverified, not passing**. `layout_assert.py` reports that count, and a screen where
half the nodes are untagged has not been checked.

## Strings: chrome goes to resources, sample content goes to state

Two kinds of text live in a Figma frame and they must not be treated the same way.

**Chrome** — labels, headings, CTAs, empty-state copy, tab names. Fixed text the app always
shows. These go to `res/values/strings.xml` and the Figma copy is the source of truth:

```kotlin
Text(stringResource(R.string.home_primary_action))     // "NÉN VIDEO NGAY"
```

**Sample content** — file names, sizes, dates, counts, percentages, avatars, thumbnails.
The designer typed `VID_20260928_compressed.mp4` and `12.9 MB` to show what the row *looks
like*, not to specify what it says. This is the single most damaging mistake this pipeline
can make:

```kotlin
// WRONG — the mock's data is now shipped to every user, forever
<string name="home_recent_video">VID_20260928_compressed.mp4</string>
private val designRecentOutputs = listOf(RecentOutput(R.string.home_recent_video, …), …)
designRecentOutputs.forEach { RecentOutputRow(it) }

// RIGHT — the design specifies the row; the state specifies what is in it
state.recentOutputs.forEach { RecentOutputRow(it) }
if (state.recentOutputs.isEmpty()) EmptyRecentOutputs()
```

It compiles, it renders pixel-identical to the frame, it passes every measurement in Phase
4 — and the shipped app shows three files the user does not have. No visual check can catch
it, because looking right is exactly the symptom.

**The test:** could this string ever differ between two users? If yes, it is content and it
comes from state. A repeated row in the design is a **list of one composable**, never N
hardcoded copies.

When the current UI state cannot supply the content, do not invent a source. Add the field
to the state class, leave a plain `// TODO: needs <field> from the ViewModel` (no node id —
R7), name the design node **in the report**, render
the empty state, and say so in the report. An unwired list is an honest gap; a hardcoded one
is a bug that ships.

## Structure

- **Screen-level composable is `internal`,** takes a UI state and lambdas, no ViewModel.
  The existing `HomeScreen(state, onChooseTool, ...)` shape is the contract — match the
  project's, don't introduce a second.
- **Private composables per section**, named after the Figma layer (`StatsHero`,
  `ToolSection`, `RecentOutputs`). A reviewer with the Figma open should find each layer
  name in the file.
- **Data-shaped repetition goes through a list**, not copy-paste. Six tool tiles in the
  design become one `toolCards` list and one `ToolTile`, the way the existing file already
  does it.
- **No new ViewModel/repository/navigation code.** If the design needs data the current
  state doesn't carry, add the field to the UI state and leave a `TODO` with the node id —
  wiring it is a separate task with separate review.

## Layout translation

| IR | Compose |
|---|---|
| `direction: column`, `gap` | `Column(verticalArrangement = Arrangement.spacedBy(token))` |
| `direction: row`, `gap` | `Row(horizontalArrangement = Arrangement.spacedBy(token))` |
| `direction: stack` | `Box` with `Modifier.align` per child |
| `width: fill` | `Modifier.fillMaxWidth()` |
| `width: wrap` | nothing (default) |
| `width: <n>` | `Modifier.width(n.dp)` — **suspicious**; prefer `weight` or `fillMaxWidth` |
| fixed-column grid | `FlowRow` with computed width, or `LazyVerticalGrid` if scrollable |

A fixed pixel width in the output is almost always the design's frame width leaking into
the code. A 350dp-wide card inside a 390dp frame is `fillMaxWidth()` with 20dp horizontal
padding — not `width(350.dp)`. The extractor cannot know this; the generator must.

## Material: the parts Compose gets wrong by default

Three things translate badly from Figma to Compose and cost more visual fidelity than any
spacing error. Handle them explicitly or the screen will measure correct and look wrong.

**Shadows are black unless you say otherwise.** `Modifier.shadow(8.dp, shape)` draws a
black shadow — invisible on a dark surface. A design with a coloured glow
(`0px 4px 6px rgba(0,219,130,0.35)`) needs the colour passed:

```kotlin
.shadow(
    elevation = 6.dp,
    shape = AppShapes.radius16,
    clip = false,
    ambientColor = AccentGlow,   // the design's shadow colour
    spotColor = AccentGlow,
)
```

`ambientColor`/`spotColor` need API 28+; below that, elevation renders black and the glow
has to be drawn (a blurred layer, or a border with the accent at low alpha). Say which you
did in the report — a neon UI with no glow is the single most visible way this pipeline
fails.

**The font is part of the design.** Figma names it (`Inter:Semi_Bold`). `FontFamily.SansSerif`
is Roboto, and every glyph then differs in width and cap height even when every `sp` value
is correct. Bundle the family in `res/font/` and set it on the type scale; if the family is
not available, **say so in the report** rather than substituting silently — it will
otherwise be misdiagnosed later as a font-weight bug.

**`fillMaxHeight()` resolves to zero in a scrollable.** A full-height accent bar written as
a `Box` child inside a `LazyColumn` item gets an unbounded height constraint and renders at
0px — the code looks right, compiles, and draws nothing:

```kotlin
// WRONG inside a LazyColumn item — unbounded height, bar disappears
Box(Modifier.align(Alignment.CenterStart).width(3.dp).fillMaxHeight().background(accent))

// RIGHT — takes the parent Box's measured size
Box(Modifier.matchParentSize().wrapContentWidth(Alignment.Start).width(3.dp).background(accent))
```

`matchParentSize()`, or a `Row` with `Modifier.height(IntrinsicSize.Min)`, both work.

## Layout contract — enforced, read `layout-contract.md` before writing a screen

Four rules, checked by `scripts/layout_rules_check.py`, which **exits 1**. They exist because
the frame is one width, one font scale, one string length, and the code has to survive all
three changing.

1. **No fixed dimension around text.** `heightIn(min = 54.dp)`, never `height(54.dp)`, on
   anything containing a `Text`. Fixed sizes stay legal for icons, dividers, accent bars.
2. **Every `Text` declares `maxLines` and `overflow`.** `maxLines = 1` alone clips mid-glyph
   with no ellipsis — the string is truncated and nothing says so.
3. **Exactly one child in a `Row` takes `weight(1f)`.** Without it a long string pushes the
   trailing icon off screen; nothing clips and nothing warns.
4. **Images carry the design's ratio** via `aspectRatio` + an explicit `ContentScale`.

The two that are wrong most often, side by side:

```kotlin
// WRONG — long name pushes the chevron past the edge, and clips with no ellipsis
Row {
    Icon(fileIcon, null, Modifier.size(IconSize))
    Text(output.fileName, maxLines = 1)
    Icon(chevron, null, Modifier.size(IconSize))
}

// RIGHT — the text is the one that gives way
Row(verticalAlignment = Alignment.CenterVertically) {
    Icon(fileIcon, null, Modifier.size(IconSize))
    Text(output.fileName, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
    Icon(chevron, null, Modifier.size(IconSize))
}
```

Several of these choices — how many lines, ellipsise or wrap, `Crop` or `Fit` — the design
**cannot answer**: it drew one string of one length. Ask about the ones where a default could
hide something the reader needs (a filename, a size, a price); default the rest and record
every one of them in `decisions.md`. The split and the defaults are in `layout-contract.md`.

## Responsiveness is not in the design

The Figma frame is one width. The code runs on many. Carry over the project's existing
adaptive behaviour rather than freezing the mock:

- text scaling — the project already branches on `LocalDensity.current.fontScale`
- width breakpoints — `BoxWithConstraints`, `widthIn(max = composerTokens.wideContentWidth)`
- long strings — `maxLines` + `TextOverflow.Ellipsis` on anything user-generated

A screen that matches the frame exactly at 390dp and breaks at 320dp or at 1.3× font scale
has not been ported, it has been traced.

## Accessibility

Carried over from the existing code, not invented: `contentDescription` on every
actionable icon, `semantics { heading() }` on section titles, `Modifier.size` on touch
targets at or above `composerTokens.touchTarget`. Icons that are purely decorative take
`contentDescription = null` — and a 52dp icon tile beside its own label is decorative.
