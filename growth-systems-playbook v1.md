# Growth Systems Playbook
### System 1: Early Viral Tweet Detection · System 2: Advanced ICP Mapping & Targeting
*Researched and compiled August 2026. Tool pricing/features in this space shift monthly — reconfirm before committing budget.*

---

## A note on methodology

Everything below comes from public research: product docs, pricing pages, 2026 teardown/comparison sites, G2 reviews, and practitioner playbooks (Indie Hackers threads, GTM engineering blogs, X's own open-sourced ranking code). I don't have access to competitors' internal codebases or private dashboards, so "copy their systems" means what it should mean anyway: extract the *mechanics* — what signals they track, what thresholds they use, how they're architected — and rebuild that logic as your own system, rather than renting theirs forever.

---

# SYSTEM 1: Early Viral Tweet Detection

## 1.1 There are actually two different jobs hiding in "track viral tweets early"

Almost every tool in this space solves **only one** of these, which is why no single app has "perfected" the whole thing:

| Job | What it means | Who's solved it |
|---|---|---|
| **A — Monitor your own posts** | Catch *your* tweet breaking out in the first 30–60 min so you can double down (reply to yourself, follow-up thread, engage every commenter) | Mostly solved. Buy, don't build. |
| **B — Monitor the ecosystem** | Catch *other people's* rising tweets (competitors, target influencers, niche keywords) early enough to reply-jump the wave, steal the content pattern, or spot a rising creator for partnership | Half-solved. This is where the real gap — and your build opportunity — is. |

## 1.2 The current tool landscape (Job A — your own account)

| Tool | Current category term | What it actually does | Price |
|---|---|---|---|
| **Black Magic** (blackmagic.so) | "X analytics + social CRM" | Real-time per-tweet tracking, follower-vs-stranger reach split, best-time-to-post, daily/weekly digest email, relationship CRM (notes/reminders per person) | Free tier; $7.99–$59.99/mo paid |
| **Tweet Hunter** | "creator growth suite" | Searchable **2–3M+ tweet swipe-file database** by keyword/handle, **TweetPredict™** (AI forecasts performance *before* you post), Lead Finder CRM | ~$49/mo (Grow plan) |
| **Typefully** | "creator publishing + analytics" | Scheduling + in-context analytics, "Trending" surfacing across platforms (X, LinkedIn, Bluesky) | From $8/mo |
| **Postwise** | "AI ghostwriter" | Drafts tweet variants in your voice, viral-post repurposing, analytics | Mid-tier pricing |
| **Hypefury / Feedhive** | "evergreen recycling / auto-plug" | Automatically re-surfaces your top performers, thread automation | From $29/mo |

None of these need to be rebuilt. If Job A is your actual need, subscribe to Black Magic or Tweet Hunter today and you're done.

## 1.3 What nobody's fully productized (Job B — the ecosystem radar)

The closest things that exist:
- Tweet Hunter's swipe-file **search** (query by keyword/handle after the fact — not real-time alerting)
- X's native lists + manual refresh (what most indie hackers actually use)
- The **"reply guy" workflow**, which is a *manual* version of exactly what you're describing: maintain a watchlist of 50–150 target accounts, scan every 15–30 min during active hours, jump on posts showing early traction with a genuine reply within the first 30–60 minutes while the algorithm is still deciding whether to expand distribution.

This manual workflow is well-documented and battle-tested by indie hacker communities — but it's manual. Automating it is the actual system to build.

## 1.4 The signal science (why the 30–60 minute window matters)

X open-sourced its ranking weights, reconfirmed through the January 2026 Grok-powered update. The simplified scoring formula:

```
Score = (Likes × 1) + (Retweets × 20) + (Replies × 13.5)
      + (Profile Clicks × 12) + (Link Clicks × 11) + (Bookmarks × 10)
```

Two things matter more than that base formula:
- **A reply that gets the original author to reply back is worth up to ~150× a single like.** Conversation depth dominates everything — this is the single most important 2026 shift.
- **Engagement velocity in the first 30–60 minutes** determines whether a post gets pushed to non-followers at all. A post loses roughly half its visibility score every six hours. If it's going to pop, it shows within the hour — slow-burn virality is rare.

Practical threshold indie hackers use manually: **10+ likes within the first 5 minutes** = worth an immediate reply. That's the human version of the z-score alert your system should automate.

## 1.5 System blueprint: "Signal Radar"

```
Layer 1 — Watchlist config
   Per project: 30–150 tracked handles (competitors, target influencers,
   customers) + a set of niche keywords/phrases to search on

Layer 2 — Ingestion
   Poll tracked handles + keyword search every 5–15 min during active hours

Layer 3 — Snapshotting
   Store engagement counts (likes/RT/replies/bookmarks) per tweet per
   timestamp → compute deltas between snapshots

Layer 4 — Velocity scoring
   Normalize each tweet's velocity against that author's trailing
   30-tweet median + stdev → z-score. Weight replies/bookmarks per the
   formula above (they matter far more than raw likes)

Layer 5 — Threshold alerting
   Push to Slack/Telegram/webhook when a tracked tweet crosses your
   threshold (e.g., z-score > 2.5) within the first 60 minutes —
   this is your "reply now" signal

Layer 6 — Swipe file
   Auto-archive anything that crosses the viral threshold into a
   searchable DB, tagged by hook type / format / topic, so it doubles
   as content-inspiration infrastructure (this is what Tweet Hunter's
   database is, just built for your niche specifically)

Layer 7 — Own-account variant
   Same pipeline pointed at your own posts, plus an auto-flag for
   "double down" actions (thread follow-up, self-reply, boost)
```

## 1.6 Data access reality (the actual constraint)

X's API pricing changed materially in 2026 and this determines what's actually buildable:

- **February 2026:** X killed the old flat Basic ($200/mo) and Pro ($5,000/mo) tiers for new signups, moving everyone to **pay-per-use**: ~$0.005 per post read, capped at 2M reads/month. Above that, Enterprise access starts around $42,000/month.
- **Third-party alternatives** run 90–99% cheaper because they aggregate/cache: TwitterAPI.io (~$0.00015/read), SocialData.tools, GetXAPI, Xpoz. These operate in a legal gray zone relative to X's own ToS, so weigh that against cost before building on one long-term.

**Practical math:** a watchlist of 100–150 accounts polled every 15 minutes during a 12-hour active window is a small number of monthly reads — well within a $50–100/month official-API budget. You don't need the cheap third-party route unless you're doing ecosystem-wide keyword search at scale, not just a curated watchlist.

## 1.7 Build vs. buy verdict

| | Verdict |
|---|---|
| **Job A (your own tweets)** | **Buy.** Black Magic or Tweet Hunter already do this well and cheaply. Building your own would be reinventing a $10–50/mo tool. |
| **Job B (ecosystem radar)** | **Build.** This is the genuine gap. A weekend MVP: Google Sheet/Airtable + n8n or Zapier + X API poll every 15 min + Slack webhook when z-score crosses threshold. Scaled version: Postgres + a cron worker + the same alerting layer, plus the swipe-file DB as a side benefit. |

---

# SYSTEM 2: Advanced ICP Mapping & Targeting

## 2.1 Current terminology (so we're speaking the same language on every project)

| Term | Meaning |
|---|---|
| **ICP** | Ideal Customer Profile |
| **TAM / SAM / SOM** | Total / Serviceable / Serviceable-Obtainable Market |
| **Firmographic / Technographic / Demographic / Psychographic** | Company attributes / tech stack / individual attributes / values-and-culture fit |
| **GTM engineering** | The 2023-coined discipline (Clay popularized it) of building revenue systems with AI + automation instead of manual ops |
| **Waterfall enrichment** | Chaining multiple data providers so if Provider A misses a field, it falls through to B, then C, until the data is found |
| **Signal-based selling / warm outbound** | Triggering outreach off a specific buying-intent event, not a cold static list |
| **Buying committee mapping** | Identifying the economic buyer, champion, technical evaluator, end user, and blocker within a target account |
| **PLG signals / PQL** | Product-led-growth behavioral signals; Product-Qualified Lead |
| **Champion tracking** | Watching former customers/users for job changes, since a champion who moves to a new ICP-fit company is a pre-warmed lead |
| **Lookalike / account expansion** | Finding companies that resemble your best existing customers |
| **AI SDR** | An AI agent that researches, scores, and drafts outreach autonomously |

## 2.2 The current tool landscape, categorized

**1) Enrichment/orchestration spine**
- **Clay** — the dominant player. 84% practitioner adoption (96% at agencies) per the 2026 State of GTM Engineering survey. Waterfalls across 150+ providers, lifts email match rates from ~40% (single-source) to 78–92%. Free tier → Launch $185/mo → Growth $495/mo.
- Persana AI, SyncGTM (cheaper alternative, ~$99/mo, similar mechanics at smaller scale)

