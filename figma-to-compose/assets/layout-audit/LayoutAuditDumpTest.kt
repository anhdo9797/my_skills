// TEMPLATE — copy into the target project's ANDROIDTEST source set. Every `TODO(...)` marker
// must be resolved before this compiles; it is intentionally not drop-in runnable. See
// ../README.md, "Filling in the template", for what each marker needs and where the numbers
// (frame width, content height) come from.
package com.example.app.layoutaudit // TODO: a package visible to both this test and the screen under audit

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import java.io.File

/**
 * Renders TODO(SCREEN_NAME) at the Figma frame's dp width and dumps every `figmaNode`-tagged
 * composable's real bounds for `layout_assert.py` to compare against `ir/screen.ui.json`.
 *
 * Run it, then pull the dump:
 *
 *     ./gradlew :app:connectedDebugAndroidTest --tests '*LayoutAuditDumpTest'
 *     adb pull /sdcard/Download/TODO(OUTPUT_FILE) render/nodes.json
 *     python3 scripts/layout_assert.py --ir ir/screen.ui.json --actual render/nodes.json \
 *             --out audit/layout.json --tolerance 1.0
 *
 * If this test's own `check(LayoutAudit.ENABLED)` fails, nothing downstream ran — that is the
 * UNMEASURED case verification.md's verdict state machine describes, not a normal failure.
 */
class LayoutAuditDumpTest { // TODO: rename to match the screen, e.g. ConnectLayoutDumpTest

    @get:Rule
    val composeRule = createComposeRule()

    @Before
    fun resetCollector() {
        LayoutAuditCollector.clear()
    }

    @After
    fun cleanup() {
        LayoutAuditCollector.clear()
    }

    @Test
    fun dumpFigmaNodeRects() {
        check(LayoutAudit.ENABLED) {
            "LayoutAudit.ENABLED is false, so every figmaNode() call in the screen under test " +
                "was a no-op and this dump would be empty. Flip it for this run (README, " +
                "\"Flipping ENABLED\") rather than letting this test report a false pass."
        }

        composeRule.setContent {
            TODO_APP_THEME { // TODO: the project's root theme composable, e.g. AppTheme(darkTheme = true) { ... }
                // Width pinned to the Figma frame's dp width so the render and the IR share a
                // coordinate space (references/pixel-fidelity.md, "What pixel-perfect cannot
                // mean"). Height pinned to the IR root node's own rect.h plus ~15% headroom —
                // not left to wrap, and not left to the test device's real window height —
                // so a LazyColumn/LazyRow is given a viewport taller than all of its content
                // and composes every item on the first pass instead of only the first
                // screenful. Read FRAME_HEIGHT_DP off `ir/screen.ui.json`'s `root.rect.h`
                // for this screen; see README, "Sizing the forced Box" for why this works and
                // when it still isn't enough (nested lazy lists, pager content).
                Box(
                    modifier = Modifier
                        .width(TODO_FRAME_WIDTH_DP.dp)   // TODO: e.g. 390 — ir/screen.ui.json root.rect.w
                        .height(TODO_FRAME_HEIGHT_DP.dp), // TODO: e.g. 1170 — root.rect.h * ~1.15
                ) {
                    TODO_SCREEN_CONTENT(TODO_FIXTURE_ARGS) // TODO: the screen's content composable + the design's own fixture state
                }
            }
        }
        composeRule.waitForIdle()

        val rects = LayoutAuditCollector.snapshotDp(composeRule.density)
        check(rects.isNotEmpty()) {
            "LayoutAudit.ENABLED is true but zero nodes were recorded — no composable in the " +
                "tree under test called Modifier.figmaNode(id). Check the import and that the " +
                "right screen/fixture is being rendered above."
        }

        File("/sdcard/Download/TODO_OUTPUT_FILE").writeText(JSONObject(rects).toString())
        // TODO: e.g. "nodes-connect.json" — give each screen its own file so parallel audits
        // on different screens don't overwrite one another on the device.
    }
}
