# Growth Systems Playbook (v2)
### System 1: Early Viral Tweet Detection · System 2: Advanced ICP Mapping & Targeting
*Researched August 2026, merged with a technical architecture spec you provided. Tool pricing/features in this space shift monthly — reconfirm before committing budget.*

---

## A note on methodology

Everything here comes from public research — product docs, pricing pages, 2026 teardowns, G2 reviews, practitioner playbooks, and X's own open-sourced ranking code — plus a technical architecture doc you supplied, which I fact-checked and merged in rather than accepting at face value. Where its tool names or claims didn't hold up on verification, I've noted the correction inline rather than silently dropping it.

---

# SYSTEM 1: Early Viral Tweet Detection

## 1.1 Two different jobs hide in "track viral tweets early"

| Job | What it means | Status |
|---|---|---|
| **A — Monitor your own posts** | Catch *your* tweet breaking out in the first 30–60 min so you can double down | Mostly solved. Buy, don't build. |
| **B — Monitor the ecosystem** | Catch *other people's* rising tweets (competitors, target influencers, niche keywords) early enough to reply-jump the wave or spot rising creators | Half-solved. This is your build target. |

## 1.2 Tool landscape (Job A — your own account) — corrected

| Tool | Platform | What it does | Price |
|---|---|---|---|
| **Black Magic** (blackmagic.so) | X | Real-time per-tweet tracking, follower-vs-stranger reach split, best-time-to-post, social CRM | Free–$59.99/mo |
| **Tweet Hunter** | X | Searchable 2–3M+ tweet swipe-file database, **TweetPredict™** pre-publish forecasting, Lead Finder CRM | ~$49/mo |
| **Typefully** | X, LinkedIn, Bluesky | Scheduling + analytics, "Trending" surfacing | From $8/mo |
| **Taplio** | ⚠️ **LinkedIn, not X** — Tweet Hunter's sister product for a different platform. Don't lump it into an X-tracking stack. | From $39/mo |
| **ScrapeCreators** | X + others | Unofficial scraping API — infrastructure for *building* tools, not an end-user growth app. Real and functional, but operating on it means you're outside X's ToS. | Credit-based |
| **ViralFinder** | ⚠️ **TikTok/Instagram/YouTube, not X.** Confirmed from its own App Store listing — a short-video trend tool, not a tweet tool. | From $13.99/mo |

## 1.3 What nobody's fully productized (Job B — the ecosystem radar)

The manual version is well-documented in indie hacker communities as the "reply guy" workflow: maintain a watchlist of 50–150 target accounts, scan every 15–30 min during active hours, reply genuinely within the first 30–60 minutes while a post is still gaining traction. Automating this — not the well-served Job A — is the actual gap worth building.

## 1.4 The signal science

X's open-sourced ranking weights (reconfirmed through the January 2026 Grok update):

**Engagement Velocity Index (EVI)** — measure engagement relative to time elapsed, not raw counts (a 1M-follower account and a 500-follower account need different baselines):

```
EVI = (13.5 × ΔReplies + 20 × ΔReposts + 10 × ΔBookmarks + 1 × ΔLikes) / Δt (minutes)
```

**Baseline deviation (author Z-score)** — the key to catching a small account outperforming itself:

```
Z = (EVI_tweet − μ_author) / σ_author
```
where μ and σ are the author's mean/stdev EVI over their last ~30 posts. **Trigger threshold: Z ≥ 2.5 within the first 30 minutes.**

**Two supporting ratios worth computing:**
- **Bookmark-to-like ratio ≥ 0.12** within 20 minutes → signals evergreen reference value (frameworks, guides), which the algorithm rewards with sustained distribution.
- **Quote-to-retweet ratio > 0.4** → signals discussion/controversy, driving longer dwell time.

**Authority multiplier (treat as a tunable heuristic, not a confirmed constant):** when a high-authority account (50k+ followers, verified industry figure) engages within the first 15 minutes, that's a strong enough signal to weight noticeably higher in your scoring — start around 3–3.5× and calibrate against your own data rather than trusting it as published fact.

The unifying reason all of this centers on 30–60 minutes: a post loses roughly half its visibility score every six hours, and if it's going to pop, it shows within the hour.

## 1.5 System blueprint — two tiers

**MVP (buildable in a weekend):**
```
X API (poll every 15 min, curated watchlist)
   → Google Sheet / Airtable (snapshot log)
   → n8n or Zapier (compute delta, EVI, z-score)
   → Slack webhook when Z ≥ 2.5
```
This is enough for a single-person watchlist of 50–150 accounts. Don't over-build past this until you've validated the alert threshold is actually catching things worth catching.

**Production tier (once MVP is validated and you want scale / multiple projects):**

