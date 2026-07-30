# Maestro Test Executor — Technical Documentation

> A skill that converts a QA test plan into Maestro YAML flows, runs each test case immediately, validates UI against the Figma design, and produces a consolidated report.
> Designed for QA testers — no source code reading required.

---

## 1. Overview — Mindmap

```mermaid
mindmap
  root((Maestro Test Executor))
    Input
      Test case list
      App ID + Platform
      Feature name
      Figma URL (optional)
      PRD / Spec (optional)
    Phases
      Phase 1: Gather Input
      Phase 2: Scan Existing Flows
      Phase 3: Analyze Test Cases
      Phase 4: Generate & Execute
      Phase 5: UI Validation
      Phase 6: Report
    Output
      YAML flows (testcase/)
      Selector catalog (selectors.md)
      Screenshots (report/screenshots/)
      Baseline + masks (report/baseline/)
      Living resumable report (report/report.md)
    References
      selectors-and-inspection.md
      yaml-flows.md
      ui-validation.md
      reporting.md
      maestro_commands.md
    Scripts
      filter_hierarchy.py
      compare_screenshots.py
```

---

## 2. Main flow — 6 Phases

```mermaid
flowchart TD
    A([📋 Test Plan\n+ Documents]) --> P1

    P1["**Phase 1: Gather Input**\n• App ID, Platform, Feature name\n• Session scope (P0 / P1 …) + resume check\n• Figma URL if UI TCs exist\n• Read PRD/Spec to clarify ambiguous steps"]
    P2["**Phase 2: Scan Existing Flows**\n• Scan .maestro/<app-id>/\n• Build selector catalog\n• Find shared flows to reuse"]
    P3["**Phase 3: Analyze Test Cases**\n• Classify: 🔧 Functional / 🎨 UI\n• Classify: ✅ Auto / ⚠️ Partial / ❌ Skip\n• Map steps → Maestro commands\n• Seed report board (all TCs = PENDING)\n• Present classification table to user"]
    P4["**Phase 4: Generate → Execute**\n• Reuse/write YAML 1 TC → run → upsert result → next TC\n• No batch-write"]
    P5["**Phase 5: UI Validation**\n• Authoring (Agent, once): Figma → assertions + baseline\n• Regression (no Agent): Maestro + diff script"]
    P6["**Phase 6: Report (resumable)**\n• Upsert rows by TC id into report.md\n• Full screenshot paths + FAIL repro steps\n• One living report + Session Log, announce"]

    P1 --> P2 --> P3 --> P4
    P4 --> P5_check{UI TCs?}
    P5_check -- Yes --> P5 --> P6
    P5_check -- No --> P6
    P6 --> Z([✅ Report updated])
```

---

## 3. Test Case Classification

```mermaid
flowchart TD
    A([TC from test plan]) --> B{Check type?}

    B -- "Behavior\n(tap, input, assert)" --> F[🔧 Functional]
    B -- "Appearance\nmatches Figma" --> U[🎨 UI Validation]

    F --> F1{Automatable?}
    F1 -- "✅ Clear" --> FA[Automatable\n→ Enter Phase 4 loop]
    F1 -- "⚠️ Needs external setup" --> FP[Partially automatable\n→ Note in report]
    F1 -- "❌ Manual only" --> FS[Skip\n→ ⏭️ SKIP in report]

    U --> U1{Figma URL\n+ screen reachable?}
    U1 -- Yes --> UA["Automatable\n→ Phase 4: capture flow\n→ Phase 5: assert + diff"]
    U1 -- No --> US[Skip\n→ ⏭️ SKIP in report]

    style F fill:#3B5BDB,color:#fff
    style U fill:#7950F2,color:#fff
    style FA fill:#0CA678,color:#fff
    style UA fill:#0CA678,color:#fff
    style FS fill:#868E96,color:#fff
    style US fill:#868E96,color:#fff
    style FP fill:#F76707,color:#fff
```

---

## 4. Phase 4 — Generate → Execute Loop

```mermaid
flowchart TD
    START([Start next in-scope TC still ⬜ PENDING]) --> W["① Analyze steps from test plan"]
    W --> Y["② Reuse or write YAML flow\n(see yaml-flows.md)"]
    Y --> C["③ File keyed to TC id:\ntestcase/TC-XXX_name.yaml"]
    C --> R["④ Run:\nmaestro test --test-output-dir=... TC-XXX.yaml"]
    R --> CHK{Result?}

    CHK -- PASS --> REC_P["⑤ Upsert ✅ PASS row\n+ full screenshot path"]
    CHK -- FAIL --> ERR["⑤ Read error\ngrep commands-*.json"]
    ERR --> FIX["Fix YAML\n(selector? timeout? nav?)"]
    FIX --> RE["Re-run"]
    RE --> CHK2{Result?}
    CHK2 -- PASS --> REC_P
    CHK2 -- FAIL --> REC_F["Upsert ❌ FAIL row\n+ Failed Test Details (repro + paths)"]

    REC_P --> NEXT{More TCs?}
    REC_F --> NEXT
    NEXT -- Yes --> START
    NEXT -- No --> DONE([Go to Phase 5/6])

    style CHK fill:#1C2333,color:#fff
    style CHK2 fill:#1C2333,color:#fff
    style REC_P fill:#0CA678,color:#fff
    style REC_F fill:#D9480F,color:#fff
```

