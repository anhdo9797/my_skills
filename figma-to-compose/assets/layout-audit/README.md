# Layout-audit instrumentation — what to copy, and where

Three Kotlin templates. They exist because a real run of this skill produced a screen with a
section title rendered at near-zero contrast, topic cards ~3x the design's height, and a
button stretched full width instead of hugging its content — and `layout_assert.py`, the
check the skill calls its primary measurement, never ran, because the tagging helper and test
harness it depends on are not things a fresh Compose project has. Every other gate went green
and the run reported success. These three files are the fix: ship the instrumentation with
the skill instead of assuming the target project already has it.

| File | Goes in | Why |
|---|---|---|
| `LayoutAudit.kt` | **main** source set | `Modifier.figmaNode(id)` is called from the generated screen composables themselves — `androidTest` code is not visible to `main` |
| `LayoutAuditCollector.kt` | **main** source set, same package | Holds what `figmaNode()` records; the dump test reads it after rendering |
| `LayoutAuditDumpTest.kt` | **androidTest** source set | The harness that renders one screen at the frame's dp size and writes the dump `layout_assert.py` reads |

A plausible destination in a typical module layout:

```
app/src/main/kotlin/<pkg>/layoutaudit/LayoutAudit.kt
app/src/main/kotlin/<pkg>/layoutaudit/LayoutAuditCollector.kt
app/src/androidTest/kotlin/<pkg>/layoutaudit/<Screen>LayoutDumpTest.kt   (one copy per screen)
```

Put `LayoutAudit.kt` and `LayoutAuditCollector.kt` once per project (they are not
screen-specific); copy `LayoutAuditDumpTest.kt` once per screen you audit, renamed, filled in.

## Dependencies this assumes

A Compose project that already renders previews or runs any Compose UI test has all of this.
Listed for the case it doesn't:

```kotlin
// app/build.gradle.kts
dependencies {
    androidTestImplementation("androidx.compose.ui:ui-test-junit4:<compose-bom-version>")
    debugImplementation("androidx.compose.ui:ui-test-manifest:<compose-bom-version>")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
}
```

- `ui-test-manifest` supplies the empty host activity `createComposeRule()` launches content
  into. Without it, `createComposeRule()` fails at runtime with a clear error naming the
  missing manifest — not a silent failure, but worth having present up front.
- `org.json.JSONObject` is used for the dump write because it ships with Android itself — no
  serialization library dependency to add.

**AGP / Compose version assumption.** Every API used here — `createComposeRule()`,
`Modifier.onGloballyPositioned`, `LayoutCoordinates.positionInRoot()`, `composeRule.density`,
the `ui-test-manifest` artifact — has been stable and unchanged since Compose UI 1.0 (2021).
Nothing here needs a specific AGP version; `references/generation.md` and `verification.md`
elsewhere in this skill assume AGP 8.5+ for the unrelated `screenshotTest` source set, but
this instrumented-test path works on any AGP old enough to run `connectedAndroidTest` at all.
**Not verified by compiling** — see "What's unverified" at the bottom.

## Filling in the template

`LayoutAudit.kt` and `LayoutAuditCollector.kt` need only a package line. `LayoutAuditDumpTest.kt`
has six `TODO` markers:

| Marker | Fill with |
|---|---|
| package line | a package both this test and the screen under test can see |
| class name | e.g. `ConnectLayoutDumpTest` |
| `TODO_APP_THEME` | the project's root theme composable, e.g. `AppTheme(darkTheme = true)` |
| `TODO_FRAME_WIDTH_DP` | the design frame's width — `ir/screen.ui.json`'s `root.rect.w` |
| `TODO_FRAME_HEIGHT_DP` | see "Sizing the forced Box" below |
| `TODO_SCREEN_CONTENT(TODO_FIXTURE_ARGS)` | the screen's content composable, called with the **design's own data**, not an empty/loading state — an empty state renders different sizes and the comparison would be measuring the wrong thing |

## Sizing the forced Box

The content is rendered inside `Box(Modifier.width(frameWidthDp).height(frameHeightDp))`
rather than left to wrap or to the test device's real window size, for two reasons:

1. **Width** must equal the frame's dp width so the render and the IR share a coordinate
   space — rendering at the device's actual width (411.4dp on a Pixel 6 Pro, say) compares a
   390dp design against bounds measured in a different space and every delta is noise.
2. **Height** must be at least the screen's full content height, not just one screenful. A
   `LazyColumn`/`LazyRow` only composes items inside its current viewport; if the viewport is
   the test device's real (and usually shorter) window, items past the fold never compose,
   `onGloballyPositioned` never fires for them, and they report as `untagged` — not wrong, just
   silently absent. Pin the height to something taller than the whole screen instead, and the
   lazy layout's viewport covers all of it on the first composition pass.

The number to use is already sitting in the IR: `root.rect.h` in `ir/screen.ui.json` is the
design frame's **total content height**, including whatever would need scrolling on a real
device — because the Figma frame itself has no viewport, it's exactly as tall as its content.
Use that value plus ~15% headroom (rounding differences between the design's measured height
and Compose's actual layout can leave a `LazyColumn` a few dp short of composing its last
item otherwise). For the Connect screen in the run that motivated this file, `root.rect.h` was
`1017`, so `TODO_FRAME_HEIGHT_DP` would be `1170`.

