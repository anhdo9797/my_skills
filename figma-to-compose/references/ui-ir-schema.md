# UI IR v2

A deliberately **narrow** intermediate representation. It covers the subset of Figma that
maps cleanly onto Compose and refuses the rest, loudly.

The temptation is to make the IR general enough for any Figma file. Resist it — a general
IR becomes half a DOM spec, and the half you build is never the half the next design
needs. Cover what the project actually draws; everything else goes to `unsupported[]` with
its node id, where a human can see it.

**What changed from v1.** v1 read only `get_metadata` geometry and a flat colour/size map,
so it could not say *how* a box sizes, what its line height is, or that it glows — and the
generator filled those gaps by guessing. v2 is built from two sources: geometry from the
metadata (for verification) and the design's intent from the context tree (for generation).
Every field below that v1 lacked is one a real run got wrong.

## What v2 covers

| Figma | IR | Compose |
|---|---|---|
| Auto-layout frame (vertical / horizontal / grid) | `container`, `direction: column \| row \| grid` | `Column` / `Row` / `LazyVerticalGrid` or `FlowRow` |
| Frame without auto-layout | `container`, `direction: stack` (or a geometry guess) | `Box` |
| Hug / fill / fixed sizing | `layout.width`, `layout.height`: `"wrap"` \| `"fill"` \| number | nothing / `fillMaxWidth()` / `width(n.dp)` |
| Fill on the main axis of a row/column | `layout.weight` | `Modifier.weight(w)` |
| Absolute-positioned child | `layout.position: {top, start, end, bottom}` | child of a `Box`, `Modifier.offset` / `align` |
| Text | `text` — content, full style, `runs` for mixed styles | `Text` / `AnnotatedString` |
| Solid fill, with alpha | `style.fill: {raw, alpha?}` | `background(Color(…).copy(alpha))` |
| Linear gradient | `style.gradient: {angle, stops[]}` | `Brush.linearGradient` |
| Drop shadow / layer shadow | `style.shadows[]`, `style.dropShadows[]` | `Modifier.shadow(…, ambientColor, spotColor)` or a drawn glow |
| Corner radius, per corner | `style.radius`, `style.corners: {tl,tr,br,bl}` | `RoundedCornerShape(…)` |
| Stroke | `style.border: {raw, width, sides?, style?}` | `border(width, color, shape)` / a side line |
| Layer opacity, blur | `style.opacity`, `style.blur`, `style.backgroundBlur` | `alpha()`, `blur()` |
| Exported vector / image | `icon` / `image` + `assets[]` | `Icon(painterResource)` / `Image` with `contentScale` |
| Image fill behind content | `style.backgroundImage` | `Box { Image(…, Crop); content }` |
| 1px-thin frame or rect | `divider` | `HorizontalDivider` / `VerticalDivider` |
| Component instance | `mapping.designComponent` + `props` (from the context) | the mapped composable |

## What v2 refuses

Boolean ops, masks, blend modes other than normal, and anything under a hidden layer
(Figma omits hidden layers from the context). Each becomes:

```json
{ "id": "17:64", "name": "badge-glow", "reason": "blend_screen" }
```

in `unsupported[]`. The generator emits a plain `// TODO: unsupported node` (R7 forbids the
node id in the comment; `unsupported[]` already carries it) at the right place and moves on.
It never invents an approximation silently.

Mixed-style text is **no longer refused** — it arrives as `text.runs`. Rotation is recorded
in `style.rotation`; apply it with `Modifier.rotate` or say in `decisions.md` why not.

## Document shape

```jsonc
{
  "schema": "ui-ir/v2",
  "source": { "fileKey": "jbLqAKuR0bpcnvJ8kX2D7z", "nodeId": "17:12", "name": "home" },
  "frame": { "width": 390, "height": 1315 },
  "fonts": ["Inter", "Roboto Mono"],          // bundle every one of these, or report it

  // Mock chrome stripped from the tree, listed so a reviewer can see it was not lost.
  "platformChrome": [
    { "id": "17:13", "name": "status-bar", "handling": "statusBarsPadding" }
  ],

  "root":        { /* node */ },
  "assets":      [ { "id": "17:864", "name": "zap", "kind": "icon",
                     "export": "https://www.figma.com/api/mcp/asset/….svg", "ext": "svg" } ],
  "sourceContext": { "texts": {…}, "styles": {…}, "assets": [ … ] },   // flat fallback
  "unsupported": [ { "id": "...", "name": "...", "reason": "..." } ],
  "mapping": { "resolvedCount": 118, "unmapped": [ … ] }               // resolve_tokens.py
}
```

## Node shape