**2) Intent/signal aggregation**
- **Unify** — aggregates 10+ intent sources (6sense, Bombora, G2, Clearbit) into automated "Plays." Growth plan ~$700/mo.
- **Warmly** — website visitor identification + intent, ~200M+ account/contact database (branded "Coldly")
- 6sense (enterprise ABM, $50K+ budgets), Bombora, G2 buyer intent

**3) Lookalike / account discovery**
- **Keyplay** — ICP definition + "find accounts like these" discovery; the analytical foundation layer, not an action-orchestration engine
- **Exa / Exa Websets** — semantic search API. Feed it a plain-language description ("Series A vertical SaaS in healthcare RCM, under 100 employees") and it returns genuinely relevant companies from the open web, not just a static database. Best for the first 30–50 high-precision matches; needs an enrichment layer downstream since it returns company names/context, not verified contacts. ~$7/1,000 searches.
- Ocean.io, Discolike, Veerview — dedicated lookalike-expansion tools that take Exa's precision output and broaden it into the thousands

**4) Champion / job-change tracking**
- **UserGems** — now positions as an "AI GTM Command Center." Tracks 21+ signals (job changes, funding, hiring, tech stack shifts) and scores against 600+ ICP criteria weekly, with an AI SDR agent ("Gem-E") drafting outreach. Enterprise pricing ($2,750–$10,000/mo) — reference point, not a starter-stage tool.
- Champify (leaner, job-change-focused alternative)

