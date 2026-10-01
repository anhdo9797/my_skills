# Pixel fidelity — measuring nodes instead of pixels

The default pipeline asks *"does this look about right?"* and answers with ink-band ratios.
This is the mode for when the answer has to be *"node 20:12 is 3dp narrower than the design
says"*.

## Read this first: the trade-off is real

**Token reuse and pixel fidelity pull in opposite directions.** Snapping 15dp to
`spacing.md`(16) is a deliberate 1dp loss, taken because one more spacing constant costs
more than one lost dp. A real run snapped **85** values. You cannot snap 85 times and be
pixel-perfect.

So pixel-perfect is a **declared mode, not the default**, and it has a precondition:
**`snappedCount` must be 0**, which means the project's theme has to carry the design's
actual values. `resolve_tokens.py --pixel-perfect` enforces this — in that mode a snap is
reported as fidelity lost, not as a resolution.

Choose it per screen. A marketing surface where the designer's exact rhythm *is* the
product earns it. An internal settings list does not.

## Why pixels can't answer the question

`spacing_audit.py` finds element boundaries by scanning for rows whose pixels differ from
the background. That has three failure modes no tuning fixes:

- **It measures ink, not elements.** A design row with a photo thumbnail and a rendered row
  with an icon produce bands 20dp apart with identical layout code. That exact false
  finding cost a repair iteration.
- **It cannot name the culprit.** "Band 7 is 0.73×" does not say which composable to edit.
- **Thin things are invisible.** A 3dp accent bar is 3 pixels at 1×. Twelve of them rendered
  at zero height and every ratio in the run stayed green.

## The method: ask Compose where things are

Compose knows the exact bounds of every composable. Tag each one with the Figma node it was
generated from, read the bounds back in a test, compare to the IR's `rect`. No pixels, no
ink profiles, no font noise — **dp against dp**.

```text
IR rect (design dp)  ─┐
                      ├─► layout_assert.py ─► per-node delta in dp
nodes.json (real dp) ─┘
```

### Three deltas, because they take three different fixes

| Delta | Meaning | Fix lives in |
|---|---|---|
| `size` | w/h differs from the design | a modifier on **this** node |
| `offset` | position within its own parent differs | the **parent's** padding or arrangement |
| `gap` | distance to the previous sibling differs | the parent's `spacedBy` |

**Absolute position is reported but never flagged.** It accumulates every ancestor's error,
so one wrong padding near the root makes a hundred healthy nodes look broken. Offset-within-
parent isolates the defect to the node that caused it.

**A node in the wrong place produces a gap finding on both sides of it.** That is one
defect, not two — move the node and both resolve. Fix in the order `size → offset → gap`,
because a wrong size moves everything after it.

## Tagging — opt-in, not permanent

Do **not** leave `testTag` in production composables. Add a project-local helper that
compiles away when no audit is running:

```kotlin
// core/ui/LayoutAudit.kt
object LayoutAudit {
    /** Flip to true (or wire to a build flag) only for a layout-audit run. */
    const val ENABLED = false
}

/** Associates a composable with the Figma node it was generated from. No-op unless auditing. */
fun Modifier.figmaNode(id: String): Modifier =
    if (LayoutAudit.ENABLED) testTag("figma:$id") else this
```

Then every composable generated from an IR node carries its id:

```kotlin
ToolCard(
    modifier = Modifier
        .figmaNode("17:39")
        .fillMaxWidth(),
)
```

With `ENABLED = false` no semantics node is added and nothing ships. With it true, the
audit test can see every node.

## Dumping the real rects

Build on the Compose test rule the project already uses — no new dependency:

```kotlin
class HomeLayoutDumpTest {
    @get:Rule val composeRule = createComposeRule()

    @Test
    fun dumpFigmaNodeRects() {
        composeRule.setContent {
            AppTheme(darkTheme = true) {
                HomeContent(state = DesignFixture.homeState)   // the design's own data
            }
        }
        composeRule.waitForIdle()

        val density = composeRule.density
        val rects = composeRule.onRoot().fetchSemanticsNode()
            .let { collect(it) }
            .mapNotNull { node ->
                val tag = node.config.getOrNull(SemanticsProperties.TestTag) ?: return@mapNotNull null
                if (!tag.startsWith("figma:")) return@mapNotNull null
                val b = node.boundsInRoot
                with(density) {
                    tag.removePrefix("figma:") to mapOf(
                        "x" to b.left.toDp().value,
                        "y" to b.top.toDp().value,
                        "w" to b.width.toDp().value,
                        "h" to b.height.toDp().value,
                    )
                }
            }.toMap()

        File("/sdcard/Download/nodes.json").writeText(JSONObject(rects).toString())
    }

    private fun collect(node: SemanticsNode): List<SemanticsNode> =
        listOf(node) + node.children.flatMap(::collect)
}
```

Three things that matter here:

- **Convert to dp.** `boundsInRoot` is in pixels; the IR is in design dp. Comparing them raw
  compares a 1440px device to a 390dp frame and every number is nonsense.
- **Use the design's own fixture data.** Empty state renders different sizes than populated
  state, and the design shows populated.
- **Render at the frame's dp width.** See the limits below.

Pull it off the device and compare:

```bash
adb pull /sdcard/Download/nodes.json render/nodes.json
python3 scripts/layout_assert.py --ir ir/screen.ui.json --actual render/nodes.json \
        --out audit/layout.json --tolerance 0.5 --strict
```

`--tolerance 1.0` is the default for a normal run; `0.5` for a pixel-perfect one. Nodes
present in the IR but missing from the dump are reported as **unverified, not passing** —
the script prints that count, and a screen where half the nodes are untagged has not been
checked.

## What pixel-perfect cannot mean

**The device is not the frame.** A Pixel 6 Pro is 411.4dp wide; the design frame is 390dp.
Nothing can be position-identical on both. So "pixel-perfect" means **pixel-perfect at the
design's width** — measure in a preview pinned to the frame's dp size
(`spec:width=390dp,height=1315dp,dpi=160`), and make everything else correct *by
construction* (`fillMaxWidth`, `weight`, padding) rather than by absolute number. A fixed
`width(350.dp)` that matches the design at 390dp is a bug at 411dp.

Check the two separately: layout assertion at the frame width, responsive behaviour at other
widths and font scales.

**Font metrics are not layout.** If the design is drawn in Inter and the app renders Roboto,
every text node's height differs regardless of `sp`. Bundle the family, or declare the
substitution in the report — otherwise it gets rediagnosed later as a weight bug.

**Effects are not measured here, by anything.** Glow, shadow, gradient, radius, icon shape:
`layout_assert.py` sees a correctly-sized box whether or not it has a neon glow around it.
That is the material check in `verification.md`, and it stays a human looking at a
magnified crop.
