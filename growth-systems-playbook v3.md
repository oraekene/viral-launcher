# Growth Systems Playbook (v3) — Multi-Platform + Indie Ecosystem
### System 1: Early Viral Detection (7 platforms) · System 2: Advanced ICP Mapping & Targeting
*Researched & compiled August 12, 2026. This space moves monthly and vendors die — reconfirm everything before spending money.*

---

## Changelog v2 → v3

1. **System 1 is now multi-platform.** X + LinkedIn + TikTok + Instagram Reels + YouTube Shorts + Bluesky + Threads, with per-platform tool tables, algorithm mechanics, data-access reality, and build/buy verdicts.
2. **Indie-ecosystem analysis added** (your ScrapeCreators point): full crawl of the "unofficial scraping API" cluster, the "faceless TikTok automation" cluster, and the X/LinkedIn indie growth-tool cluster — plus their shared pricing model, marketing playbook, and churn/failure patterns.
3. **Corrections ledger added (Section 0).** Independent verification pass on every load-bearing number from v1/v2 — several were wrong (algorithm weights garbled, cost model off by ~10–40×, decay constant fabricated, one recommended tool now dead).
4. **System 2 lightly corrected** (Clay stat bias caveat, RB2B/Exa pricing verified, Websets clarified) but otherwise stands — the ICP architecture from v2 holds up under attack better than System 1 did.

---

## 0. Corrections ledger — what v1/v2 got wrong (verified August 2026)

| # | v1/v2 claim | Verdict | Corrected fact |
|---|---|---|---|
| 1 | X ranker weights ≈ Likes×1, Retweets×20, Replies×13.5, Profile Clicks×12, Link Clicks×11, Bookmarks×10 | **GARBLED** | Only published config (2023 HeavyRanker release): like **0.5**, retweet **1.0**, reply **13.5**, **author-engaged reply 75**, bookmark **10**, profile click **12**. "20×" and "1×" and "11×" match nothing. Current public repo has the weights zeroed out (values live in private config); HeavyRanker is out of production — live ranking is ML. |
| 2 | EVI formula (13.5×replies + 20×reposts + 10×bookmarks + 1×like) "matches X's open-sourced ranker almost exactly" | **WRONG, both coefficients and the "verified" claim** | 13.5 and 10 trace to the 2023 config; 20×reposts and 1×like match nothing. v2 accepted a garbled formula on the strength of a hallucinated "independent verification." |
| 3 | "Reply-back worth ~150× a single like" | **Correct as a ratio** | 75 (author-engaged reply) ÷ 0.5 (like) = 150×. But v2 presented it as a 2026 "shift" — the ranker carrying these weights is out of production; treat as legacy-derived heuristic. |
| 4 | "A post loses roughly half its visibility score every six hours" | **FABRICATED** | No 6-hour constant exists in X's source (there is an 8h simclusters half-life, unrelated). Only empirical study (arXiv:2302.09654): **median tweet half-life ≈ 80 minutes, peak ~72 seconds**. The "act within the first hour" thesis survives — for a stronger reason than the one cited. |
| 5 | Official X API for a 100–150-account watchlist ≈ **$50–100/month** | **WRONG BY 10–40×** | Pay-per-use bills **per post read ($0.005)**, not per API call. 150 accounts × 48 polls/day (15-min × 12h) × ~1–3 new tweets per poll ≈ 7k–22k reads/day ≈ **$1,000–3,300/month**. The third-party route (TwitterAPI.io ~$0.00015/read) is not "unnecessary" — at scale it's the only affordable option. |
| 6 | "Buy Black Magic for Job A" | **DEAD RECOMMENDATION** | Black Magic announced wind-down, shutting **July 1, 2026** — already gone as of this writing. Same graveyard: Shield (LinkedIn, shut 2026 under Google+LinkedIn pressure), Zopto (shut Feb 2026), SwipeInsight (domain parked), TrendPop (dead), Xpoz/Twend (dead). |
| 7 | Clay "84% practitioner adoption (96% at agencies)" from "2026 State of GTM Engineering" | **Real but biased** | Survey is real (stateofgtme.com) but self-selected, promoted in Clay's own community forum, co-authored by a Clay employee, amplified by Clay-certified agencies. Directionally credible; not independent. |
| 8 | RB2B "free 150 resolutions/mo → $79–149+" | **Verified** | Free = 150 company-level/mo. Starter $79 (300), Pro $149 (600–2.5k), Pro+ $199. |
| 9 | Exa "~$7/1,000 searches" | **Verified** | Search $7/1k requests. "Websets" is a separate product (natural-language list-building, own billing). |
| 10 | Taplio/ViralFinder as "X growth tools" | **Confirmed wrong (v2 already caught)** | Taplio = LinkedIn (lempire, sister to TweetHunter). ViralFinder = Instagram competitor analytics web tool ($13.99–27.99), not TikTok, not X. |
| 11 | 2023 HeavyRanker weights as "current" (rows 1–6 in §9) | **SUPERSEDED — Aug 13, 2026** | xAI open-sourced the production algorithm (xai-org/x-algorithm): reply 13.5→**5.0**, quote **+5.0 (new)**, share **+2.0 (new)**, like 0.5 & retweet 1.0 unchanged, **bookmarks & profile clicks removed** (bookmark was 10, profile click was 12), author-reply 75→viewer-specific **+15 bidirectional-follow boost** (the "150×" narrative is dead — author-reply is now ≤40× a like and only for mutually-following viewers). Same provenance method, new primary source. |

