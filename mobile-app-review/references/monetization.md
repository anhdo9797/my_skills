# Monetization analysis

Ads and subscriptions are usually why the user asked for this review in the first
place — they want to know how a successful competitor makes money, and where.
Feature lists are easy to get from a store page; *where the paywall fires* is not.
That's the value you're adding, so record it with precision.

## Contents

- [Ad placements](#ad-placements)
- [Paywalls and subscriptions](#paywalls-and-subscriptions)
- [Other monetization](#other-monetization)
- [Template: analysis/monetization.md](#template-analysismonetizationmd)

---

## Ad placements

Record every ad the moment you see it, via
`changelock.py add-finding --type ad`. Reconstructing this at the end from memory
never works.

For each ad instance capture:

| Field | Notes |
|---|---|
| Screen | Which screen path it appeared on |
| Format | banner / native card / interstitial / rewarded video / app-open / MREC |
| Position | top / bottom / inline-in-feed (which index) / full-screen / after-action |
| Trigger | shown always, on screen entry, after N actions, on back-press, on app resume |
| Frequency | how often it repeated during your session; note cooldowns you observe |
| Dismissible | is there an X, and after how many seconds does it appear |
| Network | if identifiable from the ad chrome ("AdChoices", Google, AppLovin, Unity) |
| Screenshot | path |

**Do not tap the ad creative itself.** You get all the information you need from
the frame around it, and clicking generates invalid traffic. The one exception is
a **rewarded ad button inside the app** ("Watch a video to unlock") — that's an
app feature and you should document the reward, but you can describe the flow from
the entry button and the ad's close behavior without engaging the ad content.

Signals worth calling out explicitly, because they're the design decisions the
user is really asking about:
- Which screens are deliberately kept ad-free (usually onboarding, purchase flow,
  and the core value moment) — restraint is a strategy
- Whether ads gate a core action or only decorate around it
- The ad-to-content ratio in feeds (every Nth item)
- Whether removing ads is itself a paid tier, and at what price

## Paywalls and subscriptions

A **paywall trigger** is any place the app pushes toward paying. Catalog them; the
map of triggers is more interesting than the paywall screen itself.

Common trigger types to look for deliberately:
- Post-onboarding (hard paywall before first use — note if it's skippable and how
  hidden the skip is)
- Feature-gated (tapping a PRO-badged feature)
- Limit-reached (N free scans/uses per day, then a wall)
- Timed (after X minutes, or on the Nth app open)
- Persistent surface (a crown icon, a banner in settings, a tab)
- On exit / on back-press
- Discount interstitial (a "special offer" that appears when you try to close the
  paywall — always try closing once to see if this exists; it's a very common
  pattern and easy to miss)

For the paywall screen itself, extract:

- Every tier: name, price, billing period, per-period equivalent, "save X%" badge
- Which tier is preselected and which is visually emphasized (that's the one they
  want you to buy)
- Free trial: length, whether a payment method is required, when it charges
- Lifetime / one-time purchase option
- The feature list used to justify the price
- Fine print: auto-renew terms, cancellation
- Close affordance: how visible is the X, is there a delay before it appears
- Whether prices are localized

Screenshot the paywall in every state: initial, each tier selected, scrolled to the
fine print, and the exit-intent offer if one appears.

**Then stop.** Tapping through to the OS payment sheet is the boundary; screenshot
it if you reach it accidentally and cancel immediately. Never confirm.

## Other monetization

Don't stop at ads and subs — note anything else that appears:
consumable IAP (coins, credits), one-time feature unlocks, affiliate or commerce
links out to a store, sponsored content in feeds, data-collection-heavy onboarding
questions, or an email capture that feeds a marketing funnel.

## Template: analysis/monetization.md

Write in the user's language; keep table headers consistent so the file is
skimmable.

```markdown
# Monetization — <App name> <version> (<platform>)

## Summary
Two or three sentences: what the model is (ad-supported / freemium / hard paywall /
hybrid), how aggressive it feels, and the single most notable decision.

## Ad placements
| # | Screen | Format | Position | Trigger | Frequency | Screenshot |
|---|--------|--------|----------|---------|-----------|------------|

### Observations
- Ad-free zones and why they're probably ad-free
- Ratio in feeds, cooldowns observed
- Where ads interrupt the core loop vs. sit beside it

## Subscription tiers
| Tier | Price | Period | Effective /month | Trial | Preselected | Notes |
|------|-------|--------|------------------|-------|-------------|-------|

### Fine print
### Exit-intent / discount offers

## Paywall triggers
| # | Trigger | Screen | Skippable | Skip affordance | Screenshot |
|---|---------|--------|-----------|-----------------|------------|

## Free vs paid feature split
| Feature | Free | Paid | Gate type |
|---------|------|------|-----------|

## Other monetization

## Takeaways
The 3–5 things worth stealing or avoiding, stated plainly.
```
