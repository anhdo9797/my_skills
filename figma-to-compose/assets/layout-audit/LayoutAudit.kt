// TEMPLATE — copy into the target project's MAIN source set and fill in the package line.
// See ../README.md for exactly where this goes and why it lives in `main`, not `androidTest`.
package com.example.app.layoutaudit // TODO: project package, e.g. <app>.core.ui.layoutaudit

import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.layout.onGloballyPositioned

/**
 * Figma-to-Compose layout-audit instrumentation.
 *
 * Opt-in only. With [LayoutAudit.ENABLED] false (the default, and the only state production
 * builds should ever ship), `figmaNode(id)` is a pure pass-through — it adds nothing to the
 * layout tree and costs nothing beyond one boolean read. Flip it to true only for an audit
 * run (see README for how to wire that without hand-editing this file).
 *
 * Call it on every composable generated from an IR node, same call site regardless of what
 * the design looks like:
 *
 *     ToolCard(modifier = Modifier.figmaNode("17:39").fillMaxWidth())
 *
 * `LayoutAuditDumpTest.kt` reads the recorded bounds back after `waitForIdle()` and writes
 * them in the exact shape `layout_assert.py` consumes:
 * `{"<figma-node-id>": {"x":.., "y":.., "w":.., "h":..}, ...}` in dp, root-relative.
 *
 * Why `onGloballyPositioned` and not a `testTag` read back through the semantics tree (the
 * sketch in references/pixel-fidelity.md): a `clickable`, `Row`, or other semantics-merging
 * parent can fold a tagged child's semantics node into its own and silently drop the tag from
 * `fetchSemanticsNode()`'s tree — a failure mode that produced exactly this skill's own bug
 * (a tagged node reads as untagged, reports as "unverified", and nobody notices because the
 * run still exits 0). `onGloballyPositioned` fires directly off the layout pass, with no
 * semantics tree in between, so there is nothing for a `clickable` to merge away. The call
 * site (`Modifier.figmaNode(id)`) is identical either way — this is an implementation choice,
 * not a different contract.
 */
object LayoutAudit {
    /**
     * Flip to true only for an audit run, then back to false before merging. Safer: don't hand
     * -edit this at all — gate it behind a Gradle flag instead (README, "Flipping ENABLED
     * without editing this file") so a forgotten `true` can never ship to production.
     */
    const val ENABLED: Boolean = false
}

/**
 * Associates this composable with the Figma node it was generated from. No-op unless
 * [LayoutAudit.ENABLED] is true — see the class doc above before wiring this into a screen.
 */
fun Modifier.figmaNode(id: String): Modifier =
    if (LayoutAudit.ENABLED) {
        this.onGloballyPositioned { coordinates: LayoutCoordinates ->
            LayoutAuditCollector.record(id, coordinates)
        }
    } else {
        this
    }