```
+------------------+     +-----------------------+     +------------------------+
|  Ingestion Tier  | --> | Time-Series Stream DB  | --> | Velocity Scoring Engine|
|  (X API polling) |     | (Redis TimeSeries /    |     |   (EVI & Z-Score)      |
|                  |     |  ClickHouse)           |     |                        |
+------------------+     +-----------------------+     +------------------------+
                                                                    |
                                                                    v
+------------------+     +-----------------------+     +------------------------+
| Push Alerts & UI | <-- |  Semantic Dedup Layer  | <-- |  Anomaly Trigger       |
| (Slack/Webhooks) |     |  (Qdrant/Pinecone +    |     |  (Z ≥ 2.5 threshold)   |
|                  |     |   embeddings)          |     |                        |
+------------------+     +-----------------------+     +------------------------+
```

| Component | Tech | Role |
|---|---|---|
| Ingestion | X API v2 (polling every 3–5 min) | Pulls watchlist accounts + keyword searches |
| Time-series store | Redis TimeSeries or ClickHouse | Stores timestamped snapshots at t=5m/15m/30m/60m |
| Scoring worker | Python/Celery (Rust if you need real throughput) | Computes EVI + Z-score as new snapshots land |
| Semantic dedup | Qdrant/Pinecone + embeddings | Clusters duplicate commentary/memes so you don't get spammed with alerts for the same meme format |
| Alerting | Webhooks / Slack / WebSockets | Fires when Z ≥ 2.5 in the first 30–60 min |

The semantic dedup layer is a genuinely good addition over my original MVP sketch — without it, a trending format that 40 accounts are all riffing on looks like 40 separate alerts instead of one trend.

## 1.6 Data access reality

- **Official X API:** pay-per-use since Feb 2026, ~$0.005/read, 2M reads/month cap, Enterprise ~$42,000+/month above that.
- **Third-party alternatives** (TwitterAPI.io ~$0.00015/read, SocialData.tools, GetXAPI): 90–99% cheaper because they cache/aggregate, but this — and the Playwright/headless-scraping route — operates outside X's terms of service. Real tradeoff: cheaper and faster to build, but carries IP-ban and legal exposure that the official API doesn't. For a curated 100–150 account watchlist, the official API's cost is small enough (likely $50–100/month) that this tradeoff usually isn't worth taking on.

## 1.7 Build vs. buy verdict

| | Verdict |
|---|---|
| **Job A (your own tweets)** | **Buy.** Black Magic or Tweet Hunter. |
| **Job B (ecosystem radar)** | **Build**, MVP first, production tier once validated. |

---

# SYSTEM 2: Advanced ICP Mapping & Targeting

## 2.1 Current terminology

| Term | Meaning |
|---|---|
| **ICP** | Ideal Customer Profile |
| **TAM / SAM / SOM** | Total / Serviceable / Serviceable-Obtainable Market |
| **Firmographic / Technographic / Demographic / Psychographic** | Company attributes / tech stack / individual attributes / values-culture fit |
| **GTM engineering** | The discipline (Clay-popularized) of building revenue systems with AI + automation |
| **Waterfall enrichment** | Chaining data providers so a miss on Provider A falls through to B, then C |
| **Signal-based selling / warm outbound** | Triggering outreach off a specific buying-intent event, not a cold static list |
| **Buying committee mapping** | Economic buyer, champion, technical evaluator, end user, blocker |
| **Identity resolution / de-anonymization** | Matching an anonymous website visitor to a real named person |
| **PLG signals / PQL** | Product-led-growth behavioral signals; Product-Qualified Lead |
| **Champion tracking** | Watching former customers for job changes — a pre-warmed lead at their new company |
| **Lookalike / account expansion** | Finding companies that resemble your best existing customers |
| **AI SDR** | An AI agent that researches, scores, and drafts outreach autonomously |

## 2.2 Tool landscape, categorized

**Enrichment/orchestration spine**
- **Clay** — dominant player, 84% practitioner adoption (96% at agencies). Waterfalls 150+ providers, lifts match rates from ~40% single-source to 78–92%. Free → $185/mo → $495/mo.
- Persana AI, SyncGTM (leaner alternative, ~$99/mo)

**Semantic/vector account discovery**
- **Exa / Exa Websets** — feed a plain-language ICP description, get genuinely relevant companies from the open web rather than a static database. Best for first 30–50 high-precision matches; needs downstream enrichment. ~$7/1,000 searches.
- Ocean.io, Discolike, Veerview — take Exa's precision matches and expand into the thousands via vector similarity

**Intent/signal aggregation**
- **Unify** — aggregates 10+ sources (6sense, Bombora, G2, Clearbit) into automated "Plays." ~$700/mo.
- **Warmly** — website visitor ID + intent, ~200M+ database
- **RB2B** — person-level (not just company-level) US website visitor identification. Pulls LinkedIn profile + business email in real time to Slack. Free plan (150 resolutions/mo) → $79–149+/mo. Native Clay integration. Genuinely the cheapest entry point into identity resolution for a solo/indie operator.
- 6sense (enterprise ABM, $50K+ budgets), Bombora, BuiltWith (technographic change triggers — "added HubSpot in the last 14 days")

