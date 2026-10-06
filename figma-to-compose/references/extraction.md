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

## The fifth step, and the one that gets skipped

`get_metadata` carries geometry and nothing else — no string, no fill, no asset, no
auto-layout. All of that is in `get_design_context`, and `figma_to_ir.py` cannot read that
format. One command converts it:

```bash
python3 scripts/context_to_ir.py --context raw/context.json --tree raw/context-tree.json \
    --texts raw/texts.json --styles raw/styles.json --assets raw/assets.json
```

Save the MCP response **verbatim** to `raw/context.json` — the JSON envelope
(`{"content": ["<code>", …]}`) is fine, so is the bare code in a `.tsx`. Do not hand-edit or
excerpt it; the parser needs the whole file to resolve helper components.

**This is not optional and it is not a formality.** Earlier versions of this document said
only "derive `texts.json` and `styles.json` from the design context" and left it to the
agent. On the first run whose brief did not repeat that instruction by hand, nobody did it,
`figma_to_ir.py` accepted the missing flags without complaint, and the IR came out as seven
boxes with every field null and `unsupported: 0`. The screen that came out of it lost all
eleven topic-card tints and every Figma asset — the nav bar shipped as five identical
Material house glyphs — while every later gate reported the code clean, correct and
measured.

A skill that routes the rich source *around* its own generator is worse than no skill at
all, because an agent with no skill reads `get_design_context` directly and at least sees
the colours. `figma_to_ir.py` now refuses to run without `--texts` and `--styles`, and
`ir_coverage_check.py` blocks between Phase 2 and Phase 3 if the IR carried less of the
design than the thresholds allow. Neither is a style preference.

### What `context_to_ir.py` recovers that hand-derivation misses

**The layout itself.** Figma's code *is* its auto-layout: `flex flex-col` is the direction,
`gap-[16px]` the item spacing, `px-[20px] py-[24px]` the padding, `items-center` /
`justify-between` the alignment, `w-full` / `flex-[1_0_0]` / `shrink-0` + `size-[24px]` the
fill / weight / fixed sizing, `absolute left-[12px] top-[5px]` an absolutely positioned
child. Earlier versions threw all of it away and re-derived layout from x/y — and got a
54dp button's direction wrong, a `justify-between` row's gap as "24.75", and every inset card
as a fixed `width(350.dp)`. The tree carries it as stated; `figma_to_ir.py --tree` uses it.

**Text that lives below its node.** Figma often puts the node id and font on a wrapper and
the string in an id-less child:

```jsx
<p className="font-['Roboto_Mono:Regular'] leading-[0] text-[11px] text-white" data-node-id="52:176">
  <span className="leading-[normal]">00:06.200</span>
  <span className="leading-[normal] text-[#8e9aa8]">{` / 00:17.000`}</span>
</p>
```

The old flat parser skipped any element whose body contained `<`, so this string never
reached the IR. The tree reads it as one text node with two `runs` (the second overriding the
colour), and inherits family/size/colour from ancestors the way CSS does.

**The full text style.** `font-['Inter:Semi_Bold']` → family `Inter`, weight 600;
`leading-[24px]` / `leading-[1.5]` / `leading-[normal]` → line height 24, 1.5×size, or
`auto`; `tracking-[-0.02em]` → letter spacing; `uppercase`, `text-center`,
`whitespace-nowrap`, `line-clamp-2`. None of these were carried before, and every one of them
changes how big a text box is.

**Effects and paint.** `bg-[rgba(0,0,0,0.8)]` keeps its alpha; `bg-white`, `text-white`
are colours too; gradients come from `bg-gradient-to-b from-[…] to-[…]` *and* from
`style={{ backgroundImage: "linear-gradient(91.5deg, …)" }}`; `shadow-[…]` and
`drop-shadow-[…]` become shadow lists with colour and alpha; `opacity-80`, per-corner
`rounded-tl-[16px]`, `border-[1.5px]`, `border-t`.

**Component instances.** A helper `function TopicCard({ variant = "Calm" })` used as
`<TopicCard variant="Spicy" data-node-id="5:8490" />` is expanded with that instance's props,
so its `isSpicy ? … : …` ternaries resolve to the instance's own arm — fill, text and child
ids. Conditions that cannot be resolved take the default arm, are listed in the tree's
`unresolvedConditions`, and the node keeps every arm under `variants`.

**Per-variant colour, when the component is not instantiated.** A component set selected on
its own comes back as parallel ternary chains keyed on the same condition names:

```jsx
id={isSpicy ? "node-5_7804" : isRelationship ? "node-5_7764" : "node-5_7744"}
className={`… ${isSpicy ? "bg-[#ffe9ea]" : isRelationship ? "bg-[#ecfdf5]" : "bg-[#fbeff5]"}`}
```

Joining the two chains on the condition is what turns eleven identical cards back into
eleven differently-tinted ones. Reading it by eye, an agent records the default arm and
drops the rest.

**Asset ownership.** An `<img>` has no node id of its own; it belongs to the element
wrapping it. Without that attribution nothing can later check that the `Image(` in the
generated Kotlin points at a downloaded Figma export rather than a stock glyph.

**CSS-variable fills.** `bg-[var(--pink\/pink-500,#fd75a7)]` carries the hex in the
fallback slot, with the `/` escaped. The hex is the value that matters.

## Assets: Figma exports SVG, Android wants vector drawable

This step has no default tool and it has now cost two runs. One shipped a bespoke five-icon
nav bar as five identical Material house glyphs; another stalled for two and a half hours
probing for a converter that was not installed. Neither failure was visible in any gate.

**Check what exists before planning around it.** On a bare macOS box, usually none of these:

```bash
for c in rsvg-convert magick convert inkscape; do command -v $c || echo "$c MISSING"; done
command -v npx   # usually present
```

Two routes, in order of preference:

1. **`npx -y svg2vectordrawable -i in.svg -o out.xml`** — produces real Android vector
   drawable XML, which is the correct target: it scales at every density and is what the
   platform wants. Needs network for the first package fetch.
2. **Ask Figma for a PNG instead.** `get_screenshot` on the icon node returns a raster. No
   tooling, no network beyond Figma. The icon stops being scalable, which is a real cost on
   a multi-density app — record it in `decisions.md` rather than letting it pass unnoticed.

**Never substitute a stock glyph.** `Icons.Default.Home` in place of the design's own icon
is the single most damaging silent failure in this pipeline, because the screen still looks
plausible. If no route produces the real asset, **leave the slot empty** and say so in the
report: a reviewer notices a hole immediately and never notices a wrong-but-reasonable icon.

A frame of any size carries more of these than it looks. One real screen needed **93 SVG and
66 PNG**. Budget for it, and convert in one batch rather than per icon.

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
