# Phase 4: Feasibility — Deep Methodology

This reference provides the complete scoring model, the verdict rules, cost estimation, risk
assessment, and revenue projection methods. Read this before executing Phase 4.

All benchmark numbers (conversion rates, eCPM, CPI, store fees, hourly rates) live in
`benchmarks.md` — use those, with their dates and sources, instead of numbers from memory.

---

## Table of Contents
1. [Scoring Model — 7 Criteria Detailed](#scoring-model--7-criteria-detailed)
2. [Confidence per Criterion](#confidence-per-criterion)
3. [Calculating the Score — use the script](#calculating-the-score--use-the-script)
4. [Verdict Rules](#verdict-rules)
5. [MVP Scoping with MoSCoW](#mvp-scoping-with-moscow)
6. [Cost Estimation Framework](#cost-estimation-framework)
7. [RICE Prioritization](#rice-prioritization)
8. [Risk Assessment Matrix](#risk-assessment-matrix)
9. [Revenue Projection Model](#revenue-projection-model)

---

## Scoring Model — 7 Criteria Detailed

Score each criterion 1-10 using the guidelines below. Avoid "5" as a default — push yourself
to decide whether it's above or below average. When the data needed for a criterion is missing,
still give your best estimate, **and mark its confidence Low** (next section). Never park an
unmeasured criterion at a comfortable 6 without saying it's a guess.

The store anchors are starting points, not formulas: they measure demand that is **already
served**. Adjust ±1 for trend direction, keyword breadth, and evidence from outside the stores.

### 1. Market Demand (Weight: 20%)

| Score | Criteria | Google Play anchor (top 5 apps for the core keyword, installs combined, bucket floors) | App Store anchor (top 5, ratings combined) |
|-------|----------|:---:|:---:|
| 9-10 | Strong evidence: large and growing, multiple independent signals | ≥ 50M | ≥ 500K |
| 7-8 | Good evidence: stable/growing, validated demand | 5M-50M | 50K-500K |
| 5-6 | Mixed signals: some demand, unclear growth | 500K-5M | 5K-50K |
| 3-4 | Weak evidence: niche or declining interest | 50K-500K | 500-5K |
| 1-2 | No evidence: speculative, shrinking | < 50K | < 500 |

**Underserved niches**: when installs are low because nobody serves the niche well (the
opportunity you're looking for), outside evidence — community size and growth, search interest,
spending on non-app alternatives — can lift the score by up to +2, but only with Medium or High
confidence evidence.

### 2. Competition Gap (Weight: 20%)

| Score | Criteria |
|-------|----------|
| 9-10 | 🟢 No direct competitor above ~100K installs (Play) / ~1K ratings (iOS), or leaders are < 4.0★ or not updated in 12+ months |
| 7-8 | 🟢 One solid competitor; the rest weak, stale, or badly rated; obvious exploitable weaknesses |
| 5-6 | 🟡 2-3 decent apps (4.3-4.6★, 1M+ installs) with regular updates; differentiation possible but challenging |
| 3-4 | 🟡 Strong leaders (4.6★+, 10M+ installs, active teams); only a sub-audience is underserved |
| 1-2 | 🔴 Dominated by well-funded brands, network effects, or the platform itself |

**Platform risk cap**: if the OS vendor or a device maker ships the same feature for free (built
into the OS, a first-party app, or flagship-only AI features), cap Competition Gap at 4 unless
the idea targets users that built-in feature doesn't reach — and say which users.

### 3. USP Strength (Weight: 15%)

| Score | Criteria |
|-------|----------|
| 9-10 | Clear, defensible, hard-to-copy USP that addresses a proven pain point |
| 7-8 | Strong USP with evidence of demand, some defense against copying |
| 5-6 | Decent differentiation but could be replicated by competitors quickly |
| 3-4 | Weak differentiation, mostly incremental improvement |
| 1-2 | No clear USP — "me too" product |

### 4. Technical Feasibility (Weight: 15%)

| Score | Criteria |
|-------|----------|
| 9-10 | Team has all skills needed, proven tech stack, no technical risks |
| 7-8 | Mostly feasible with current skills, minor learning/research needed |
| 5-6 | Some new tech required, moderate learning curve, manageable risks |
| 3-4 | Significant technical challenges, major unknowns or new tech dependencies |
| 1-2 | Beyond team capability, requires expertise/infrastructure team doesn't have |

If the whole idea hinges on one unproven technical step (an accuracy target, an OS API that may
not expose the data, on-device model speed), say so and model the "spike fails" scenario.

### 5. Revenue Potential (Weight: 15%)

Anchor on **evidence that people pay in this niche**, then on how much:

| Score | Criteria | Evidence anchor (best direct competitor) |
|-------|----------|:---:|
| 9-10 | Strong model fit, proven willingness to pay | ≥ $100K/month |
| 7-8 | Clear monetization path, paying users visible | $20K-100K/month |
| 5-6 | Viable but thinly proven | $5K-20K/month |
| 3-4 | Unclear monetization, price-sensitive audience | $1K-5K/month |
| 1-2 | Audience expects everything free, no paying competitor | < $1K/month or none |

Without revenue estimates, use willingness-to-pay proxies — paid subscriptions or IAP price
ranges on competitors' listings, a premium tier competitors keep pushing, funding raised on
revenue — and mark confidence Medium or Low accordingly.

### 6. Time to MVP (Weight: 10%)

| Score | Criteria (with the current team) |
|-------|----------|
| 9-10 | MVP in 2-4 weeks |
| 7-8 | MVP in 4-8 weeks |
| 5-6 | MVP in 8-12 weeks |
| 3-4 | MVP in 3-6 months |
| 1-2 | MVP > 6 months |

### 7. Scalability (Weight: 5%)

| Score | Criteria |
|-------|----------|
| 9-10 | Naturally scalable: content-driven, no per-user cost scaling |
| 7-8 | Good scalability with standard architecture |
| 5-6 | Moderate scaling needs, some infrastructure or per-use API cost |
| 3-4 | Scaling requires significant rearchitecting or costs grow with usage faster than revenue |
| 1-2 | Fundamentally hard to scale (e.g., requires human operators per user) |

---

## Confidence per Criterion

Every score carries the confidence of the evidence behind it (source tiers are defined in
`data_sources.md`):

| Confidence | When |
|-----------|------|
| **High** | Tier A measurement (store page, store-data tool, official numbers), fetched for this report |
| **Medium** | Tier B source, two agreeing Tier C sources, or Tier A data older than ~6 months |
| **Low** | One Tier C source, your own proxy model, or no data at all |

In the report's scoring table, add a **Confidence** column and keep the **Notes** column to the
evidence in 5-10 words ("Play: top 5 = 12M installs", "proxy model, no revenue data").

---

## Calculating the Score — use the script

Don't do the arithmetic by hand. Put the ideas in a JSON file and run:

```bash
python3 scripts/score.py ideas.json --lang vi     # or --lang en
# quick single idea:
python3 scripts/score.py --scores 6,8,8,7,6,7,8 --confidence L,H,M,M,M,M,H --name TankMate
```

The script prints the ranking table, a per-idea breakdown, applies the verdict rules below,
and adds two kinds of sensitivity:

- **Downside** (automatic): every Low-confidence criterion 2 points worse. If the verdict
  collapses, the idea rests on guesses — say so in the verdict.
- **Scenarios** (you define them): the decisive risk for the idea, e.g.
  `"scenarios": {"Spike fails": {"usp_strength": 5, "technical_feasibility": 5}}`.

Weights:

```
Overall = Market Demand × 0.20 + Competition Gap × 0.20 + USP Strength × 0.15
        + Technical Feasibility × 0.15 + Revenue Potential × 0.15
        + Time to MVP × 0.10 + Scalability × 0.05
```

Rounded half-up to one decimal (7.05 → 7.1). The verdict uses the rounded score.

---

## Verdict Rules

One set of rules for the whole skill — the ranking table, each idea's verdict, and the
executive summary all use these labels. `scripts/score.py` implements exactly this.

| Overall | Verdict | Meaning |
|:-------:|---------|---------|
| ≥ 7.5 | 🟢 **Go** | Build it; validate in parallel |
| 6.5 - 7.4 | 🟡 **Conditional Go** | Build only after the named validation passes |
| 5.5 - 6.4 | 🟠 **Backup** | Keep in reserve if better ideas fail validation |
| < 5.5 | 🔴 **No-Go** | Reject — record why in "Ideas Considered but Rejected" |

**Hard gates** (applied after the band):
- One criterion ≤ 3 → at best Conditional Go (name the weak criterion and the path to fix it).
- Two or more criteria ≤ 3 → No-Go.
- Market Demand or Revenue Potential at **Low** confidence → at best Conditional Go: unverified
  demand or monetization can't support a Go.

**Before writing "Go" or "Conditional Go", also check**, and mention any failure in the verdict:
- Break-even within 12 months in the optimistic case, 18 in the conservative case
- Every high risk (score ≥ 16 in the risk matrix) has a mitigation
- The conditions are concrete and testable ("CPI below $X in a fake-door test", "≥ 85%
  accuracy on 50 test photos"), not "if the market responds well"

---

## MVP Scoping with MoSCoW

For each top idea, define the MVP scope using MoSCoW prioritization:

### Must-Have (MVP launch blockers)
Features the app literally cannot function without. Be ruthless — "nice to have"
is NOT "must have".

**Test**: "Would a user uninstall immediately if this were missing?" If yes → Must.

### Should-Have (Week 2-4 post-launch)
Features that significantly improve the experience but aren't launch blockers.

**Test**: "Would a user give a 3-star review without this?" If yes → Should.

### Could-Have (V1.1 - V1.2)
Features that enhance but don't define the product. These are your planned updates
to maintain momentum.

### Won't-Have (explicitly excluded)
Features you're consciously choosing NOT to build. Document these to avoid scope creep.

---

## Cost Estimation Framework

### Modular estimation approach

Break the MVP into modules and estimate hours for each:

| Module | Typical Hours (Solo Dev) | Typical Hours (2-3 Dev Team) |
|--------|--------------------------|------------------------------|
| Project setup + architecture | 8-16h | 16-24h |
| UI/UX design + design system | 16-40h | 16-40h |
| Authentication (if needed) | 8-16h | 8-16h |
| Core feature 1 | 20-60h | 15-40h |
| Core feature 2 | 20-60h | 15-40h |
| Core feature 3 | 20-60h | 15-40h |
| Data persistence / Backend | 16-40h | 24-60h |
| API integrations | 8-24h per integration | 8-24h per integration |
| Paywall / ads / analytics setup | 8-16h | 8-16h |
| Testing + QA | 15-25% of total dev | 15-25% of total dev |
| App Store preparation | 8-16h | 8-16h |
| **Buffer (always add)** | **+20-30%** | **+15-25%** |

### Cost calculation

```
Total Hours = Sum of modules + Buffer
Total Cost  = Total Hours × Hourly Rate            (freelance / agency)
            = Team months × Monthly cost per person (in-house team)
```

Take hourly rates and monthly salaries from `benchmarks.md`, matched to where the team is.
State which one you used in the report's context line.

Also budget the **running costs** that scale with users: per-call AI/API costs, backend
hosting, and the store commission on revenue (see `benchmarks.md`).

### Quick estimation shortcuts

| App Complexity | Solo Dev Timeline | 3-4 person team |
|---------------|-------------------|-----------------|
| **Simple** (1-2 screens, single feature) | 2-4 weeks | 1-2 weeks |
| **Medium** (5-8 screens, 3-5 features) | 6-12 weeks | 4-8 weeks |
| **Complex** (10+ screens, backend, real-time) | 3-6 months | 2-4 months |
| **Very Complex** (social features, marketplace) | 6-12 months | 4-8 months |

---

## RICE Prioritization

When deciding feature priority, use RICE scoring:

```
RICE Score = (Reach × Impact × Confidence) / Effort
```

| Factor | How to estimate |
|--------|----------------|
| **Reach** | How many users per month will this feature affect? (1-10 scale based on %) |
| **Impact** | How much will each user benefit? (3=massive, 2=high, 1=medium, 0.5=low, 0.25=minimal) |
| **Confidence** | How sure are you about the estimates? (100%=high, 80%=medium, 50%=low) |
| **Effort** | Person-months to build (lower = better) |

Features with highest RICE scores go into Must-Have.

---

## Risk Assessment Matrix

For each top idea, identify and classify risks:

### Risk categories

| Category | Examples |
|----------|---------|
| **Market risk** | Demand is speculative, trend might reverse, market too small |
| **Technical risk** | Core feature technically challenging, dependency on unstable API |
| **Platform risk** | OS vendor ships the feature, store policy change, API access revoked |
| **Competitive risk** | Big player could enter, competitor could copy USP quickly |
| **Regulatory risk** | Health/finance regulations, data privacy compliance (GDPR, etc.) |
| **Monetization risk** | Users unwilling to pay, ad revenue lower than expected |
| **Execution risk** | Team too small, key person dependency, burnout |

### Risk matrix template

| Risk | Probability (1-5) | Impact (1-5) | Risk Score | Mitigation |
|------|-------------------|-------------|------------|------------|
| ... | ... | ... | P × I | ... |

**Risk Score interpretation:**
- 1-6: Low risk — monitor
- 7-15: Medium risk — have a mitigation plan
- 16-25: High risk — must address before committing

### Cheapest validation step

For each idea, define the **minimum investment** to validate demand. Costs for paid tests
depend on CPI — take it from `benchmarks.md` for the target market.

| Validation Method | Cost | Time | Signal Strength |
|-------------------|------|------|----------------|
| Store keyword + competitor check (`store_lookup.py`) | $0 | 2-4 hours | Low-Medium |
| Reddit/forum post gauging interest | $0 | 1 day | Medium |
| Landing page + waitlist | $50-200 | 1-2 days | Medium |
| Prototype (Figma clickable) shown to 5-10 target users | $0-100 | 2-5 days | Medium-High |
| Technical spike on the riskiest step | team time | 1-2 weeks | High (for technical risk) |
| Fake-door / paid ad test (store listing or landing page) | CPI × ~200-500 installs/clicks | 3-7 days | High |
| Soft launch (basic MVP, 1 market) | dev cost + small ad budget | 2-4 weeks | High |

---

## Revenue Projection Model

For each top idea, project revenue at two scenarios. Use the funnel numbers from
`benchmarks.md` (download → trial → paid, eCPM, ARPDAU) and cite which ones you used.

### Conservative estimate (~25th percentile)
- Organic growth only, slow ASO ramp
- Conversion at the low end of the benchmark range (or 50% of the median)
- Minimal marketing budget
- Timeline: revenue meaningful at month 6+

### Optimistic estimate (~75th percentile)
- ASO working plus some paid acquisition
- Benchmark median conversion
- Some marketing investment (state the monthly budget)
- Timeline: revenue meaningful at month 3+

### Projection template

```
Month 1-3:  [organic downloads/month] × [conversion %] × [net price] = $X/month
Month 4-6:  [growing downloads] × [improved conversion] × [net price] = $Y/month
Month 7-12: [stable downloads] × [retention-adjusted conversion] × [net price] = $Z/month

Net price = list price − store commission (benchmarks.md)

Break-even analysis:
- Total investment: $[dev cost + marketing]
- Monthly net revenue at month 6: $[conservative]
- Break-even month: [calculation]
```

Every projection is a model, not a measurement — label it so, and list the assumptions under the
table.
