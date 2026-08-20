# Reading a screen properly

This is the thinking part of the review, and it is where the whole thing lives or
dies. Everything else — navigating, screenshotting, writing files — is mechanical.

## Why a protocol at all

Left to instinct, the failure mode is predictable and severe: you look at a
screenshot, four or five things jump out (the big CTA, the title, the tab bar),
you tap the most interesting one, and you move on. The report that comes out of
that says the Home screen has six elements when a careful human counts fourteen.
What gets lost is exactly the stuff the user is paying for — the small "3/5 free
scans left" counter, the crown badge in the corner, the banner ad you stopped
seeing after the second screen, the row that's half-cut at the bottom edge
signalling more content below.

The second failure mode is quieter and worse: **inventing behaviour from labels.**
A button says "Premium", so the report claims it opens a subscription page — but
nobody tapped it, and it actually opens a rewarded-ad dialog. The report reads
fluently and is wrong, which is worse than being incomplete, because the user
can't tell.

The protocol below is designed against both. It costs a few minutes per screen and
it is the difference between a UI dump and an analysis.

## Contents

- [Step 1 — Zone sweep](#step-1--zone-sweep)
- [Step 2 — Six lenses](#step-2--six-lenses)
- [Step 3 — Emit the Screen Read](#step-3--emit-the-screen-read)
- [Step 4 — Cross-check against the accessibility tree](#step-4--cross-check-against-the-accessibility-tree)
- [Step 5 — Emit the Test Plan](#step-5--emit-the-test-plan)
- [Step 6 — Hypothesis, action, verdict](#step-6--hypothesis-action-verdict)
- [Evidence rules](#evidence-rules)

---

## Step 1 — Zone sweep

Do not scan the screenshot freely. Sweep it in six fixed zones, top to bottom, and
say out loud what is in each one — including "nothing". Fixed zones are what stop
you from skipping the boring regions, and the boring regions are where the
monetization hides.

| # | Zone | What normally lives here | What gets missed here |
|---|---|---|---|
| 1 | Status bar | Time, battery, signal | Whether the app is fullscreen/immersive; a notification the app just fired |
| 2 | Top bar / header | Back or close, title, right-hand actions | Avatar, crown/PRO badge, notification dot, streak counter, settings gear, search icon |
| 3 | Main content | Feed, form, hero, list | Section headers, quota/limit text, inline promo cards, "sponsored" labels, disabled/greyed items |
| 4 | Floating layer | FAB, snackbar, tooltip | Coach marks, onboarding bubbles, badge dots on tabs, a dimmed scrim meaning a modal is open |
| 5 | Bottom area | Tab bar, sticky CTA | Banner ad sitting above the tab bar, "skip" text in tiny grey type, safe-area padding hiding a row |
| 6 | Off-screen | — | Content cut at the bottom edge, horizontal carousels with an item peeking in, a drawer handle, hidden tabs behind a "More" |

Zone 6 is not visible in the screenshot by definition — that's the point. Ask
explicitly: *is anything cropped at any edge?* A row that's half-visible at the
bottom, a card peeking in from the right, a scrollbar hint. Each of those is a
promise that there is more, and each one you ignore is a hole in the report.

### Reading affordances, not just content

A partially-revealed element is not a smaller version of the full thing — it's a
promise that a gesture reveals more, and transcribing what's visible without
acting on that promise is how a report ends up describing the loading dock
instead of the payload. This matters most exactly where it's easy to miss: the
**result of the core flow** frequently lands in a bottom sheet peeking a tenth of
the screen, not the full result — a scan, a search hit, an order confirmation.
Screenshotting that peek state and calling it "the result" is a hole in the
report shaped exactly like the thing the user ran the flow to see.

Recognize the signal, know the matching probe, before you write anything down:

| Visual signal | What it usually means | Probe |
|---|---|---|
| A short pill/bar at the top-center of a panel (a grabber) | Draggable bottom sheet | Swipe up **on the sheet**, not the background, until it stops moving or reaches full height |
| A panel occupying a small slice of the screen, rounded top corners, background dimmed above it | Peek-state bottom sheet | Same — swipe up; if it snaps to a middle height, keep going to the max |
| A full-bleed photo/image with no visible chrome around it | Often opens a dedicated fullscreen/zoom viewer on tap | Tap it once; check for pinch-zoom, swipe-to-dismiss, and any action bar that only appears in that viewer |
| Text cut with "…", a "Show more" link, or a fade-out gradient at the bottom edge | Expandable/truncated text | Tap "Show more" or the text block itself |
| A row or card visibly cut off at the screen's edge | More content in that direction | Scroll/swipe past it — don't stop at the first fully-visible item |
| A "+3" badge, a stacked-card look, a carousel with a sliver of the next item showing | More items than currently on screen | Scroll/swipe until the count or content stops changing |
| A chevron (⌄/⌃/›) beside a row or section header | Collapsible section | Tap it |

The unifying test, when in doubt: **if an element looks like it's showing a
fraction of something, it usually is.** This is exactly what
`references/flow-investigation.md` means by "every intermediate state
screenshotted" for the core flow's happy path — a peek sheet mid-expansion is an
intermediate state, not the destination.

## Step 2 — Six lenses

Pass over the same screenshot six times, each time asking one question. Different
questions surface different things; one pass with "what's here?" surfaces the
least.

**Lens 1 — Identity.** What screen is this, and which standard pattern is it? Feed
/ detail / form / list+detail / onboarding step / paywall / settings / empty state
/ error state / permission prompt / result screen. Naming the pattern instantly
tells you what *should* be there, so you can notice what's missing — a feed with
no pull-to-refresh, a form with no validation, a settings screen with no account
row.

**Lens 2 — Intent.** What does the app want you to do here? Rank the visual
emphasis: size, colour saturation, position, contrast, whitespace around it,
motion. The most emphasised element is the app's business answer for this screen.
Then ask the harder question: is the emphasised action the one that helps the
*user* most, or the one that helps the *app* most? The gap between those two is
the most quotable finding you can produce.

**Lens 3 — Full inventory.** Now list literally everything visible, interactive or
not, including things you'd normally filter out as chrome. Count them. If your
count is under eight on a real app screen, you are almost certainly still
filtering — go back and look again at zones 2, 4, and 5.

**Lens 4 — State.** What does this screen tell you about state? Badge counts,
quota text ("3 of 5 free scans"), toggle positions, selected tab, progress bars,
timestamps, "NEW" tags, greyed-out/locked items, skeleton loaders. State elements
are the ones that reveal the app's *rules*, and rules are what the user wants to
learn. A grey "Export" row with a padlock teaches you more than the five colourful
rows above it.

Ask one more question in this pass: **is what I'm looking at the screen, or just
its empty state?** A list with nothing in it, a profile with no history, a cart
with no items — these are not the screen, they're the screen before it has been
used. Everything that makes the screen interesting (rows, swipe actions, sort and
filter controls, item detail, in-list ads, sync indicators) is hidden until data
exists. If you're on an empty data-dependent screen, the highest-priority item in
your Test Plan is *producing the data* — see `references/flow-investigation.md`
step 5 for how, then come back and read the screen again for real. Document both
states: the empty one is a genuine UX finding (it's what every new user sees), the
populated one is where the features are.

**Lens 5 — Money.** Scan specifically for: crown / diamond / star / lock icons,
the words PRO / Premium / Plus / Unlock / Upgrade / Free trial, any price, any
countdown timer, any "watch a video to…", any ad frame (a bordered rectangle with
tiny text, an "AdChoices" triangle, a suspiciously off-brand font), any "sponsored"
or "promoted" label. Do this as a dedicated pass — money elements are deliberately
designed to sit at the edge of attention, and a general sweep skips them.

**Lens 6 — Absence.** What is *not* here that you'd expect from the pattern named
in Lens 1? No back button on a detail screen means gesture-only navigation. No ads
on a screen where every sibling screen has one means it's a deliberate ad-free
zone. No login prompt on a personalised feed means anonymous personalisation.
Absence is evidence; record it.

## Step 3 — Emit the Screen Read

Before touching the device again, write out the Screen Read. Writing it is not
bureaucracy — it is what forces the sweep to actually finish, because an
incomplete table is visible in a way an incomplete thought is not.

```
SCREEN READ — <screen-path>
Pattern:  <feed | detail | form | paywall | settings | ...>
Purpose:  <one sentence>
Primary action (app's intent): <element> — because <size/colour/position>
Zones swept: 1 [..] 2 [..] 3 [..] 4 [..] 5 [..] 6 [..]

| # | Element (as shown) | Zone | Type | Source | State / notes |
|---|--------------------|------|------|--------|---------------|
| 1 | ← Back             | 2    | navigation | both | |
| 2 | Avatar (top-right) | 2    | navigation | vision-only | no a11y label |
| 3 | "3/5 scans left"   | 3    | content    | both | free quota indicator |
| 4 | Scan Plant (CTA)   | 3    | action     | both | primary, largest element |
| 5 | Crown badge        | 2    | paywall-trigger | vision-only | |
| 6 | Banner ad          | 5    | ad         | vision-only | above tab bar, always on |
| 7 | Row cut at bottom  | 6    | —          | vision-only | must scroll |

Absences: no search, no refresh affordance, no settings entry point
```

`Source` is one of `both`, `vision-only`, `tree-only` — see the next step for why
that column matters. This table becomes section 4 of the screen report almost
verbatim, so the work is not duplicated.

## Step 4 — Cross-check against the accessibility tree

Now compare your visual inventory against
`mobile_list_elements_on_screen`. The three cases each mean something:

- **In both** — high confidence. Use the tree's coordinates to tap.
- **Vision-only** — you can see it, the tree can't. Very common for icon buttons,
  ad units, WebView content, canvas-drawn UI, and custom controls. This is a
  finding twice over: it's an accessibility gap worth noting in the report, and
  it's a hint about the app's implementation. To tap it, estimate the position
  from the screenshot relative to nearby labeled elements, then verify with a
  screenshot afterwards.
- **Tree-only** — the tree reports something you can't see. Usually it is
  off-screen (below the fold), transparent, zero-sized, or behind a modal. Do not
  assume it's visible to users. Check by scrolling; if it never appears, note it
  as hidden rather than reporting it as a feature.

If your visual count and the tree count differ wildly in either direction, stop and
look again before proceeding. That discrepancy is almost always you missing
something, not the tools being wrong.

## Step 5 — Emit the Test Plan

The Screen Read says what exists. The Test Plan says what you're going to do about
it, and — more importantly — **what question each action is meant to answer.**
Acting without a question is how you end up tapping fifteen things and learning
nothing.

```
TEST PLAN — <screen-path>

| # | Item | Question to answer | Action | Priority | Risk |
|---|------|-------------------|--------|----------|------|
| 1 | Scan Plant | What is the core loop, and where's the free limit? | tap, complete one scan | P0 | may trigger ad |
| 2 | "3/5 scans left" | Is the quota daily or lifetime? resets when? | read copy, tap it | P0 | none |
| 3 | Crown badge | Which paywall variant, what tiers/prices? | tap, screenshot, close | P1 | NEVER purchase |
| 4 | Banner ad | Format, network, does it persist across screens? | observe only | P1 | do not tap creative |
| 5 | Avatar | What's in the account area? | tap → queue as child screen | P2 | none |
| 6 | Cut-off row (zone 6) | What's below the fold? | swipe up until stable | P2 | none |
```

Priorities exist so that a session that runs out of budget runs out of it in the
right place:

- **P0** — the core loop and anything gating it, plus *producing the data this
  screen exists to show* if it's empty. Without this the review is worthless.
- **P1** — monetization: ads, paywalls, quotas, upsells. This is usually the
  headline deliverable.
- **P2** — secondary features, navigation branches, settings that reveal capability.
- **P3** — cosmetic and low-signal. Skip freely.

Work the plan in priority order, not top-to-bottom. If you must stop early, you
will have stopped having answered the questions that matter.

Also decide, per row, whether the action **stays on this screen** (probe it now) or
**opens a new screen** (queue it, don't follow it now). Following branches
immediately is how a breadth-first review silently becomes a depth-first one and
never comes back.

There is one deliberate exception: an action that starts the app's **core flow**.
That one you follow all the way through, because a flow reported as "tapped Scan,
camera opened" is the screenshotter's version of the review. Flows get their own
protocol and their own report — see `references/flow-investigation.md`.

## Step 6 — Hypothesis, action, verdict

For every P0/P1 row you execute, run this three-beat cycle explicitly:

1. **Hypothesis** — "Tapping Crown opens a subscription paywall with yearly and
   monthly tiers."
2. **Action + evidence** — tap, save a screenshot, list elements.
3. **Verdict** — confirmed / refuted / partial, and what actually happened.

Write the verdict, not the hypothesis, into the report. When a hypothesis is
refuted, that's usually the most interesting line in the whole screen report —
"the Crown badge does not open a paywall; it opens a rewarded-ad dialog offering
one free scan" is exactly the kind of detail the user cannot get from a store
listing.

Keep the cycle honest about surprises. If a tap produces something you didn't
predict at all — an interstitial, a permission dialog, a hard login wall, a crash —
that surprise is a finding. Record it with `add-finding` before you continue,
because in five screens' time you will not remember which tap caused it.

## Evidence rules

These exist because a confidently wrong report is worse than a short one, and the
user has no way to audit your claims except the screenshots you attach.

- **Never describe behaviour you did not observe.** If you didn't tap it, you don't
  know what it does. Write "not tested" or "presumed from label (unverified)" and
  keep going — those phrases cost you nothing and preserve the report's
  trustworthiness.
- **Every behavioural claim needs a screenshot** that shows it, referenced from the
  report. If you can't point at an image, soften the claim.
- **Quote UI copy exactly**, especially prices, quota text, and trial terms.
  Paraphrasing "7 days free, then ₫799,000/year" into "has a free trial" throws
  away the part the user needed.
- **Separate observation from interpretation.** "The upgrade prompt appeared after
  the third scan" is an observation. "The app gates the core loop aggressively" is
  an interpretation. Both belong in the report — in different sections, clearly
  distinguishable.
- **When you're unsure, say the uncertainty and what would resolve it.** "Unclear
  whether the 5-scan limit is daily or per-install; would need a second session
  the following day to confirm." That sentence is genuinely useful. A confident
  guess in its place is not.
- **The changelock enforces the screenshot floor mechanically, not just on trust.**
  `update-screen --status done` refuses a screen with no `--screenshot`, and
  `add-edge --status observed` refuses a transition with no `--evidence`. Hitting
  one of these isn't a bug in the tool — it's the rule catching exactly the
  shortcut you were about to take. Fix the actual gap (go take the screenshot)
  rather than reaching for `--force`.
