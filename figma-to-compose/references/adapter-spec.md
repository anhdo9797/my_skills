# Project adapter — optional

One JSON file per Android project, at `<ANDROID_ROOT>/.figma/adapter.json`. It is the only
project-specific thing in this pipeline, and the pipeline runs fine without it.

**Skip it when:** the project has no design system, the design is a visual direction the
codebase has not adopted, or you just want the screen built. Generation emits idiomatic
Compose with raw values; each one is listed with its Figma node in `ir/mapping-report.json` for review.

**Add it when:** the project has components and tokens worth reusing, and you would rather
the generated screen call `ComposerCard` and `spacing.md` than rebuild both. It is worth the
hour it takes to curate, and it pays off from the second screen onward.

It answers four questions:

1. What tokens does this project have, and what raw value is each one?
2. What composables exist, and which Figma shapes do they correspond to?
3. How do I build, render, and test this project?
4. How close is close enough?

## Shape

```jsonc
{
  "project": "video-composer",
  "root": "/abs/path/to/project",
  "sourceSet": "app/src/main/java/com/videocomposer/app",

  "fingerprint": {
    // What the rest of this file was derived from, so a later run can tell whether it
    // still is. One sha256 per theme source file, keyed by path relative to `root` — the
    // same files listed in `theme.files`. See "Staleness is fatal, not advisory" below.
    "algorithm": "sha256",
    "files": {
      "app/src/main/java/com/videocomposer/app/ui/theme/Color.kt": "ea52f0…",
      "app/src/main/java/com/videocomposer/app/ui/theme/Theme.kt": "5413b2…"
      // ...
    }
  },

  "theme": {
    "package": "com.videocomposer.app.ui.theme",
    "themeComposable": "VideoComposerTheme",
    "tokenAccessor": "composerTokens",

    "spacing":    { "xxs": 4, "xs": 8, "sm": 12, "md": 16, "lg": 24, "xl": 32, "xxl": 48 },
    "radii":      { "chip": 14, "control": 16, "card": 22, "panel": 28, "hero": 32 },
    "shapes":     { "extraSmall": 10, "small": 14, "medium": 20, "large": 28, "extraLarge": 36 },

    "colors": {
      // Both schemes the project wires, kept apart — a project can ship light and dark at
      // once, and collapsing them into one map makes one of the two simply wrong in the
      // adapter. Each inner map is role -> hex; roles are MaterialTheme.colorScheme slots,
      // so generated code can emit `MaterialTheme.colorScheme.<role>` directly.
      "light": {
        "primary": "#17141D", "onPrimary": "#FFFFFF",
        "surface": "#FFFFFF", "onSurface": "#17141D"
        // ...
      },
      "dark": {
        "primary": "#E4E1E9", "onPrimary": "#121319",
        "surface": "#1B1B21", "onSurface": "#E4E1E9"
        // ...
      }
      // An adapter written before this (schemeless) shape instead has `colors` as a single
      // flat role -> hex map, with no scheme name attached. resolve_tokens.py still reads
      // it — see "Choosing a colour scheme" below — but it carries whichever one scheme the
      // scanner found first, and `--dark` has nothing to switch to.
    },

    "typography": {
      // style -> the three things that can be measured off a render
      "titleMedium": { "size": 16, "lineHeight": 22, "weight": 600 },
      "bodySmall":   { "size": 13, "lineHeight": 19, "weight": 400 }
      // ...
    }
  },

  "components": [
    {
      "name": "ComposerCard",
      "file": "ui/component/ComposerSurfaces.kt",
      "kind": "container",
      "props": ["onClick", "containerColor", "borderColor", "modifier", "content"],
      "figmaHints": ["card", "tile", "tool-*", "*-card"],
      "confidence": "review"     // "confirmed" once a human has checked it
    }
  ],

  "commands": {
    "build":          "./gradlew :app:assembleDebug",
    "unitTest":       "./gradlew :app:testDebugUnitTest",
    "screenshotTest": "./gradlew :app:validateDebugScreenshotTest",
    "screenshotUpdate": "./gradlew :app:updateDebugScreenshotTest",
    "lint":           "./gradlew :app:lintDebug"
  },

  "tolerance": {
    "spacingRatio":  0.12,   // |actual/design - 1| allowed
    "fontSizeRatio": 0.10,
    "colorDeltaE":   6,
    "snapDistance":  { "spacing": 2, "radius": 3, "fontSize": 1 }
  },

  "literalWhitelist": [
    "0.dp", "1.dp",          // hairlines and zero are not design decisions
    "0f", "1f"
  ]
}
```

