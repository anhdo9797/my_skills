# The self-test loop — run it, catch it, fix it, run it again

Phase 4 measures. This file is about the step after: turning a measurement into a loop that
closes on its own, so a defect is caught by the process rather than by whoever happens to
look at the screenshots.

## Why this exists

Three real runs produced the evidence:

| Defect | What caught it | What should have |
|---|---|---|
| Two tab captures were byte-identical; a tap had missed and the report counted them as two states | `md5` typed by hand, afterwards | `state_distinct_check.py` |
| A `#141414` title rendered pale grey on every screen | a human looking at a PNG | `layout_rules_check.py` R5 — it does now |
| Topic cards rendered ~3× the design's 80dp | a human looking at a PNG | `layout_assert.py` — it does now, when it runs |
| The IR carried 7 empty boxes and the screen lost 11 tints | a human reading the IR | `ir_coverage_check.py` — it does now |

Every one of those shipped through a run that reported success. The pattern is not that the
checks were wrong; it is that **the judgement lived in a person's habits instead of in the
pipeline**.

## The loop

```
          ┌───────────────────────────────────────────────┐
          ▼                                               │
  generate / repair ──► host gates ──► device run ──► read numbers
                        (seconds)      (minutes)      │
                                                      │
                        converged, or budget spent ───┘
```

**Two loops, not one, and the difference is cost.**

The **inner loop** is the host gates plus the JVM render: `layout_rules_check.py`,
`ir_coverage_check.py`, `compose_quality_gate.py`. Seconds per iteration, so it runs on
every edit. `references/repair-loop.md` bounds it: max 4 iterations, aggregate deviation
must decrease, one finding family per iteration, layout and style only.

The **outer loop** is the device: install, drive, capture, dump bounds, assert. Minutes per
iteration, so it runs **once per repair cycle, not once per edit**. This is the long-standing
rule that the emulator never goes inside the repair loop, and it still holds — but the reason
is cost, not signal quality. A dp assertion read from `LayoutCoordinates` is the same kind of
number as the host measurement; a pixel ratio is not, and that is what must never drive
repair.

## The device step, in order

```bash
./gradlew :app:installDevDebug
# drive each state the design draws, capturing as you go
adb -s <device> exec-out screencap -p > device/<state>.png

python3 scripts/state_distinct_check.py --dir device/ \
    --expect for-you your-turn answered completed \
    --map for-you=raw/5_8469/design.png your-turn=raw/5_8536/design.png \
          answered=raw/5_8590/design.png completed=raw/5_8644/design.png

./gradlew :app:connectedDevDebugAndroidTest   # dumps real bounds
python3 scripts/layout_assert.py --ir ir/screen.ui.json --actual render/nodes.json \
    --min-coverage 0.6 --json audit/layout.json
```

### Distinctness is judged as a ratio, never as an absolute

`state_distinct_check.py` asks whether each capture is really a different state. Byte-identical
captures fail unconditionally — the navigation did not happen.

Near-identical is the interesting case, and an absolute threshold **cannot** decide it. A
tab whose tap silently failed and two tabs the design genuinely draws alike produce the same
small number. Measured on a real run: three tabs differed by 1.1–1.6 of 255 mean grey, which
an absolute threshold flagged as a failed transition — and the design draws those same three
tabs 1.2–1.3 apart. Nothing was wrong.

So pass `--map` and let the design set the scale:

```
answered.png vs your-turn.png   device 1.14 · design 1.26 · ratio 0.91
```

91% of the difference the design demands. A failed tap scores near zero against the same
baseline. This is the skill's own ratio doctrine applied where it was missing.

## Every state the design draws needs a way in

A design with an empty state and no control that reaches it is not a design flaw; it means
the state is driven by data. Reaching it for a capture is a product decision, and it has a
right answer and two wrong ones:

- **Right** — a debug-gated input the ViewModel reads only when `BuildConfig.DEBUG`:
  `adb shell am start -n <app>/.MainActivity --ez force_empty true`. Release never sees it.
- **Wrong** — overloading a real gesture (a long press, a second tap on the selected tab).
  It puts test-only behaviour on the user's path, and a real run shipped exactly that.
- **Wrong** — skipping the capture and asserting the state in a unit test instead. The unit
  test is worth having, but it is not evidence that the screen renders.

Record the choice in `decisions.md` with the node ids of the states it unlocks, and say in
the report that the path is debug-only, so a reviewer knows it exists and knows it does not
ship.

## What is still missing, stated plainly

The on-device step **dumps, it does not assert**. `LayoutAuditDumpTest` renders the screen,
writes `render/nodes.json`, and exits; the pass/fail happens afterwards on the host when
somebody runs `layout_assert.py`. So no Gradle task goes red when fidelity regresses, and
nothing re-runs by itself.

Turning it into an assertion is not a matter of adding `assertEquals`. The frame is 390dp
and the device is whatever it is — 411.4dp on the emulator used here. Asserting raw design
dp fails on every device that is not exactly the frame's width. A correct assertion compares
what is actually device-independent:

| Quantity | Device-independent? | Assert on it |
|---|---|---|
| Height, gaps, padding, insets | yes | absolute dp |
| Width of a fixed-size element (icon, 100dp bar) | yes | absolute dp |
| Width of a full-bleed element | **no** | expect the device width, not 390 |
| Width of an inset element | **no** | expect device width minus the design's insets |
| x offset of anything centred or right-aligned | **no** | derive from the device width |

Until that distinction is implemented, the device step stays a measurement read by an agent,
and the honest verdict vocabulary in `references/verification.md` applies: `UNMEASURED` when
nothing was compared, `STOPPED UNCONVERGED` when numbers exist and repair did not close them.
Do not claim a passing self-test the pipeline cannot produce.
