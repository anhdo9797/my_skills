# Phase 2: Analysis — Deep Methodology

This reference provides the complete framework for competitor analysis and market assessment.
Read this before executing Phase 2. Which data tools you can use was settled in the capability
check (`data_sources.md`); benchmark numbers come from `benchmarks.md`.

---

## Table of Contents
1. [5-Step Competitor Analysis Framework](#5-step-competitor-analysis-framework)
2. [Competitor Identification](#step-1-competitor-identification)
3. [Keyword & ASO Analysis](#step-2-keyword--aso-analysis)
4. [App Store Listing Audit](#step-3-app-store-listing-audit)
5. [Product & Review Deep Dive](#step-4-product--review-deep-dive)
6. [Performance Tracking](#step-5-performance-tracking)
7. [Revenue Estimation Methods](#revenue-estimation-methods)
8. [Competitive Strength Rating](#competitive-strength-rating)
9. [Analysis Output Template](#analysis-output-template)

---

## 5-Step Competitor Analysis Framework

This is a systematic process — don't skip steps. Each builds on the previous.

### Step 1: Competitor Identification

Identify **three types** of competitors:

| Type | Definition | Example |
|------|-----------|---------|
| **Direct** | Same problem, same audience, similar features | Uber vs. Lyft |
| **Indirect** | Same problem, different approach or audience | Uber vs. Public Transit App |
| **Potential** | Not in the space yet, but could enter easily | Google Maps adding ride-hailing |
| **Platform** | The OS or device maker ships it built-in or as a first-party app | Built-in recorder transcription on flagship phones |

**How to find them:**
1. Search 5-10 core keywords in the target store and country — with the keyword-ranking
   capability if available, otherwise `python3 scripts/store_lookup.py play-search "<kw>"` /
   `ios-search "<kw>"`
2. Note apps that appear in the top 10 across multiple keywords
3. Search "best [category] apps [year]" on the web
4. Check "Similar apps" / "You might also like" sections
5. Search Product Hunt and recent store launches for new entrants
6. Check whether Google/Apple/Samsung or another OEM ships the feature — a platform competitor
   changes the whole verdict

**Target**: Identify 3-5 direct competitors + 2-3 indirect competitors per niche.

### Step 2: Keyword & ASO Analysis

Understanding competitors' keyword strategy reveals their positioning and traffic sources.

**What to analyze:**
- App title and subtitle / short description — which keywords do they prioritize?
- Description — keyword density and highlighted features
- Search ranking for category terms

**Look for keyword gaps:**
- High-volume terms that no competitor ranks well for
- Long-tail variations competitors ignore
- Localized terms (in target language/market) without strong results

**Reading keyword data correctly** (details in `data_sources.md`):
- A keyword with **0 ranking apps or "not synced"** means no data — check the store search page
  before calling it uncontested.
- **Null popularity** means the metric isn't available on this plan, not that nobody searches.
- The number of apps ranking (e.g. "250 apps") is a cap of the tool, not market size. Judge by
  the **quality** of the top 5-10: installs, ratings, freshness.

### Step 3: App Store Listing Audit

The store listing is the competitor's "sales page" — study it carefully. Get the numbers with
the app-metadata capability or `python3 scripts/store_lookup.py play <pkg...>` / `ios <id...>`.

| Element | What to analyze |
|---------|----------------|
| **Icon** | Style, color, visual clarity at small size |
| **Screenshots** | Feature highlights, messaging, visual style |
| **Video preview** | Do they have one? What do they showcase first? |
| **Title + Subtitle** | Keyword strategy, brand positioning |
| **Description** | First 3 lines (visible before "Read More"), feature order |
| **Update frequency** | Last updated date; stale for 12+ months = possibly abandoned |
| **Monetization flags** | Contains ads / in-app purchases / price; IAP price range on the listing |
| **Rating + count** | Volume indicates market size; score indicates quality |
| **Installs (Play)** | Bucket (`100K+` = 100,001-500,000); use the floor in calculations |

**Track changes**: Note if they update metadata frequently — this signals an active ASO strategy
you'll need to compete against.

### Step 4: Product & Review Deep Dive

This is where you find the real competitive intelligence.

**Review analysis process:**
1. Read recent reviews of the top 3 competitors — aim for 30+ per app, weighted toward 1-3★.
   With a review-text capability, pull them directly; otherwise read the reviews on the store
   page and search the web for complaints ("[app] not working", "[app] alternative",
   `site:reddit.com [app]`). Say which route you used — a handful of reviews is Low confidence.
2. Categorize into themes using this framework:

| Category | Examples | Your Action |
|----------|---------|-------------|
| **Feature requests** | "I wish it had X" | Potential USP features |
| **UX complaints** | "Too confusing", "Takes too many taps" | UX advantage opportunity |
| **Pricing complaints** | "Too expensive", "Not worth subscription" | Monetization differentiation |
| **Quality issues** | "Crashes", "Slow", "Battery drain" | Technical quality as differentiator |
| **Missing audience** | "Not suitable for beginners" | Niche-down opportunity |
| **Praise** | "Love the X feature" | Must-have features for MVP |

3. **Count complaint frequency** — the most common complaints are the strongest opportunity
   signals. Quote 1-2 short real reviews per theme as evidence.

**Hands-on product audit** (optional, expensive): when one competitor decides the verdict and
the user wants depth, recommend a teardown with the `mobile-app-review` skill (if installed) —
it drives the app on a device and maps flows, paywalls and data handling. Put it in "Recommended
Next Steps" rather than doing it inside this research.

### Step 5: Performance Tracking

Don't just take a snapshot — understand the trajectory:

- **Download trend**: from a download-estimate capability if available; otherwise install-bucket
  changes, or rating-count growth between two dated observations
- **Review velocity**: how many new reviews per week (indicates active user base)
- **Update cadence**: weekly releases = active team; no updates in 12 months = abandoned
- **Category ranking movement**: rising or dropping, from a top-charts capability or web reports

---

## Revenue Estimation Methods

Exact revenue data is private, but you can make educated estimates. Use the first method that
is available, and always say which one you used.

### Method 1: Market-intelligence estimates
If the capability check found a working revenue/download-estimate tool, use it — Tier A for
direction, but still an estimate. Treat a locked or null result as "no data", never as $0.

### Method 2: Public numbers
Company announcements, funding news citing ARR, founder interviews, public filings, industry
reports listing top grossers. Tier B — cite with date.

### Method 3: Funnel model (no estimates available)

Use the numbers in `benchmarks.md` (dated, sourced), not memory:

**For subscription apps:**
```
Monthly revenue ≈ Downloads/month × Download→paid % × Net price per month
Net price = list price × (1 − store commission)
```
Use the store-specific conversion: Android converts far below iOS (see `benchmarks.md`).

**For ad-supported apps:**
```
Monthly revenue ≈ DAU × ARPDAU × 30
or  DAU × Impressions/DAU/day × eCPM / 1000 × 30
```

**For IAP / one-time purchase apps:**
```
Monthly revenue ≈ MAU × Paying user % × ARPPU
```

### Method 4: Proxy signals
- Install bucket (Play) or rating count (iOS) → rough lifetime downloads, using the ratios in
  `benchmarks.md` (wide uncertainty — present as a range)
- Top-grossing chart position in the category
- Paid subscription / IAP items on the listing = someone pays; no monetization flags = nobody
  pays this app yet

**Important**: Always present revenue estimates as ranges, not exact numbers. Flag the method.

---

## Competitive Strength Rating

After completing the analysis, rate each niche:

### 🟢 Weak Competition — "Go" signal
- Top apps < 4.0★, or < 100K installs (Play) / < 10K ratings (iOS)
- Leaders not updated in 12+ months
- Clear, recurring complaints in reviews
- No major brand or platform owner in the niche
- Simple feature set (your team can match + exceed quickly)

### 🟡 Moderate Competition — "Proceed with caution"
- Top apps 4.0-4.5★ with 100K-5M installs (Play) / 10K-100K ratings (iOS)
- Active but not aggressive update cadence
- Some gaps but competitors are decent
- Mix of indie and company-backed apps
- Differentiation is possible but requires clear USP

### 🔴 Strong Competition — "Avoid or niche down"
- Top apps 4.5★+ with 10M+ installs (Play) / 100K+ ratings (iOS)
- Frequent updates, strong ASO, active marketing
- Backed by well-funded companies, or the platform ships it built-in
- Strong network effects or ecosystem lock-in
- Very hard to differentiate without massive investment

---

## Analysis Output Template

For each niche analyzed, produce this summary (headings and labels in the report's language):

```markdown
### [Niche Name]

**Competition Level**: 🟢/🟡/🔴

**Top Competitors:** (store, country, fetch date)
| App | Rating | Ratings | Installs | Monetization | Last Updated |
|-----|--------|---------|----------|-------------|-------------|
| ... | ... | ... | ... | ... | ... |

**Key Weaknesses Found:** (with review evidence)
1. [Most common complaint]
2. [Second most common]
3. [Third most common]

**Revenue Estimate**: $X-Y/month (method used, confidence)

**Verdict**: [1-2 sentence assessment — pass to Phase 3 or reject?]
```
