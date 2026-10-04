# UI IR v1

A deliberately **narrow** intermediate representation. It covers the subset of Figma that
maps cleanly onto Compose and refuses the rest, loudly.

The temptation is to make the IR general enough for any Figma file. Resist it — a general
IR becomes half a DOM spec, and the half you build is never the half the next design
needs. Cover what the project actually draws; everything else goes to `unsupported[]` with
its node id, where a human can see it.

## What v1 covers

| Figma | IR role | Compose |
|---|---|---|
| Auto-layout frame (vertical) | `container` + `direction: column` | `Column` |
| Auto-layout frame (horizontal) | `container` + `direction: row` | `Row` |
| Frame without auto-layout | `container` + `direction: stack` | `Box` |
| Text | `text` | `Text` |
| Rectangle / ellipse with fill | `surface` | `Box`/`Surface` with background |
| Vector / icon frame | `icon` | `Icon(painterResource(...))` |
| Image fill | `image` | `Image` |
| 1px-thin frame or rect | `divider` | `HorizontalDivider` |
| Instance of a component | `component` | the mapped composable |

## What v1 refuses

Boolean ops, masks, blend modes other than normal, rotation, non-uniform corner radii,
multiple fills on one node, inner shadows, text with mixed styles in one run, and anything
under a hidden layer. Each becomes:

```json
{ "id": "17:64", "name": "sec-title-edit", "reason": "mixed_text_styles" }
```

in `unsupported[]`. The generator emits a plain `// TODO: unsupported node` (R7 forbids the
node id in the comment; `unsupported[]` already carries it) at the
right place and moves on. It never invents an approximation silently.

## Document shape

```jsonc
{
  "schema": "ui-ir/v1",
  "source": {
    "fileKey": "jbLqAKuR0bpcnvJ8kX2D7z",
    "nodeId": "17:12",
    "name": "home",
    "fetchedAt": "2026-09-29T15:00:00Z"
  },
  "frame": { "width": 390, "height": 1315 },

  // Layers recognised as mock chrome, stripped from the tree, listed here so a reviewer
  // can see they were not silently dropped.
  "platformChrome": [
    { "id": "17:13", "name": "status-bar",              "handling": "statusBarsPadding" },
    { "id": "17:111", "name": "home-indicator-container","handling": "navigationBarsPadding" }
  ],

  "root":        { /* node */ },
  "assets":      [ { "id": "17:864", "name": "zap", "kind": "icon", "export": "ic_zap.xml" } ],
  "unsupported": [ { "id": "...", "name": "...", "reason": "..." } ],

  // Written by resolve_tokens.py, not by the extractor.
  "mapping": {
    "resolvedCount": 118,
    "unmapped": [ { "kind": "color", "raw": "#0B0F0D", "nodes": ["17:12"], "nearest": "surface", "distance": 41.2 } ]
  }
}
```

## Node shape

```jsonc
{
  "id": "17:28",
  "name": "stats-hero",
  "role": "container",

  "layout": {
    "direction": "column",
    "gap":     { "raw": 15, "token": "spacing.md", "snapped": true },
    "padding": { "top": 18, "end": 20, "bottom": 18, "start": 20,
                 "token": { "vertical": "spacing.md", "horizontal": "spacing.lg" } },
    "width":   "fill",          // "fill" | "wrap" | <number>
    "height":  "wrap",
    "align":   { "main": "start", "cross": "stretch" }
  },

  "style": {
    "fill":   { "raw": "#0F1511", "token": "colorScheme.surfaceContainerLow" },
    "radius": { "raw": 22,        "token": "radii.card" },
    "border": { "raw": "#1E2B22", "width": 1, "token": "colorScheme.outlineVariant" }
  },

  // role: "text" only
  "text": {
    "content": "TỔNG DUNG LƯỢNG ĐÃ TIẾT KIỆM",
    "style": { "size": 11, "weight": 600, "lineHeight": 13,
               "token": "typography.labelSmall" },
    "color": { "raw": "#7A8B80", "token": "colorScheme.onSurfaceVariant" },
    "maxLines": 1
  },

  "mapping": { "component": "ComposerCard", "via": "figmaHints:card", "confidence": 0.7 },

  "children": [ /* nodes */ ]
}
```

## `sourceContext`: where the content lives when the tree is a skeleton

The IR root carries `sourceContext` — the full `texts`, `styles` and `assets` maps from
`context_to_ir.py`, flat and keyed by node id. It is not a backup copy. On a screen built
from component instances it is **where most of the design actually is**, and generating from
the tree alone produces a correct-looking, empty screen.

`get_metadata` does not expand component instances. Eleven "Topic card" instances come back
as eleven childless sibling nodes with geometry and nothing else. Measured on one real frame:

```
text    tree 12 + sourceContext 15 = 27/27
style   tree  6 + sourceContext 88 = 94/94
asset   tree  1 + sourceContext 25 = 26/26
```

Six of ninety-four styled nodes were in the tree. The per-instance tint, icon and label for
all eleven cards existed only in `sourceContext`, and `ir_coverage_check.py` reported 100%
— honestly, because the content did arrive. It now prints a note when the tree's share is
this thin, so nobody discovers it the hard way.

**What this costs you.** `sourceContext` is flat, so it has no notion of "card 3 of 11".
Rebuilding that grouping means reading `raw/<node>/context.json` directly — the generated
JSX names each variant and its colour in parallel ternary chains, and the node ids of a
repeated component usually advance by a fixed stride. Verify the stride against the design
rather than assuming it; an off-by-one here silently assigns the wrong colour to every card.

**What this does not change.** The tree is still what you lay out from — direction, gap,
padding and geometry are all there and all derived. `sourceContext` supplies what goes
*inside* the boxes. Read both.

## The invariant that makes the gate work

**Every styled value carries both `raw` and `token`.** `raw` is what Figma said; `token` is
what the project calls it. `token: null` is not an error in the IR — it is a fact, and
`resolve_tokens.py` collects every one of them into `mapping.unmapped`.

That is the whole point of the IR. Without the pair, you cannot tell "the design uses
16dp, which is `spacing.md`" from "the design uses 15dp and nobody noticed" — and the
second one is how a codebase accumulates 40 near-identical spacings.

`snapped: true` marks a value that was **not** an exact token match but fell within
`tolerance.snapDistance` and was pulled to the nearest token. Snapping is how a design
drawn at 15dp becomes `spacing.md` instead of a new token. Every snap is recorded so a
reviewer can see the pipeline made a decision, and the report totals them: a frame with
80 snaps is a design that was not drawn on the project's grid, which is worth saying out
loud rather than absorbing.

## Reading order

The tree is emitted in **visual order** (top-to-bottom, then left-to-right), not in Figma's
z-order. Compose reads as a document, and a generator that follows z-order produces a file
whose structure nobody can match against the design.
