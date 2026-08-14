# Build Variants & APP_ID (derive it, don't hardcode)

Maestro launches an app by its `applicationId` (the bundle id), and that app must already be
installed on the device. **This value is project-specific — always derive it from the repo at hand,
never assume a literal id.** Getting it wrong is the #1 cause of "Unable to launch app `…`": the
flow is fine, the variant just isn't on the device.

Two independent axes decide both the id and which APK is installed:
- **Flavor** (`productFlavors` / `flavorDimensions`, e.g. `dev`/`prod`, `free`/`paid`) — often adds
  an `applicationIdSuffix`, so it usually *does* change the id.
- **Build type** (`debug`/`release`) — may add its own `applicationIdSuffix`; decides logging,
  Crashlytics, minify/R8.

## Deriving APP_ID from the project

`app/build.gradle.kts` (or `build.gradle`) is the source of truth. Compute:

```
applicationId = defaultConfig.applicationId
              + (flavor.applicationIdSuffix    ?: "")
              + (buildType.applicationIdSuffix ?: "")
```

So read `defaultConfig.applicationId`, then add the suffix (if any) of the chosen flavor and the
chosen build type. A flavor with no suffix leaves the id unchanged; a build type with no suffix
leaves it unchanged.

Pull the pieces straight from the file:

```bash
grep -nE 'applicationId|applicationIdSuffix|productFlavors|buildTypes|create\(' \
  app/build.gradle.kts app/build.gradle 2>/dev/null
```

Cross-check against what's actually on the device (substitute a fragment of the base id):

```bash
adb shell pm list packages | grep <base-id-fragment>   # which variant(s) are present
```

## Worked example (illustrative — your project will differ)

Given `defaultConfig.applicationId = "com.example.app"`, a `dev` flavor with
`applicationIdSuffix = ".dev"`, a `prod` flavor with no suffix, and `debug`/`release` adding no
suffix, the matrix is:

| Variant     | APP_ID (`-e APP_ID=`)     | Install task              |
|-------------|---------------------------|---------------------------|
| devDebug    | `com.example.app.dev`     | `:app:installDevDebug`    |
| devRelease  | `com.example.app.dev`     | `:app:installDevRelease`  |
| prodDebug   | `com.example.app`         | `:app:installProdDebug`   |
| prodRelease | `com.example.app`         | `:app:installProdRelease` |

Here the build type doesn't change the id (no build-type suffix) — only the flavor does. Recompute
this table for the project you're in; the suffixes and flavor names are whatever the gradle file says.

If the project has **no flavors**, there's just `debug`/`release`, and `APP_ID` is usually
`defaultConfig.applicationId` (plus a `.debug` suffix only if the `debug` build type declares one).

## Choosing a variant

Default to the **debug build of the default/dev flavor** unless the user names one. "Test the debug
build" → keep the current flavor, use the `debug` build type. "Test prod" → the prod flavor's id.
Map the choice to **both** the `APP_ID` and the matching `./gradlew :app:install<Variant>` task.

## Install then run

```bash
# Install the chosen variant (its install task name follows the variant)
./gradlew :app:install<Variant>          # e.g. :app:installDevDebug

# Run flows, passing the derived id to the ${APP_ID} placeholder
maestro test -e APP_ID=<derived-applicationId> .maestro

# With a JUnit report
maestro test -e APP_ID=<derived-applicationId> --format junit --output build/maestro/report.xml .maestro
```

Release builds are minified (R8/ProGuard). If a flow that passes on debug fails on release, suspect a
shrink rule stripping something — that is a real signal, not a test bug.
