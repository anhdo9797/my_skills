# Maestro Command Reference

Maestro runs YAML "flows" against a real device/emulator, simulating human
interaction. This is the working subset you need for authoring reliable flows.
Full docs: https://docs.maestro.dev (corpus: https://docs.maestro.dev/llms-full.txt).

## Flow file structure

```yaml
appId: ${APP_ID}        # or a literal id; web uses `url:` instead
name: Favorite from list
tags:
  - smoke
  - favorite
---
- launchApp
- tapOn: "Favorites"
- assertVisible: "Rice Egg Pork"
```

Everything above `---` is config (frontmatter); everything below is the ordered
command list. `name` and `tags` are optional but strongly recommended — `tags`
drive `--include-tags`/`--exclude-tags` selection and reporting clarity.

## Selectors — in priority order

Resilient selectors are the difference between a suite that lasts and one that
breaks on every copy tweak. Prefer earlier options:

```yaml
- tapOn:
    id: "favorite_button"      # 1. accessibility id — Compose testTag / semantics. Best.
- tapOn: "Rice Egg Pork"        # 2. visible text (exact). Fine, but breaks on copy/locale changes.
- tapOn:
    text: "Next"
    index: 1                    # 3. disambiguate duplicates by index
- tapOn:
    point: "50%,75%"            # 4. coordinates — last resort, brittle, screen-size dependent
```

Text matching is exact by default; regex is supported (`text: ".*Pork.*"`).
You can also match by relative position (`below:`, `above:`, `containsChild:`).

## Commands

### App lifecycle
```yaml
- launchApp                       # launch (resumes if already running)
- launchApp:
    clearState: true              # cold start, wipes app data — use for deterministic tests
    permissions: { location: allow }
- stopApp
- clearState                      # wipe app data without launching
- back                            # Android back
```

### Input & interaction
```yaml
- tapOn: "Login"
- doubleTapOn: "Map"
- longPressOn: "Item"
- inputText: "user@example.com"
- eraseText: 10                   # delete N chars from focused field (omit N = clear all)
- pressKey: Enter                 # Enter | Backspace | Home | Tab | etc.
- hideKeyboard
- copyTextFrom: { id: "code_field" }   # capture into ${maestro.copiedText}
```

### Gestures / scrolling
```yaml
- scroll                          # one scroll down
- scrollUntilVisible:
    element:
      text: "Categories"          # scroll until this is on screen, then stop
    direction: DOWN
- swipe:
    direction: UP
    duration: 400
```

### Assertions — prove the outcome
```yaml
- assertVisible: "Good Morning, Tom!"
- assertVisible:
    id: "favorite_button"
- assertNotVisible: "Loading…"
- assertTrue: ${output.count > 0}
```
A flow with no assertion proves nothing. Always end a scenario on the assertion
that matches its expected result.

### Waiting (avoid flakiness)
```yaml
- waitForAnimationToEnd            # wait for animations/transitions to settle
- extendedWaitUntil:
    visible: "Home"
    timeout: 8000                  # ms — wait up to 8s for slow loads/network
```
Prefer `extendedWaitUntil` / `scrollUntilVisible` over fixed sleeps; they wait only
as long as needed and fail fast with a clear reason.

### Composition & repetition
```yaml
- runFlow: ../common/launch_clear_state.yaml   # reuse shared setup — DRY
- runFlow:
    when:
      visible: "Allow"                          # conditional sub-flow
    file: grant_permission.yaml
- repeat:
    times: 3
    commands:
      - tapOn: "Next"
```

### Capture for debugging
```yaml
- takeScreenshot: favorites_after_tap   # saved next to the report; cite path on failure
```

## Reusable patterns

**Clear-cache launch (common/launch_clear_state.yaml):**
```yaml
appId: ${APP_ID}
name: Launch app with clean state
---
- launchApp:
    clearState: true        # wipes app data → deterministic cold start
```

**Warm / with-cache launch (common/launch_keep_state.yaml):**
```yaml
appId: ${APP_ID}
name: Launch app keeping cached state
---
- launchApp                 # no clearState → cached data/session/onboarding flag survive
```
Use the clear-cache launch for first-run/onboarding and any test that must not depend
on prior state. Use the warm launch for persistence tests — "favorite survives
relaunch", "onboarding is skipped on second launch", offline cache, kept login. A
persistence test typically runs clear-state once to establish data, then relaunches
warm to assert it survived.

**Feature flow reusing it:**
```yaml
appId: ${APP_ID}
name: Favorite from list
tags: [favorite, smoke]
---
- runFlow: ../../common/launch_clear_state.yaml
- scrollUntilVisible: { element: { text: "Rice Egg Pork" }, direction: DOWN }
- tapOn: { id: "favorite_button", below: "Rice Egg Pork" }
- tapOn: "Favorites"
- assertVisible: "Rice Egg Pork"
```

## CLI

```bash
# Single flow / a whole directory (uses .maestro/config.yaml if present)
maestro test -e APP_ID=com.example.app flows/smoke/favorite.yaml
maestro test -e APP_ID=com.example.app flows/

# Select by tag
maestro test --include-tags smoke flows/
maestro test --exclude-tags slow flows/

# Machine-readable report (only when you want JUnit XML; not required for PASS/FAIL)
maestro test flows/ --format junit --output build/maestro/report.xml

# Pass variables into flows (${VAR})
maestro test -e USER_EMAIL=test@example.com flows/login.yaml

# Live re-run while editing
maestro test --continuous flows/favorite.yaml
```

**Exit codes:** `0` all passed · `1` one or more failed · non-zero otherwise.
Maestro needs a running emulator/device (`adb devices` to check on Android).
`maestro studio` opens an interactive inspector to discover ids/text on screen.
