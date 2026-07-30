# Maestro Commands Reference

Quick reference for mapping manual test steps to Maestro YAML commands.

## Table of Contents

- [App Lifecycle](#app-lifecycle)
- [Tap & Click](#tap--click)
- [Text Input](#text-input)
- [Scrolling](#scrolling)
- [Assertions](#assertions)
- [Waiting](#waiting)
- [Navigation](#navigation)
- [Flow Control](#flow-control)
- [Device Control](#device-control)
- [Evidence Capture](#evidence-capture)
- [AI-Powered](#ai-powered)
- [Selector Strategies](#selector-strategies)

---

## App Lifecycle

### launchApp

Launch the app under test. Use `clearState: true` to start fresh.

```yaml
# Simple launch
- launchApp

# Launch with cleared data (fresh install state)
- launchApp:
    clearState: true

# Launch a different app
- launchApp:
    appId: "com.other.app"
```

### stopApp

Stop the app without clearing state.

```yaml
- stopApp

# Stop a specific app
- stopApp:
    appId: "com.example.app"
```

### killApp

Force-kill the app process.

```yaml
- killApp

# Kill a specific app
- killApp:
    appId: "com.example.app"
```

### clearState

Clear app data without launching.

```yaml
- clearState

# Clear a specific app
- clearState:
    appId: "com.example.app"
```

---

## Tap & Click

### tapOn

Tap an element found by text, id, or other selectors.

```yaml
# By visible text
- tapOn: "Login"

# By text with regex (case-insensitive)
- tapOn:
    text: "(?i)sign in"

# By resource ID (regex)
- tapOn:
    id: "btn_login"

# By index (when multiple matches exist)
- tapOn:
    text: "Item"
    index: 0

# Tap at specific coordinates (percentage of screen)
- tapOn:
    point: "50%,50%"

# Optional tap (won't fail if element missing)
- tapOn:
    text: "Allow"
    optional: true
```

### doubleTapOn

Double-tap an element.

```yaml
- doubleTapOn: "Element text"

- doubleTapOn:
    id: "element_id"
```

### longPressOn

Long-press on an element.

```yaml
- longPressOn: "Element text"

- longPressOn:
    id: "element_id"
```

---

## Text Input

### inputText

Type text into the currently focused field.

```yaml
- inputText: "hello@example.com"
```

### eraseText

Delete characters from the currently focused field.

```yaml
# Erase 20 characters
- eraseText: 20

# Erase a lot to clear the field
- eraseText: 100
```

### pasteText

Paste text from clipboard.

```yaml
- pasteText
```

### copyTextFrom

Copy text from an element to clipboard.

```yaml
- copyTextFrom:
    id: "text_element"
```

### setClipboard

Set clipboard content directly.

```yaml
- setClipboard: "Text to paste"
```

### hideKeyboard

Dismiss the on-screen keyboard.

```yaml
- hideKeyboard
```

### pressKey

Press a hardware/software key.

```yaml
# Press Enter/Return
- pressKey: Enter

# Press Back (Android)
- pressKey: Back

# Press Home
- pressKey: Home

# Press Tab
- pressKey: Tab
```

### Common Pattern: Clear and Re-enter Text

```yaml
- tapOn:
    id: "input_name"
- eraseText: 100
- inputText: "New Value"
- hideKeyboard
```

---

## Scrolling

### scroll

Scroll the screen in a direction.

```yaml
# Scroll down
- scroll:
    direction: DOWN

# Scroll up
- scroll:
    direction: UP
```

### scrollUntilVisible

Scroll until a specific element becomes visible. Much more reliable than fixed scrolling.

```yaml
# Scroll down to find element by text
- scrollUntilVisible:
    element:
      text: "Save"
    direction: DOWN

# With timeout
- scrollUntilVisible:
    element:
      id: "footer_element"
    direction: DOWN
    timeout: 10000

# Scroll within a specific container
- scrollUntilVisible:
    element:
      text: "Target Item"
    direction: DOWN
    centerElement: true
```

### swipe

Swipe in a direction or between coordinates.

```yaml
# Swipe directions
- swipe:
    direction: LEFT
- swipe:
    direction: RIGHT
- swipe:
    direction: UP
- swipe:
    direction: DOWN

# Swipe between specific points
- swipe:
    start: "90%,50%"
    end: "10%,50%"
```

---

## Assertions

### assertVisible

Verify an element is visible on screen. This is your primary assertion command.

```yaml
# By text
- assertVisible: "Welcome back"

# By ID
- assertVisible:
    id: "welcome_message"

# With timeout
- assertVisible:
    text: "Loading complete"
    enabled: true
```

### assertNotVisible

Verify an element is NOT visible on screen.

```yaml
- assertNotVisible: "Error message"

- assertNotVisible:
    id: "error_banner"
```

### assertTrue

Assert a condition is true (typically used with JavaScript).

```yaml
- assertTrue:
    condition: "${output.status == 'success'}"
```

---

## Waiting

### waitForAnimationToEnd

Wait for all animations to finish. Essential after navigation or screen transitions.

```yaml
- waitForAnimationToEnd

# With custom timeout (ms)
- waitForAnimationToEnd:
    timeout: 5000
```

### extendedWaitUntil

Wait for a specific condition with a longer timeout. Use this for async operations like network requests.

```yaml
# Wait for element to appear
- extendedWaitUntil:
    visible:
      text: "Recipe Ready"
    timeout: 15000

# Wait for element to disappear
- extendedWaitUntil:
    notVisible:
      text: "Loading..."
    timeout: 10000
```

---

## Navigation

### back

Press the system back button.

```yaml
- back
```

### openLink

Open a URL or deep link.

```yaml
# Open URL in browser
- openLink: "https://example.com"

# Open deep link
- openLink: "myapp://recipe/123"
```

---

## Flow Control

### runFlow

Execute another flow file (subflow). Essential for code reuse.

```yaml
# Run a shared flow
- runFlow: shared/login.yaml

# Run with environment variables
- runFlow:
    file: shared/navigate.yaml
    env:
      TARGET_SCREEN: "Settings"

# Run conditionally
- runFlow:
    when:
      visible: "Login"
    file: shared/login.yaml
```

### repeat

Repeat a set of commands.

```yaml
# Repeat N times
- repeat:
    times: 3
    commands:
      - tapOn: "Add Item"
      - inputText: "Item"

# Repeat while condition is true
- repeat:
    while:
      visible: "Next"
    commands:
      - tapOn: "Next"
```

### retry

Retry commands if they fail.

```yaml
- retry:
    maxRetries: 3
    commands:
      - tapOn: "Submit"
      - assertVisible: "Success"
```

---

## Device Control

### setPermissions

Set app permissions.

```yaml
# Android
- setPermissions:
    permissions:
      android.permission.CAMERA: allow
      android.permission.ACCESS_FINE_LOCATION: allow

# iOS
- setPermissions:
    permissions:
      camera: allow
      location: always
```

### setLocation

Set device GPS location.

```yaml
- setLocation:
    latitude: 10.762622
    longitude: 106.660172
```

### setOrientation

Set screen orientation.

```yaml
- setOrientation: landscape
- setOrientation: portrait
```

### addMedia

Add media files to the device gallery.

```yaml
- addMedia:
    - path/to/image.jpg
```

### toggleAirplaneMode

Toggle airplane mode (Android only).

```yaml
- toggleAirplaneMode
```

---

## Evidence Capture

### takeScreenshot

Capture a screenshot with a label. Useful for test evidence.

```yaml
- takeScreenshot: "TC-001_step_3_result"
```

### startRecording / stopRecording

Record video of the test execution.

```yaml
- startRecording: "test_recording"
# ... test steps ...
- stopRecording
```

---

## AI-Powered

### assertWithAI

Use AI to verify visual or semantic conditions.

```yaml
- assertWithAI: "The login form is displayed with email and password fields"
```

### assertNoDefectsWithAI

Check for visual defects using AI.

```yaml
- assertNoDefectsWithAI
```

### extractTextWithAI

Extract text from screen using AI vision.

```yaml
- extractTextWithAI:
    query: "What is the total price?"
    outputVariable: "totalPrice"
```

---

## Selector Strategies

### By Text (most common)

```yaml
- tapOn: "Button Label"
- tapOn:
    text: "(?i)case insensitive"  # Regex supported
```

### By Resource ID

```yaml
- tapOn:
    id: "btn_submit"
- tapOn:
    id: ".*partial_id.*"  # Regex supported
```

### By Accessibility ID / Test ID

```yaml
- tapOn:
    testId: "submit-button"
```

### By Index (when multiple matches)

```yaml
- tapOn:
    text: "Item"
    index: 2  # Third match (0-indexed)
```

### By Point (coordinates)

```yaml
- tapOn:
    point: "50%,80%"  # Center horizontally, 80% from top
```

### Combined Selectors

```yaml
# Below another element
- tapOn:
    text: "Submit"
    below: "Form Title"

# Above another element
- tapOn:
    text: "Cancel"
    above: "Submit"

# Inside a container
- tapOn:
    text: "Delete"
    childOf:
      id: "item_container"
```

### Selector Priority (use in this order)

1. **`id`** — Most stable, survives UI changes
2. **`testId`** — Explicitly set for testing
3. **`text`** — Readable but may change with i18n
4. **`text` regex** — Flexible but less precise
5. **Point/coordinates** — Last resort, very fragile

---

## Test Step → Maestro Command Mapping

| Test Step Description | Maestro Command |
|----------------------|-----------------|
| "Open the app" | `launchApp` |
| "Tap on X button" | `tapOn: "X"` |
| "Enter text in field" | `tapOn: {id}` + `inputText: "value"` |
| "Clear the field" | `eraseText: 100` |
| "Scroll down to find X" | `scrollUntilVisible: {element: {text: "X"}}` |
| "Verify X is visible" | `assertVisible: "X"` |
| "Verify X is NOT visible" | `assertNotVisible: "X"` |
| "Go back" | `back` |
| "Wait for loading" | `extendedWaitUntil: {notVisible: {text: "Loading"}}` |
| "Long press on X" | `longPressOn: "X"` |
| "Swipe left" | `swipe: {direction: LEFT}` |
| "Take screenshot" | `takeScreenshot: "label"` |
| "Select from dropdown" | `tapOn: "dropdown"` + `tapOn: "option"` |
| "Toggle switch" | `tapOn: {id: "switch_id"}` |
| "Dismiss dialog" | `tapOn: "OK"` or `back` |
| "Allow permission" | `tapOn: "Allow"` or `setPermissions` |