---

## 5. UI Validation — Two-tier model

> **Core principle:** the Agent participates **only once, at authoring time**. Every later regression run works with no Agent.

```mermaid
flowchart LR
    subgraph AUTHORING ["🟣 Authoring — Agent participates (once)"]
        direction TB
        A1["Fetch Figma design\nvia Figma MCP get_screenshot"]
        A2["Analyze the screen:\n• Static elements → Tier 1\n• Dynamic elements → mask\n• Chrome → ignore"]
        A3["Tier 1: Write assertions\ninto the YAML flow"]
        A4["Tier 2 (optional):\nApprove baseline screenshot\nCreate masks.json sidecar"]
        A1 --> A2 --> A3
        A2 --> A4
    end

    subgraph REGRESSION ["🟢 Regression — No Agent"]
        direction TB
        R1["Run capture flow\n(navigate → waitForAnimation\n→ takeScreenshot)"]
        R2["Tier 1: Maestro runs\nassertVisible / assertNotVisible\n(deterministic)"]
        R3["Tier 2 (if baseline exists):\npython3 compare_screenshots.py\nbaseline.png actual.png --masks-file"]
        R4{Both tiers pass?}
        R5[✅ TC PASS]
        R6[❌ TC FAIL\n+ evidence link]
        R1 --> R2
        R1 --> R3
        R2 --> R4
        R3 --> R4
        R4 -- Yes --> R5
        R4 -- No --> R6
    end

    AUTHORING -->|"Assertions baked\ninto YAML\n+ baseline.png\n+ masks.json"| REGRESSION

    style AUTHORING fill:#F3F0FF,stroke:#7950F2
    style REGRESSION fill:#EBFBEE,stroke:#0CA678
```

---

## 6. Three screen bands — UI comparison logic

```mermaid
flowchart TD
    subgraph SCREEN ["Actual screen"]
        TOP["🚫 STATUS BAR\n(real clock, battery, signal)\n→ ALWAYS IGNORE\n--ignore-top"]
        MID["✅ CONTENT AREA\n→ COMPARE\nDecides PASS/FAIL"]
        BOT["⚠️ BOTTOM BAND\n• OS nav (gesture/3-button) → IGNORE\n• App tab bar → COMPARE if in design\n--ignore-bottom (OS strip only)"]
    end

    MID --> CLS{Classify element}
    CLS -- "Static / Structural\n(label, button text, icon,\nlayout, color, heading)" --> ST["→ Tier 1: assertVisible\n→ Tier 2: comparison region"]
    CLS -- "Dynamic / Data-driven\n(API images, list rows,\navatar, count, price, date)" --> DY["→ Do not assert content\n→ Tier 2: add mask\n--mask x1,y1,x2,y2"]

    style TOP fill:#FFE3E3,stroke:#C92A2A
    style MID fill:#EBFBEE,stroke:#0CA678
    style BOT fill:#FFF9DB,stroke:#F59F00
    style ST fill:#D0EBFF,stroke:#1971C2
    style DY fill:#FFE8CC,stroke:#E8590C
```

---

## 7. Selector Resolution — Priority order

```mermaid
flowchart TD
    Q([Need a selector for an element]) --> S1

    S1["1️⃣ Existing YAML flows\n(selectors proven against the real app)"]
    S2["2️⃣ Selector catalog\n(.maestro/<app-id>/selectors.md)"]
    S3["3️⃣ Supporting docs / Figma\n(label text from the design)"]
    S4["4️⃣ Live inspection — filter script\nmaestro hierarchy | python3 scripts/filter_hierarchy.py\n(~1-5k tokens, not 250k)"]
    S5["5️⃣ Live inspection — subagent\n(for complex screens)"]
    S6["6️⃣ Regex fallback\ntext: '(?i)edit'"]
    S7["7️⃣ Ask the user\n(never guess)"]

    S1 -- "Found ✅" --> DONE([Use this selector\nRecord it in the catalog])
    S1 -- "Not present" --> S2
    S2 -- "Found ✅" --> DONE
    S2 -- "Not present" --> S3
    S3 -- "Found ✅" --> DONE
    S3 -- "Unclear" --> S4
    S4 -- "Found ✅" --> DONE
    S4 -- "Too complex" --> S5
    S5 -- "Found ✅" --> DONE
    S5 -- "Still unsure" --> S6
    S6 --> DONE
    S1 -- "Nothing at all" --> S7

    style S1 fill:#0CA678,color:#fff
    style S2 fill:#0CA678,color:#fff
    style DONE fill:#1971C2,color:#fff
    style S7 fill:#F76707,color:#fff

    note1["❌ NEVER:\nRead a raw inspect_screen dump\nRead hierarchy_*.json directly\nRead app source (Kotlin/Swift/Dart)"]
```

---

## 8. Directory structure