**5) PLG / community signal**
- **Common Room** — reads community activity (Slack, Discord, GitHub, LinkedIn, X) and ties it to account/person records. Best fit if you have an active developer community.
- **Trigify** — LinkedIn-only signal tracking (who's engaging with competitor content, etc.)
- Endgame, Pocus, Koala, Calixa — PLG behavioral signal surfacing (free-to-paid conversion triggers)
- Reo.dev — developer-native signals (GitHub, package installs, CLI usage) for technical products

**6) Outbound execution**
- Instantly, Smartlead (sequencing), Apollo.io (database + enrichment + sequencing in one, strong free tier)

## 2.3 The 5-layer "perfect ICP" system blueprint

This is designed to be **reusable across every project** — the whole point of building it once, properly.

**Layer 1 — Market Mapping (define the universe)**
Define the market through three lenses simultaneously, not just one:
- *Problem-based:* who feels this pain most acutely
- *Solution-based:* who currently buys adjacent/competing tools
- *Lookalike-based:* who resembles your best current (or hypothesized) customers

Use a semantic search layer (Exa/Websets) to enumerate the company universe from a natural-language description of the ideal buyer, then filter that universe down from TAM → SAM → SOM using firmographic filters.

**Layer 2 — Multi-dimensional ICP definition**
Don't define ICP on firmographics alone — that's the most common reason ICP mapping fails to predict actual buyers:
- Firmographic (size, industry, revenue, geography, funding stage)
- Technographic (existing tech stack, integration compatibility)
- Behavioral/intent (website visits, content engagement, hiring signals)
- Psychographic/cultural fit (harder to quantify — an AI pass on a company's public writing/tone can approximate this)
- **Buying committee** — map by role, not just company: economic buyer, champion, technical evaluator, end user, likely blocker

**Layer 3 — Enrichment & scoring (the waterfall)**
Chain providers so a miss on Provider A falls through to B, then C — this is the single mechanic that separates 40% match-rate tools from 80–90% ones. Score every account on two axes: ICP-fit (static, structural) and timing (dynamic — "why now"). Refresh scores continuously as new signals arrive.

**Layer 4 — Signal-based triggering**
Define concrete trigger events per market segment — job changes into relevant roles, funding events, hiring surges in a specific function, tech stack changes, competitor mentions in job postings. Auto-generate a target list only when ICP-fit AND an active trigger are both present — this is what separates "signal-based selling" from a static cold list.

**Layer 5 — The reusable meta-framework**
For every new project, you feed the system four inputs and it runs Layers 1–4 automatically:
1. Product/offer description (plain language)
2. 3–5 seed "great fit" customers (real or hypothesized, for lookalike modeling)
3. Market keywords / adjacent tool names
4. Non-negotiable firmographic filters

Output: a ranked account + contact list with the reasoning attached to each entry (why it's a fit, what trigger fired).

## 2.4 Recommended starter stack

| Layer | Tool | Cost |
|---|---|---|
| Market mapping / semantic discovery | Exa Websets | ~$7/1,000 searches, free credits to start |
| Orchestration + waterfall enrichment | Clay | Free tier → $185/mo when you need volume |
| Signal layer (add once you're doing active outbound, not just mapping) | Warmly or Unify | Warmly is the lighter/cheaper entry point |
| Execution | Apollo.io or Instantly | Apollo has a strong free tier |

Clay is the right spine specifically *because* it's flexible enough to be templated fresh for each new project rather than locked to one ICP — that's the property you need given you're reusing this across every project you run.

## 2.5 Reusable per-project intake template

Copy this for every new project before running the system:

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
8. Success metric (what does "good fit" mean — deal size, usage
   threshold, retention pattern):
```

## 2.6 One open item

I don't have visibility into your existing **industries sourcing engine variants** — this is a fresh session and nothing about that came through here. If you paste in what that system already does (even roughly), I can show you exactly where this 5-layer framework should extend it versus replace it, instead of guessing at overlap.