**Meta-lesson for every future research pass:** numbers with no primary-source provenance in this space are usually AI-garbled blog noise. The only load-bearing facts in v1/v2 that survived verification are ones I could trace to a primary source (X pricing docs, arXiv, HeavyRanker release config, Live pricing pages).

---

# SYSTEM 1: Early Viral Detection — Multi-Platform

## 1.1 The job split holds — and now applies to 7 platforms

| Job | What it means | Status (every platform) |
|---|---|---|
| **A — Monitor your own posts** | Catch your post breaking out in the first hour so you can double down | Mostly solved on X & LinkedIn by cheap tools. Build only where tools don't exist (TikTok/Shorts) |
| **B — Monitor the ecosystem** | Catch *other people's* rising posts early enough to reply-jump / steal the pattern / spot rising creators | **Open on every platform.** Zero verified tools alert on third-party engagement velocity in real time anywhere. This is the whitespace. |

The single biggest finding of this research round: **nobody — on any platform — has productized "alert me when someone else's post is about to blow up."** Every tool in every category does one of: (a) your own account analytics, (b) after-the-fact viral libraries/swipe files, (c) "currently trending" boards (crossed the threshold hours ago), or (d) keyword/mention alerts (text match, not velocity). The closest things: CreatorCrawl (scraping API that markets "pings you when something starts climbing"), Virlo (claims pre-peak alerts on tracked TikTok/Shorts/Reels creators), Pentos trackers (custom notifications, enterprise). None are verified to work as advertised. You are not late to this market — it doesn't exist.

## 1.2 Platform reality matrix

| Platform | Algorithm's early-velocity mechanic | Data access for a solo builder | Best existing tools (others' posts, realtime) | Feasibility of building your own radar |
|---|---|---|---|---|
| **X** | 2023 ranker: reply 13.5 / author-reply 75 / bookmark 10 / like 0.5 / retweet 1.0; empirical half-life ~80 min | Official API pay-per-use $0.005/post, 2M cap, no free tier. Third-party scraping APIs 33× cheaper, ToS-grey | **None (gap confirmed)** | **Build — medium cost, medium risk** |
| **LinkedIn** | ~40% of a post's lifetime interactions happen day one; comment velocity strongest signal; carousels 17× images; no published weights | **No API path exists** — engagement metrics for other people's posts are UI-only; everything else is cookie scraping that LinkedIn is actively killing | None (ViralBrain = after-the-fact; Octolens = mention alerts) | **Don't build** (platform actively bans the tooling) |
| **TikTok** | Test-cohort loop: early completion-rate/rewatch/share pushes into bigger pools; 2026: search/TikTok-SEO & sounds matter; Creative Center audio lists degraded 2026 | Worst-in-class. No public organic-metrics API; Research API = approved researchers only; industry runs on scraping (refresh 6×/day max in "real-time" tools) | None realtime (TrendTok claims rise/fall, weak; Pentos/Virlo closest) | **Build only via scraping APIs — highest ToS risk** |
| **Instagram Reels** | Official ranking: predicted reshare, completion, like, audio-page visit; "popularity" (how many, how fast) | Graph API = own media only; public profiles via scraping; 2026 pattern: session-based tools (Reelyzer uses *your* logged-in browser) | None | **Build via session-scraping or Reelyzer-style extension — fragile** |
| **YouTube Shorts** | V/S ratio (% viewed vs swiped away), % viewed, loops — subscriber count barely matters | **Actually fine**: Data API v3, 10k quota/day free, videos.list = 1 unit, search.list capped 100/day (the real bottleneck) | vidIQ/TubeBuddy = your own channels | **Build — easiest & legit** |
| **Bluesky** | No published weights; engagement-driven FTL/Discover; small network | Open ATProtocol — most permissive API of all | Blueview, Bluesky Meter, Clearsky, Bsky Tracker, Fedica, TheBlue.social, Agent Sky, BluePilot | **Build — cheapest, fully legal** |
| **Threads** | Feed driven by engagement + interaction graph; limited public analytics | No public analytics in 2026; only limited own Insights | Metricool, Iconosquare, Sendible, Minter.io, ThreadsDashboard | **Low priority; waiting game** |