```mermaid
mindmap
  root(.maestro/<app-id>/)
    config.yaml
    selectors.md [selector catalog by screen]
    common/
      launch_clear_state.yaml
      login.yaml
    <feature-name>/
      testcase/ [1 file = 1 TC, keyed to TC id]
        TC-001_name.yaml
        TC-002_name.yaml
      flow/ [shared navigation flows]
        navigate_to_screen.yaml
      report/
        report.md [THE one living report - updated in place every session]
        screenshots/ [takeScreenshot output]
        figma/ [Figma exports at authoring time]
        baseline/ [approved baseline images]
          TC-010.png
          TC-010.masks.json
        diff/ [heatmaps on Tier 2 failure]
        YYYY-MM-DD_HHmm/ [maestro --test-output-dir logs, one dir per run]
```

---

## 9. Report structure (one living, resumable file)

```mermaid
mindmap
  root(report.md - one file per feature)
    Header
      App ID + Platform
      Feature name
      Device / OS / Build [for Environment when logging bugs]
      Last updated
    Summary [cumulative across all sessions]
      Total planned / Executed / Pending
      Passed / Failed / Skipped
      Pass rate + Progress X/60
      "This session" line
    Test Results Table [= progress board]
      Columns: Name | Priority | Step | Status | Evidence | Session
      Status: ⬜ PENDING / ✅ PASS / ❌ FAIL / ⏭️ SKIP / 🔄 RETRY
      Upsert by TC id - never overwrite other sessions
      Evidence: link + full path
    Failed Test Details [= handoff to bug logging]
      Priority + Suggested severity
      Environment
      Steps to Reproduce [from clean state]
      Expected vs Actual
      Screenshots [absolute paths]
      Reproduction flow [YAML path]
    UI Validation Details
      Tier 1 / Tier 2 verdict
    Session Log [audit trail of each session]
    Recommendations
```

---

## 9b. Multi-session / Resume — running a large plan in priority slices

> A 60-case plan across P0→P4: each session runs one slice (S1=P0, S2=P1 …). One living report + one YAML per TC id, updated in place.

```mermaid
flowchart TD
    START([Start a new session]) --> CHK{report.md\nalready exists?}
    CHK -- No --> SEED["Seed board:\nwrite ALL TCs = ⬜ PENDING\n(every priority)"]
    CHK -- Yes --> READ["Read report.md\n→ learn ✅/❌/⬜\n→ pick up Device/OS/Build"]
    SEED --> SCOPE
    READ --> SCOPE["Determine session scope\n(e.g. P1)"]
    SCOPE --> LOOP["For each in-scope TC still ⬜:\nreuse/write YAML → run"]
    LOOP --> UP["Upsert row by TC id\n(don't touch other sessions' rows)\n+ full screenshot path"]
    UP --> FAIL{FAIL?}
    FAIL -- Yes --> DET["Write Failed Test Details:\nrepro steps + expected/actual\n+ absolute screenshot paths"]
    FAIL -- No --> AGG
    DET --> AGG["Recompute Summary\n+ append Session Log"]
    AGG --> ANN["Announce:\nran/✅/❌ + cumulative\n+ failures + next session scope"]
    ANN --> DONE([Next session → P2 …])

    style SEED fill:#868E96,color:#fff
    style READ fill:#1971C2,color:#fff
    style UP fill:#0CA678,color:#fff
    style DET fill:#D9480F,color:#fff
    style ANN fill:#7950F2,color:#fff
```

---

## 10. Reference Map

| Situation | Read file |
|-----------|-----------|
| Need an unknown selector | `references/selectors-and-inspection.md` |
| Write / fix a YAML flow | `references/yaml-flows.md` |
| Author a UI TC (Figma → assertions + baseline) | `references/ui-validation.md` |
| Produce / update the report, or resume a session | `references/reporting.md` |
| Find the right Maestro command | `references/maestro_commands.md` |
| Compress a hierarchy dump | `scripts/filter_hierarchy.py` |
| Run a visual baseline diff | `scripts/compare_screenshots.py` |

---

## 11. Key Anti-Patterns

| ❌ Avoid | ✅ Instead |
|---------|-----------|
| Read a raw `inspect_screen` dump | `filter_hierarchy.py` or a subagent |
| Write all YAML first, then run | 1 TC → run → fix → next TC |
| Hardcoded `sleep: 5000` | `waitForAnimationToEnd` / `extendedWaitUntil` |
| Read app source code | YAML flows + MCP inspect + docs |
| Agent in the regression loop | Tier 1 assertions + Tier 2 diff script |
| Flag status bar / API images as bugs | Mask chrome, don't assert dynamic content |
| Re-inspect the same screen repeatedly | Persist to `selectors.md`, read it back |
| Index-based selector | `id`, `testId`, or `text` |
| `--debug-output` | Always use `--test-output-dir` |
| A new timestamped report every session / overwriting the report | One living `report.md`, upsert rows by TC id |
| Duplicating YAML per session (`TC-017_v2.yaml`) | One YAML per TC id, edit in place, tag by priority |
| Screenshot path as bare filename / relative link | Absolute path in Failed Test Details |
| A FAIL row with only "element not found" | Failed Details: repro steps + expected/actual + path (foundation for bug logging) |
