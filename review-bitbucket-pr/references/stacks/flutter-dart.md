# Stack profile: Flutter / Dart

Use this profile when the diff touches `.dart` files or the repository has a `pubspec.yaml`. It supplies the concrete detectors for the contract's coverage and quality gates. It does not replace them — read `../review-contract.md` first.

Everything here yields to the repository's own conventions. Confirm the localization mechanism, the state-management library, and the generated-file layout from the repo before applying the defaults below.

## Detecting project conventions

Check these before reviewing, because they determine what half the detectors below even mean:

| Question | Where to look |
| --- | --- |
| Localization mechanism and source file | `pubspec.yaml` (`flutter_localizations`, `intl`, `slang`, `easy_localization`), `l10n.yaml`, `assets/localization/*.arb`, `lib/l10n/` |
| Access pattern for translated strings | Existing call sites — `context.translate.x`, `S.of(context).x`, `AppLocalizations.of(context)!.x`, `'key'.tr()` |
| State management | `pubspec.yaml` — Riverpod, Bloc, Provider, GetX |
| Generated output directories | `build.yaml`, `l10n.yaml`, `.gitignore`, and `part` directives (`*.g.dart`, `*.freezed.dart`, `lib/generated/`) |
| Lint rules already enforced | `analysis_options.yaml` — do not hand-report what the analyzer already fails on |

## User-facing copy gate — detectors

Inspect every changed string literal reaching any of:

`Text`, `Text.rich`, `RichText`, `SelectableText`, and the `label`, `labelText`, `title`, `subtitle`, `hintText`, `helperText`, `errorText`, `counterText`, `tooltip`, `message`, `semanticLabel` parameters — plus `AppBar` titles, `SnackBar` / `MaterialBanner` content, `AlertDialog` / `CupertinoAlertDialog` title and content, button children, `PopupMenuItem` children, `Tab` labels, `TextField` decoration, notification title/body, and any `toString`/getter on an enum or status type that a widget renders.

Each must resolve through the project's localization mechanism, or have a stated non-user-facing reason.

Also flag:

- Hard-coded copy assembled by concatenation or interpolation, which breaks word order in other languages. The ICU placeholder or plural form in the ARB is the correct place.
- `toUpperCase()` / `toLowerCase()` on displayed copy without a locale, which mangles Turkish dotted I among others.
- A changed ARB key whose meaning drifted from its UI consumer, whose placeholders no longer match the call site, or whose ICU `plural`/`select` syntax is malformed.
- Terminology inconsistent with neighbouring keys, and capitalization or punctuation out of step with the rest of the file.

Treat the ARB (or the equivalent source file) as the source of truth and `lib/generated` as output. Out of scope: internal logs, technical identifiers, API field names, debug strings, and content the backend localizes.

## Complexity gate — detectors

Inspect every changed `build` method, widget-returning method, or UI factory that has more than roughly 50 meaningful lines — blank lines and closing-only lines do not count — or that carries two or more independent state branches such as empty, loading, error, and content.

Split points that are genuinely worth raising: a state-specific subtree that could be a purpose-named builder (`_buildEmptyState`) or, when it owns state or is reused, a widget class. A short purpose-named builder that already exists is the target state, not a finding.

Watch for splits that break behaviour rather than improve it: a subtree pulled out of a `ListView`/`CustomScrollView` in a way that loses scroll or refresh semantics, or a `const` constructor lost in the move, which costs rebuilds.

## Compatibility gate — detectors

Search for consumers whenever the diff changes or removes: a constructor parameter (especially a required one gaining a default, or an optional one becoming required), a public method or its signature, a route name or deep-link path, an enum or status value, an analytics event name or its parameter map, a persisted key or Hive/Isar/SharedPreferences field, a JSON field feeding `fromJson`, or a provider's family key shape.

Dart specifics that hide a stale consumer: an added enum value with `switch` statements elsewhere that are non-exhaustive or fall through a `default`; a renamed JSON key where the model still deserializes the old one for existing users; a changed `copyWith` signature; a widget parameter removed while a call site passes it positionally.

## Runtime and lifecycle — Flutter specifics

- `BuildContext` used after an `await` without a `mounted` / `context.mounted` guard. Reachable whenever the user can leave the screen while the future is in flight — check whether the surrounding code or the caller already guards it before reporting.
- `setState` or state mutation after dispose; a `StreamSubscription`, `AnimationController`, `TextEditingController`, `FocusNode`, `ScrollController`, or `Timer` created without a matching `dispose`.
- `ref.watch` inside a callback or a non-build method, which creates a dependency at the wrong time; `ref.read` in `build`, which misses rebuilds.
- Work in `build` that should not repeat: allocation, sorting, network calls, `Future` creation.
- `Future`s started and not awaited where ordering matters, and duplicate submissions with no in-flight guard.

## Riverpod and immutable state

- Use `ref.watch` for rendering, `ref.read` for commands, `ref.listen` for one-off UI effects such as snackbars and navigation.
- Update state immutably through `copyWith`; mutating a field on the existing state object skips the rebuild.
- Match the provider lifecycle and family identity used nearby. Prefer feature-scoped disposal (`autoDispose`) unless the state is intentionally long-lived — a lingering provider keeps stale data across screen entries.
- Freezed unions: check that every new variant is handled at each `when`/`map` site, and that `maybeWhen` fallbacks are not swallowing a case that needs handling.

## Generated sources

`*.g.dart`, `*.freezed.dart`, and `lib/generated/**` change through their inputs. A hand-edit there is a Minor at minimum, because the next `build_runner` run erases it silently. When an input changed but its generated output did not appear in the diff, ask whether generation was run.

## Verification commands

Prefer one focused command over a broad pass. This environment uses FVM:

```bash
fvm flutter test test/path/to/focused_test.dart
fvm dart analyze lib/features/<feature>
```

Do not run `build_runner`, `pub get`, or `pub upgrade` during a review — they write to the working tree.
