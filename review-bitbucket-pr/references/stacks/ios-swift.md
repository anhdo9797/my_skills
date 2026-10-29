# Stack profile: iOS (Swift / Objective-C)

Use with `mobile-common.md` when the diff touches `.swift`, `.m`/`.h`, storyboards/xibs, `Info.plist`, entitlements, or Xcode project files. Repository conventions override these defaults.

## Detecting conventions

- UI toolkit: SwiftUI vs UIKit (or mixed); navigation (NavigationStack, coordinators, router).
- Architecture: MVVM, TCA, VIPER, Clean; DI approach; concurrency model (async/await, Combine, GCD).
- Localization: String Catalog (`*.xcstrings`), `Localizable.strings`, `String(localized:)`, `NSLocalizedString`. Lint: SwiftLint config.
- Dependencies: SPM `Package.resolved`, CocoaPods `Podfile.lock`.

## Detectors

- **Memory/lifecycle:** retain cycles from closures capturing `self` strongly (missing `[weak self]` where the closure is stored, escapes, or lives in a Combine sink / Timer / NotificationCenter observer); delegates not `weak`; observers or `AnyCancellable`s not stored/removed; `Task {}` not cancelled when the owner disappears.
- **Main-actor/threading:** UI updates off the main thread; missing `@MainActor` on view-model state bound to UI; blocking work in `viewDidLoad` / `body`; data races on shared mutable state; `DispatchQueue.main.sync` risks; Swift concurrency `Sendable` warnings ignored.
- **SwiftUI:** heavy work in `body`; wrong property wrapper (`@State` vs `@StateObject` vs `@ObservedObject`) that recreates or leaks state; unstable `id` in `ForEach`/`List`; `.task` / `.onAppear` triggering duplicate loads; missing `Equatable`/identity causing excessive redraw.
- **UIKit:** Auto Layout constraint conflicts or missing safe-area use; cell reuse leaking state (`prepareForReuse`); `reloadData` where granular updates are expected; main-thread image decoding in cells.
- **Safety:** force unwrap (`!`), `try!`, `fatalError`, forced casts, unchecked array indexing on data that comes from outside; `as!` on server data.
- **Security/privacy:** secrets in `UserDefaults` instead of Keychain; ATS exceptions (`NSAllowsArbitraryLoads`); sensitive data in logs (`print`/`os_log` without privacy annotations); missing or unlocalized `NS…UsageDescription` for a new permission; new entitlement / background mode / URL scheme; Universal Link / URL-scheme handler trusting unvalidated input; app-switcher snapshot of sensitive screens.
- **OS compatibility:** API newer than the deployment target without `#available`/`@available`; deprecated API with changed behaviour; Dynamic Type, Dark Mode, and iPad / multitasking layouts.
- **Resources and copy:** hard-coded literals in `Text("…")`, `.title`, `.accessibilityLabel`, alerts, notification content; string concatenation instead of format/plural variants; new key missing from the String Catalog base locale or marked stale.
- **Data:** Core Data / SwiftData model change without a lightweight/custom migration or model-version bump; changed `Codable` keys breaking cached or persisted data; enum case added with a `default:` swallowing it in `switch`.
- **Generated/vendored:** `Pods/`, `*.generated.swift`, R.swift/SwiftGen output, `Package.resolved` — review the input or dependency change, not hand edits.
- **Project files:** `project.pbxproj` merge damage (duplicate or missing file references, target membership), signing/provisioning changes (report, do not infer intent).

## Verification

```bash
xcodebuild test -scheme <Scheme> -destination 'platform=iOS Simulator,name=iPhone 15' -only-testing:<Target>/<TestClass>
swiftlint lint --path <changed/path>
```

Do not run `pod install`, SPM resolve with updates, or generators that rewrite tracked files.
