# Stack profile: Mobile (platform-neutral core)

Read this profile for **every** mobile diff — native Android, native iOS, Flutter, React Native, Kotlin/Swift Multiplatform, or a mix — and then read the one platform profile that matches the changed files (`flutter-dart.md`, `android-kotlin.md`, `ios-swift.md`, `react-native.md`). This file holds the risks that come from being a mobile app, regardless of framework; the platform profile holds the framework detectors. The universal gates in `../review-contract.md` still apply.

Everything here yields to the repository's own conventions. Confirm the localization mechanism, state/architecture pattern, supported OS versions, and release process from the repo before applying a default.

## Detecting project conventions

| Question | Where to look |
| --- | --- |
| Platforms and min OS versions | `build.gradle(.kts)` (`minSdk`, `targetSdk`), `Info.plist` / `*.xcodeproj` (`IPHONEOS_DEPLOYMENT_TARGET`), `pubspec.yaml` (`environment`), `package.json` |
| Localization mechanism | `strings.xml` / `values-*`, `*.xcstrings` / `Localizable.strings`, `*.arb`, i18n JSON, `i18next`, `slang` |
| Architecture / state pattern | Neighbouring feature: MVVM, MVI, Clean, Bloc, Riverpod, Redux, TCA |
| Permissions and entitlements | `AndroidManifest.xml`, `Info.plist` usage strings, `*.entitlements` |
| Generated or vendored output | `build/`, `Pods/`, `*.g.dart`, `R.java`, `generated/`, lockfiles |
| Release / signing config | `*.gradle` signing blocks, `fastlane/`, `ExportOptions.plist` — never open keystores or provisioning secrets |

## Mobile-specific risk checklist

Run these against every changed hunk where they apply. Each one is a finding only when you can name a reachable trigger.

### Lifecycle and process death

- Work, callbacks, listeners, or subscriptions that outlive the screen/view-model/activity owner (leaks, crashes after dispose, UI updates on a destroyed view).
- State held only in memory that must survive rotation, backgrounding, or **process death** (draft input, in-flight checkout, selected item). Check whether saved-state / restoration is used nearby.
- Background→foreground and cold-start paths: does the screen behave when launched from a deep link, notification, or restored state with no prior navigation stack?
- Configuration changes (rotation, font scale, dark mode, locale change, split-screen/foldable) that recreate or resize the UI.

### Threading and responsiveness

- Network, disk, DB, JSON parsing, image decoding, or heavy loops on the main/UI thread.
- UI mutation from a background thread; missing dispatch back to main.
- Unbounded concurrency, duplicate in-flight requests, missing cancellation when the owner goes away, races between refresh and paging.

### Network, offline, and data

- Failure paths: timeout, no connectivity, 4xx/5xx, malformed payload, empty list — each must end in a recoverable UI state, not an endless spinner.
- Retry/backoff that can hammer the API; missing idempotency on submit actions the user can double-tap.
- Pagination/caching correctness: stale cache shown as fresh, cache not keyed by user/locale, offline writes lost.
- **Persisted data and migrations**: a changed local schema, key, or model needs a migration or a compatible read path for existing installs. Mobile users upgrade across many versions; there is no "redeploy everyone".
- API contract drift: new required field, renamed key, enum value the old backend or old app version does not know. Older app versions stay in the field for months — check backward compatibility of anything shared with a server.

### Security and privacy (mobile)

- Tokens, PII, or credentials in logs, crash reports, analytics payloads, screenshots/app-switcher snapshots, clipboard, or plain preferences. Secrets belong in Keychain / Keystore / secure storage.
- Cleartext HTTP, disabled TLS validation, trust-all certificates, pinning removed.
- Exported components / URL schemes / deep links that accept untrusted input without validation; WebView with JavaScript bridges or arbitrary URL loading.
- New permission or entitlement: is it needed, is the rationale string present and localized, and is the denied/limited state handled?
- Never open signing keys, keystores, provisioning profiles, or `.env`/secret files to check these.

### Permissions and platform behaviour

- Runtime permission requested without handling denial, "ask next time", limited access (iOS photo picker, Android 14 partial media), or permanent denial.
- Behaviour that differs by OS version: API available only above `minSdk` / deployment target without a guard; deprecated API with a changed contract; background execution limits; notification channels / authorization.
- Battery and background work: wake locks, location updates, polling timers that keep running off-screen.

### UI correctness and accessibility

- Layout robustness: small/large screens, notch/safe areas/edge-to-edge insets, keyboard overlap, landscape, large text/Dynamic Type, RTL.
- Accessibility: interactive element without a label/role/hint, touch target well under platform minimum (~44pt iOS / 48dp Android), information conveyed by color alone, focus order broken by the change.
- Loading, empty, error, disabled, and success states all reachable and visually distinct.
- Lists: stable keys/ids, recycling-safe item state, no heavy work in item build/bind, image sizing/caching.

### Performance and size

- Unnecessary re-render/recomposition/rebuild, work in render paths, large images loaded at full resolution, unbounded in-memory lists.
- New heavy dependency or large asset for a small gain (binary size matters on mobile). Flag only when the cost is concrete.
- Startup-path additions (work in `Application.onCreate`, `didFinishLaunching`, `main()`).

### Analytics and release safety

- Analytics events/params renamed or dropped (breaks dashboards); PII added to events.
- Feature flags/remote config: safe default when config is missing or the fetch fails; flag removed while code still branches on it.
- Version/build-number bumps, signing, and store-metadata changes are release-sensitive — report them but do not infer intent.

## User-facing copy gate — mobile notes

Every changed user-visible string must use the platform's localization mechanism: Android `strings.xml` (`R.string`, `stringResource`) with plurals/format args instead of concatenation; iOS `String(localized:)` / `NSLocalizedString` / String Catalog; Flutter ARB; RN i18n library. Also include: accessibility labels, notification text, permission usage descriptions (`NSCameraUsageDescription` etc.), widget/extension text, and error text shown to users. Check that a new key exists in the **base** locale and that placeholders/plurals match their call site. Out of scope: logs, identifiers, backend-localized content.

## Complexity gate — mobile notes

Judge by neighbouring files, not a fixed number. Raise it when a View/Composable/ViewController/Fragment/widget `build` mixes rendering with business logic or carries several independent state branches (loading/empty/error/content), or when a ViewController/Activity/Fragment grows logic that belongs in the presentation-state layer the repo already uses.

## Compatibility gate — mobile notes

Search consumers when the diff changes: public API of a shared module, a route/deep-link/URL scheme, a notification payload key, an analytics event, a persisted key or DB column, a serialized model, an enum/sealed case (check exhaustive `when`/`switch`), an exported Android component, a bridge/method-channel/native-module signature (both sides must change together), or a minimum OS version.

## Verification

Prefer one focused local check over a full build, and only when it validates a finding you are about to post. Use the repo's own commands through its wrappers (`fvm flutter` for Flutter, `./gradlew :module:testDebugUnitTest --tests …` for Android, `xcodebuild test -only-testing:…` for iOS, the package script for RN). Never run commands that write to the working tree (dependency install/upgrade, code generation, pod install) during a review.