## `figmaHints` — how a Figma node finds its composable

Matched against the Figma **layer name**, lowercased, in this order:

1. exact match
2. glob (`tool-*`)
3. token overlap (`recent-item-1` → `recent`, `item` → a component hinting `item`)

A node that matches nothing gets `mapping.component: null` and is generated as a raw
`Column`/`Row`/`Box`. That is allowed, but the quality gate counts it: a screen where most
nodes map to nothing usually means the designer's naming and the code's naming have
drifted, and the fix is the adapter, not the generated file.

**Naming discipline pays for itself here.** A Figma file whose layers are named
`tool-tile`, `section-header`, `recent-item` maps almost for free. One named `Frame 427`
maps to nothing and every node needs a human.

## Choosing a colour scheme

`theme.colors` carries both schemes the project wires. `resolve_tokens.py` matches design
colours against one of them at a time — **light by default**, because that is what
generation targets unless told otherwise:

```bash
python3 scripts/resolve_tokens.py --adapter .figma/adapter.json --ir ... --out ... --report ... --dark
```

Pass `--dark` when the Figma frame being resolved is itself a dark-mode surface. Resolving
a dark frame against the light scheme is the same mistake the adapter used to make
internally — reporting the wrong scheme's roles as "nearest" and "unmapped" — just moved
from scan time to resolve time, where at least it is now a deliberate choice instead of a
silent default.

If the requested scheme is missing from the adapter (a project with only `lightColorScheme`
declared, asked to resolve `--dark`), `resolve_tokens.py` falls back to whichever scheme it
has and says so on stderr — it does not refuse, because a project that only has one scheme
isn't stale, it just doesn't have the other one yet.

An adapter generated before this fix has `theme.colors` as a single flat role → hex map
(no `light`/`dark` keys) — whichever scheme the old scanner picked, usually light but not
guaranteed. `resolve_tokens.py` still reads it as that adapter's one and only scheme, with a
note on stderr that `--dark` has nothing to switch to. Regenerate to get both.

## Project conventions the scanner handles

Benchmarked against five unrelated Compose codebases. Each of these is a real style someone
ships, and each one broke the scanner until it didn't:

| Declaration style | Example |
|---|---|
| Typed data-class tokens | `data class Spacing(val md: Dp = 16.dp)` |
| Object constants, inferred type | `object AppSpacing { val space16 = 16.dp }` |
| Direct palette | `val Ink = Color(0xFFF8F7FB)` |
| **Aliased palette** | `val LightPrimary = ColorBrand` → resolved through the chain |
| Inline type scale | `titleMedium = TextStyle(fontSize = 16.sp, …)` |
| **Factory-built scale** | `val H1 = appTextStyle(SemiBold, 28.sp, 32.sp)`, where `appTextStyle` is any `fun …: TextStyle` |
| **Aliased scale** | `val headingH1: TextStyle = AppHeadingH1` |
| **Slots wired to a ramp** | `Typography(displayLarge = AppHeadingH1, …)` |
| Partial or empty `Typography()` | unset slots fall back to the Material 3 baseline, tagged `"source": "material3-default"` |

Two things this buys: a project that never writes a hex literal still reports a full colour
scheme, and a project that uses stock Material typography still resolves every text node
instead of reporting the whole screen unmapped.

What it still cannot see: values computed at runtime, tokens behind a `when`/branch, and
anything built by a factory called with a variable instead of a literal. Those come back
missing rather than wrong — check the counts against what you know the project has.

## Generating the skeleton

```bash
python3 scripts/scan_design_system.py --project <ANDROID_ROOT> --out <ANDROID_ROOT>/.figma/adapter.json
```

What the scanner can and cannot do:

