# Report Template — App Research Report

Use this template for the final report. This is a **decision document** — every section
exists to help the reader decide what to build next. A ranking table alone is useless without
the detailed breakdown that follows.

---

## Language

Write the **whole** report — headings, table headers, labels, verdicts — in the language of the
user's request unless they ask for another. The template below is in English; translate every
heading. Don't leave English headings over a Vietnamese body.

Standard Vietnamese headings (use these so reports stay consistent with each other):

| English | Tiếng Việt |
|---------|-----------|
| App Idea Research Report | Báo cáo nghiên cứu ý tưởng App |
| Data limitations | Giới hạn dữ liệu |
| Executive Summary | Tóm tắt điều hành |
| Ranking Overview | Bảng xếp hạng |
| Market Context | Bối cảnh thị trường |
| Niche Map | Bản đồ ngách |
| Detailed Analysis | Phân tích chi tiết |
| What It Is / How It Works | Đây là gì / Cách hoạt động |
| Opportunities & Challenges | Cơ hội & Thách thức |
| Revenue Projection | Dự phóng doanh thu |
| MVP Timeline | Timeline MVP |
| Verdict | Kết luận |
| Ideas Considered but Rejected | Các ý tưởng đã xem xét nhưng loại |
| Portfolio Strategy | Chiến lược portfolio |
| Recommended Next Steps | Bước tiếp theo đề xuất |
| Sources & Evidence | Nguồn & Bằng chứng |
| Confidence Notes | Mức độ tin cậy |

Verdict labels and criterion names in Vietnamese are the ones `scripts/score.py --lang vi` prints.

---

## File name and location

- Name: `app_research_{YYYY-MM-DD}_{slug}_report.md` — `slug` is 2-4 lowercase words joined by
  hyphens describing the scope (e.g. `android-micro-niche`, `local-ai`).
- Location, first match wins: the folder the user names → an existing `draft/` folder in the
  working directory → the working directory.
- The idea registry (`ideas_registry.md`, see the end of this file) lives in the same folder.

---

## Template

