# Phase 4: Feasibility — Deep Methodology

This reference provides the complete scoring model, cost estimation framework, risk assessment
templates, and revenue projection methods. Read this before executing Phase 4.

---

## Table of Contents
1. [Scoring Model — 7 Criteria Detailed](#scoring-model--7-criteria-detailed)
2. [Weighted Average Calculation](#weighted-average-calculation)
3. [MVP Scoping with MoSCoW](#mvp-scoping-with-moscow)
4. [Cost Estimation Framework](#cost-estimation-framework)
5. [RICE Prioritization](#rice-prioritization)
6. [Risk Assessment Matrix](#risk-assessment-matrix)
7. [Revenue Projection Model](#revenue-projection-model)
8. [Go/No-Go Decision Framework](#gono-go-decision-framework)

---

## Scoring Model — 7 Criteria Detailed

Score each criterion 1-10 using the guidelines below. Avoid "5" as a default — push yourself
to decide whether it's above or below average.

### 1. Market Demand (Weight: 20%)

| Score | Criteria |
|-------|----------|
| 9-10 | Strong evidence: high search volume, growing trend, large TAM, active demand signals |
| 7-8 | Good evidence: moderate search volume, stable/growing trend, validated demand |
| 5-6 | Mixed signals: some search volume but unclear growth, limited direct evidence |
| 3-4 | Weak evidence: low search volume, niche/declining interest |
| 1-2 | No evidence: speculative demand, no search data, shrinking market |

### 2. Competition Gap (Weight: 20%)

| Score | Criteria |
|-------|----------|
| 9-10 | 🟢 Weak competition: few quality apps, clear gaps, abandoned leaders |
| 7-8 | 🟢 Moderate-weak: competitors exist but have obvious, exploitable weaknesses |
| 5-6 | 🟡 Moderate: decent apps exist, differentiation possible but challenging |
| 3-4 | 🟡 Moderate-strong: good competitors, narrow windows for differentiation |
| 1-2 | 🔴 Strong: dominated by well-funded, high-quality apps with strong moats |

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

### 5. Revenue Potential (Weight: 15%)

| Score | Criteria |
|-------|----------|
| 9-10 | Strong revenue model fit, category benchmarks show $10K+/month for top apps |
| 7-8 | Clear monetization path, category benchmarks show $3-10K/month for mid-tier |
| 5-6 | Viable monetization but unproven, estimated $1-3K/month |
| 3-4 | Unclear monetization, low price sensitivity in audience, < $1K/month likely |
| 1-2 | Very difficult to monetize, audience expects everything free |

### 6. Time to MVP (Weight: 10%)

| Score | Criteria |
|-------|----------|
| 9-10 | MVP in 2-4 weeks with current team |
| 7-8 | MVP in 4-8 weeks |
| 5-6 | MVP in 8-12 weeks |
| 3-4 | MVP in 3-6 months |
| 1-2 | MVP > 6 months |

### 7. Scalability (Weight: 5%)

| Score | Criteria |
|-------|----------|
| 9-10 | Naturally scalable: content-driven, no per-user cost scaling |
| 7-8 | Good scalability with standard architecture |
| 5-6 | Moderate scaling needs, some infrastructure cost |
| 3-4 | Scaling requires significant rearchitecting |
| 1-2 | Fundamentally hard to scale (e.g., requires human operators per user) |

---

## Weighted Average Calculation

```
Overall Score = (Market Demand × 0.20)
              + (Competition Gap × 0.20)
              + (USP Strength × 0.15)
              + (Technical Feasibility × 0.15)
              + (Revenue Potential × 0.15)
              + (Time to MVP × 0.10)
              + (Scalability × 0.05)
```

Round to 1 decimal place.

### Score interpretation

| Score Range | Verdict |
|-------------|---------|
| 8.0 - 10.0 | 🟢 **Strong candidate** — Pursue with confidence |
| 6.5 - 7.9 | 🟡 **Viable with caveats** — Proceed but address weak criteria |
| 5.0 - 6.4 | 🟠 **Marginal** — Only if no better options available |
| Below 5.0 | 🔴 **Reject** — Too risky for the expected return |

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
| Testing + QA | 15-25% of total dev | 15-25% of total dev |
| App Store preparation | 8-16h | 8-16h |
| **Buffer (always add)** | **+20-30%** | **+15-25%** |

### Cost calculation

```
Total Hours = Sum of modules + Buffer
Total Cost = Total Hours × Hourly Rate

Hourly rate reference (2025-2026):
- Self (opportunity cost): $20-50/h
- Freelancer (Vietnam/SEA): $15-35/h
- Freelancer (EU/US): $50-150/h
- Agency: $80-250/h
```

### Quick estimation shortcuts

| App Complexity | Solo Dev Timeline | Rough Cost (Self) |
|---------------|-------------------|-------------------|
| **Simple** (1-2 screens, single feature) | 2-4 weeks | $1-3K |
| **Medium** (5-8 screens, 3-5 features) | 6-12 weeks | $3-10K |
| **Complex** (10+ screens, backend, real-time) | 3-6 months | $10-30K |
| **Very Complex** (social features, marketplace) | 6-12 months | $30K+ |

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

For each idea, define the **minimum investment** to validate demand:

| Validation Method | Cost | Time | Signal Strength |
|-------------------|------|------|----------------|
| Landing page + waitlist | $50-200 | 1-2 days | Medium |
| App store keyword research | $0 | 2-4 hours | Low-Medium |
| Reddit/forum post gauging interest | $0 | 1 day | Medium |
| Prototype (Figma clickable) | $0-100 | 2-5 days | Medium-High |
| Soft launch (basic MVP, 1 market) | $500-2000 | 2-4 weeks | High |
| Paid ad test (test demand with ads) | $100-500 | 3-7 days | High |

---

## Revenue Projection Model

For each top idea, project revenue at two scenarios:

### Conservative estimate (bottom 25th percentile)
- Assume slow organic growth only
- Lower conversion rates (use 50% of benchmark)
- Minimal marketing budget
- Timeline: revenue meaningful at month 6+

### Optimistic estimate (75th percentile)
- Assume moderate ASO + some paid acquisition
- Benchmark conversion rates
- Some marketing investment ($200-500/month)
- Timeline: revenue meaningful at month 3+

### Projection template

```
Month 1-3:  [organic downloads/month] × [conversion %] × [price] = $X/month
Month 4-6:  [growing downloads] × [improved conversion] × [price] = $Y/month
Month 7-12: [stable downloads] × [retention uplift] × [price] = $Z/month

Break-even analysis:
- Total investment: $[dev cost + marketing]
- Monthly revenue at month 6: $[conservative]
- Break-even month: [calculation]
```

---

## Go/No-Go Decision Framework

After scoring, use these decision rules:

### Go ✅
- Overall score ≥ 7.0
- No single criterion below 4
- Risk mitigation plan exists for all high-risk items
- Break-even possible within 12 months
- Team is excited about the idea (motivation matters!)

### Conditional Go ⚠️
- Overall score 6.0-6.9
- One criterion below 4 but has clear improvement path
- Higher risk tolerance required
- Consider as backup if top ideas fail validation

### No-Go ❌
- Overall score < 6.0
- Multiple criteria below 4
- High-risk items without mitigation
- Break-even beyond 18 months
- Team has no enthusiasm for the domain
