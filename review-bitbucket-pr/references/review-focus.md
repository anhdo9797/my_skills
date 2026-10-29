# Review focus: Clean code, Security, Memory, Architecture

These four pillars are what this skill optimises for. Review every changed hunk against them first; findings outside them (style, naming nits, formatting) need a much higher bar and usually should not be posted. The contract still owns the evidence threshold and severity; the stack profiles own the framework-specific detectors. This file says what to look for per pillar and how to rank.

Tag each finding with its pillar in the working notes (`Clean`, `Security`, `Memory`, `Architecture`) so the result can report coverage per pillar.

## Priority order

When time or diff size forces a choice, review in this order: **Security → Memory → Architecture → Clean code**. A leaked token or a crash from a leak outranks a long function. Large-PR coverage statements should say which pillars were fully covered.

## 1. Security

- Secrets, tokens, API keys, or PII hard-coded, logged, sent to analytics/crash reports, or stored in plain preferences/`UserDefaults`/`AsyncStorage`/`SharedPreferences` instead of Keychain / Keystore / secure storage.
- Transport: cleartext HTTP, disabled or trust-all TLS validation, removed pinning, ATS / `usesCleartextTraffic` exceptions.
- Untrusted input: deep links, URL schemes, intents, push payloads, WebView messages, file/clipboard/QR input used without validation or sanitization; injection into SQL, JS bridges, or shell/URL construction.
- Authorization and session: token refresh/logout leaves stale credentials, data not cleared on logout, user A's cache shown to user B, client-side-only checks guarding a privileged action.
- Exposure: exported Android components without permission, new entitlement/permission without need, sensitive screens in app-switcher snapshots or screenshots, sensitive data in backups or clipboard.
- Never open `.env`, keystores, provisioning profiles, or private keys to verify; describe what you would need instead.

Severity hint: credential exposure, auth bypass, or sensitive data leak → `Blocker`/`Major`; weakened hardening with no direct exploit path → `Major`/`Minor`.

## 2. Memory

- Leaks: closures/lambdas capturing the owner (`self`, Activity, Fragment, BuildContext, component instance) in anything stored or long-lived; listeners, observers, subscriptions, timers, controllers, `AnyCancellable`, `Disposable`, event emitters registered and never released; static/singleton holding a view or context.
- Lifetime: work or coroutines/tasks/futures that outlive the screen or view-model and are not cancelled; callbacks touching a destroyed view; Fragment/view bindings retained after `onDestroyView`.
- Allocation and retention: unbounded caches or in-memory lists, full-resolution images decoded for small views, large payloads held in state, bitmaps/streams/cursors/files not closed on the error path, allocation or sorting inside render/build/body/bind paths.
- Redundant rebuild: state shape that forces whole-tree recomposition/rebuild/re-render, missing stable keys in lists causing item churn.
- Process-level: state that must survive process death held only in memory; state that must *not* survive (sensitive) retained too long.

Severity hint: leak on a frequently visited screen or crash path → `Major`; leak in a rarely used, bounded flow → `Minor`. Require a named trigger ("open then back 10× keeps N instances alive") rather than "might leak".

## 3. Architecture

- Layering: presentation renders state and handles navigation/UI effects; presentation-state layer (ViewModel/Bloc/Provider/Presenter/store) owns state transitions; domain/repository own data access and error translation; transport clients are not called from UI. Infer boundaries from directories actually present.
- Business logic, validation, and multi-step async work inline in UI callbacks, `build`/`body`, Activities, Fragments, ViewControllers, or components.
- Dependency direction: lower layers importing upper layers, feature modules reaching into each other's internals, new global singletons or service locators where the repo injects dependencies.
- State: single source of truth, immutable updates, no duplicated state mirrored between layers, unidirectional flow kept; one-off effects (navigation, toasts) modelled the way neighbours model them.
- Public contracts: module/API surface widened unnecessarily; DTOs leaking into UI; platform types leaking into domain; native/bridge boundary changed on one side only.
- Abstraction budget: a new abstraction needs ≥ 2 real uses or a multi-step behaviour; a one-caller interface is a finding only when it adds a hop without hiding anything.
- Consistency over preference: the nearest sibling feature is the standard. Cite it.

Severity hint: layering violation that will force a rewrite or breaks testability on a core flow → `Major`; localized deviation → `Minor`.

## 4. Clean code

- Functions/components that mix responsibilities or carry several independent state branches; judge by sizes in the same directory, not an absolute limit. Blank lines and closing brackets are not complexity.
- Duplicated logic (≥ 3 occurrences, or 2 with divergence risk), magic numbers/strings with domain meaning, deep nesting that early return would flatten, boolean-flag parameters that hide two behaviours.
- Names that mislead (not merely "could be better"), dead code, commented-out code, TODOs without owner/ticket, comments that restate the code or contradict it.
- Error handling that swallows exceptions, catches too broadly, or returns a default that hides failure; inconsistent with neighbours.
- Tests: new behaviour or a bug fix with no protection where regression risk is concrete; tests tied to timing, network, or order.
- User-facing copy not going through the project's localization mechanism (see the contract's copy gate).

Severity hint: mostly `Minor`/`Suggestion`. Raise to `Major` only when the mess hides a defect or makes a core flow untestable.

## Do not post

Pure formatting a linter owns, alternative-but-equivalent styles, renames that are marginally better, and refactors outside the PR. Four pillars is a focus, not a license to pad: a PR with nothing real in them gets `Approve`.