| | |
|---|---|
| **Reliable** — parsed from source | spacing/radii/shape values, palette hex, typography sizes/weights, composable names + signatures + files |
| **Guessed** — needs human review | `figmaHints`, `kind`, which composable is "the card" vs "the tile" |
| **Never inferred** | `commands`, `tolerance`, `literalWhitelist` — defaults are written, confirm them |

Every guessed component starts at `"confidence": "review"`. Flip to `"confirmed"` by hand.
The pipeline warns on `review` components but does not block — it blocks on unmapped
*tokens*, which are a correctness issue, not a naming one.

## Staleness is fatal, not advisory

`fingerprint` exists because an adapter is a *snapshot*, and nothing used to notice when the
project moved on without it. A theme file edited after the scan — a colour added, a role
rewired — leaves every value the old adapter recorded for that file simply wrong, with
nothing in `mapping-report.json` to mark it as such. That already happened once: a worker
added a brand palette to `Color.kt` after the adapter was generated, `resolve_tokens.py` ran
against the stale one anyway, and reported a colour as an unmapped raw value when the
project in front of it, by then, had a token for it. Nobody could tell from the report that
it was answering a question about a project that no longer existed.

This is why `resolve_tokens.py` treats a stale adapter differently from an unmapped value.
Unmapped is honest — it means "no token fits," and generation proceeds with the raw value
marked for review. Stale is not honest — every number the adapter produces, mapped or
unmapped, might be describing a theme that has since changed, and there is no way to tell
*which* numbers from the output alone. So `resolve_tokens.py` checks the fingerprint
**before** resolving anything, and on any mismatch it refuses to run:

```
error: adapter is stale — theme sources changed since it was generated
  changed: app/src/main/java/.../ui/theme/Color.kt
  added:   app/src/main/java/.../ui/theme/Brand.kt

Regenerate it:
  python3 scan_design_system.py --project /abs/path/to/project --out /abs/path/to/.figma/adapter.json --force
```

It names every file that was edited, added, or removed — not just edited; a file added to
the theme package is exactly as much a reason the adapter no longer describes the project as
a changed hex literal is. There is no override flag. Regenerating takes about a second and
re-reads the project as it is right now, which is the only fix that actually addresses the
problem — an override would just mean choosing, deliberately this time, to trust numbers
that are known to be wrong.

An adapter with no `fingerprint` at all (written by a `scan_design_system.py` from before
this existed) gets the same refusal, not a warning. Its freshness is simply unverifiable —
that is the same situation as a known-stale adapter from the report's point of view, nothing
in it can be vouched for — and a warning is exactly what this incident showed goes
unnoticed. Regenerating is the same one command either way.

## Pixel-perfect mode needs the theme to carry the design's values

`snappedCount` in the mapping report is a **fidelity budget being spent**: each snap is a
design value rounded to the nearest token. A normal run accepts that trade — one more
spacing constant usually costs more than one lost dp. A pixel-perfect run cannot.

So `resolve_tokens.py --pixel-perfect` refuses to snap and reports each would-be snap with
its exact dp cost, which turns "the theme is close enough" into a list of values to add.

The measured difference between the two orders of work, same design, two codebases:

| | Theme left as-is | Theme designed from the design first |
|---|---|---|
| snapped | **85** | **24** |
| raw values in the screen | 56 | **0** |

Designing the theme from the design before generating is not a nicety — it is what makes
pixel fidelity reachable at all, because the tokens then *are* the design's numbers.

## When the adapter and the design disagree completely

If `resolve_tokens.py` reports that most colors in the frame match no palette entry, the
design is a **different theme**, not a different screen.

This does not stop generation. The screen is built with the design's own values, and the mapping report says plainly that the palette did not
match. **Put that in the PR description** — a reviewer seeing "38 of 41 colours are new;
this frame is a dark redesign" reads the diff completely differently than one who does not.

What happens next — migrate the shared theme, scope a second one, or ship the screen
off-palette for now — is a decision about the codebase, made by the people who own it, with
the working screen in front of them. Do not add forty one-off entries to the adapter to make
the report look clean; that hides the finding instead of reporting it.
