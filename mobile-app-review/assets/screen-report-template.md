# <Screen name>

> `<screen-path>` · <app name> v<version> · <platform> · captured <YYYY-MM-DD>

<!--
Write this file in the user's language. Keep element labels, package names, and
paths in their original form. Drop any section that doesn't apply to this screen
rather than writing "N/A" — an empty section is noise, and a report full of noise
stops getting read.
-->

## 1. What this screen is for

Two to four sentences. What job does this screen do for the user, what is the
primary action, and how does it fit into the app's core loop? This is the part a
reader remembers; the tables below are reference material.

## 2. How to get here

`Launch → Home → tap "Avatar" (top-right)`

Note any precondition: onboarding completed, logged in, an item must exist, etc.

## 3. Screenshots

![Initial state](../../screenshots/<screen-path>/01-initial.png)
*Initial state on entry*

![Scrolled](../../screenshots/<screen-path>/02-scrolled.png)
*Scrolled to bottom — <what new appears>*

## 4. Elements

Carried over from the Screen Read. Pattern: `<feed | detail | form | paywall | …>`.

| # | Element | Zone | Type | Source | Behaviour (observed) | Leads to |
|---|---------|------|------|--------|----------------------|----------|
| 1 | Avatar | 2 | navigation | vision-only | Opens account page | [Profile](profile/README.md) |
| 2 | Scan Plant | 3 | action | both | Opens camera; 3 free scans/day | [Scan](scan_plant/README.md) |
| 3 | "3/5 scans left" | 3 | content | both | Free quota; resets — *not tested* | — |
| 4 | Banner ad | 5 | ad | vision-only | Always present, above tab bar | — |

Zones: 1 status bar · 2 header · 3 content · 4 floating · 5 bottom · 6 off-screen.
Types: `navigation` · `action` · `input` · `toggle` · `ad` · `paywall-trigger` ·
`content` · `system`. Source: `both` · `vision-only` · `tree-only` —
`vision-only` means no accessibility node, which is itself worth reporting.

Write `not tested` or `unverified` in the Behaviour column rather than guessing
from the label. An honest gap is more useful than a plausible invention.

**Absences:** what you'd expect from this pattern but didn't find — no search, no
pull-to-refresh, no ads here while every sibling screen has one.

## 5. Behaviour and data state

Walk through what actually happens on this screen, step by step, with screenshots
inline where they help. Cover the working path first, then variations (error state,
offline, first-time vs returning).

If the screen is data-dependent, show **both states** and say how you produced the
data: "empty on first entry; after one scan it shows a dated row with a thumbnail,
swipe-left to delete". The empty state is what every new user sees, and the
populated state is where the real features are — a report that only shows one of
them has covered half the screen.

If this screen is a step inside a flow rather than a destination, keep this section
short and link to the flow report, which is where the substance belongs:
→ [Scan → health result](../../flows/scan-plant/README.md)

## 6. Monetization on this screen

- **Ads:** format, position, trigger, frequency
- **Paywall triggers:** what's gated, what the prompt says, where it leads
- **Free limits:** any quota you observed and how it's communicated

Omit the section entirely if the screen is clean — and say so in section 7,
because a deliberately ad-free screen is itself a finding.

## 7. Notes and observations

What's well done and worth borrowing. What's friction. Anything surprising —
unusual patterns, performance issues, inconsistencies with the rest of the app.
Be specific and concrete; "the empty state offers a sample plant to try, which
removes the cold-start problem" beats "good UX".

## 8. Limitations of this pass

What you couldn't test and why: login required, needs a real camera subject,
network-dependent, region-locked, would have required a purchase.

## 9. Child screens

- [Profile](profile/README.md) — done
- [Scan Plant](scan_plant/README.md) — queued
- Settings — already documented at [../settings/README.md](../settings/README.md)
