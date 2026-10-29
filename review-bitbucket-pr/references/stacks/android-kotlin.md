# Stack profile: Android (Kotlin / Java)

Use with `mobile-common.md` when the diff touches `.kt`, `.java`, `AndroidManifest.xml`, `res/`, or Gradle files. Repository conventions override these defaults.

## Detecting conventions

- UI toolkit: Jetpack Compose vs XML/View Binding; navigation (Navigation component, Compose Navigation, Voyager, custom).
- Architecture: ViewModel + StateFlow/LiveData, MVI, Clean layers; DI (Hilt, Koin, Dagger, manual).
- Localization: `res/values*/strings.xml`, `plurals`, `stringResource`. Lint config in `lint.xml`, detekt/ktlint configs.

## Detectors

- **Lifecycle:** collecting flows with `collect` in `lifecycleScope` without `repeatOnLifecycle` / `collectAsStateWithLifecycle`; `GlobalScope`; Fragment view references kept after `onDestroyView`; static/context leaks (Activity stored in a singleton); coroutine launched in a view-model without handling cancellation.
- **Process death:** state kept only in a ViewModel field when `SavedStateHandle` is used for the same kind of state elsewhere.
- **Compose:** unstable parameters causing recomposition, work in composition (sorting, allocation), `remember` missing/mis-keyed, side effects outside `LaunchedEffect`/`DisposableEffect`, state hoisting violated, missing `key` in `LazyColumn`, `collectAsState` instead of lifecycle-aware variant.
- **Threading:** blocking I/O on `Dispatchers.Main`; hard-coded dispatchers where the repo injects them; `runBlocking` on main; swallowed `CancellationException`.
- **Manifest and security:** new `exported="true"` component without a permission/intent validation; `usesCleartextTraffic`; new permission; backup rules exposing sensitive data; WebView `setJavaScriptEnabled` / `addJavascriptInterface`; sensitive data in `SharedPreferences` instead of encrypted storage; `Log` with tokens/PII.
- **OS compatibility:** API above `minSdk` without `Build.VERSION.SDK_INT` guard or `@RequiresApi`; Android 13+ notification permission, Android 14 partial media access, foreground-service type, exact-alarm restrictions, edge-to-edge insets.
- **Resources:** hard-coded `Text("…")`/`setText("…")`/`contentDescription`; concatenated strings instead of format args/plurals; missing base-locale key; `dp`/`sp` misuse (text in `dp`), hard-coded colors bypassing the theme.
- **Data:** Room schema change without a `Migration` or version bump; changed `@Entity` columns; `exportSchema` file not updated; Retrofit/serialization model with non-null field for an optional payload key; sealed class case added with non-exhaustive `when` elsewhere.
- **Build:** R8/ProGuard rules for reflection/serialization added or missed; version catalog or dependency bump with a large blast radius; debug-only code reachable in release.
- **Generated sources:** `build/`, KSP/KAPT output, `BuildConfig`, Hilt components — change inputs, not outputs.

## Verification

```bash
./gradlew :module:testDebugUnitTest --tests "com.example.FooTest"
./gradlew :module:lintDebug
```

Do not run tasks that modify tracked files or the dependency lockfile.