## 1.3 X — the corrected system

### Tool landscape (Job A — own posts)
| Tool | What it does | Price | Status |
|---|---|---|---|
| ~~Black Magic~~ | Real-time per-tweet tracking, social CRM | Free–$59.99 | **SHUT DOWN July 1, 2026** |
| **Tweet Hunter** (lempire) | 2–3M+ swipe-file DB, TweetPredict™, Lead Finder CRM | $49 (no AI) / $99 (AI) | Alive. Indie parent co. Swipe file = after-the-fact, not alerts |
| **Typefully** | Cross-platform writing/scheduling (X, LinkedIn, Threads, Bluesky, Mastodon) | Free (15 posts/mo) → $10/set | Alive. Indie (Marc Köhlbrugge) |
| **Postwise** | AI writer, viral repurposing, multi-platform scheduling | $37 / $97 (annual) | Alive. Indie (XO LABS) |
| **Hypefury** | Evergreen recycling, auto-DM, Smart Engaging (reply-guy builder) | mid-tier | Alive. Indie (Yannick Veys) |
| **ReplyGenius** | AI contextual replies on Reddit/X/LinkedIn (the *seeding* half) | Free 25/mo → $9 / $19 | Alive. Indie. Validated by a Pieter Levels reply |

**Buy verdict for Job A on X:** Tweet Hunter. Black Magic is gone — that's the market telling you something about building long-term on X analytics.

### The corrected signal science (all numbers now traceable — updated Aug 13, 2026)

```
OFFICIAL PRODUCTION WEIGHTS — xai-org/x-algorithm, home-mixer/params/param.rs (released Aug 13, 2026).
Final Score = Σ weight × P(action), Phoenix transformer predictions:

  reply 5.0 · quote 5.0 · share 2.0 (DM 5.0, copy-link 20.0) · follow-author 4.0
  retweet 1.0 · like 0.5 · click 0.4 · open-link 0.2 · video-open/photo-expand 0.05
  bookmarks & profile clicks: REMOVED from scoring (bookmark 10 and profile click 12 in the
  old 2023 config are dead; bookmarks now only feed the ML dwell-regret gate)
  author-reply: viewer-specific +15 boost on reply weight when the author follows the viewer
  back (the old "75×/150×" constant is dead — author-reply is ≤40× a like, not 150×)
  negative: not-interested −43.2 · block −31.2 · mute −58.8 · report −234

  Adjustments: out-of-network ×0.75 discount · author diversity ×0.5 decay (floor 0.25)
  · new-author boost for ≤1,000-follower accounts on ≤24h-old posts
  · AgeFilter: posts >48h never enter the For You pipeline (hard cutoff — act fast or never)
```
- **Early velocity window:** empirical median half-life ≈ 80 min (arXiv:2302.09654) + the 48h hard cutoff. A post that will pop shows it inside ~1 hour. The old "6-hour half-life" claim is dead — retire it. The "150× reply-back" story is also dead — replaced by the actual 2026 weights above.
- **Replies and quotes are now equal at 5.0** — the spec's Q/R ratio heuristic is superseded by quotes carrying the same weight as replies in the score itself.
- **Author-in-thread is a quality trigger, not a constant** — track it as a first-class event (the radar does), weight it via calibration.
- **Practitioner threshold** (manual, used by reply-guys): ~10 likes in 5 min ≈ worth jumping on — still valid as a floor, but pods game it; pair with reply/quote velocity + author-in-thread.

### Corrected cost model (this killed the v2 plan — read it)
Official API bills **per post read at $0.005**. Realistic math for a 150-account radar, 15-min polls, 12h active:
- ~1–3 new tweets per account per poll → **7k–22k reads/day → $1,000–3,300/month** on the official API.
- That's the entire "official API is cheap" thesis dead for Job B at scale. Options:
  1. **Shrink the watchlist** — 30 high-value accounts at 15-min polls ≈ $200–400/mo official. Fine for reply-guy territory.
  2. **Third-party read APIs** (TwitterAPI.io $0.15/1k ≈ 33× cheaper, SocialData.tools $0.20/1k read-only, GetXAPI $0.05/1k cheapest, ScrapeCreators $0.99–1.88/1k) — same ballpark of $30–100/mo. ToS-grey; platform-policy risk is the price of affordability. ScrapeCreators' cached results at 0 credits + "no rate limits" is the best UX in the category.
  3. **Hybrid:** official API for a small critical watchlist, third-party for the wide net.

