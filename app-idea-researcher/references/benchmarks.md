# Benchmarks — Revenue, Costs, Conversion

**As of: 2026-10-06.** Every number here has a source and a date. Use these instead of numbers
from memory, cite them in the report (e.g. "RevenueCat SOSA 2026"), and copy the source into
the report's Sources section.

**Refresh rule**: if this file is more than 12 months old, or a number decides a verdict,
re-verify it with web research and update this file (keep the date line current).

Numbers marked *(derived)* are arithmetic or judgment on top of the sources, not published
figures — treat them as Low confidence.

---

## Table of Contents
1. [Store fees](#1-store-fees)
2. [Subscription funnel](#2-subscription-funnel)
3. [Subscription prices and plan mix](#3-subscription-prices-and-plan-mix)
4. [Revenue per install and LTV](#4-revenue-per-install-and-ltv)
5. [Retention and renewal](#5-retention-and-renewal)
6. [Reality check: how new apps actually do](#6-reality-check-how-new-apps-actually-do)
7. [Ad monetization](#7-ad-monetization)
8. [Install buckets and rating ratios](#8-install-buckets-and-rating-ratios)
9. [User acquisition and demand-test costs](#9-user-acquisition-and-demand-test-costs)
10. [Team and development cost](#10-team-and-development-cost)
11. [Sources](#sources)

---

## 1. Store fees

For a developer under $1M/year, **plan on 15% on both stores**.

| Store / region | Small developer (< $1M/yr) | Notes |
|---|---|---|
| Google Play, most countries (until the global rollout, announced for 2027-09-30) | 15% (subscriptions 15%) | [S1] |
| Google Play, US/UK/EEA (from 2026-06-30), AU/JP (from 2026-09-30) | 10% service fee + 5% billing fee if Play Billing is used (= 15%); 10% with alternative billing / web links | Epic settlement terms [S2][S3] |
| Apple App Store (Small Business Program) | 15% on IAP and subscriptions from day one | Threshold: $1M proceeds in the prior calendar year [S4] |
| Apple, outside SBP | 30%, subscriptions 15% after 12 months of paid service | [S5] |
| Apple, US link-out purchases | 0% at present (court order); a 5-15% fee is proposed, not approved | Re-check before relying on it [S6] |

## 2. Subscription funnel

| Metric | Value | Source |
|---|---|---|
| Download → paid by day 35, median all apps | **2.0%** (top 10%: > 9.1%) | RevenueCat SOSA 2026 [R1] |
| Download → paid D35, **by store** | **Android 0.9% vs iOS 2.6%** | RevenueCat [R2] |
| Download → paid D35, by region | North America 2.8%, Western Europe 2.0%, APAC 2.4%, India/SE Asia 0.7% | [R1] |
| Download → paid D35, by category | Health & Fitness 2.9%, Business 2.6%, Education 2.4%, Gaming 1.0% | [R1] |
| Hard paywall vs freemium, D35 | 10.7% vs 2.1% | [R1][R2] |
| Install → trial start, median | 10.9% (Adapty, iOS-heavy); RevenueCat D30 by category: Business 9.1%, H&F 6.9%, Education 6.5% | [A1][R3] |
| Trial → paid | ~32.5% (RevenueCat; **Android ≈ iOS** once a trial starts); Adapty median 25.6% | [R2][A1] |
| Trial → paid, by category (RevenueCat) | H&F 37.7%, Travel 43.5%, Photo & Video 22.2% | [R1] |
| Trial → paid, by trial length | ≤ 4 days 25.5%, 5-9 days 37.4%, 17-32 days 42.5% | [R4] |
| Adapty category funnels (install→trial / trial→paid) | Utilities 13.8% / 26.2%; Photo & Video 14.0% / 30.5%; Productivity 9.8% / 29.5% | [A2][A3][A4] |

**Android takeaway**: the gap is at the top of the funnel (fewer users start a trial or reach a
paywall), not in trial conversion. For Android-first projections, use ~0.9% download→paid as the
median, not iOS numbers.

## 3. Subscription prices and plan mix

| Metric | Value | Source |
|---|---|---|
| Median price, all apps (RevenueCat) | Weekly ~$5-6, monthly $8.00, annual $34.80 | [R1] |
| Median annual by region | North America $39.99, Western Europe $39.44, India/SE Asia $18.32 | [R1] |
| Median by category | H&F $39.94/yr, $9.99/mo; Education $44.99/yr | [R1][R3] |
| Median price (Adapty, iOS-heavy) | Weekly $7.48, monthly $12.99, annual $38.42 | [A2][A3] |
| Revenue share by plan (Adapty, revenue-weighted) | Weekly 55.5%, annual 22.5%, monthly 11.7%, one-time ~10% | [A5] |
| Units sold by plan (RevenueCat) | Monthly 42%, yearly 34%, weekly 24% | [R1] |

## 4. Revenue per install and LTV

| Metric | Value | Source |
|---|---|---|
| RPI day 14 / day 60, median all apps | $0.23 / $0.34 | [R1][R3] |
| RPI by category (D14 / D60) | H&F $0.48 / $0.66; Business $0.31 / $0.50; Gaming $0.08 / $0.14 | [R1] |
| RPI by region (D14 / D60) | North America $0.38 / $0.55; India/SE Asia $0.08 / $0.11 | [R1] |
| RPI, hard paywall vs freemium (D14) | $2.32 vs $0.27 | [R1] |
| 12-month LTV per install (Adapty, median) | H&F $1.21, Utilities $1.09, Photo & Video $0.82; US ≈ 2× global | [A2][A3] |
| Year-1 realized LTV per payer | Median ~$23; H&F $35.64, Gaming $11.22 | [R1] |
| **Android RPI** | Not published. Plan on **0.3-0.5× iOS** *(derived from 0.9% vs 2.6% conversion)* | [R2] |

## 5. Retention and renewal

| Metric | Value | Source |
|---|---|---|
| First renewal, monthly / annual | H&F 57% / 25%; Productivity 54% / 23%; Photo & Video 48% / 23%; Education 56% / 24%; Utilities 57% / 35% | RevenueCat [R5] |
| First renewal range across categories | Monthly 42-61%, annual 23-40% | [R5] |
| Annual plan, year-1 retention | ~28% | [R6] |
| Day-380 retention, trial subscribers | Annual 19.9%, monthly 14.2%, weekly 5.5% | Adapty [A5] |
| Involuntary churn (billing failures share of cancellations) | Google Play 31-32% vs App Store 14-15% | [R2][R7] |

## 6. Reality check: how new apps actually do

Use this to sanity-check every projection. An optimistic case that beats most of these numbers
needs a stated reason.

| Metric | Value | Source |
|---|---|---|
| New subscription apps reaching **$1K MRR within 2 years** | **17%** | RevenueCat [R1][R8] |
| New subscription apps reaching **$10K MRR within 2 years** | **4.6%** | [R1][R8] |
| Median monthly revenue one year after launch | ~$72 (top 10%: > $2,500) | [R1] |
| Lifetime revenue of new apps (Adapty) | 57.7% under $1K; 22.4% $1-10K; 12% $10-100K; 7.9% above $100K | [A6] |
| Revenue concentration | Top 10% of apps earn 94.5% of revenue | [A6] |
| Hybrid (subscription + other) models | Only ~10% of apps; 63.5% subscription-only | [R1] |

Rule of thumb: a conservative month-12 projection above **$1K/month** says the idea beats ~83% of
launches — the report must explain why (proven demand, weak competitors, distribution edge).

## 7. Ad monetization

Public eCPM data is mostly **games**; non-game apps earn less. The defaults below are
*(derived)*: annual averages, Android, non-game, Q4 seasonality removed, ~20-30% below games.

| Market | Banner | Interstitial | Rewarded | App open |
|---|---|---|---|---|
| US | $0.3-0.8 | $5-10 | $8-14 | $3-8 |
| UK / DE / FR | $0.15-0.3 | $3-6 | $5-9 | $2-4 |
| Global blended | $0.1-0.3 | $1.5-4 | $3-8 | n/a |
| SEA / Vietnam / India | $0.05-0.2 | $0.5-2 | $1-4 | $0.5-2.3 |

Reference points behind them:
- Appodeal (Q4 2024, games-focused): US Android interstitial ~$12.3, rewarded ~$13.2, banner
  ~$0.6; global Android interstitial ~$1.65, rewarded ~$3.0, banner ~$0.12 [D1]. Q4 runs
  20-40% above Q1 [D2].
- MonetizeMore (2024 data, mixed apps): Vietnam interstitial $0.72-1.51, app open $1.30-2.34;
  US interstitial $6.50-8.57 [D3].
- Bidlogic Q2 2026: eCPMs trending up (iOS interstitial +10-17%, Android +3-14% in developed
  markets) [D4].

| Metric | Value | Source |
|---|---|---|
| ARPDAU, utility apps with ads | ~$0.01-0.035 average, $0.05+ top *(vendor estimates, low rigor)* | [D5][D6] |
| US Android utility, interstitial + app open + banner | ~$0.03-0.06 ARPDAU *(derived)* | — |
| Sessions per DAU, utility | ~0.8-1.8 per day (vs 4-5 for games) | [D6][D7] |
| Fill rate | 85-95% Tier-1-heavy traffic, 70-85% mixed, 50-70% emerging markets | [D7] |

Ad revenue formula: `Monthly ≈ DAU × ARPDAU × 30`. Use 70-80% of any calculator's output [D7].

**Google Play policy constraints**: no unexpected full-screen interstitials; they must be
closeable (within 15 s unless opt-in rewarded) and shown at natural breaks; repeated interstitials
during tasks count as "Made for Ads" [D8]. App open ads only at launch/loading, and not in
Designed for Families apps [D9]. No 2026 policy change to full-screen or app-open ads found.

## 8. Install buckets and rating ratios

**Google Play install labels are lower bounds** [I1]:

| Label | Range | | Label | Range |
|---|---|---|---|---|
| 1K+ | 1,001-5,000 | | 500K+ | 500,001-1M |
| 5K+ | 5,001-10,000 | | 1M+ | 1,000,001-5M |
| 10K+ | 10,001-50,000 | | 5M+ | 5,000,001-10M |
| 50K+ | 50,001-100,000 | | 10M+ | 10,000,001-50M |
| 100K+ | 100,001-500,000 | | 50M+ | 50,000,001-100M |

- Use the floor in calculations and show the range. Buckets span 2-5×.
- Star ratings only show with enough ratings: 0.1% of apps under 100 installs show one, 93.6%
  of apps above 1M do [I2]. A missing rating on a small app is normal, not a data error.
- **Ratings → downloads**: no credible current ratio exists. Use **ratings × 60-200** as a rough
  cross-check *(derived from an old iOS study of ~1 review per 62 downloads [I3] and tool
  heuristics of 1 per 100-200 [I4])*. Always Low confidence; prefer install buckets on Android.

## 9. User acquisition and demand-test costs

| Market | CPI, non-game | Source |
|---|---|---|
| Tier-1, Android | Productivity/AI $0.80-2.50; H&F $1-5; Education $1.50-4.50; Shopping $0.80-4 | Admiral Media 2026 [U1] |
| Tier-1, iOS | Productivity/AI $2-6; H&F $2-10; Education $3-9 (iOS ≈ 2-3.5× Android) | [U1] |
| Tier-2 / Tier-3 | 50-70% / 3-8× lower than Tier-1 | [U1] |
| Blended iOS + Android | US $3.50-6.50; UK $2.80-5.00; DE $2.50-4.50; Vietnam $0.30-0.90; Indonesia $0.40-1.20; India $0.20-0.70 | SEM Nexus 2026 [U2] (low-medium confidence) |
| Apple search ads, median CPI | Global $1.80; US $4.06; UK $2.60 | AppTweak 2026 [U3] |

| Meta ads (2026) | CPM | CPC |
|---|---|---|
| US | $23.00 | $2.69 |
| UK | $10.31 | $1.95 |
| Germany | $10.05 | $1.45 |
| Vietnam | $2.10 | $0.15 |
| India | $2.60 | $0.20 |

Source: AdAmigo [U4] (vendor blog, low-medium confidence).

**Demand-test budgets** *(derived)*:
- Fake door, 500 landing-page clicks × CPC: ~$75 (Vietnam), ~$725 (DE), ~$975 (UK), ~$1,350 (US).
- Install test, 100-200 installs × CPI: ~$100-500 for a US Android non-game audience.
- Set the pass/fail threshold before launching. ~2-3% click intent from cold traffic is a
  meaningful signal [U5]; median landing-page conversion is ~6.6% across industries [U6].

## 10. Team and development cost

**Vietnam (local employers, gross monthly salary)** — ITviec 2025-26 [T1]:

| Role | Median |
|---|---|
| Mobile dev, 1-2 yrs / 3-4 yrs / 5-8 yrs | 28.8M / 29.05M / 37.35M VND |
| Backend dev, 3-4 yrs / 5-8 yrs | 30.1M / 39.9M VND |
| QA/QC (all levels) | 31.2M VND |
| UI/UX designer, mid-level | 22-45M VND [T2][T3] |

- Employer on-cost ≈ +30% (social, health, unemployment insurance and union fee ≈ 23.5%, plus a
  13th-month salary ≈ 8.3%) [T4].
- Example *(derived)*: Android + backend + designer, all mid-level ≈ 87M VND gross ≈ 115M VND with
  on-cost ≈ **$4,400/month** (≈ 26,000 VND/USD). Hanoi runs 10-15% below HCMC, Da Nang 20-30% below [T5].
- International-hiring view, mid-level: $1,500-2,800/month [T5].

**Hourly rates (freelance / agency)**:

| Where | Rate | Source |
|---|---|---|
| Vietnam freelance mobile | Junior $18-30, mid $30-45, senior $45-65 | [T6] |
| Vietnam agency mobile | Mid $25-39, senior $39-56 | [T4] |
| Vietnam UI/UX freelance, mid | $28-42 | [T2] |
| Eastern Europe | $40-85 | [T7] |
| Western Europe | $70-120 | [T7] |
| US / Canada | $82-130 overall; mobile mid-level $108-165 | [T7][T8] |

For a self-funded team, the opportunity cost is the team's monthly salary bill — use that for
break-even, and state which basis you used.

---

## Sources

**Store fees**
- [S1] Google Play Console Help, Service fees — https://support.google.com/googleplay/android-developer/answer/112622
- [S2] Google Play Console Help, Understanding Google Play's lower service fees (2026) — https://support.google.com/googleplay/android-developer/answer/16954621
- [S3] Android Developers Blog, Expanded billing choice and lower fees (2026-06) — https://android-developers.googleblog.com/2026/06/play-expanded-billing.html
- [S4] Apple, App Store Small Business Program — https://developer.apple.com/app-store/small-business-program/
- [S5] Apple, Auto-renewable subscriptions — https://developer.apple.com/app-store/subscriptions/
- [S6] MacRumors, Apple link-out fee proposal (2026-08-13) — https://www.macrumors.com/2026/08/13/app-store-fees-apple-link-outs/

**Subscriptions**
- [R1] RevenueCat, State of Subscription Apps 2026 (2026-03) — https://www.revenuecat.com/state-of-subscription-apps
- [R2] RevenueCat, The Android paywall conversion gap (2026-03-25) — https://www.revenuecat.com/blog/engineering/android-paywall-gap
- [R3] RevenueCat, SOSA 2026 Business / Education cuts — https://www.revenuecat.com/state-of-subscription-apps-2026-business/ , https://www.revenuecat.com/state-of-subscription-apps-2026-education
- [R4] RevenueCat, How long should your free trial be? (2026-09-28) — https://www.revenuecat.com/blog/growth/free-trial-length
- [R5] RevenueCat, Average subscription renewal rates by category (2026-04-24) — https://www.revenuecat.com/blog/growth/average-subscription-renewal-rates-by-app-category
- [R6] PPC Land on RevenueCat SOSA Part 2 (2026-05-28) — https://ppc.land/95-of-annual-app-subscribers-who-cancel-never-return-revenuecat-finds/
- [R7] RevenueCat, Google Play billing error churn (2026-04-02) — https://www.revenuecat.com/blog/growth/google-play-billing-error-churn-how-to-fix
- [R8] PPC Land on RevenueCat data, "The app middle class is dying" (2026-03-12) — https://ppc.land/the-app-middle-class-is-dying-and-revenuecats-data-shows-exactly-how-fast/
- [A1] Adapty, State of In-App Subscriptions 2026 (2026-03) — https://adapty.io/state-of-in-app-subscriptions-report/
- [A2] Adapty, Utilities benchmarks (2026) — https://adapty.io/blog/utilities-app-subscription-benchmarks/
- [A3] Adapty, Photo & Video benchmarks (2026) — https://adapty.io/blog/photo-video-app-subscription-benchmarks/
- [A4] Adapty, Productivity benchmarks (2026-03-27) — https://adapty.io/blog/productivity-app-subscription-benchmarks/
- [A5] Adapty, Weekly vs monthly vs annual (2026-03-26) — https://adapty.io/blog/weekly-monthly-annual-subscription-plan/
- [A6] Adapty, 94.5% of subscription revenue goes to 10% of apps (2026-03-20) — https://adapty.io/blog/app-subscription-revenue-concentration/

**Ads**
- [D1] Appodeal, The Latest eCPM Report 2025 (Q4 2024 data) — https://appodeal.com/wp-content/uploads/2025/03/Appodeal-The-Latest-eCPM-Report-2025.pdf
- [D2] Playio, 2026 Mobile Game eCPM Benchmarks — https://blog.playio.co/mobile-game-ecpm-benchmarks-2026
- [D3] MonetizeMore, 2026 eCPM Insights (2024 data) — https://www.monetizemore.com/blog/ecpm-insights/
- [D4] Bidlogic, Q2 2026 eCPM growth (2026-07-31) — https://bidlogic.io/2026/07/31/q2-2026-ecpm-growth-interstitial-rewarded-video-and-banner-trends/
- [D5] Perkox, ARPDAU Benchmarks 2026 (2026-08-28) — https://blog.perkox.com/2026/08/arpdau-benchmarks-2026/
- [D6] MonetizeMore, 2026 AdMob & Mobile Monetization Playbook — https://www.monetizemore.com/blog/admob-monetization/
- [D7] Playwire, AdMob eCPM benchmarks / revenue calculator (2025) — https://www.playwire.com/blog/admob-ecpm-benchmarks-what-publishers-should-expect
- [D8] Google Play policy, Ads — https://support.google.com/googleplay/android-developer/answer/9857753
- [D9] Google AdMob Help, App open ad guidance — https://support.google.com/admob/answer/9341964

**Installs & ratings**
- [I1] CPIDroid, How Google displays the app installs count — https://cpidroid.com/blog/93/how-google-displays-the-app-installs-count-on-google-play-listing
- [I2] Testers Community, Inside Google Play in 2026 (2026-09-16) — https://www.testerscommunity.com/research/google-play-statistics
- [I3] Sensor Tower, Visualizing the iOS App Store (2013, outdated) — https://sensortower.com/blog/visualizing-the-ios-app-store
- [I4] Sonar, App revenue estimates: how they work and fail (2026-08-10) — https://trysonar.app/blog/app-revenue-estimates-how-they-work-and-fail

**User acquisition**
- [U1] Admiral Media, Mobile App Marketing Benchmarks 2026 (2026-04-19) — https://admiral.media/mobile-app-marketing-benchmarks-2026/
- [U2] SEM Nexus, CPI by Country 2026 (2026-07-22) — https://semnexus.com/cpi-by-country-where-app-budget-goes-furthest-2026
- [U3] AppTweak, Apple Ads benchmarks 2026 — https://www.apptweak.com/en/aso-blog/apple-ads-benchmarks
- [U4] AdAmigo, Meta Ads CPM and CPC by country 2026 (2026-10-04) — https://www.adamigo.ai/blog/meta-ads-cpm-cpc-benchmarks-by-country-2026
- [U5] Userpilot, Fake door testing — https://userpilot.com/blog/fake-door-testing/
- [U6] ClickMinded, Landing page conversion benchmark 2026 — https://www.clickminded.com/landing-page-conversion-benchmark/

**Team cost**
- [T1] ITviec, Vietnam IT Salary & Recruitment Market Report 2025-2026 — https://itviec.com/report/vietnam-it-salary-and-recruitment-market
- [T2] Second Talent, UI/UX designer rates in Vietnam (2026-09-14) — https://www.secondtalent.com/developer-rate-card/ui-ux-designer-vietnam/
- [T3] UI/UX Jobs Board, UI/UX designer salary Vietnam (2026) — https://uiuxjobsboard.com/salary/ui-ux-designer/vietnam
- [T4] Second Talent, True cost to outsource software development in Vietnam (2026-09-10) — https://www.secondtalent.com/resources/true-cost-outsource-software-development-vietnam/
- [T5] VietnamDevs, Vietnam software developer salaries 2026 (2026-03-20) — https://vietnamdevs.com/blog/vietnam-software-developer-salaries-2026-guide-for-international-recruiters
- [T6] Second Talent, Mobile app developer rates in Vietnam (2026-07) — https://www.secondtalent.com/developer-rate-card/vietnam-mobile-app-developer/
- [T7] Arc, Freelance developer rates in 2026 (2026-05-26) — https://arc.dev/employer-blog/freelance-developers-cost/
- [T8] Second Talent, Mobile app developer cost by country (2026-09-24) — https://www.secondtalent.com/resources/cost-hire-mobile-app-developer-by-location/
