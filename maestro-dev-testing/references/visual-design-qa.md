# Visual and Design QA with Figma + Maestro

Use this reference when the user asks to test UI accuracy against Figma, responsive
behavior, font size, spacing, typography, clipping, density, or visual polish.

> **Doing the actual per-screen visual judgment?** The grid-overlay + vision method
> lives in `vision-ui-testing.md` — that's what reads each screenshot, scans it
> cell-by-cell, and turns findings into a PASS/FAIL/NEEDS_REVIEW verdict. This file
> covers the surrounding concerns: Figma baseline collection, the device/viewport
> matrix, and where exact-measurement checks belong. Use the two together: this file
> to plan and source baselines, `vision-ui-testing.md` to execute the review.

## What Maestro can and cannot prove

Maestro is an end-to-end driver. It is good at proving that a screen can be reached,
important UI is visible, interactions work, orientation changes do not break the flow,
and screenshots were captured from a real app/device.

Maestro is not a Compose layout inspector. It cannot directly assert runtime values such
as `fontSize = 16.sp`, `padding = 24.dp`, baseline alignment, or token bindings. Treat
those as design-review checks unless you also inspect the source or add Compose/screenshot
tests designed for exact layout measurement.

Use these status meanings in reports:

| Status | Meaning |
|--------|---------|
| PASS | Maestro assertion passed, or the vision scan found no defect and the screen matches intent/Figma within tolerance. |
| FAIL | The app reached the target screen, but the expected UI/visual behavior was not observed — including a **Critical** vision finding (overlap, clipping, off-screen, missing element). |
| NEEDS_REVIEW | Evidence captured and the vision scan found only **Minor** (subjective) issues, or exact font/spacing parity still needs Figma/human review. |
| PENDING | The check could not run because the required device, app install, Figma node, or environment was missing. |
| ERROR | The flow or environment failed before the intended check could complete. |

## Figma baseline collection

When the user provides a Figma URL, prefer a node-specific URL. If the URL does not contain
`node-id`, ask for the exact node URL before claiming design parity.

Collect only what you need:

1. Use `get_design_context` for the target node to understand structure, text, dimensions,
   and design intent.
2. Use `get_screenshot` for a visual baseline render. Keep the Figma node id in the testcase
   and report so evidence can be traced back to the design.
3. Use `get_variable_defs` when typography, color, or spacing tokens matter.
4. If the Figma design contains multiple breakpoint frames, map each frame to a device or
   viewport scenario explicitly.

## Device and viewport matrix

Only claim responsive coverage for profiles that actually ran. Default to this matrix when
the user does not specify devices and the environment can support them:

| Profile | Purpose |
|---------|---------|
| Phone portrait | Main user path and smallest common width. |
| Phone landscape | Orientation stress for height and horizontal layout. |
| Tablet or largest available emulator | Wide layout, multi-column behavior, and spacing density. |

If a profile is not available, keep the testcase in `report.md` as `PENDING` and include the
missing emulator/device reason.

## Planning visual QA cases

Each visual testcase should state:

- Figma source: file/node URL or node id.
- Screen state: route, data state, cache mode, and setup flow.
- Device profile: emulator/device name, orientation, and relevant resolution if known.
- Objective checks: Maestro assertions such as visible title, no blocking dialog, loaded state,
  and flow completion.
- Visual evidence: screenshot file name from `takeScreenshot`; optional screenshot assertion if
  the project maintains baselines.
- Review checks: font size, spacing, alignment, clipping, truncation, density, and token parity.

## Authoring Maestro flows for visual evidence

Use stable selectors to reach the screen, then wait for it to settle before taking evidence.

```yaml
appId: ${APP_ID}
name: Recipe detail visual QA - phone portrait
tags: [visual, recipe]
---
- runFlow: ../../common/launch_clear_state.yaml
- runFlow: ../../common/open_recipes_tab.yaml
- tapOn: "Rice Egg Pork"
- extendedWaitUntil:
    visible: "Rice Egg Pork"
    timeout: 8000
- waitForAnimationToEnd
- assertVisible: "Rice Egg Pork"
- takeScreenshot: VIS-01-recipe-detail-phone-portrait
```

Use `assertScreenshot` only when the project has accepted baseline images and a clear update
process. Screenshot diffs can be noisy because fonts, system rendering, status bars, locale,
dynamic content, and device density all affect pixels.

## Reporting visual results

In `RUN_REPORT.md`, include:

- Figma node/source used as the baseline.
- Device matrix and which profiles ran.
- Exact Maestro command.
- Screenshot paths for each visual testcase.
- Observations for responsive layout, font size, spacing, clipping, and alignment.
- Which checks are objective PASS/FAIL and which are `NEEDS_REVIEW`.

In `report.md`, keep one row per testcase/device profile. Put screenshot paths and Figma node
ids in `Result / evidence`, and put review instructions or fix recommendations in
`Notes / next action`.

## When to recommend another test layer

Recommend Compose UI tests, Paparazzi/Roborazzi-style screenshot tests, or source-level token
checks when the user needs exact automated checks for:

- Typography values (`sp`, font family, weight, line height).
- Padding/margin/size values in `dp`.
- Token binding parity with the design system.
- Stable pixel diffing across many screen sizes in CI.

Maestro should remain the real-device journey and evidence layer; exact layout measurement is
better handled closer to the UI framework.