**Champion/job-change tracking**
- **UserGems** — "AI GTM Command Center," 21+ signals, AI SDR agent ("Gem-E"). Enterprise pricing ($2,750–$10,000/mo) — a reference point, not a starter-stage tool.
- Champify (leaner job-change-focused alternative)

**PLG/community signal**
- Common Room (community signal — Slack/Discord/GitHub), Trigify (LinkedIn-only), Endgame/Pocus/Koala/Calixa (PLG behavioral surfacing), Reo.dev (developer-native: GitHub, package installs, CLI)

**Data verification & outbound execution**
- Cognism, Dropcontact (secondary waterfall providers behind Apollo)
- ZeroBounce, Rejoiner (MX/SMTP verification — keep bounce rate under 2% before outreach)
- Instantly, Smartlead (sequencing), Apollo.io (database + enrichment + sequencing, strong free tier)

## 2.3 The system blueprint — 5 layers, reusable across every project

**Layer 1 — Market Mapping**
Define the universe through three lenses at once: problem-based (who feels this pain), solution-based (who buys adjacent tools), lookalike-based (resembles your best customers). Feed 5–10 seed accounts into a semantic search layer (Exa) — this beats NAICS/SIC codes because it matches on what a company actually *does*, via embeddings of homepage/value-prop/case-study content, not an industry category that often doesn't fit specialized business models.

**Layer 2 — Multi-dimensional ICP definition**
Firmographic + technographic + behavioral/intent + psychographic + **buying committee** (economic buyer, champion, technical evaluator, end user, likely blocker — mapped by role, not just company).

**Layer 3 — Waterfall enrichment**
```
Primary (Apollo) → Secondary (Cognism/ZoomInfo) → Verification gate (ZeroBounce, <2% bounce target)
```

**Layer 4 — Signal-based triggering + scoring matrix**
Score every account on two axes and route by quadrant — this is a genuinely useful upgrade over a single blended score, because it separates "is this a fit" from "is now the moment":

| Segment | Fit Score | Intent Score | Action |
|---|---|---|---|
| **Tier 1** | ≥ 80 | ≥ 70 | Immediate personalized outbound / direct SDR call |
| **Tier 2** | ≥ 80 | < 70 | Content nurture + LinkedIn warmth sequence |
| **Tier 3** | < 80 | ≥ 70 | Retargeting ads to test intent validity |
| **Disqualified** | < 50 | any | Dropped from active queues |

Trigger events to feed the Intent axis: job changes into relevant roles, funding events, hiring surges in a specific function, tech stack changes (BuiltWith), website visits (RB2B), competitor mentions in job postings.

**Layer 4b — AI buying-committee research agent**
An AI agent scraping recent job postings from target companies to extract pain points, tools already in use, and stated strategic goals — synthesizing a persona brief per buying-committee role before a human ever touches the account. This is a real, buildable capability (Claude/GPT + a scraping step), not vaporware.

**Layer 5 — Closed-loop feedback** *(phase 2 — add once you have conversion data, not needed to launch)*
When an account converts to Closed-Won, feed its embedding back into the vector cluster and recalculate the centroid — your lookalike discovery in Layer 1 gets sharper every time you close a deal. This is a legitimate active-learning pattern, but it needs actual closed-deal volume to be worth the engineering effort — don't build this before you have 15–20 real conversions to learn from.

**Layer 6 — The reusable meta-framework**
For every new project, four inputs run the whole pipeline: (1) product/offer description, (2) 3–5 seed accounts, (3) market keywords, (4) non-negotiable firmographic filters. Output: a ranked account+contact list with the reasoning attached to each entry.

## 2.4 Recommended starter stack

| Layer | Tool | Cost |
|---|---|---|
| Market mapping | Exa Websets | ~$7/1,000 searches |
| Orchestration + waterfall | Clay | Free → $185/mo |
| Identity resolution / intent (cheapest entry point) | RB2B | Free → $79+/mo |
| Verification | ZeroBounce | Pay-per-verify |
| Execution | Apollo.io or Instantly | Apollo has a strong free tier |

## 2.5 Reusable per-project intake template

```
PROJECT: _______________

1. Product/offer one-liner:
2. Problem solved, and who feels it most acutely:
3. 3–5 seed "great fit" customers (real or hypothesized):
4. Known competitors / adjacent tools people already buy:
5. Non-negotiable firmographic filters
   - Geography:
   - Company size:
   - Industry:
   - Funding stage / revenue band:
6. Buying committee hypothesis
   - Economic buyer:
   - Champion:
   - Technical evaluator:
   - Likely blocker:
7. Trigger-event hypothesis (what "why now" signals matter here):
8. Success metric (deal size, usage threshold, retention pattern):
```

## 2.6 Still open

I still don't have visibility into your **industries sourcing engine variants** — nothing about it has come through in this conversation. Paste in what it already does and I'll map exactly where this framework extends it vs. replaces it.
