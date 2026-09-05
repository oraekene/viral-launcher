# Working System Architecture — v4
### The system that survives the red team. Multi-platform Viral Radar + ICP Engine, buildable by one person, calibrated by data instead of asserted by vibes.

**Design date:** August 12, 2026
**Lineage:** Red team audit of "Growth Systems Playbook v1/v2" and the "Two final things" spec. Every design decision below either fixes a verified defect in one of those documents or is new. Nothing is asserted that can be verified for free — and every unverifiable constant is a *parameter with a calibration date*, not a fact.

---

## 0. Design principles (the red team's verdicts, turned into rules)

1. **Proportionality.** One Postgres instance + one Python worker + cron. No ClickHouse, no Redis TimeSeries, no Rust, no Qdrant. Those were the spec's answer to a 150-account workload; this system will handle 500 accounts on a $10 VPS. (Playbook §2.4, Spec §1 — both guilty.)
2. **Constants have provenance or a calibration date.** The first table in the codebase is a `param_versions` table. Every threshold ships with either a primary-source URL or `calibration_status = pending` and an expiry date. After expiry, an uncalibrated constant is automatically flagged in every alert. (Both docs failed this.)
3. **Cold start before trust.** Z-scores require baselines. Two weeks of crawl-only before the first alert fires. (Both docs failed this.)
4. **The action loop closes the system.** Every alert produces a logged action; every action produces a 30-day outcome; thresholds are re-fitted on outcomes. A detection system with no action loop is a thermometer with no treatment protocol — the red team's #1 shared failure of both documents.
5. **No single source of data.** Per platform, ≥2 swappable providers behind one interface. Vendor mortality is a feature of this market (Black Magic, Shield, Zopto, SwipeInsight, Xpoz, Twend all died in 12 months). Provider death = config change, not system outage. (Playbook §2.3's dead-recommendation failure.)
6. **Corrected signal physics.** Published 2023 weights as *starting parameters* (like 0.5, retweet 1.0, reply 13.5, author-reply 75, bookmark 10, profile click 12), 80-minute empirical half-life as the urgency model. The garbled 20×/1× weights and the fabricated 6-hour decay are dead. (Verification receipts, red team §2.1–2.2.)
7. **Cost is modeled, metered, and capped.** Per-provider daily spend caps with alerts. The playbook's "$50–100/month" claim was 10–40× wrong; this system meters every read and shows the bill. (Red team §2.4.)
8. **Scraping risk is concentrated and isolated.** Write/auth-token services (GetXAPI, account sales) are excluded. Read-only public-data providers only. Playwright headless clusters are excluded entirely — the red team's ToS finding stands. (Red team §3.4.)

---

## 1. System overview

```
                         ┌────────────────────────────────────────────────┐
                         │              POSTGRES (single instance)         │
                         │  radar: posts, snapshots, baselines, alerts,   │
                         │         actions, outcomes, params              │
                         │  icp: projects, accounts, scores, signals,     │
                         │         enrichment_runs, closed_wins           │
                         └───────▲───────────────▲────────────────────────┘
                                 │               │
                     ┌───────────┘               └───────────┐
                     │                                        │
        ┌────────────┴─────────────┐            ┌─────────────┴────────────┐
        │   SYSTEM 1: RADAR        │            │   SYSTEM 2: ICP ENGINE    │
        │   (viral detection)      │            │   (market → account list) │
        │                          │            │                           │
        │  Ingest worker (cron)    │            │  Discovery (Exa Websets)  │
        │   └ providers (≥2/plat)  │            │  Intake template          │
        │  Scoring worker          │            │  Hard-filter gate         │
        │   └ EVI + z, guards      │            │  Waterfall enrichment     │
        │  Baseline worker         │            │  Verification gate        │
        │  Dedup (near-dup hash)   │            │  Signal overlay           │
        │  Alert router (Slack)    │            │  Fit×Intent matrix        │
        │  Action logger           │            │  Persona agent (capped)   │
        │  Calibration harness     │            │  Closed loop (phase 2)    │
        └──────────────────────────┘            └───────────────────────────┘
                     │                                        │
                     └──────────────────┬─────────────────────┘
                                        │
                          ┌─────────────┴─────────────┐
                          │  OPS: cost meter, provider │
                          │  health, backups, dashboard│
                          └───────────────────────────┘
```

**Deployment:** one VPS ($10–20/mo) or Railway/Render hobby. Python 3.12, FastAPI (read-only dashboard), psycopg3, httpx, pydantic, APScheduler or plain cron, Slack webhook for alerts. Docker optional. **No k8s, no queues-as-a-service, no vector DB.** When a worker fails, it retries; if it fails 3×, it alerts. That's the entire ops model for v1.

---

## 2. Shared infrastructure

### 2.1 The constants table (design rule #2, enforced)

```sql
CREATE TABLE param_versions (
  id SERIAL PRIMARY KEY,
  system TEXT NOT NULL,               -- 'radar' | 'icp'
  name TEXT NOT NULL,                 -- e.g. 'x_weights.reply'
  value_json JSONB NOT NULL,
  source_url TEXT,                    -- primary source, or NULL if unverifiable
  calibration_status TEXT NOT NULL DEFAULT 'pending',  -- 'sourced' | 'pending' | 'calibrated'
  calibration_expires_at TIMESTAMPTZ,
  deployed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  notes TEXT
);
```

Every parameter read by the scoring or scoring-matrix code comes from here. Alerts carry `params_version_id`. The dashboard shows: `7 params sourced, 4 pending calibration, 1 expired — alerts from expired params are labeled "UNTRUSTED"`.

### 2.2 Provider abstraction (design rule #5)

```python
class DataProvider(Protocol):
    platform: str
    def get_author_recent_posts(self, author_id: str, since_id: str | None) -> list[Post]: ...
    def get_post_metrics(self, post_ids: list[str]) -> dict[str, Metrics]: ...
    def get_author_history(self, author_id: str, n_posts: int) -> list[Post]: ...
    def cost_estimate(self, op: str, n_items: int) -> float: ...  # USD
```

Providers ship with health + cost logs (`provider_logs` table). Per-provider **daily spend cap** (default $2/day/provider for scraping providers) — when hit, the worker degrades to the secondary provider and pages the operator. Config-driven provider map:

| Platform | Primary (default) | Secondary (fallback) | Tertiary |
|---|---|---|---|
| YouTube | Official Data API (free) | — (Data API is reliable; scrape fallback not needed) | — |
| X (critical list ≤30) | Official API pay-per-use | ScrapeCreators X endpoints | SocialData.tools |
| X (wide net 150–500) | ScrapeCreators | SocialData.tools | TwitterAPI.io |
| Bluesky | ATProtocol (free) | — | — |
| TikTok (sound velocity) | ScrapeCreators TikTok endpoints | Bright Data dataset (monthly) | Apify actor |
| Instagram | Deferred to phase 2 (session-scraping is fragile; re-evaluate) | | |

**Excluded:** GetXAPI, TwitterAPI.io write/account endpoints, Playwright clusters, any provider selling auth tokens or accounts. (Red team §3.4, §2.3.)

### 2.3 Cost meter

Every provider call logs `cost_usd_cents`. Dashboard sums per provider/platform/day. Budget model in §7. If monthly data cost exceeds budget by 20%, alert fires before the invoice does.

### 2.4 Ops checklist (all cheap, all mandatory)

- `provider_logs` alerting: 3 consecutive failures → Slack page.
- Daily health email/`/health` endpoint: DB size, last snapshot per platform, stale watchlist entries (no new post in 7 days → flag for review).
- Nightly `pg_dump` to object storage (30-day retention).
- Staleness sweeper: watchlist entries auto-suspended after 30 days of zero signal (with review queue).
- **Weekly 30-minute landscape recon** (calendar-blocked): re-check the alive/dead list in Appendix B of the playbook. Vendor mortality is an input to this system, not an exception.

---

## 3. SYSTEM 1 — THE RADAR (multi-platform early viral detection)

### 3.1 Build order and why

| Step | Platform | Rationale |
|---|---|---|
| 1 (week 1) | YouTube Shorts | Official API is free and legal; validates the whole engine (baselines, z-scoring, dedup, alerts) at zero financial risk |
| 2 (weeks 2–4) | X | The money platform; hybrid cost model; proves the provider abstraction with the paid/scraped pair |
| 3 (weeks 5–6) | Bluesky | Free ATProtocol; cheap second real platform; early position |
| 4 (weeks 7–8) | TikTok | Sound-velocity signal via scraping providers; highest ToS risk, lowest build cost (no video analysis — just counts) |
| 5 (later) | Instagram | Session-scraping fragility; re-evaluate the Reelyzer pattern when the rest works |

### 3.2 Data model (delta from shared schema)

```sql
CREATE TABLE watchlist_items (
  id SERIAL PRIMARY KEY, project_id INT REFERENCES projects(id),
  platform TEXT NOT NULL, external_entity_id TEXT NOT NULL,  -- user id / channel id / sound id / keyword
  entity_type TEXT NOT NULL,  -- 'creator' | 'competitor' | 'target_customer' | 'keyword' | 'sound'
  priority TEXT NOT NULL DEFAULT 'medium',  -- critical (official API) vs medium vs low (wide net)
  authority_score INT DEFAULT 0,            -- estimated influence; NOT used in scoring
  active BOOLEAN DEFAULT true, notes TEXT
);

CREATE TABLE posts (
  id BIGSERIAL PRIMARY KEY, platform TEXT, post_external_id TEXT UNIQUE,
  author_external_id TEXT, content TEXT, posted_at TIMESTAMPTZ,
  first_seen_at TIMESTAMPTZ, url TEXT, fingerprint TEXT,  -- near-dup hash, see 3.5
  UNIQUE(platform, post_external_id)
);

CREATE TABLE post_snapshots (
  id BIGSERIAL PRIMARY KEY, post_id BIGINT REFERENCES posts(id),
  ts TIMESTAMPTZ NOT NULL, likes INT, reposts INT, replies INT,
  bookmarks INT, views BIGINT, quotes INT, author_replies INT,
  source_provider TEXT, cost_usd_cents NUMERIC(6,3)
);

CREATE TABLE author_stats (
  platform TEXT, author_external_id TEXT, computed_at TIMESTAMPTZ,
  n_posts INT, mean_evi NUMERIC, std_evi NUMERIC, median_evi NUMERIC,
  follower_count BIGINT, PRIMARY KEY(platform, author_external_id, computed_at)
);

CREATE TABLE alert_events (
  id BIGSERIAL PRIMARY KEY, post_id BIGINT, platform TEXT,
  alert_ts TIMESTAMPTZ, signal_kind TEXT,      -- 'z_score' | 'velocity_floor' | 'author_reply_back' | 'sound_spike'
  z_score NUMERIC, score_raw NUMERIC, params_version_id INT,
  status TEXT DEFAULT 'new',                    -- new | acted | skipped | stale
  meta JSONB
);

CREATE TABLE alert_actions (
  id BIGSERIAL PRIMARY KEY, alert_id BIGINT REFERENCES alert_events(id),
  action_ts TIMESTAMPTZ, action_kind TEXT,   -- 'replied' | 'threaded' | 'noted' | 'skipped'
  action_text TEXT, platform_response_id TEXT  -- the reply/comment id if replied
);

CREATE TABLE action_outcomes (
  id BIGSERIAL PRIMARY KEY, action_id BIGINT REFERENCES alert_actions(id),
  measured_at TIMESTAMPTZ,                    -- 30 days after action
  outcome_json JSONB,  -- {engagement_gained, author_replied_back, post_became_viral,
                       --  impressions_delta (if measurable), value_flag}
  value_flag BOOLEAN  -- the single ground-truth label used for calibration
);
```

### 3.3 The scoring engine (all corrections applied)

**Step 1 — Per-platform raw score.** X, using *starting* weights from the **Aug 13, 2026 official release** (xai-org/x-algorithm, `home-mixer/params/param.rs` — the actual production defaults, updated by xAI's own cron from their config system):

```
EVI_2026(t) = 5.0·Δreplies + 5.0·Δquotes + 2.0·Δshares + 1.0·Δreposts + 0.5·Δlikes
```

What changed vs the old 2023 config (and what the old values were): reply **13.5 → 5.0**; quote **new, 5.0** (quotes now weigh the same as replies); share **new, 2.0** (share-via-DM 5.0, share-via-copy-link 20.0 — unobservable externally); retweet 1.0 (unchanged); like 0.5 (unchanged); **bookmarks: removed from scoring entirely** (only appears as a feature in the ML dwell-regret gate); **profile clicks: zeroed** (was 12); the old "author-reply 75×" is now a **viewer-specific bidirectional-follow boost (+15 on reply weight)** — not a global constant, not observable from public metrics, so the radar treats author-reply-back as a **qualitative trigger, not a weighted term**.

- Δs are computed between snapshots; **minimum Δt guard:** no scoring before t=10 min; snapshots smoothed with an exponential moving average whose time constant = 80 minutes (the empirical half-life). This kills the spec's early-snapshot variance explosion (red team §3.3).
- Author-reply-back events are ingested as first-class metrics (scraped/computed from replies whose author = post author) — still the strongest *conversation* signal, just no longer a 75× constant.
- Platform variants: YouTube (views + like/comment velocity, normalized by channel size), Bluesky (like/repost/reply velocity), TikTok (sound-velocity in §3.6).

**Step 2 — Z-score with the small-account fix (red team §3.3):**

```
Z = (S − μ_author) / σ_eff
σ_eff = max(σ_author, σ_floor)          # σ_floor = 0.5 × cohort-median σ
                                        # cohort = similar-size authors in your watchlist
```

- Baselines: trailing 30 posts per author, recomputed nightly, with follower-growth normalization (`S_normalized = S × (f0/f_now)^0.5`).
- No Gaussian assumption is made about the distribution — calibration (§3.7) fits the actual distribution from outcome data.

**Step 3 — Triggers (each produces an alert card):**

| Signal | Condition | Params version |
|---|---|---|
| z-score | Z ≥ 2.5 within first 60 min | pending calibration |
| velocity floor (new authors, no baseline yet) | ≥10 likes (or platform-equivalent) in 5 min | pending calibration |
| author reply-back | post-author replies to any comment within 60 min of first snapshot | sourced heuristic |
| sound spike (TikTok) | sound's video-count delta > 3× cohort median in 3h | pending calibration |

The z-score and floor triggers are *both* present (playbook's sin was choosing one; the spec's was trusting the other) — calibration decides which one actually predicts outcomes.

**Step 4 — Dedup (red team §3.7, but proportional):** `fingerprint` = SimHash of normalized text (lowercased, URL/emoji stripped). Same-format alerts within 24h collapse into one alert card showing member count and the highest-z member. Embeddings only if SimHash proves insufficient — measured, not assumed.

### 3.4 Alert routing and the alert card

Slack webhook (Telegram as backup). Card fields: platform, author, text snippet, URL, score, z, which signal fired, age of post, **calibration status of the thresholds that fired** (`TRUSTED` vs `UNCALIBRATED — treat as signal, not gospel`), and a one-button action menu (Replied / Skipped / Noted). Every card must resolve to an `alert_actions` row within 24h, or it's stale and counted as a false alarm.

### 3.5 The action loop (design rule #4 — the piece both documents lacked)

```
alert fires ──► human acts (reply/thread) ──► action logged
                                             └──► 30-day outcome measured:
                                                  • did the reply itself gain engagement?
                                                  • did the post author reply back?
                                                  • did the post cross virality threshold
                                                    (e.g., 10× author's median post reach)?
                                                  → value_flag = TRUE only if yes
                                                            to ≥1 of the above
```

The 30-day outcome is the ground truth. It feeds §3.6. If you never act on alerts, this system degrades to noise — the red team's core finding was that detection is the easy 20%.

### 3.6 Calibration harness (the anti-assertion engine)

- After **≥100 resolved alerts**, fit: `precision = value_flag TRUE / acted alerts`; `recall` against a post-hoc "missed virality" query (posts that crossed the virality threshold without alerting).
- Grid-search z-thresholds (1.5 → 4.0), floor thresholds, and the Δt window to maximize precision with recall ≥ 60%. Winner becomes `params_version` marked `calibrated`, with its measured precision/recall stored in `notes`.
- Re-run monthly, and every time the outcome distribution shifts by >20% (drift detection on value_flag rate).
- **Per-project calibration:** outcomes are bucketed by `project_id` so each project's thresholds converge on its own niche dynamics instead of one global number.

### 3.7 Cost model (corrected math, per design rule #7)

| Platform | Watchlist | Poll cadence | Est. monthly data cost |
|---|---|---|---|
| YouTube | 100 channels | 15 min | **$0** (official API, 10K units/day free; 100 channels × 96 polls × ~1 video = ~9.6K reads < quota; search capped 100/day → use channel-upload feeds instead of search) |
| X critical (official API) | ≤30 accounts | 15 min × 12h | ~$75–150 (30 × 48 polls × ~0.75 new tweets ≈ 1,100 reads/day × $0.005 × 30) |
| X wide net (scraper) | 150–500 | 15 min × 12h | ~$15–50 (ScrapeCreators $0.99–1.88/1K; 216K tweets/mo ≈ $32) |
| Bluesky | 100 accounts | 15 min | **$0** (ATProtocol) |
| TikTok | 50 sounds + 50 creators | 30 min | ~$10–30 (ScrapeCreators cached results often 0 credits) |

**Radar total: ~$100–230/month.** Two knobs if over budget: (a) shrink critical list, (b) drop poll cadence to 30 min on the wide net. Both are config, not code. The official-API-only fantasy ($50–100 for 150 accounts) is dead — this is the honest number.

---

## 4. SYSTEM 2 — THE ICP ENGINE (with every red-team defect fixed)

### 4.1 Pipeline (module order = the order money moves)

```
[1] Intake template (per project)         ← human input, 15 min
[2] Discovery: Exa Websets                ← semantic market mapping, $7/1K
[3] Hard-filter gate (local code)         ← zero spend on garbage  ★fix
[4] Waterfall enrichment (verified)       ← Apollo → Cognism → Dropcontact  ★fix
[5] Verification gate (ZeroBounce)        ← cascade on FAILURE, not first result  ★fix
[6] Signal overlay (RB2B, BuiltWith, hiring/funding feeds)
[7] Fit×Intent matrix → tiers            ← thresholds from constants table
[8] Persona agent (budget-capped)        ← LLM cost ceiling per account  ★fix
[9] Outbound (Apollo/Instantly)          ← only Tier 1 + signal-fired
[10] Closed-loop centroid                 ← phase 2, ≥15–20 closed-won
```

### 4.2 Fixes applied (all traceable to red team §3.5)

| Red-team defect | Fix |
|---|---|
| Waterfall stops at first provider result, accepting garbage | **Verification-gated waterfall:** Provider A result is only accepted if it passes the verification gate; if it fails, cascade continues to B, then C. A result that fails verification never enters the DB. |
| Module 4 LLM budget unbounded | **Per-account cap: $0.50 LLM budget** (default, configurable). Persona briefs generated only for accounts that pass Tier 1/2 in the matrix. Batch-processed. No brief for a score it can't use. |
| Module 1 reinvents Exa | Deleted. Discovery IS Exa Websets (plus seed accounts + natural-language criteria). Custom embeddings only in phase 2 for the closed loop, and even then on closed-won accounts only. |
| Thresholds asserted | Fit ≥80 / Intent ≥70 are starting parameters in the constants table, `calibration_status = pending`, calibrated on conversion outcomes per project (§4.5). |
| "Retargeting ads to test intent validity" | Replaced: Tier-3 (high intent, low fit) accounts get a 2-line manual outreach test or content-nurture sequence — an email costs $0; an ad campaign costs $500 and tests the wrong hypothesis. |
| BuiltWith 14-day signals noisy | BuiltWith used only as a *coarse* technographic snapshot (has/dosn't-have), never as a timing trigger. Timing comes from RB2B (visitor identity), hiring feeds, and funding feeds. |
| RB2B misdescribed | Used as designed: script-tag visitor identification, person-level, Slack-push. Free tier 150 resolutions/mo → $79 at 300. |
| Ghost job postings pollute persona data | Job-board scraping requires job posts to be older than 14 days AND from company careers page, not aggregators. Recency ≠ quality here. |

### 4.3 Intake template (the reusable per-project input — unchanged from playbook, it was right)

```
PROJECT: _______________
1. Product/offer one-liner:
2. Problem solved, and who feels it most acutely:
3. 3–5 seed "great fit" customers (real or hypothesized):
4. Known competitors / adjacent tools people already buy:
5. Non-negotiable firmographic filters (geo, size, industry, funding, revenue band):
6. Buying committee hypothesis (economic buyer / champion / technical evaluator / blocker):
7. Trigger-event hypothesis (what "why now" signals matter here):
8. Success metric (deal size / usage threshold / retention pattern):
```

### 4.4 Fit×Intent matrix (parameters, not doctrine)

| Segment | Fit | Intent | Action | Calibration |
|---|---|---|---|---|
| Tier 1 | ≥80 | ≥70 | Personalized outbound (human or AI SDR draft) | pending → calibrated on win rate per project |
| Tier 2 | ≥80 | <70 | Content nurture + LinkedIn warmth | pending |
| Tier 3 | <80 | ≥70 | 2-line manual test or nurture; no ad spend | pending |
| Disqualified | <50 | any | Dropped | fixed |

Intent axis inputs: RB2B visits (person-level), hiring velocity for relevant roles, funding rounds, job-posting tech-stack mentions. Each signal has `signal_type` + `observed_at` — intent freshness decays over 30 days (a funding round from 11 months ago is not intent).

### 4.5 Closed loop (phase 2, only after volume — playbook's demotion was correct)

- After 15–20 closed-won accounts in a project: embed them, compute centroid, feed back into Websets seed list.
- Until then: the loop is the *outcome* table (`closed_wins` → per-project win-rate-by-tier), which recalibrates the matrix thresholds from §4.4 — a cheap, tabular loop that doesn't need a vector DB. The vector loop is a refinement on top of a working tabular loop, not a replacement for one.

---

## 5. Shared tables & integration between the two systems

The two systems share: `projects`, `param_versions`, `provider_logs`, and the cost meter. The real integration is **intentional, not accidental:**

- **Radar → ICP:** alert_events on `target_customer` and `competitor` watchlist types feed the ICP intent axis (a target account whose content is exploding = intent + relevance signal). Conversely, accounts scoring Tier 1/2 in ICP get added to the radar watchlist as `target_customer` — you're now watching your best prospects' content for reply-guy entry points. This is the compounding loop neither source document had.
- **ICP → Radar:** each new project's intake template auto-generates its radar watchlist (competitors + target creators + niche keywords from field 4/3).

---

## 6. Failure modes & mitigations (red team §5 extended)

| Failure | Likelihood | Mitigation |
|---|---|---|
| Data provider dies (vendor mortality) | High — 7 dead in 12 months | ≥2 providers/platform behind the abstraction; weekly recon; config swap |
| Official X API cost spike | High | Per-provider daily spend caps; critical list ≤30; degrade to scraper |
| Alert fatigue → ignored alerts | High | SimHash dedup; calibration drives thresholds down to what actually predicts value; UNTRUSTED labeling until calibrated |
| Small-account z-score explosion | High | σ_eff floor + winsorization (computed, in code, not asserted) |
| Reply-guy account bans | Medium | Human-paced replies (no automation of the act), warm-up, max N replies/account/day; watchlist spread across 2–3 accounts |
| Platform policy change (e.g., another Feb-2026 API pricing event) | Medium | The provider abstraction + cost meter make the event visible within a day; budget knobs are config |
| LLM budget blowout (persona agent) | Medium | Per-account cap $0.50; batch; only Tier 1/2 |
| Ghost job postings polluting ICP data | Medium | Careers-page-only sourcing, 14-day age floor |
| Scraper returns stale/cached data silently | Medium | Provider health: snapshot staleness detection (no new snapshots for X min → degrade); cached-result stamps in `source_provider` |
| Backups lost / DB corrupt | Low | Nightly pg_dump, 30-day retention |

---

## 7. Full cost model (monthly, steady state)

| Item | MVP (month 1–2) | Production (month 3+) |
|---|---|---|
| VPS (2 vCPU/4GB) or Railway | $10 | $20 |
| YouTube radar | $0 | $0 |
| X official API (30-account critical) | $75 | $150 |
| X scraper wide net (ScrapeCreators) | $15 | $35 |
| Bluesky radar | $0 | $0 |
| TikTok sound radar | $10 | $30 |
| Exa Websets (ICP discovery) | $0–15 | $30 |
| Apollo free / paid | $0 | $49–99 |
| ZeroBounce (pay-per-verify) | $0 | $20 |
| RB2B | $0 (free 150) | $79–149 |
| Clay | **$0 — excluded from v1** (see note) | $185 when enrichment volume demands |
| **Total** | **~$110–125** | **~$390–530** |

**Clay note:** the playbook made Clay the spine; the red team flagged credit burn at top-of-funnel and the biased adoption stat. v1 keeps the spine free (Apollo + verified cascade + ZeroBounce in local code). Clay enters only as a convenience layer once the waterfall volume justifies its price — it's an optional execution surface, not the architecture.

---

## 8. Build plan (one person, nights/weekends ≈ 8–10 weeks)

| Phase | Duration | Deliverable | Exit criterion |
|---|---|---|---|
| **P0 Foundation** | Week 1 | DB schema, provider interface, param_versions table, cost meter, Slack alert skeleton, YouTube provider | YouTube snapshots flowing; $0 spend |
| **P1 YouTube radar** | Week 2 | Baseline worker, scoring engine (guards + σ-floor), dedup, alert→action logger | 100-channel watchlist; first alerts; action loop closes |
| **P2 X radar** | Weeks 3–4 | X official + scraper providers, hybrid watchlist, 30-day baseline buildup (cold start — **no trusted alerts until baselines exist**) | Critical list + wide net flowing; ~$100/mo spend |
| **P3 Bluesky + TikTok** | Weeks 5–6 | Bluesky provider (free), TikTok sound-velocity worker | Sound-spike alerts fire; dedup handles format floods |
| **P4 Calibration v1** | Week 7 | Outcome scoring (≥100 alerts), threshold fit, first calibrated params version | Precision/recall published per project |
| **P5 ICP v1** | Weeks 8–9 | Intake template UI, Exa discovery, hard-filter gate, verified waterfall, Fit×Intent matrix | A real project runs end-to-end: intake → 200 scored accounts with reasoning |
| **P6 Loop closure** | Week 10 | RB2B + hiring/funding signals, persona agent (capped), radar↔ICP watchlist coupling | Tier 1 lists auto-generated from live signals; closed-wins table populating |
| **Phase 2 (later)** | Month 3+ | Closed-loop centroid, Clay integration if needed, Instagram re-eval, per-project calibration v2 | Only after ≥15–20 closed-won |

**Cold-start is a milestone, not a detail:** P1's exit criterion explicitly forbids trusting alerts before author baselines exist. Anyone who skips P0–P1 to "save time" reintroduces the exact failure the red team found in both documents.

---

## 9. The constants table, v0 (every number, with its provenance or its due date)

| # | Parameter | Value | Status | Source / calibration due |
|---|---|---|---|---|
| 1 | x_weights.like | 0.5 | sourced | xai-org/x-algorithm `home-mixer/params/param.rs` (Aug 13, 2026 production defaults) |
| 2 | x_weights.retweet | 1.0 | sourced | same |
| 3 | x_weights.reply | 5.0 | sourced | same (was 13.5 in 2023 config) |
| 4 | x_weights.quote | 5.0 | sourced | same (new in 2026; quotes = replies in weight) |
| 5 | x_weights.share | 2.0 | sourced | same (new in 2026; share-via-DM 5.0, share-via-copy-link 20.0 unobservable) |
| 6 | x_weights.bookmark / profile_click | **0 — removed** | sourced | same (bookmarks only feed the ML dwell-regret gate feature `n_bm_share`; profile clicks zeroed) |
| 7 | x_author_reply | qualitative trigger (was 75×/bidirectional +15) | sourced | same — viewer-specific boost, unobservable from public metrics; keep as alert trigger, not a weighted term |
| 8 | decay.half_life | 80 min | sourced | arXiv:2302.09654 (median tweet half-life); AgeFilter in x-algorithm hard-cuts posts at 48h |
| 9 | oon_discount | 0.75 | sourced | x-algorithm `oon_weight_factor` (out-of-network posts discounted; topic OON 0.5) |
| 10 | new_author_boost | ≤1,000 followers, ≤24h old | sourced | x-algorithm cold-start params (boost toward position ratio 0.85) |
| 11 | author_diversity | ×0.5 after 1st post, floor 0.25 | sourced | x-algorithm `author_diversity_decay` |
| 12 | z.threshold | 2.5 | pending | calibrate at ≥100 outcomes (P4) |
| 13 | velocity_floor.likes_5min | 10 | pending | calibrate at ≥100 outcomes |
| 14 | min_dt | 10 min | sourced | variance guard (design) |
| 15 | sigma_floor | 0.5 × cohort median | pending | calibrate at ≥100 outcomes |
| 16 | sound_spike.factor | 3× cohort median / 3h | pending | calibrate at ≥100 outcomes |
| 17 | icp.fit_threshold | 80 | pending | calibrate on win rate per project |
| 18 | icp.intent_threshold | 70 | pending | calibrate on win rate per project |
| 19 | intent.decay | 30 days | pending | calibrate |
| 20 | persona.budget_per_account | $0.50 | sourced | cost guard (design) |
| 21 | alert.action_ttl | 24h | sourced | staleness guard (design) |
| 22 | provider.daily_spend_cap | $2/provider | sourced | cost guard (design) |

Rows 1–11 are the only *facts* in the system — everything else is a starting point with a due date. That is the entire philosophical difference between this architecture and both documents it was born from. (Rows 1–7 were re-verified against the official Aug 13, 2026 release — the method stood; five of the six weight values changed.)

---

## 10. What "done" looks like (the acceptance test the red team demands)

A system that:
1. Detects a post before it crosses 10× the author's median reach — and you can prove it (calibrated precision/recall per project, not anecdotes).
2. Turns every alert into a logged action with a 30-day outcome — the action loop runs with zero gaps.
3. Maps a new project from intake template to 200 scored accounts in one afternoon for under $50.
4. Keeps every threshold in the constants table, with a calibration date in the past or future — never "trust me."
5. Survives the death of any one vendor as a config change.
6. Bills less than $550/month in production, and can prove it from the cost meter.

Build P0 this weekend. The rest follows.
