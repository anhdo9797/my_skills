# Screen exploration loop

This is the engine of the review. Read it before your first detailed screen.

## Contents

- [Two sources of truth](#two-sources-of-truth)
- [The loop, step by step](#the-loop-step-by-step)
- [Element classification](#element-classification)
- [Screen signatures and dedupe](#screen-signatures-and-dedupe)
- [Routes: how resume works](#routes-how-resume-works)
- [Handling interruptions](#handling-interruptions)
- [Getting unstuck](#getting-unstuck)
- [Budget discipline](#budget-discipline)

---

## Two sources of truth

The one-line version, because it governs every step below: **look at the
screenshot to decide what exists and what it means; use
`mobile_list_elements_on_screen` to decide where to tap.**

The accessibility tree lies by omission — icon-only buttons, WebViews, canvases,
and especially ad units often have no meaningful node. Vision, meanwhile, guesses
pixel coordinates badly, and a mistap can land you in a purchase flow. Each tool
covers the other's blind spot, and neither alone produces a correct report.

`references/screen-reading.md` has the full protocol for merging them and for the
systematic sweep that stops you from missing half the screen. Read it before your
first detailed screen.

## The loop, step by step

For each screen popped from the queue:

**1. Navigate.** Replay the screen's stored `route` from a known state. Prefer
starting from wherever you already are if you can get there in one or two taps;
otherwise terminate and relaunch the app for a clean base. Resolve each route step
by its `label` against a fresh `mobile_list_elements_on_screen` — coordinates
change between app versions and screen states, labels usually don't. If a step's
label is gone, look for a visually equivalent element in the screenshot before
giving up.

**2. Settle, then capture.** Wait for animations and network loads to finish (take
a screenshot; if it shows a spinner or skeleton, take another after a beat). Then:

```
mobile_save_screenshot → screenshots/<screen-path>/01-initial.png
```

Save every screenshot you reference in a report. Use `mobile_take_screenshot` for
your own quick looks that don't need to be kept — saving everything bloats the
folder and makes the report harder to read.

Naming: `NN-<what-it-shows>.png`, zero-padded, in the order a reader should see
them — `01-initial.png`, `02-scrolled.png`, `03-after-tap-premium.png`,
`04-paywall.png`. The numbering is the narrative.

**3. Read the screen — the Screen Read.** This is the step that determines the
quality of everything downstream, and it has its own protocol in
**`references/screen-reading.md`**. Read that file before your first screen and
follow it every time: sweep the six zones, pass the six lenses, and emit the
Screen Read table. Do not skip to tapping because the screen "looks simple" —
simple-looking screens are exactly where the quota counters and banner ads hide.

**4. Cross-check with `mobile_list_elements_on_screen`.** Mark each element
`both` / `vision-only` / `tree-only` as described in the screen-reading protocol.
Then emit the **Test Plan** — every item you'll probe, the question each probe is
meant to answer, and its priority. Work the plan in priority order so that
stopping early still leaves you with the answers that matter.

**5. Capture the whole screen, not just the viewport.** Swipe up until the content
stops changing (compare screenshots; two identical ones means you've hit the
bottom). Save a screenshot at each meaningful new section, and re-list elements —
scrolled-in content brings new nodes, and this is where mid-feed ads and
"upgrade" upsells hide. Scroll back to the top before moving on so the screen is
in a known state.

Also check horizontal carousels and side-scrolling rows the same way.

**6. Classify every element.** See the table below. Classification is what turns
an inventory into a plan: `navigation` and `action` elements become queue entries,
`ad` and `paywall-trigger` become findings, the rest are just documented.

**7. Execute the Test Plan.** For each row, run the hypothesis → action → verdict
cycle from the screen-reading protocol: predict what will happen, do it, save a
screenshot, then write down what *actually* happened. Prefer reversible probes
(toggles you can toggle back, tabs, info sheets); never touch destructive ones.
If a tap opened a whole new screen rather than a small state change, don't explore
it now — back out and let the queue handle it. Refuted hypotheses are findings,
not mistakes: write them down.

Two things override "back out and queue it":

- **The screen is empty because it has no data.** Go produce the data before
  writing the report — `references/flow-investigation.md` step 5 lists how. An
  empty list is the screen's cold-start state, not the screen.
- **The row starts a flow** (scan, search, checkout, login, upload). Flows are
  followed end to end, with a case matrix, into a flow report. Documenting "tapped
  Scan → camera opened" and stopping there loses the entire feature.

**8. Write the screen report.** Use `assets/screen-report-template.md`. Write it
now, while the screen is fresh, into `report/<screen-path>/README.md`. Don't batch
report-writing to the end of the session: an unwritten report is a report that
dies with your context.

**9. Queue the children.** Every `navigation` element that opens a screen you
haven't already documented gets an `add-screen` call, with `route` = this screen's
route plus the tap that opens it. Give each a stable `id` derived from its label
(`profile`, `scan_plant`, `settings/notifications`).

**10. Back out and record.** Return to the parent screen and verify with a
screenshot that you're actually there — Android's BACK sometimes exits the app,
and continuing from the wrong screen corrupts every route you record afterwards.
Then `update-screen --status done` with the report path and screenshot list.

## Element classification

| Type | What it is | What to do with it |
|---|---|---|
| `navigation` | Opens another screen (tab, list row, card, menu item, back/close) | Queue it, unless already documented — then cross-link |
| `action` | Does something in place (submit, scan, play, share, refresh) | Describe the effect; probe if safe |
| `input` | Text field, picker, slider, search box | Note type, placeholder, validation, keyboard |
| `toggle` | Switch, checkbox, radio, segmented control | Note default state and what it controls |
| `ad` | Banner, native ad card, rewarded button, interstitial trigger | Record as a finding — see `monetization.md` |
| `paywall-trigger` | Crown/PRO badge, "Upgrade", limit-reached prompt, gated feature | Record as a finding; follow to the paywall, screenshot it, never buy |
| `content` | Text, image, chart — not interactive | Mention only if it carries product meaning |
| `system` | OS permission dialog, share sheet, keyboard | Handle and note; not part of the app's own UI |

When something is both — a "Scan" button that shows an ad before scanning — record
the primary type and note the secondary behavior. Those hybrids are usually the
most interesting monetization findings in the whole app.

## Screen signatures and dedupe

Apps are graphs, not trees. Settings links to Profile links to Settings. Without a
dedupe rule you will loop forever.

Before writing a report, compute a rough **screen signature**: the screen's title
plus its 3–5 most distinctive text labels, lowercased. Compare it against the
signatures of screens already in the changelock (`status` prints them).

- **Match** → this is a screen you've documented. Don't write a second report.
  Instead, add a cross-link line to the *parent* screen's report ("→ opens
  [Settings](../settings/README.md)") and mark the queue entry `skipped` with a
  note pointing at the existing report.
- **Near-match** (same layout, different data — e.g. a detail screen for a
  different item) → document the *pattern* once, and note in the report which
  variants exist and how they differ. Reviewing twenty item-detail screens teaches
  you nothing the first one didn't.

Store the signature with each screen via `update-screen --signature`.

## Routes: how resume works

A route is the sequence of actions from a cold app launch to the screen. It's what
lets tomorrow's session reach a screen today's session merely discovered.

```json
"route": [
  {"action": "launch"},
  {"action": "tap", "label": "Avatar", "x": 980, "y": 120},
  {"action": "tap", "label": "Settings", "x": 540, "y": 800}
]
```

Rules that keep routes usable:
- `label` is the source of truth; `x`/`y` are hints that may go stale.
- Record the shortest reliable path, not the wandering path you actually took.
- Include non-tap steps that matter: `{"action":"swipe","direction":"up"}`,
  `{"action":"type","label":"Search","text":"rose"}`,
  `{"action":"wait","note":"3s interstitial ad, tap X top-right"}`.
- If a screen is only reachable after state (onboarding done, item created), say
  so in a `precondition` note on the screen rather than encoding it as taps.

## Handling interruptions

Real apps interrupt constantly. Handle these without derailing:

- **OS permission dialog** — note which permission and when it's asked (that's a
  finding: asking for location on first launch vs. at point of use is a real UX
  signal). Grant it if the feature needs it and it's harmless; deny if it's
  invasive and you can continue, then note the degraded behavior. On Android you
  can also set permissions from the shell, which makes both directions testable:
  `adb shell pm grant|revoke <pkg> android.permission.CAMERA`.
- **A camera opens** — that's a flow step, not a screen. Don't report "camera
  opened" and stop: `references/camera-flows.md` gets a known image in front of
  the lens so the flow can actually run.
- **Interstitial ad** — screenshot it *before* dismissing (this is evidence for
  the monetization report: which action triggered it, format, how long until the
  close button appears). Then close via the X. Don't tap the ad body.
- **Rating prompt / notification opt-in** — screenshot, note the trigger, dismiss.
- **Paywall** — screenshot every state including scrolled tiers and the
  fine print, extract prices and trial terms, then close. Never proceed to
  payment.
- **Login wall** — mark the branch `blocked`, note what's behind it.
- **Crash** — `mobile_get_crash` if available, screenshot, record as a finding
  with the exact repro steps, then relaunch and continue. A crash you can
  reproduce is one of the most valuable things this review can produce.

## Getting unstuck

If you don't recognize the current screen or a tap did nothing:

1. Screenshot and look — you may just be on a loading state.
2. `mobile_press_button BACK` (Android) or find a close/X/chevron in the elements.
3. If lost, `mobile_terminate_app` then `mobile_launch_app` and replay the route
   from scratch. This is cheap and always works; reach for it early rather than
   flailing.
4. If a screen is reachable but unusable (infinite spinner, requires a scan of a
   real object, requires a camera view of something you don't have), mark it
   `blocked` with the reason and move on. Note it in the report — "requires
   pointing the camera at a real plant" is legitimate, reportable information
   about the app.

Never repeat the same failing tap more than twice. If two attempts fail, change
approach.

## Budget discipline

Screenshots and element lists are the expensive part of this loop. Spend them
where they buy information:

- Do save: each distinct visual state, each ad, each paywall, each error.
- Don't save: near-identical frames, every intermediate scroll position on a long
  feed, animation mid-frames.
- Aim for 3–6 saved screenshots on a rich screen, 1–2 on a simple one.

Check in with yourself every few screens: is the queue growing faster than you're
draining it? If so, prune — collapse repetitive detail screens into a pattern
entry, and prioritize breadth (all top-level features documented) over depth (one
feature explored to the leaf). A review that covers every feature at depth 2 is
more useful to the user than one that covers a single feature at depth 6.

The one thing breadth never outranks is the **core flow**. Keep enough budget in
reserve to run it end to end with real input, including the case matrix — if the
choice is the core flow or five more screens, take the flow. Screens survive in the
queue for the next session; a review that never established whether the app's main
feature works has failed at its actual job, however wide it spread.
