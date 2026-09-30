# Phase 5 — Repair loop

The loop that most Figma→code pipelines die in. It dies the same way every time: the diff
signal is a pixel percentage, the agent cannot tell what to change, it guesses, the number
moves 0.1%, and it guesses again until the budget is gone.

Two things prevent that: **findings with addresses**, and **a hard budget**.

## Findings with addresses

The repair loop consumes `audit/*.json` — never a heatmap, never a pixel ratio. Each
finding names a node, a property, and a number:

```json
{ "node": "20:12", "property": "gap", "actual": 20, "design": 15,
  "ratio": 1.33, "band": [0.88, 1.12], "token": "spacing.md" }
```

That maps to exactly one edit: the `Arrangement.spacedBy` in the composable that renders
`20:12`. If a finding cannot be traced to a node and a property, it is not a repair input
— it is a note for a human.

## Triage before you repair: is this a defect or an artifact?

A measurement is evidence that two images differ. It is **not** evidence that the code is
wrong. Run every finding past this before spending an iteration on it — the checks cost
seconds and the iterations don't.

| Signal | Likely cause | Action |
|---|---|---|
| Every band mispaired from the top down | Platform chrome not cropped out of the design | Fix the input, re-measure |
| Only the final gap is huge | Render fills the device; design frame stops at its content | Ignore — trailing space is not a measurement |
| A repeated row is uniformly short, and its gap is bigger by the same amount | Fixture divergence, not layout | Check the fixture, not the modifier |
| One element off, neighbours fine | **Real defect** | Repair it |
| Everything off by the same ratio | One wrong token or theme value | One fix, not N |

The middle row is the subtle one and it cost a real iteration to see. Three recent-output
rows each measured 74dp in the design and 54dp in the render — 0.73×, three times over,
which reads as an obvious padding bug. The card was `.height(74.dp)` in both. The design's
rows carry a **photo thumbnail** whose pixels reach the card's edges; the render's carry a
52dp icon tile, so the ink profile saw only the inner content. The 20dp that vanished from
each row reappeared in each gap (12dp → 32dp), which is the tell: **when a height shrinks
and its neighbouring gap grows by the same amount, the element did not move — the
measurement boundary did.**

The general rule: a spacing audit measures *ink*, so anything that changes how far the ink
reaches — a photo vs an icon, a filled card vs a transparent one, a long string vs a short
one — changes the number without changing the layout. Before repairing a geometry finding,
confirm the two sides are actually showing the same kind of content.

## Budget

| Rule | Value |
|---|---|
| Max iterations | **4** |
| Aggregate deviation must decrease | every iteration |
| Two consecutive flat/worse iterations | **stop** |
| Finding families per iteration | **one** (all spacing, or all typography, not both) |
| Files touched | only the generated screen file(s) |

One family at a time because the two interact: fixing type size changes line heights,
which changes every measured vertical gap. Fix them together and you cannot tell which
edit moved which number — that ambiguity is what the loop is trying to avoid.

## What may change

**Allowed:** layout modifiers, arrangement/alignment, spacing and radius tokens,
typography style selection, color token selection, `maxLines`/overflow.

**Not allowed inside the loop:** ViewModel, repository, navigation, domain, strings'
*meaning*, new dependencies, the adapter, the tolerance bands.

Widening a tolerance to make a finding pass is the failure mode this rule exists for. If a
band is genuinely wrong, that is a separate change with its own justification, made
outside a run.

## Stopping without converging

A normal outcome. Report it plainly:

```
Repair stopped after 4 iterations. 3 findings remain:
  20:12  gap        1.33× design (band 0.88–1.12)  — design spec is 15dp, project grid has no 15; snapped to md(16) leaves 1.33× against the measured render
  17:34  height     1.18× design
  20:45  fontSize   0.86× design
```

Then say which are pipeline limits and which are real defects. Remaining findings that all
trace to one cause — a design drawn off the project's spacing grid, say — are one sentence
to the designer, not four more iterations.

## Escalate instead of iterating when

- the same finding survives two iterations with edits that should have moved it →
  something upstream is wrong (wrong node mapping, wrong preview device size, design
  screenshot at the wrong scale)
- findings appear on nodes nobody edited → the render fixture is non-deterministic
- fixing a finding requires touching a disallowed file → stop, report, let a human scope it
- the aggregate got worse after a "fix" → revert that iteration before continuing

Reverting is cheap here because each iteration is one family of small edits. Keep them as
separate commits, or the revert becomes its own debugging session.
