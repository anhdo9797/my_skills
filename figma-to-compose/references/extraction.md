# Phase 1 — Extraction

Everything comes from Figma MCP. Save each response to `raw/` before processing it, so a
re-run of Phase 2 costs nothing and the inputs stay auditable.

## The four calls

```
get_metadata(fileKey, nodeId)        → raw/metadata.xml
get_variable_defs(fileKey, nodeId)   → raw/variables.json
get_design_context(fileKey, nodeId)  → raw/context.json
get_screenshot(fileKey, nodeId, maxDimension=<2× frame width>) → raw/design.png
```

Extract `fileKey` and `nodeId` from the URL:
`figma.com/design/<fileKey>/<name>?node-id=17-12` → `fileKey=<fileKey>`, `nodeId=17:12`
(the dash becomes a colon).

## What each call is for

**`get_metadata` is the geometry source.** It returns every node's id, name, type, x, y,
width, height as XML. This is the backbone of the IR — absolute positions let the
extractor derive gaps and padding by subtraction, which is more reliable than trusting
auto-layout properties that may not exist on hand-positioned frames.

**`get_variable_defs` is the token source when it exists.** On a file with a proper
variable set you get `{"color/surface/base": "#0B0F0D"}` and token resolution becomes a
lookup. **On most real files it returns `{}`** — the design was drawn with raw values.
That is not an error and not a blocker; it means `resolve_tokens.py` falls back to
value-matching against the adapter's palette. Record which mode was used in the report,
because value-matching is the mode that produces `snapped` values and needs review.

**`get_design_context` is the style source** — fills, strokes, typography, effects, and
the text content. Heavier than the other calls; it is also the call the Figma plugin skill
`figma-design-to-code` gates on, so load that skill before calling it.

**`get_screenshot` is the measurement baseline**, not documentation. Request it at
**2× the frame width** so the spacing and typography audits have pixels to measure — a 1×
export beside a 3× device screenshot throws away real sensitivity (see
`maestro-test-executor/references/ui-metrics.md`). The URL it returns is short-lived;
`curl` it to `raw/design.png` immediately.

## Platform chrome

A mock frame usually carries the device's chrome as real layers — status bar with a fake
`9:41`, signal/wifi/battery icons, a home indicator pill, sometimes a fake keyboard. These
are **not content**. The extractor strips them into `platformChrome[]` by name match:

```
status-bar, statusbar, status bar, ios-*, android-status-*,
home-indicator*, nav-bar-ios, notch, dynamic-island, keyboard
```

and records the Compose handling (`statusBarsPadding`, `navigationBarsPadding`). Two
failure modes this prevents: reproducing a fake `9:41` clock as a `Text`, and measuring
the design's total height against a device screenshot whose real status bar is a different
height.

**A bottom tab bar is not chrome.** It looks like chrome and it is app content — it stays
in the tree. The rule is: drawn by the OS → chrome; drawn by the app → content.

## Multiple states

One frame is one state. A screen with loading / empty / error / content states needs one
`nodeId` per state, extracted separately into `ir/<state>.ui.json`. Do not try to infer
the empty state from the populated one — the design usually differs by more than removing
rows, and inferring it is how a pipeline invents UI that no designer drew.

## get_metadata is depth-bounded; plan for stub responses

`get_metadata` returns a bounded tree. When the Figma frame you need is deeper than the
budget, it comes back as a self-closing stub with no children — and it looks like valid
output.

**Real example:** Against file `CY141mXMtUzL6qWmhosLlh`:

- `get_metadata(fileKey, "5-8468")` (a section) returned its 7 child frames as stubs,
  self-closing, no children
- `get_metadata(fileKey, "5-8469")` (one of those frames, the screen to implement)
  returned: `<frame id="5:8469" name="Connect" x="130" y="151" width="390" height="1017" />`
  — no children at all
- `get_metadata(fileKey, "5-8470")` (the direct child of 5:8469) returned a correct, fully
  nested tree about 4 levels deep

**How to tell a stub from a leaf node:**
A stub is self-closing and has no children, but its Figma screenshot plainly has content.
A real leaf node is a text or vector — primitive types that have no children by design.

**The descend-and-stitch procedure:**
When a parent comes back shallow but you know it has content, call `get_metadata` on each
of its children (by id). Then hand-assemble one well-formed `metadata.xml` whose root is
your target frame, integrating the deeper responses beneath it.

**Fidelity requirement:** The stitched output must stay faithful to Figma — same ids,
same x/y/w/h, no invented nodes. The IR will derive layout from geometry, and a wrong
coordinate silently becomes wrong Compose.

## Establishing Figma access: call, don't ping

To prove Figma MCP is ready, **make one cheap real call against the target node**, not a
port check or process check. Call `get_metadata` on the node you are about to extract. If
it returns a valid tree (stub or full), the MCP works. If it fails, stop.

**Wrong signal:** A task might tell you to check whether the Figma Desktop MCP server's
TCP port `127.0.0.1:3845` is open. This port proves nothing — a project can wire to any
Figma MCP transport (desktop, remote, different instance), so an open or closed port says
nothing about your actual capability.

**Real example:** In a production run, the port stayed closed the entire time, and the
worker polled it for eight minutes before nearly aborting with `EXTRACTION FAILED`. The
Figma MCP was working perfectly — it was just a different instance, not the desktop one.

**The correct test:** `get_metadata(fileKey, targetNodeId)` against the exact frame you
will extract. The response is your readiness signal:

- Valid tree (any depth, even a stub) → proceed
- Failed call → stop and diagnose the MCP connection

A stub response (see above) is **not** a failure signal. It is a valid response that needs
the descend-and-stitch procedure.