### System blueprint "Signal Radar" — v3 corrections applied
```
Layer 1 — Watchlist (30–150 handles + niche keywords + 10–20 rising-creator candidates)
Layer 2 — Ingestion: official API (small list) + one scraping API (wide net), 5–15 min polls
Layer 3 — Snapshot store: Postgres/SQLite time-series (NOT ClickHouse/Redis at this scale)
Layer 4 — Velocity scoring per the corrected weights; z-score vs author's trailing-30-post baseline
Layer 5 — Threshold alerts: z ≥ 2.5 within 60 min AND/OR author-reply-back occurred
Layer 6 — Semantic dedup: cheap near-dup hashing (SimHash/MinHash) first; embeddings only if needed
Layer 7 — Own-account variant (double-down flags)
Layer 8 — ALERT→ACTION LOOP (new): every alert requires a logged action (replied / skipped) and
          30-day follow-up on whether the interaction gained engagement. This is the only way to
          calibrate thresholds. Nothing in v2 had this — it's the difference between a toy and a system.
```
**Cold-start rule (new):** z-scores need baselines. Run the crawler for **7 days before trusting a single alert**; until then, use the 10-likes-in-5-min floor. Neither v2 nor the spec mentioned this.

## 1.4 LinkedIn — where tools go to die

### Tool landscape (the Taplio world)
| Tool | What it does | Price | Indie/VC | Notes |
|---|---|---|---|---|
| **Taplio** (lempire) | Publishing + own analytics + **5M-post viral DB** + "Engage" comment automation | $39 / $69 / $199 | Indie parent co | Sister product of TweetHunter. Chrome-extension (cookie) based |
| **ViralBrain** | AI content + **tracks 4,900 named creators "in real time"** + Trending Posts board | Pro (14-day trial) | Indie (Growth Tribe founders) | Closest thing to third-party tracking on LinkedIn — but threshold is after-the-fact (~50K views/7d), not velocity alerts |
| **Kleo** | AI ghostwriting + swipe file + analytics (X + LinkedIn) | $99 | Indie (Jake Ward, Lara Acosta, Cam Trew) | "Built by creators, not investors" |
| **Supergrow** | AI publishing + Engage comment tool | $19 / $39 / $139 | Indie | API/OAuth publishing — avoids cookie scraping |
| **Octolens** | Real-time mention/competitor/keyword alerts (LinkedIn + X + Reddit + HN + 150K news) | ~$119–499 | Indie | **Text-match alerts, NOT engagement velocity** |
| **MagicPost** | Publishing + analytics + viral library | $35 / $69 | Indie (IN) | Claims official LinkedIn API partner status |
| **HeyReach / Expandi / Dux-Soup** | Outreach automation (connections, like/comment steps) | $79–999 / $99 / tiers | Indie-ish | Comment-on-post campaign steps = reply-guy automation |
| ~~Shield~~ | Post analytics | — | **SHUT DOWN** | Co-founders: "Google and LinkedIn made it clear we could not continue operating Shield as it was built" (2018–2026) |
| ~~Zopto~~ | Outreach automation | — | **SHUT DOWN Feb 2026** | |

**Algorithm reality:** ~40% of a post's interactions happen day one (Metricool 2026 study, 673K posts); comment velocity is the strongest practitioner-cited signal; questions get +77% more comments; carousels 17× images; posts from personal profiles dominate. LinkedIn has **never published weights** — everything is practitioner consensus.

