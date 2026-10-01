// TEMPLATE — copy into the same MAIN source set and package as LayoutAudit.kt.
package com.example.app.layoutaudit // TODO: same package as LayoutAudit.kt

import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.unit.Density

/**
 * In-memory store of the real bounds `Modifier.figmaNode(id)` records during one composition.
 * Read back by `LayoutAuditDumpTest.kt` after `composeRule.waitForIdle()`, cleared before each
 * dump so a previous test's nodes never leak into the next one's output.
 *
 * Deliberately a flat map, not a tree: `layout_assert.py` reconstructs parent/sibling
 * relationships from the IR, not from this dump, so this side only needs node id -> rect.
 *
 * Not thread-safe beyond what a single Compose UI thread needs. If a future version of this
 * harness records from multiple composables concurrently (it doesn't today — Compose layout
 * and the `onGloballyPositioned` callbacks that drive this run on the UI thread), swap the
 * backing map for a `java.util.concurrent.ConcurrentHashMap` first.
 */
object LayoutAuditCollector {
    private val coordinates = mutableMapOf<String, LayoutCoordinates>()

    /** Called by `Modifier.figmaNode(id)` on every layout pass; last call for a given id wins. */
    fun record(id: String, layoutCoordinates: LayoutCoordinates) {
        coordinates[id] = layoutCoordinates
    }

    /** Call before setting content for a fresh dump — see LayoutAuditDumpTest.kt's @Before. */
    fun clear() {
        coordinates.clear()
    }

    /**
     * node id -> {x, y, w, h} in dp, relative to the Compose root — the exact shape
     * `layout_assert.py --actual` expects. Coordinates are read from `positionInRoot()` /
     * `size`, not `boundsInWindow()`: root-relative is what makes this comparable to the IR's
     * `rect`, which is itself relative to the design frame's own origin, not to a device window.
     *
     * Skips any node whose `LayoutCoordinates` detached before this ran (e.g. scrolled out and
     * disposed) rather than writing a stale or zeroed rect — a missing id is reported
     * correctly by `layout_assert.py` as untagged, which is honest; a zeroed one would read as
     * a real (and catastrophic) size/offset finding.
     */
    fun snapshotDp(density: Density): Map<String, Map<String, Float>> = with(density) {
        coordinates
            .filterValues { it.isAttached }
            .mapValues { (_, c) ->
                val pos = c.positionInRoot()
                val size = c.size
                mapOf(
                    "x" to pos.x.toDp().value,
                    "y" to pos.y.toDp().value,
                    "w" to size.width.toDp().value,
                    "h" to size.height.toDp().value,
                )
            }
    }
}