```markdown
# App Idea Research Report — [scope]

> **Date**: [YYYY-MM-DD]
> **Team**: [size + roles] | **Stack**: [tech] | **Market**: [target regions]
> **Monetization**: [preferred model] | **Budget**: [range] | **Timeline**: [target MVP]
> **Risk appetite**: [red ocean / blue ocean / balanced]
> Mark anything the user didn't provide as *(assumed)* and say what you assumed.

> ⚠️ **Data limitations**
> | Capability | Status | Source actually used |
> |-----------|:------:|---------------------|
> | Keyword → ranking apps | ✅/⚠️/❌ | ... |
> | Keyword popularity | ✅/⚠️/❌ | ... |
> | App metadata | ✅/⚠️/❌ | ... |
> | Reviews | ✅/⚠️/❌ | ... |
> | Revenue / download estimates | ✅/⚠️/❌ | ... |
> - [Anything else you could not reach: Trends, Reddit, a paywalled report...]
> - **All revenue projections are models, not measurements.**

> 📎 **Related reports**: [earlier reports or registry entries reused, and what was re-scored] (omit if none)

---

## Executive Summary

[2-4 sentences: what was explored, which idea ranks #1 and its verdict, the key reason, and
the biggest risk. A busy reader gets the decision here.]

**Signals**: store keyword/trend [✅/⚠️/❌] · competitor gap [✅/⚠️/❌] · revenue momentum
[rising/flat/unclear] — one short reason each.

---

## Ranking Overview

| Rank | App Idea | Score | Verdict | Confidence | MVP | Revenue, month 12 (cons – opt) |
|:----:|----------|:-----:|---------|:----------:|:---:|:------------:|
| 🥇 1 | **[Name]** — [one-line USP] | 7.3 | 🟡 Conditional Go | Medium | 8w | $3K – $10K/mo |
| 🥈 2 | **[Name]** — [one-line USP] | 7.0 | 🟡 Conditional Go | Low | 6w | $2K – $6K/mo |
| 🥉 3 | **[Name]** — [one-line USP] | 6.2 | 🟠 Backup | Medium | 4w | $1K – $3K/mo |

[Confidence = the confidence of Market Demand and Revenue Potential, the two criteria that gate
a Go. Scores and verdicts come from `scripts/score.py`.]

The Executive Summary + Ranking Overview must work as a one-page decision view on their own.

---

## Market Context  *(optional — when several ideas share the same macro facts)*

[Platform, category and monetization trends that apply to every idea, stated once with
sources, so the per-idea sections don't repeat them.]

---

## Niche Map  *(optional — when more than ~10 niches were scanned)*

| Group | Niche | Demand signal | Competition | Team fit | Status |
|-------|-------|---------------|:-----------:|:--------:|--------|
| [A. Vision AI] | [niche] | [one line + source] | 🟢/🟡/🔴 | ✅/⚠️/❌ | Shortlisted / Rejected (why) |

---

## Detailed Analysis

### 🥇 #1: [App Name]

#### 1. What It Is

[2-3 sentences describing the product concept. What does the app do? Who is it for?
How does the user interact with it? The reader should be able to picture the app.]

**Category**: [e.g., Health & Fitness > Mood Tracking]
**Target User**: [specific persona, e.g., "Working professionals 25-40 struggling with stress"]
**Monetization**: [specific model for this idea]

#### 2. How It Works

1. **Onboarding**: [What the user sees first]
2. **Core action**: [What the user does daily/regularly]
3. **Value moment**: [When the user gets the "aha" — the reason they come back]
4. **Key screens**: [List 3-5 main screens by name]

#### 3. Opportunities & Challenges

**✅ Opportunities**
- [Opportunity — market gap, trend, or USP advantage, with evidence]
- ...

**⚠️ Challenges**
- [Challenge — competition, platform, technical, or monetization risk]
- ...

**Competitors snapshot** ([store], [country], fetched [date]):

| Competitor | ⭐ Rating | Ratings | 📥 Installs | Updated | ⚠️ Key Weakness |
|------------|:---------:|:-------:|:----------:|:-------:|----------------|
| [Real app] | 4.2 | 12K | 500K+ | 2026-08 | [weakness, from reviews] |

**Competition Level**: 🟢 Weak / 🟡 Moderate / 🔴 Strong

**Keyword & Store Trend Signals**:
- [Keyword ranking quality, autocomplete, category movement — with source and date]
- [If a signal was unavailable, say so: "keyword popularity: not available (plan-locked)"]

#### 4. Revenue Projection

**Model**: [How the app makes money — be specific]
**Revenue Momentum**: [Rising / Flat / Unclear] — [why, based on evidence]

| Timeline | Conservative | Optimistic |
|----------|:-----------:|:---------:|
| Month 1-3 | $X/mo | $Y/mo |
| Month 4-6 | $X/mo | $Y/mo |
| Month 7-12 | $X/mo | $Y/mo |
| **Break-even** | Month X | Month Y |

**Assumptions**: [downloads/month, conversion %, net price, eCPM — each tied to `benchmarks.md`
or another cited source]

#### 5. MVP Timeline

**Estimated effort**: [X weeks] | **Estimated cost**: [$range, and the rate basis]

**Must-Have (Launch — V1.0)**:
- [ ] [Core feature 1]
- [ ] [Core feature 2]

**Deferred to V1.1+**:
- [Feature — reason it's deferred]

**Validation step before building**: [Cheapest test with a pass/fail threshold set in advance]

#### 6. Verdict

[1-2 sentences: build or not, under which concrete, testable conditions, and what to validate
first. "Build if X ≥ Y" — not "could potentially be viable".]

| Criterion | Score | Confidence | Notes (evidence, 5-10 words) |
|-----------|:-----:|:----------:|------------------------------|
| Market Demand | 8/10 | High | Play: top 5 = 12M installs |
| Competition Gap | 7/10 | High | One solid rival, rest < 4.0★ |
| USP Strength | 7/10 | Medium | Top complaint in 40% of reviews |
| Technical Feasibility | 8/10 | Medium | Known stack, one ML spike |
| Revenue Potential | 6/10 | Low | Proxy model, no revenue data |
| Time to MVP | 8/10 | Medium | 6 weeks, 2 devs |
| Scalability | 9/10 | High | No per-user server cost |
| **Overall** | **7.4** | | **🟡 Conditional Go** |

**Sensitivity**: [Downside line from score.py; the decisive scenario, e.g. "If the
accuracy spike fails: 6.3 → 🟠 Backup"]

---

### 🥈 #2 ... 🥉 #3

[Same 6 sections. Every section is required.]

---

## Ideas Considered but Rejected

| # | Idea | Category | Reason for Rejection |
|:-:|------|----------|---------------------|
| 1 | ... | ... | [Specific reason with evidence — "Google ships it free on Pixel", not "too competitive"] |

---

## Portfolio Strategy  *(optional — when ideas share a technical core or audience)*

[What can be built once and reused, in which order to ship, and how the shared core changes
time-to-MVP for the later ideas.]

---

## Recommended Next Steps

| # | Action | Timeline | Details / pass-fail threshold |
|:-:|--------|----------|-------------------------------|
| 1 | Fill the data gaps that could flip the ranking | This week | [which numbers, from where] |
| 2 | Validate #1 | Week 1-2 | [fake door / landing page / prototype + threshold] |
| 3 | Technical spike | Week 1-2 | [the riskiest step and its success criterion] |
| 4 | Competitor teardown (optional) | Week 2 | [`mobile-app-review` on the decisive competitor] |
| 5 | Go/No-Go meeting | Week 3 | [the conditions from the verdict] |

---

## Sources & Evidence

Group by research topic or idea. One line per source: what it supports — title/tool — URL —
date (and the store/country/query for store data).

### Market & platform
- ...
### #1 [App Name]
- ...

---

## Confidence Notes

- **High**: [which kinds of data in this report are measured, e.g. store installs/ratings fetched on DATE]
- **Medium**: [industry reports, triangulated estimates]
- **Low**: [proxy revenue models, single anecdotal sources]
- **What would change the ranking**: [the one or two unknowns that could reorder the top 3]
```

