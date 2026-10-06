# Data Sources — Capability Discovery & Fallbacks

Read this before Phase 1. It tells you how to find out, at runtime, which data you can actually
get in this session, and what to do when a source is missing or locked.

---

## Table of Contents
1. [Principle: capabilities, not vendors](#principle-capabilities-not-vendors)
2. [Capability catalog](#capability-catalog)
3. [Step 1 — Discover tools](#step-1--discover-tools)
4. [Step 2 — Probe once](#step-2--probe-once)
5. [Step 3 — Classify every response](#step-3--classify-every-response)
6. [Step 4 — Record the capability map](#step-4--record-the-capability-map)
7. [Public store fallbacks](#public-store-fallbacks)
8. [Other web fallbacks](#other-web-fallbacks)
9. [Source tiers and confidence](#source-tiers-and-confidence)
10. [Splitting the research work](#splitting-the-research-work)

---

## Principle: capabilities, not vendors

The research needs certain **kinds** of data (keyword rankings, ratings, revenue estimates...).
Which tools supply them differs per machine, per account, and per subscription plan, and it
changes over time. So:

- **Never assume a specific data provider is connected.** Discover what this session has.
- **Never read MCP configuration files or credentials** (`.mcp.json`, settings files, env files)
  to find out what is installed. Look at the tools you have been given, nothing else.
- **A tool being listed does not mean it works.** Plans gate endpoints. Probe before relying on it.
- If no store-data tool exists at all, the research still runs — on public store pages and web
  sources — and the report says so.

---

## Capability catalog

| ID | Capability | Used in | Search terms for discovery | If unavailable |
|----|-----------|---------|---------------------------|----------------|
| C1 | Keyword → apps ranking for it | Phase 1, 2 | keyword, ranking, search apps | Store search page (`store_lookup.py play-search` / `ios-search`) |
| C2 | Keyword popularity / difficulty / volume | Phase 1 | keyword popularity, volume, difficulty, competitiveness | Store autocomplete, number + quality of ranking apps, web trend articles |
| C3 | Related keywords / suggestions | Phase 1 | keyword suggestions, related keywords | Store autocomplete, "related searches" on web |
| C4 | Find an app by name / publisher | Phase 2 | app search, find app, publisher | Store search page, web search |
| C5 | App metadata (installs, rating, rating count, last update, price, IAP, ads) | Phase 2 | app details, listing, metadata | `store_lookup.py play` / `ios` |
| C6 | Review text | Phase 2 | reviews, ratings | Store page reviews via web fetch, web search for complaints |
| C7 | Download / revenue estimates per app | Phase 2, 4 | estimates, revenue, downloads, metrics | Public company data, press, proxy estimation (see `benchmarks.md`) |
| C8 | Top charts / category rank movement | Phase 1 | top charts, ranks, category | Web articles on chart movers, Apple top charts via web |
| C9 | Category / market aggregates | Phase 1, 4 | aggregate, market, catalog stats | Industry reports (Tier B sources) |
| C10 | Web search + page fetch | All | web search, fetch | None — if missing, say research is limited to model knowledge and flag everything as Low confidence |

---

## Step 1 — Discover tools

1. Look through the tools available in this session. Some environments list every tool up front;
   others expose a **tool search** for deferred tools — in that case run one search per
   capability using the search terms above (e.g. "keyword ranking apps", "app reviews",
   "revenue downloads estimates").
2. For each match, read its description and confirm it really serves that capability (a
   "keywords" tool for an ad platform is not organic keyword ranking).
3. Several tools may serve one capability. Prefer the one whose description matches the target
   store (Google Play / App Store) and returns data for **any** app, not only apps the account owns.
4. Write-type tools (reply to review, track/untrack keyword, create campaign...) are never needed
   for research. Do not call them.

---

## Step 2 — Probe once

Make **one cheap call per capability**, early, before planning the research:

- Use a head term in the user's domain and target market (e.g. "habit tracker", country `US`,
  store `google_play`). Ask for the smallest page size the tool allows.
- Chain IDs: take an app ID returned by C1 and use it to probe C5, C6, C7.
- If a tool's description or an error mentions **credits or per-call cost**, probe it at most
  once and note the cost; don't use it in bulk without the user's consent.
- Total probing budget: roughly one call per capability (≤ 10 calls). Don't probe every tool.

---

## Step 3 — Classify every response

Apply this to probes **and** to every later call. Misreading these is the most common way a
report ends up with wrong conclusions.

| What you see | Meaning | What to do |
|--------------|---------|-----------|
| 401/403, "upgrade", "unlock", "partner access", "plan", "subscription required" | **Locked by plan** | Mark ❌ for the whole run. Don't retry, don't call it per app. Use the fallback. |
| "not owned", "only your apps", "tracked apps only" | **Ownership-limited** — works only for the account's own apps | Mark ❌ for competitor research. |
| Network error, timeout, 429, 5xx | **Transient** | Retry once. Still failing → mark ⚠️ and try once more later in the run. Never conclude "locked" from a network error. |
| Call succeeds but key fields are `null` / missing (e.g. popularity null while the tool says it supports popularity) | **Silently gated** | Treat as "not available", **never as zero or low**. Mark ⚠️ partial. |
| 0 results, "syncing", "not synced", very old `last_synced` | **No data yet** | Means "no data", **not "no competitors"** or "no demand". Verify with a store search page before concluding anything. |
| Results look normal | ✅ Available | Use it, cite it with the query date. |

---

## Step 4 — Record the capability map

Keep a small map while you work and put it in the report's **Data limitations** block:

```markdown
| Capability | Status | Source actually used |
|-----------|:------:|---------------------|
| Keyword → ranking apps | ✅ | Store-data MCP, Google Play US, 2026-10-06 |
| Keyword popularity | ⚠️ null on current plan | Store autocomplete + ranking quality |
| App metadata | ❌ plan-locked | Play store pages via store_lookup.py |
| Reviews | ❌ ownership-limited | Play page reviews + web complaints |
| Revenue estimates | ❌ plan-locked | Proxy model (benchmarks.md) |
```

Describe tools by capability in the report ("store-data MCP", "ASO tool") — the provider name
may be mentioned when citing a data point, but the skill itself never depends on one.

---

## Public store fallbacks

`scripts/store_lookup.py` (Python 3 standard library, no install) reads public store data:

```bash
# Google Play: package ids in search order
python3 scripts/store_lookup.py play-search "habit tracker" --gl US --limit 10
# Google Play: installs bucket, rating, rating count, last updated, category, price, ads/IAP flags
python3 scripts/store_lookup.py play org.isoron.uhabits com.habitnow --gl US
# App Store: search (rating count, rating, last release date, price, genre)
python3 scripts/store_lookup.py ios-search "habit tracker" --country us --limit 10
# App Store: lookup by numeric id
python3 scripts/store_lookup.py ios 1438388363 --country us
```

Add `--json` for machine-readable output. The script prints `null` for any field it could not
find — it never guesses. If Google changes the Play page layout and fields come back null,
fetch the page directly (`https://play.google.com/store/apps/details?id=<pkg>&hl=en&gl=US`) and
read the values yourself.

How to read store numbers:
- **Play installs are buckets** (`100K+` means 100,001–500,000). Use the bucket floor in
  calculations and say so.
- **iOS has no install count.** Use rating count as the scale proxy (see `benchmarks.md` for
  conversion ratios and their uncertainty).
- Store data is per country. Query the target market; if revenue comes from US/EU, query US too.
- Always note the fetch date next to the number.

---

## Other web fallbacks

| Need | Fallback |
|------|----------|
| Keyword demand | Store autocomplete (type the term in a store search page), Google Trends when fetchable, web search for "[term] app" volume articles |
| Forum pain points | Web search `site:reddit.com "[problem]" app`; if Reddit pages can't be fetched, use search snippets and say so |
| Revenue of a competitor | Company press, funding news, public filings, interviews, industry reports; otherwise proxy model |
| Category trends | Industry reports (RevenueCat, Sensor Tower, data.ai and similar insights pages), tech press citing them |

---

## Source tiers and confidence

| Tier | Examples | Gives confidence |
|------|----------|-----------------|
| **A — Primary measurement** | Store pages, store APIs, market-intelligence tool data, official company numbers, filings | **High** |
| **B — Credible secondary** | Industry reports with stated methodology, reputable press citing Tier A data | **Medium** (High if two Tier B sources agree) |
| **C — Anecdotal / inferred** | Roundup blogs, forum posts, search snippets, your own proxy model | **Low** |

Every scoring criterion in Phase 4 carries the confidence of the evidence behind it. A score
built on Tier C only is Low confidence, no matter how plausible it sounds.

---

## Splitting the research work

When the environment can run subagents, parallelize — research is mostly independent questions:

- **Web questions** (market reports, competitor news, forum signals, benchmarks): hand each one
  to a web-research subagent — the project's dedicated web-research agent if one is defined —
  with a focused question plus context (target market, platform, what decision it feeds).
  Launch independent questions in parallel, e.g. one per niche.
- **Store-data tool calls** stay with the agent that has those tools (usually you). Many
  subagents can't see MCP tools.
- **You synthesize.** Subagents return facts with sources; scoring, verdicts and the report are
  yours.

Without subagents, do the same work sequentially — the method doesn't change.