```jsonc
{
  "id": "17:28",
  "name": "stats-hero",
  "role": "container",              // container | text | icon | image | surface | divider | component
  "rect": { "x": 20, "y": 112, "w": 350, "h": 150 },   // design geometry; absent on grafted nodes

  "layout": {
    "layoutSource": "auto-layout",  // "auto-layout": read from the design, exact
                                    // "geometry":    derived from x/y — a guess, check it
    "direction": "column",
    "gap":     { "raw": 14, "token": null },
    "spacing": [12, 20, 12],        // geometry only: per-gap values when they disagree
    "padding": { "top": 18, "end": 20, "bottom": 18, "start": 20, "token": null },
    "align":   { "main": "start", "cross": "start" },  // main: start|center|end|spaceBetween…
    "width":   "fill",              // "fill" | "wrap" | <dp>
    "height":  "wrap",
    "weight":  1,                   // fills the parent's main axis
    "margin":  { "start": 20, "end": 20 },   // geometry only: fill, inset symmetrically
    "position": { "top": 0, "start": 0, "bottom": 0 },  // absolutely positioned in its parent
    "aspectRatio": 1,
    "clip": true,
    "selfAlign": "stretch"
  },

  "style": {
    "fill":     { "raw": "#0F1511", "alpha": 0.8, "token": null },
    "gradient": { "type": "linear", "angle": 180,
                  "stops": [ { "raw": "#0F3326", "token": null, "position": 0 },
                             { "raw": "#0A2B1E", "token": null, "position": 1 } ] },
    "radius":   { "raw": 20, "token": null },
    "corners":  { "tl": 16, "tr": 0, "br": 0, "bl": 16 },
    "border":   { "raw": "#00DC82", "token": null, "width": 1, "sides": ["top"] },
    "shadows":     [ { "x": 0, "y": 4, "blur": 12, "spread": 0,
                       "color": { "raw": "#000000", "alpha": 0.3, "token": null } } ],
    "dropShadows": [ { "x": 0, "y": 4, "blur": 10, "spread": 0,
                       "color": { "raw": "#00DB82", "alpha": 0.12, "token": null } } ],
    "opacity": 0.8
  },

  // role: "text"
  "text": {
    "content": "00:06.200 / 00:17.000",
    "style": { "fontFamily": "Roboto Mono", "fontStyle": "Regular", "size": 11, "weight": 400,
               "lineHeight": 16,          // dp; "auto" = the font's own line height
               "letterSpacing": -0.36,    // dp (px); 0/absent = none
               "token": null },
    "color": { "raw": "#FFFFFF", "token": null },
    "runs": [ { "text": "00:06.200" },
              { "text": " / 00:17.000", "color": { "raw": "#8E9AA8", "token": null } } ],
    "align": "center", "textCase": "upper", "decoration": "underline",
    "singleLine": true, "ellipsis": true, "maxLines": 2,
    "lines": 1                            // rect.h / lineHeight — how many lines the design drew
  },

  "mapping": { "designComponent": "TopicCard", "props": { "variant": "Spicy" } },
  "children": [ /* nodes */ ]
}
```

A `run` lists only what differs from the node's own text style.

## Instances and grafted nodes

`get_metadata` does not expand component instances: eleven "Topic card" instances come back
as eleven childless nodes. The context tree has their content, so `figma_to_ir.py --tree`
**grafts** each instance's subtree under it, with Figma's own instance-child ids
(`I5:8490;5:7750`) so two cards never share an id.

Grafted nodes have **no `rect`** — Figma gave no geometry for them. `layout_assert.py` counts
them as unverified, not passing. To measure them, `get_metadata` the instance node itself and
stitch its children in (`references/extraction.md`, *descend-and-stitch*).

## `sourceContext`: the flat fallback

The IR root still carries the flat `texts`, `styles` and `assets` maps from
`context_to_ir.py`, keyed by node id. With `--tree` the tree carries nearly everything and
this is only a safety net — `ir_coverage_check.py` counts what reached the tree and what only
reached `sourceContext`. Without `--tree` (v1 behaviour) it is where most of an
instance-heavy screen's content lives, and rebuilding "card 3 of 11" from it is manual and
error-prone. Use `--tree`.

## The invariant that makes the gate work

**Every styled value carries both `raw` and `token`.** `raw` is what Figma said; `token` is
what the project calls it. `token: null` is not an error in the IR — it is a fact, and
`resolve_tokens.py` collects every one of them into `mapping.unmapped`.

That is the whole point of the IR. Without the pair, you cannot tell "the design uses
16dp, which is `spacing.md`" from "the design uses 15dp and nobody noticed" — and the
second one is how a codebase accumulates 40 near-identical spacings.

`snapped: true` marks a value that was **not** an exact token match but fell within
`tolerance.snapDistance` and was pulled to the nearest token. Every snap is a deliberate
loss of fidelity, recorded so a reviewer can see it; a frame with 80 snaps was not drawn on
the project's grid, which is worth saying out loud rather than absorbing. For a screen
where the exact rhythm matters, use `--pixel-perfect` (see `pixel-fidelity.md`).

## Reading order

Children are emitted in **layout order**: the design context's order for auto-layout
containers (that *is* the auto-layout order), left-to-right for a geometry row,
top-to-bottom for a geometry column, and top-to-bottom-then-left-to-right for a stack.
Sorting a row by `(y, x)` — what v1 did — reorders it by its own vertical centring: a 16dp
chevron at y=4 lands before a 20dp title at y=6.
