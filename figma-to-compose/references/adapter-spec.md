# Project adapter — optional

One JSON file per Android project, at `<ANDROID_ROOT>/.figma/adapter.json`. It is the only
project-specific thing in this pipeline, and the pipeline runs fine without it.

**Skip it when:** the project has no design system, the design is a visual direction the
codebase has not adopted, or you just want the screen built. Generation emits idiomatic
Compose with raw values, each marked with its Figma node id for review.

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

  "theme": {
    "package": "com.videocomposer.app.ui.theme",
    "themeComposable": "VideoComposerTheme",
    "tokenAccessor": "composerTokens",

    "spacing":    { "xxs": 4, "xs": 8, "sm": 12, "md": 16, "lg": 24, "xl": 32, "xxl": 48 },
    "radii":      { "chip": 14, "control": 16, "card": 22, "panel": 28, "hero": 32 },
    "shapes":     { "extraSmall": 10, "small": 14, "medium": 20, "large": 28, "extraLarge": 36 },

    "colors": {
      // role -> hex. Roles are MaterialTheme.colorScheme slots, so generated code can
      // emit `MaterialTheme.colorScheme.<role>` directly.
      "primary": "#17141D", "onPrimary": "#FFFFFF",
      "surface": "#FFFFFF", "onSurface": "#17141D"
      // ...
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

## When the adapter and the design disagree completely

If `resolve_tokens.py` reports that most colors in the frame match no palette entry, the
design is a **different theme**, not a different screen.

This does not stop generation. The screen is built with the design's own values, each
marked with its node id, and the mapping report says plainly that the palette did not
match. **Put that in the PR description** — a reviewer seeing "38 of 41 colours are new;
this frame is a dark redesign" reads the diff completely differently than one who does not.

What happens next — migrate the shared theme, scope a second one, or ship the screen
off-palette for now — is a decision about the codebase, made by the people who own it, with
the working screen in front of them. Do not add forty one-off entries to the adapter to make
the report look clean; that hides the finding instead of reporting it.