This does not help a lazily-loaded list whose true length isn't in the design at all (an
infinite feed, say) — there the IR only describes the fixture's first page, and that's the
right page to measure against. It also doesn't reach into a *nested* lazy list or a pager
inside the audited screen; those need their own, separately-sized forced viewport if you tag
nodes inside them.

## Tagging a repeated list item — tag the first instance only

A Figma design draws **one** card for a repeated list (one `TopicCard` node, say), and the IR
carries that one node's geometry. The generated Compose renders it N times
(`items(state.topics) { topic -> TopicCard(topic) }`). If every instance calls
`Modifier.figmaNode("17:39")` with the same id, `LayoutAuditCollector.record()` simply
overwrites the previous instance's bounds each time — the dump ends up holding whichever
instance happened to compose last, not the first one the design shows, and `layout_assert.py`
compares the design's card to an arbitrary later card with no way to tell you which.

Tag only the first instance:

```kotlin
itemsIndexed(state.topics, key = { _, topic -> topic.name }) { index, topic ->
    TopicCard(
        topic = topic,
        modifier = if (index == 0) Modifier.figmaNode("17:39") else Modifier,
    )
}
```

This is exactly the shape of the screen that motivated this file — eleven `TopicCard`s from
one Figma template node — so expect to need it whenever a `LazyColumn`/`LazyRow` wraps
`items(...)`.

## Flipping `ENABLED` without hand-editing the file

`LayoutAudit.ENABLED` is a `const val false` by default, which is deliberate: a compile-time
constant lets R8 strip the dead `onGloballyPositioned` branch entirely from a minified release
build, so the instrumentation costs nothing in production even if the file is never removed.
The simplest way to run an audit is to hand-edit it to `true`, run the dump test, then revert
— acceptable for an occasional, deliberate audit run, and what `references/pixel-fidelity.md`
already assumes elsewhere in this skill. Do not merge it as `true`.

A project that wants this wired into a dedicated Gradle variant instead (so audit runs never
touch a file by hand) can turn `ENABLED` into a `BuildConfig` read:

```kotlin
// LayoutAudit.kt
object LayoutAudit {
    val ENABLED: Boolean = BuildConfig.LAYOUT_AUDIT_ENABLED
}
```

```kotlin
// app/build.gradle.kts
android {
    buildTypes {
        debug {
            buildConfigField("boolean", "LAYOUT_AUDIT_ENABLED", "false")
        }
        // a dedicated variant / flavor can set this to "true" instead
    }
}
```

This is a **suggestion, not shipped code** — `ENABLED` as `const val` is what the template
files above actually contain, because it needs no Gradle changes to work at all and this
skill cannot assume a project's `build.gradle.kts` shape. Swap it for the `BuildConfig`
version if the project already has `buildFeatures { buildConfig = true }` wired up.

## Relationship to `references/pixel-fidelity.md`

That reference sketches the same call site (`Modifier.figmaNode("17:39")`) but reads bounds
back through the semantics tree (`testTag` + `fetchSemanticsNode()`). This implementation
reads `LayoutCoordinates` directly via `onGloballyPositioned` instead, to avoid a real failure
mode of the semantics approach: a `clickable`, `combinedClickable`, `Row`, or similar modifier
can merge a child's semantics node into its parent's, which silently drops the child's
`testTag` out of the tree the dump test walks — a tagged node then reads as untagged with no
error, exactly the kind of quiet gap this whole task exists to close.

The public surface (`Modifier.figmaNode(id)`, the JSON shape, `layout_assert.py`'s contract)
is identical either way. **Use one implementation, not both** — tagging the same node with a
`testTag` dump and an `onGloballyPositioned` dump at once doesn't conflict mechanically, but
it is two sources of truth for one measurement and only invites a mismatch nobody can explain.

## What's unverified

The dump template now uses the target app's private files directory rather than
`/sdcard/Download`; pull it with `adb exec-out run-as <applicationId> cat files/<output> > render/nodes.json`.
Android 10+ scoped storage can reject the previous shared-storage write.

Everything in this directory is written against stable, long-documented Compose UI test APIs,
reasoned through carefully, and matched against the exact JSON shape `layout_assert.py --help`
prints (confirmed by running it; see `references/verification.md`'s fixture run). None of it
has been compiled or run against a real Android project — this task had no Kotlin toolchain or
device available. Specifically unverified:

- That `LayoutAuditDumpTest.kt` compiles once the `TODO` markers are filled in.
- That the forced-height trick reliably pre-composes every `LazyColumn` item in practice,
  rather than only in the mental model of how lazy-layout viewport sizing works.
- That `org.json.JSONObject(Map<String, Map<String, Float>>)` serializes the nested maps as
  nested JSON objects on every Android API level this might run on (it does on the versions
  this reasoning was checked against, and the exact same call shape is already used in
  `references/pixel-fidelity.md`'s own sketch, which this task did not author).
- Real device/emulator behavior: window insets, multi-window, or a theme that itself consumes
  `onGloballyPositioned` for something else before the content reaches these composables.

Treat a first run on any given project as a trial: run the dump test once, inspect
`render/nodes.json` by eye before trusting `layout_assert.py`'s report, and expect to adjust
package names, the theme call, and the fixture before it compiles.
