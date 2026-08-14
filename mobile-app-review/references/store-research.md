# Store and landing page research

Twenty minutes of research before you touch the device makes the whole review
sharper. The store listing tells you what the developer believes their headline
features are; the reviews tell you where the app actually hurts; the pricing text
tells you which paywalls to go hunting for. Go in with hypotheses, not blank.

## Resolving the app

From a name, a bundle id, or a link, get to a canonical listing:

- Play Store: `https://play.google.com/store/apps/details?id=<package>&hl=en&gl=US`
- App Store: `https://apps.apple.com/us/app/id<numericId>` (search by name if you
  only have the name; the bundle id is not in the URL)

Use WebSearch to find the listing, then WebFetch it. If several apps share the
name, present the top candidates to the user with developer, install count, and
rating, and let them choose — reviewing the wrong app wastes an entire session.

Note that store content is localized. Fetch the user's locale (`hl=vi&gl=VN`) if
they're reviewing for a Vietnamese market, and the US listing for the global
picture. Prices in particular differ a lot, and if the two disagree that's worth a
line in the report.

## What to extract

Into `00-overview/store-listing.md`:

**Identity** — exact name, developer, package/bundle id, category, current
version, last updated, size, minimum OS, content rating.

**Scale** — install count (Android) or rating count (iOS), rating value and
distribution. Growth signal: how recently and how often it updates.

**Positioning** — the short description and the first two lines of the long
description. That's the elevator pitch the developer chose, and it tells you the
one thing they think sells the app.

**Claimed features** — the bullet list from the long description. Keep this
verbatim-ish; in Phase 4 you'll check each claim against what you actually found
in the app, and gaps between the two are a genuinely interesting finding.

**In-app purchase range** — Play Store shows a price range, App Store lists the
top IAP items with exact names and prices. This is your paywall preview: if the
listing shows a "Yearly Premium ₫799,000" item you know to keep hunting until you
find where it's sold.

**Screenshots and video** — what the developer chose to show first, and in what
order. Note it; when you get in the app you'll see whether the real first-run
experience matches the marketing.

**What's new** — the recent changelog entries show what they're actively investing
in.

**Reviews** — read a sample of recent 1★ and 5★. Don't summarize sentiment; look
for *specifics*: complaints about aggressive ads, subscription confusion, a
feature that doesn't work, a paywall that appeared after an update. These give you
a targeted list of things to verify on-device, which is much better than exploring
blind.

**Data safety / privacy** — what data the app declares it collects and shares.
Useful context for the permission requests you'll see later.

## Landing page

If the developer has a marketing site (linked from the listing), fetch it into
`00-overview/landing-page.md`. Look for what the store listing can't tell you:

- Pricing page with the real tier structure, often clearer than the in-app paywall
- Feature comparison table (free vs pro) — a gift, since it hands you the gate map
- Web-app or cross-platform story
- Company info, team size, funding — context for how much to read into their
  design choices
- Blog/changelog for roadmap signals

Keep this section short if the site is thin. Not every app has one; say so and
move on rather than padding.

## Turning research into a plan

End `00-overview/store-listing.md` with two things.

**First, a core-flow hypothesis.** The headline of the long description usually
*is* the app's core flow; write it as one line before you open the app:

> Core flow (hypothesis): point the camera at a plant → get species + health
> verdict → result saved to a history. Free tier appears limited (IAP list shows
> "50 scans"), so expect a quota and a paywall somewhere in this flow.

This single line is what keeps the on-device work aimed at what the app is *for*
instead of at whatever screen happens to be in front of you. You'll confirm or
correct it in the overview pass — either way it's cheap. See
`references/flow-investigation.md` for what to do with it.

**Second, a short list — three to six items — of things to verify on-device**,
drawn from the research above. For example:

> - Listing advertises "unlimited scans" but IAP list includes "50 scans" — find
>   the real free limit
> - Recent reviews complain about a full-screen ad on app open — confirm
> - Feature "Plant care reminders" is claimed but not in any screenshot — check
>   whether it's gated

This list is what makes the exploration phase targeted rather than aimless, and
each item you resolve becomes a concrete finding in the final report.

## Optional signals

If the user has Sensor Tower, Adjust, or similar MCP connectors available, they can
give download/revenue estimates and ad-network intelligence that no store page
will. Check whether those tools are connected; if they are, pull the numbers. If
they aren't, don't block on it — the review works fine without them.