---

## Mandatory Sections Checklist

Report-level:
- [ ] Context block with assumptions marked
- [ ] **Data limitations** block with the capability map
- [ ] Executive Summary + Ranking Overview (with Verdict and Confidence columns)
- [ ] Detailed Analysis for the top 3-5 ideas
- [ ] Ideas Considered but Rejected
- [ ] Recommended Next Steps
- [ ] **Sources & Evidence** (one section — no separate appendix)
- [ ] **Confidence Notes**

Each idea in Detailed Analysis MUST include all 6 sections:
- [ ] **What It Is** — Product description + target user
- [ ] **How It Works** — Core user flow + key screens
- [ ] **Opportunities & Challenges** — Both sides, with competitor snapshot and store signals
- [ ] **Revenue Projection** — Model + 3/6/12 month estimates + break-even + assumptions
- [ ] **MVP Timeline** — Features + timeline + cost + validation step
- [ ] **Verdict** — Direct conclusion + scoring table with confidence + sensitivity

If any section is missing, the analysis is **incomplete** and cannot support a real decision.

## Formatting Rules

1. **Both sides always** — every opportunity section needs challenges, no cheerleading
2. **Concrete numbers** — "$2-4K/month" not "good revenue potential"
3. **Specific competitors** — name real apps with real ratings and fetch dates, not "[App 1]"
4. **Direct verdicts** — "Build this if X" not "This could potentially be viable"
5. **Brief justifications** — in scoring tables, 5-10 words max per cell
6. **Visualize the product** — after "What It Is" + "How It Works", the reader should be able
   to sketch the app on a napkin
7. **Source-backed claims** — every trend, keyword, or revenue claim ties to evidence
8. **No data ≠ zero** — write "not available" for locked or missing data; never fill the gap
   with a number that looks measured

---

## Idea Registry

`ideas_registry.md` sits next to the reports and tracks every idea across runs, so a new run
can reuse earlier work instead of re-researching the same niche.

```markdown
# Idea Registry

| ID | Idea | Niche | Platform / Market | Score | Verdict | Team context | Date | Status | Report | Notes |
|----|------|-------|-------------------|:-----:|---------|--------------|------|--------|--------|-------|
| tankmate | TankMate — AI aquarium assistant | Aquarium | Android / Global | 7.1 | 🟡 Conditional Go | 4 people, Kotlin | 2026-10-06 | researched | app_research_2026-10-06_android-micro-niche_report.md | Test-strip reading spike decides it |
```

- **ID**: short stable slug; one row per idea. Rejected ideas get a row too (Score may be `—`).
- **Status**: `researched` · `rejected` · `parked` · `validating` · `building` · `launched`.
  Only the user moves an idea past `researched`/`rejected`/`parked`; keep whatever they set.
- **Upsert**: when an idea is re-scored, update Score/Verdict/Team context/Date/Report in place
  and say what changed in Notes ("re-scored for 2-person Flutter team: 7.1 → 6.4").
- Create the file on the first run if it doesn't exist.
