# Phase 2: Analysis — Deep Methodology

This reference provides the complete framework for competitor analysis and market assessment.
Read this before executing Phase 2.

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

**How to find them:**
1. Search 5-10 core keywords in App Store / Google Play
2. Note apps that appear in top 10 across multiple keywords
3. Search "best [category] apps [year]" on web
4. Check "Similar apps" / "You might also like" sections
5. Search Product Hunt for recent launches in the category

**Target**: Identify 3-5 direct competitors + 2-3 indirect competitors per niche.

### Step 2: Keyword & ASO Analysis

Understanding competitors' keyword strategy reveals their positioning and traffic sources.

**What to analyze:**
- App title and subtitle — which keywords do they prioritize?
- Description — keyword density and highlighted features
- Search ranking for category terms

**Look for keyword gaps:**
- High-volume terms that no competitor ranks well for
- Long-tail variations competitors ignore
- Localized terms (in target language/market) without strong results

**Tools** (if user has access): AppTweak, ASODesk, MobileAction, AppRadar, Foxdata.

### Step 3: App Store Listing Audit

The store listing is the competitor's "sales page" — study it carefully:

| Element | What to analyze |
|---------|----------------|
| **Icon** | Style, color, visual clarity at small size |
| **Screenshots** | Feature highlights, messaging, visual style |
| **Video preview** | Do they have one? What do they showcase first? |
| **Title + Subtitle** | Keyword strategy, brand positioning |
| **Description** | First 3 lines (visible before "Read More"), feature order |
| **Update frequency** | How often they release updates (active team signal) |
| **App size** | Bloated = possible UX issues |
| **Rating + count** | Volume indicates market size; score indicates quality |

**Track changes**: Note if they update metadata frequently — this signals an active ASO strategy
you'll need to compete against.

### Step 4: Product & Review Deep Dive

This is where you find the real competitive intelligence.

**Review analysis process:**
1. Read **50-100 recent reviews** per major competitor (mix of all ratings)
2. Categorize into themes using this framework:

| Category | Examples | Your Action |
|----------|---------|-------------|
| **Feature requests** | "I wish it had X" | Potential USP features |
| **UX complaints** | "Too confusing", "Takes too many taps" | UX advantage opportunity |
| **Pricing complaints** | "Too expensive", "Not worth subscription" | Monetization differentiation |
| **Quality issues** | "Crashes", "Slow", "Battery drain" | Technical quality as differentiator |
| **Missing audience** | "Not suitable for beginners" | Niche-down opportunity |
| **Praise** | "Love the X feature" | Must-have features for MVP |

3. **Count complaint frequency** — the most common complaints are the strongest opportunity signals

**Competitor product audit** (if feasible):
- Download and use top 3 competitor apps
- Document the onboarding flow (steps, friction points)
- Note feature set, UX patterns, and performance
- Screenshot anything noteworthy

### Step 5: Performance Tracking

Don't just take a snapshot — understand the trajectory:

- **Download trend**: Growing, stable, or declining?
- **Review velocity**: How many new reviews per week? (indicates active user base)
- **Update cadence**: Weekly releases = active team; no updates in 6 months = abandoned
- **Category ranking movement**: Rising or dropping?

---

## Revenue Estimation Methods

Exact revenue data is private, but you can make educated estimates:

### Method 1: Third-party intelligence tools
| Tool | Access | Reliability |
|------|--------|------------|
| **Sensor Tower** | Freemium (limited free data) | High (industry standard) |
| **data.ai (App Annie)** | Enterprise pricing | High |
| **AppMagic** | Affordable indie plans | Moderate-High |
| **AppTweak** | Freemium | Moderate |
| **Appfigures** | Developer-friendly pricing | Moderate |

### Method 2: Manual estimation (when no tools available)

**For ad-supported apps:**
```
Estimated Daily Revenue = DAU × Sessions/Day × Ads/Session × eCPM / 1000

Typical eCPM ranges:
- US/EU: $5-15 (banner), $15-50 (interstitial), $20-80 (rewarded video)
- SEA/VN: $1-5 (banner), $5-15 (interstitial), $10-30 (rewarded video)
```

**For subscription apps:**
```
Estimated Monthly Revenue = Downloads/Month × Trial Conversion % × Price

Typical conversion rates:
- Free trial → Paid: 2-5% (utility), 5-15% (productivity/health)
- Freemium → Paid: 1-3% (games), 3-8% (tools)
```

**For IAP apps:**
```
Estimated Monthly Revenue = MAU × Paying User % × ARPPU

Typical paying user %: 2-5% (games), 5-10% (tools)
```

### Method 3: Proxy signals
- App store ranking position correlates with download volume
- Number of reviews × 50-100 ≈ rough total downloads (varies by category)
- "Bestseller" or "Editor's Choice" badges = significant revenue

**Important**: Always present revenue estimates as ranges, not exact numbers.
Flag the estimation method used.

---

## Competitive Strength Rating

After completing the analysis, rate each niche:

### 🟢 Weak Competition — "Go" signal
- Top apps have < 4.0 stars or < 10K reviews
- No app updated in 6+ months
- Clear, recurring complaints in reviews
- No major brand/company backing competitors
- Simple feature set (your team can match + exceed quickly)

### 🟡 Moderate Competition — "Proceed with caution"
- Top apps have 4.0-4.5 stars with 10K-100K reviews
- Active but not aggressive update cadence
- Some gaps but competitors are decent
- Mix of indie and company-backed apps
- Differentiation is possible but requires clear USP

### 🔴 Strong Competition — "Avoid or niche down"
- Top apps have 4.5+ stars with 100K+ reviews
- Frequent updates, strong ASO, active marketing
- Backed by well-funded companies
- Strong network effects or ecosystem lock-in
- Very hard to differentiate without massive investment

---

## Analysis Output Template

For each niche analyzed, produce this summary:

```markdown
### [Niche Name]

**Competition Level**: 🟢/🟡/🔴

**Top Competitors:**
| App | Rating | Reviews | Downloads (est.) | Monetization | Last Updated |
|-----|--------|---------|-------------------|-------------|-------------|
| ... | ... | ... | ... | ... | ... |

**Key Weaknesses Found:**
1. [Most common complaint]
2. [Second most common]
3. [Third most common]

**Revenue Estimate**: $X-Y/month (category average for top 5)

**Verdict**: [1-2 sentence assessment — pass to Phase 3 or reject?]
```