**Data-access reality (the killer):** LinkedIn's official API has **no endpoint for engagement metrics on other people's posts**. The Posts API can read *by author URN* but requires `r_member_social` ("restricted — approved users only"), and the response schema contains no reactions/impressions at all. Analytics endpoints cover only your own org. Every third-party tool runs on cookie/session scraping — and LinkedIn has been executing this category since the April 2025 crackdown (Shield's shutdown is the canonical postmortem).

**Verdict: do NOT build a LinkedIn radar.** You'd be building a product LinkedIn has proven it will kill, on top of the most ban-prone data access in the industry. Use Taplio's 5M-post DB for after-the-fact pattern-mining and Supergrow/Taplio Engage for comment automation. If you must watch specific accounts: manual list + periodic checks, or Octolens for keyword triggers.

## 1.5 TikTok — the treasure with the worst map

**Algorithm:** every video hits a small test cohort; strong early completion rate, rewatches, shares, comments push into larger pools. 2026 shift: search/TikTok-SEO and trending sounds became core discovery levers; TikTok's own Creative Center degraded its audio lists in 2026 — which is why third-party sound charts (Tokchart, Metricool) are having a moment.

**Tool landscape:**
| Tool | What it does | Price | Notes |
|---|---|---|---|
| ~~ViralFinder~~ | IG competitor analytics (web) — **not TikTok** | $13.99 / $27.99 | Mislabeled in the source spec |
| **TrendTok Analytics** (iOS) | Trend discovery, claims rise/fall/emerging predictions | Free + IAP | Reviews say predictions weak; mostly curated sound lists |
| **TokBoard** | Free trend boards, 80M-video index | Free | Solo dev (Melanie Mohr) |
| **Pentos** | Trackers + custom trend notifications + account analytics | $99 / $299 / $999 | Its own FAQ: "TikTok doesn't share organic content data via API" — trackers only start logging when you add them, no backfill |
| **Exolyt** | TikTok listening/analytics, refresh 1–6×/day by plan | Free → $400 → $950 | Enterprise clientele (Ogilvy, P&G) |
| **Virlo** | 3-platform listening, claims "spot viral content before it peaks", automated alerts | $49 / $199 | New indie (2025–26). The closest to what you want — unverified, one to watch |
| **TikAlyzer** | AI critique of *your* videos (hook/retention) | $9.99–49.99 | Own-content only |
| **TikTok Creative Center** | Official free trend/sound charts | Free | Baseline every paid tool competes against |
| **WinningHunter** | Ad spy for ecom (Meta/TikTok ads) | $49–249 | NOT creator trend detection — different job |

**Data access:** no public organic-metrics API. Research API & Commercial Content API are for approved researchers/academics. The entire industry scrapes tiktok.com endpoints (unstable, ToS-grey). Realistic refresh for a scraper-fed radar: 15–60 min.

**Verdict:** worth tracking as a **secondary radar fed by a scraping API** (ScrapeCreators has 22 TikTok endpoints; Bright Data sells 294M-record TikTok datasets from $0.0025/record; Apify actors pay-per-event with $5 free/month). For TikTok the playable signal isn't engagement velocity per se — it's **sound/hashtag velocity** (a sound exploding across many small accounts precedes the format wave). Track sounds, not just accounts.

## 1.6 Instagram Reels — session-scraping is the new pattern

**Algorithm (official, Meta):** ranking on predicted **reshare, watch-to-completion, like, and audio-page visit**; "popularity" = how many and how fast people engage; demotions for low-res/watermarked/muted/reposted. Early velocity is built into the model by design.

**Tools:** ViralFinder (IG competitor "viral score" = over-performance vs account average — actually the closest existing mechanic to your z-score idea, just after-the-fact), Reelyzer ($14/mo — Chrome extension reading any public profile's reels through *your own logged-in session*; the clever 2026 indie pattern: zero server-side scraping), Analisa (follower audit + hashtag reports), Pentos/Exolyt/Virlo (multi-platform), Metricool/Shortimize for scheduling+analytics.

**Verdict:** a Reels radar is buildable via Reelyzer-style session scraping (fragile) or scraping APIs. The interesting angle for IG: **audio-page velocity** (how fast a track is accruing new reels) is the earliest viral signal — same sound-tracking mechanic as TikTok.

## 1.7 YouTube Shorts — the one you can actually build legally

**Algorithm:** Shorts ranking dominated by **% viewed vs swiped-away (V/S ratio), % viewed, loops/replays**; subscriber count barely matters.

**Tools:** vidIQ / TubeBuddy (own-channel SEO/analytics), Shortimize ($49–249, creator/UGC campaign analytics, multi-platform), SanishTech (free YouTube utilities).

**Data access — the good news:** YouTube Data API v3 gives **10,000 quota units/day free**; `videos.list` = 1 unit (≈10K video reads/day); `search.list` capped at 100/day (the real bottleneck). A Shorts velocity radar (views/likes/comments per video in first hours, normalized by channel size) is **fully buildable on the official API, legally, for ~$0**. This is the best first platform to prove the radar pattern on.

**Verdict: build Shorts first as your validation platform**, then port the engine to X (paid API) and TikTok/IG (scraping APIs).

## 1.8 Bluesky & Threads — cheap options, early days

**Bluesky:** open ATProtocol = the most permissive API in social. Tools: Blueview, Bluesky Meter, Clearsky, Bsky Tracker (follower charts), Fedica (deep dashboards), TheBlue.social (real-time follower/activity heatmaps), Agent Sky, BluePilot (growth). A full velocity radar here is trivially buildable and legal — but the platform is small; treat as a practice ground + early-positioning play.

**Threads:** no public analytics in 2026 (native Insights limited; third-party: Metricool, Iconosquare, Sendible, Minter.io, ThreadsDashboard). Wait — nothing buildable yet.

## 1.9 The indie ecosystem (your ScrapeCreators point) — the crawl results

### Cluster 1: Unofficial social-data APIs (the pickaxe sellers)
| Tool | Platforms | Pricing | Backing | Posture/notes |
|---|---|---|---|---|
| **ScrapeCreators** (archetype) | 36 platforms, 100+ endpoints (TikTok 22, IG 19, YT 16, X 6, LinkedIn 6, Reddit, Threads, Truth Social, Bluesky, Spotify, Twitch…) | Free 100 credits; $47 = 25K credits; $497 = 500K; credits never expire; cached results = 0 credits | **Bootstrapped: Adrian Horning (Austin), team of 3** | Sells CLI, MCP, Claude Code skill, n8n node, **Apify actors** (sells on a rival's marketplace). "Is social media scraping legal?" answered head-on. The template to copy |
| **TwitterAPI.io** | X: 75+ endpoints, real-time WebSocket streams, **write actions** | $0.15/1K; $0.18/1K profiles; from $29/mo streams | Prism Digital LLC (DE) | Also sells **"Buy Twitter Accounts"** — grey-zone floor of the category |
| **SocialData.tools** | X read-only (profiles, posts, followers, lists, spaces) | $0.20/1K, no subscription, no free plan | Unverifiable founder | "Read-only by design… nothing to get rate-limited" |
| **GetXAPI** | X: 69 endpoints incl. writes, **auth_token login/recovery** | $0.05/1K — cheapest verified | Unverifiable founder | Sells account-recovery endpoints — squarely grey. Aggressive SEO machine |
| **CreatorCrawl** | 6 platforms, **MCP-first** (60 tools) | Free 50; $29/5K; $99/20K; $299/100K | "Talk to the founder" | Markets **real-time trend detection**: "pings you when something starts climbing, not after the peak" — the closest existing claim to your system |
| **SociaVault** | 25+ platforms | Free 50; $29/6K → $399/200K | Ziddec Inc (Ola Olaniyan) | "Public data only" compliance posture; paid press-release distribution as marketing |
| **Apify** | Actor marketplace (the distribution layer others sell on) | Free plan, pay-per-run | Czech, well-funded | 30% recurring affiliate program — a core ecosystem channel |
| **ScrapingBee / Scrapingdog** | General + dedicated Google/Amazon/YT/LinkedIn | $49–599 / $40–30K | France / India (bootstrapped founders) | Enterprise posture (SOC2, GDPR) vs the indies' "trust me" |
| **Bright Data** | Proxies + datasets (TikTok: 294.7M records from $0.0025/record, min $250) | Usage-based | VC | "Ethical web data" marketing; the enterprise pole |
| **Zyte / Octoparse** | Full-stack scraping | PAYG + enterprise | Established | Zyte = 50% recurring affiliate — highest in category |
| **Dead:** Twend.pro, Xpoz, SocialCrawl, SwipeInsight, IndieRadar | | | | Churn is the category's defining feature |

### Cluster 2: Faceless-account automation (the demand generators)
Faceless.video ($20–149, Bubble-built indie, auto-publishes generated videos on schedule), FacelessReels (affiliate program, "posts even while you sleep"), Argil ($100–200, VC-signaled, microdrama angle), Creatify ($24M VC — Katzenberg's WndrCo), InVideo AI (200+ models incl. Veo 3.1, clone-site parasite layer), OpusClip (clip repurposing with auto-publish + agent API). **These tools are the ScrapeCreators customer base** — the automated account networks you described are real, and they run on Cluster 1 APIs.

### Cluster 3: Indie X/LinkedIn growth tools
Covered in §1.3–1.4. Key addition: **ReplyGenius** ($9–19) is the purest "seeding" tool (AI replies that weave your product into threads — validated by a Pieter Levels reply), and Hypefury is the purest "influencer-customer" tool (testimonial wall: Justin Welsh, Ali Abdaal, Matt Gray, Arvid Kahl…).

### The archetype analysis — what these tools share (copy these mechanics)
1. **Pricing: pay-as-you-go credits that never expire, no subscription, cached/failed results free, "no rate limits"** — explicitly marketed against Apify/Bright Data's monthly-credit subscriptions. Psychological contract: "buy the pickaxe, not the mine."
2. **Marketing: founder-as-product.** Named human + email + X handle ("email goes straight to the engineer who built it"), anti-enterprise "run by a human" page (borrowed from LogSnag), influencer testimonial walls on the homepage (ScrapeCreators' homepage IS a wall of dev-influencers tagging @adrian_horning_).
3. **Agent-first distribution = the new SEO.** Every verified tool ships MCP servers, CLI, llms.txt, OpenAPI, Claude Code skills, plus pre-baked "Ask AI about us" ChatGPT/Grok prompts — they're optimizing for being recommended *by agents*, not ranked by Google.
4. **SEO content machines + comparison pages** ("vs Apify", "vs Bright Data", "twitter-api-alternatives", cost calculators, free tools as lead magnets).
5. **Affiliate/influencer programs as the growth loop** (Apify 30%, Zyte 50%, plus Postwise, Hypefury, Creatify, InVideo, FacelessReels).
6. **PR distribution** (SociaVault's GlobeNewswire release syndicated to Business Insider/AP/Benzinga).
7. **The ecosystem is self-reinforcing:** Cluster 2 farms accounts → those accounts need Cluster 1 APIs → Cluster 1 APIs market via Cluster 3's influencers.

### What this means for you (reperformed analysis)
- **The "grunge" marketing you described is confirmed as the category's default GTM** — and it's copyable: founder-brand + influencer testimonials + free tools + affiliate + agent-friendly docs. It's also why the tools you asked about have no sales teams and no enterprise pricing pages.
- **The data layer of your System 1 should buy from Cluster 1, not build.** ScrapeCreators-class APIs give you multi-platform coverage for ~$30–100/mo with credits that don't expire — the correct posture is: your IP is the scoring/alerting/action layer, not the scraper.
- **Never single-source a vendor in this category.** The churn evidence is overwhelming (Black Magic, Shield, Zopto, SwipeInsight, TrendPop, Xpoz, Twend all dead in 12 months). Build your ingestion behind an interface with ≥2 interchangeable providers (official API + one scraper) so a vendor death is a config change, not a system outage.
- **Buy from the read-only, "public data" end of the spectrum** (SocialData.tools, SociaVault, ScrapeCreators' public-data endpoints) and avoid write/auth-token services (GetXAPI, TwitterAPI.io account sales) — the enforcement risk is concentrated there.

## 1.10 Build vs. buy verdict (v3)

| Platform | Job A (own posts) | Job B (ecosystem radar) |
|---|---|---|
| X | **Buy:** Tweet Hunter ($49–99) | **Build** (medium priority — 2nd build target) |
| LinkedIn | **Buy:** Supergrow or Taplio | **Don't build** — platform kills this category |
| YouTube Shorts | Buy: vidIQ/TubeBuddy or build (free API) | **Build FIRST** — legal, free, validates the engine |
| TikTok | Buy: TikAlyzer for critique; Creative Center for trends | **Build on scraping API, sound-velocity signal** (3rd) |
| Instagram Reels | Buy: Analisa/Metricool | Build via session-scraping (last) |
| Bluesky | Buy: Fedica/Blueview | Build (practice ground, cheapest) |
| Threads | Buy: Metricool | Wait |

---

# SYSTEM 2: Advanced ICP Mapping & Targeting (v3 — corrected, otherwise stands)

## 2.0 v3 corrections
- **Clay 84%/96% stat:** real, but from a self-selected survey promoted in Clay's community, co-authored by a Clay-affiliated author. Directional, not independent. (v2 source list already implied this; now explicit.)
- **RB2B pricing verified:** Free 150 company-level resolutions/mo → $79/300 → $149/600–2.5K → $199/2.5M.
- **Exa verified:** Search $7/1K requests; Websets is a separate list-building product (natural-language ICP criteria → AI-verified company lists → CSV/API → Clay).
- **Additions from this research round:** CreatorCrawl/SociaVault/ScrapeCreators all do LinkedIn profile scraping that ICP enrichment needs (jobs, tech, decision-makers) at Cluster-1 prices — genuinely cheaper supplemental waterfall providers behind Clay for a solo operator.

## 2.1–2.6 The 5-layer system (unchanged from v2, restated)

**Layer 1 — Market Mapping:** three lenses (problem-based, solution-based, lookalike-based) via Exa Websets semantic discovery. Feed 5–10 seed accounts; match on what companies *do*, not NAICS codes.

**Layer 2 — Multi-dimensional ICP:** firmographic + technographic + behavioral + psychographic (AI tone pass) + buying committee (economic buyer / champion / technical evaluator / end user / blocker).

**Layer 3 — Waterfall enrichment:** Apollo → Cognism/ZoomInfo/Dropcontact → verification gate (ZeroBounce MX/SMTP, <2% bounce target). Add Cluster-1 LinkedIn scrapers as cheap supplemental providers.

**Layer 4 — Signal overlay + Fit×Intent scoring matrix:**
| Segment | Fit | Intent | Action |
|---|---|---|---|
| Tier 1 | ≥80 | ≥70 | Immediate personalized outbound |
| Tier 2 | ≥80 | <70 | Content nurture + LinkedIn warmth |
| Tier 3 | <80 | ≥70 | Retargeting test |
| Disqualified | <50 | any | Dropped |

Trigger events: job changes, funding, hiring surges, tech-stack changes (BuiltWith), website visits (RB2B), competitor mentions in job posts. AI buying-committee agent (job-posting scrape → persona briefs) — real and buildable; budget token costs per account.

**Layer 5 — Closed-loop feedback (phase 2):** closed-won accounts re-center the ICP vector cluster. Needs 15–20 conversions to matter; don't build early.

**Reusable intake template** — unchanged from v2 (§2.5): 4 inputs in, ranked list with reasoning out. **This is the piece that makes the system reusable across every project — it stays.**

## 2.7 One open item (still)

Your **industries sourcing engine variants** still haven't been pasted in — the Layer 1 overlap question (extend vs. replace) remains unanswered. The faster you drop that in, the faster System 2 is actually yours instead of a copy of Clay's.

---

## Appendix A — verified sources (primary where possible)
- X API pricing: docs.x.com/x-api/getting-started/pricing (pay-per-use, $0.005/post, 2M cap; free tier discontinued Feb 2026; Enterprise ~$42K industry-reported)
- X ranker weights: github.com/twitter/the-algorithm — HomeGlobalParams.scala (defaults zeroed; published 2023 config: like 0.5, RT 1.0, reply 13.5, author-reply 75, bookmark 10, profile click 12); analyses: juleshenry.github.io (May 2025), note.com/daigo_miyoshi, pasqualepillitteri.it (May 2026)
- Tweet half-life: arXiv:2302.09654 ("The Half-Life of a Tweet", median ~80 min, peak ~72s)
- Clay stat: stateofgtme.com (State of GTM Engineering 2026, 225+ respondents, self-selected, Clay-community-promoted)
- RB2B: rb2b.com/pricing (verified tiers)
- Exa: exa.ai/pricing ($7/1K; Websets separate at exa.ai/websets)
- LinkedIn API: learn.microsoft.com/en-us/linkedin/marketing/restricted-use-cases + Posts API docs (r_member_social restricted; no engagement fields for others' posts)
- TikTok: developers.tiktok.com (Research/Commercial API = approved researchers only); Buffer Aug 2026 guide (Creative Center audio-list changes)
- IG ranking: about.instagram.com/blog/announcements/instagram-ranking-explained
- YouTube: developers.google.com/youtube/v3 (10K quota/day, 100 search.list/day); youtube.com/howyoutubeworks
- LinkedIn algorithm: Metricool 2026 LinkedIn Study (673,658 posts; ~40% day-one interactions; carousels 17×)
- Live tool pages fetched Aug 12, 2026: scrapecreators.com (+about), twitterapi.io, socialdata.tools, getxapi.com, creatorcrawl.com, sociavault.com, apify.com, scrapingbee.com, scrapingdog.com, brightdata.com, zyte.com, octoparse.com, faceless.video, facelessreels.com, argil.ai/pricing, creatify.ai, invideo.io, opus.pro, tweethunter.io, typefully.com, postwise.ai, hypefury.com, taplio.com, replygenius.io, blackmagic.so (shutdown banner), kleo.so, heyreach.io, dux-soup.com, expandi.io, viralbrain.ai, octolens.com, metricool.com, pentos.co, exolyt.com, viralfinder.app, reelyzer.com, tokboard.com, trendtok (App Store), tikalyzer.com, virlo.ai, shortimize.com, vidIQ, tubebuddy.com, sanishtech.com, explodingtopics.com, useagentsky.com, getbluepilot.com, skypilot.social, minter.io

## Appendix B — verified dead (do not recommend)
Black Magic (shut July 1 2026) · Shield (LinkedIn, shut 2026) · Zopto (shut Feb 2026) · SwipeInsight (parked) · Xpoz (parked) · Twend.pro (dead) · TrendPop (dead) · SocialCrawl (dead) · IndieRadar (dead) · Authentic (never verified) · WaveGen (never verified) · Inspo (never verified)
