# Stack profile: React Native (and Expo)

Use with `mobile-common.md` when the diff touches `.ts`/`.tsx`/`.js` in a repository with `react-native` or `expo` in `package.json`, or native code under `android/` / `ios/` (read that platform's profile too for the native files). Repository conventions override these defaults.

## Detecting conventions

- Expo managed vs bare; new architecture (Fabric/TurboModules) flag; navigation library (React Navigation, Expo Router); state (Redux Toolkit, Zustand, React Query, MobX); i18n library (`i18next`, `react-intl`, `expo-localization`).
- Lint/test: ESLint config (react-hooks rules), TypeScript `strict`, Jest/Detox setup.

## Detectors

- **Hooks and rendering:** missing or wrong `useEffect` dependencies, effects without cleanup (listeners, timers, subscriptions, `AppState`, `Keyboard`, `Linking`), state updates after unmount, stale closures, inline objects/functions causing re-render of memoized children, expensive work in render without `useMemo`.
- **Lists:** `FlatList`/`FlashList` without stable `keyExtractor`, `ScrollView` rendering large data, heavy item components without memoization, missing `getItemLayout`/`estimatedItemSize` where the repo uses it.
- **Async/network:** unhandled promise rejections, missing loading/error states, race between requests (no cancellation/`AbortController`/query key), duplicate submits, React Query cache keys missing params.
- **Bridge/native boundary:** JS↔native module signature changed on one side only; new native module without autolinking/pod/gradle updates; event emitter listeners not removed; heavy sync bridge calls on the JS thread.
- **Security:** tokens in `AsyncStorage` instead of Keychain/Keystore-backed storage; secrets bundled in JS (the bundle is readable); `console.log` of PII/tokens left in release; WebView `originWhitelist`/`onMessage` trusting unvalidated input; deep-link params used without validation.
- **Platform differences:** `Platform.OS` branches missing one platform; behaviour tested on one OS only (keyboard avoidance, safe area, permissions, shadows vs elevation, back button on Android).
- **Copy and accessibility:** literals in `<Text>`, `placeholder`, `accessibilityLabel`, `Alert.alert`, toasts, notification content not going through the i18n function; concatenation instead of interpolation/plural; interactive `Pressable` without `accessibilityRole`/label; touch targets too small.
- **Compatibility:** TypeScript types loosened with `any`/`as` hiding a contract change; navigation route/param names changed with callers elsewhere; OTA-update (Expo/CodePush) compatibility — a JS change that requires a newer native binary will crash older installs; enum/union value added while consumers use `default`.
- **Dependencies/build:** new native dependency (needs rebuild, increases binary size), version bump of `react-native`/Expo SDK (large blast radius), `package.json` changed without lockfile, Hermes/proguard/pod changes.

## Verification

```bash
npx jest path/to/focused.test.tsx
npx tsc --noEmit
npx eslint <changed files>
```

Use the package manager the repo uses. Do not run installs, `pod install`, or `expo prebuild` — they write to the working tree.
