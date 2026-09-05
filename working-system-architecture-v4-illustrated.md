# Working System Architecture v4 — Illustrated Walkthrough
### Every chapter is one scenario, run with real numbers. All people/companies/tweets are fictional.

**Companion to:** `working-system-architecture-v4.md` — same system, now watching it work. Numbers are internally consistent across chapters (the same tweet, the same accounts, the same costs appear again and again). Units: EVI = weighted engagement score per hour; z = (EVI − author baseline mean) / σ_eff.

---

# CHAPTER 1 — The Radar: one tweet, from cold start to calibration

## 1.1 Setup: the project and its watchlist

Project **ClipDeck** (AI tool: long-form YouTube → faceless Shorts/TikToks, auto-published). Its intake template (Chapter 2) auto-generates this radar watchlist:

```
WATCHLIST "ClipDeck" (55 items, created 2026-08-19)
  CRITICAL (official X API, ≤30):
    @marcreyes      creator/competitor   (200K followers, builds faceless tools)
    @jennahq        target influencer    (90K, video-ops content)
    @clipbot9000    competitor tool      (12K)
  MEDIUM (wide net, scraping provider):
    @videobrother, @reelskate, @facelessfan, @contentcowboy ... (37 accounts)
  KEYWORD STREAMS (2):
    "faceless automation", "shorts repurposing"
  SOUNDS (TikTok, 15):
    aurora_bass_2026, retro_piano_loop ... 
```

## 1.2 Cold start (weeks 1–2): no alerts, only baselines

Per design rule #3, the system crawls and refuses to alert until baselines exist. The dashboard week 1:

```
BASELINE COVERAGE — 2026-08-26
  @marcreyes     30/30 posts   mean EVI 38  σ 15   follower 200,042 ✓
  @jennahq       30/30         mean EVI 22  σ 9    follower 91,150   ✓
  @clipbot9000   27/30         mean EVI 12  σ 6    follower 12,008   ✓ (3 posts too
  ...                                                                   new to count)
  55 watchlist → 51 baselines complete, 4 pending (new accounts)
  ALERTS DISABLED: 4 of 55 authors lack baselines. Estimated completion: 4 days.
```

The 4 new accounts get the **velocity-floor trigger** (10 likes in 5 min) instead of z-scoring until baselines exist — and every alert they produce is labeled `UNTRUSTED — no baseline`.

## 1.3 Tuesday 09:00 — the breakout tweet

`@marcreyes` posts at 09:00:

> "Nobody talks about what it actually costs to run 40 faceless accounts. Let's do the math. 🧵"

Scoring worker snapshots (min-Δt guard: no scoring before t=10 min; EMA smoothing, 80-min time constant):

| t | likes | replies | RTs | quotes | shares | author_replies | ΔS (window) | raw EVI /h | smoothed EVI | z | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 min | 20 | 3 | 2 | 0 | 0 | 0 | — | — | — | — | below min-Δt, **not scored** (the spec's t=5 variance explosion, prevented) |
| 10 min | 60 | 12 | 8 | 3 | 2 | 0 | 117 | 702 | 82.5 | **2.97** | **ALERT FIRES** (z ≥ 2.5, within 60 min) at 09:10 |
| 30 min | 300 | 85 | 120 | 40 | 30 | 1 | 838 | 2,514 | 620 | 38.8 | author replied to a commenter @ 09:28 → `author_reply_back` trigger; alert card upgraded |
| 60 min | 1,150 | 420 | 700 | 210 | 140 | 4 | 3,750 | 9,000* | 1,599 | 104 | post is compounding; next snapshot 09:35 already queued for the reply |

\* window EVI at t=60; cumulative EVI = 5,005. Where ΔS at t=10 = 5.0(12) + 5.0(3) + 2.0(2) + 1.0(8) + 0.5(60) = **117** — the Aug-13-2026 production weights from `param.rs` (replies 5.0, quotes 5.0, shares 2.0, reposts 1.0, likes 0.5; bookmarks & profile clicks no longer weighted; author-reply is a qualitative trigger, not a 75× term).

## 1.4 The alert card (Slack, 09:10)

```json
{
  "alert_id": 4123,
  "card_ts": "2026-08-26T09:10:03Z",
  "platform": "x",
  "project": "ClipDeck",
  "author": "@marcreyes",
  "post_age_min": 10,
  "text": "Nobody talks about what it actually costs to run 40 faceless accounts. Let's do the math. 🧵",
  "url": "https://x.com/marcreyes/status/4123...",
  "score": {"raw_evi": 702, "smoothed_evi": 82.5, "z": 2.97},
  "signals": ["z_score"],
  "params_version": 5,
  "threshold_status": "UNCALIBRATED — treat as signal, not gospel",
  "dedup_cluster": null,
  "actions": [{"label": "Replied", "value": "replied"}, {"label": "Skipped", "value": "skipped"}, {"label": "Noted", "value": "noted"}]
}
```

At 09:28 the `author_reply_back` trigger fires: the card updates in place (same alert id), adds `"signals": ["z_score","author_reply_back"]` — the author is actively in the thread, which is now a *conversation* signal (the Aug-2026 algorithm only boosts author-replies by +15 for mutually-following viewers, so the radar treats it as a quality trigger rather than a 75× constant). **This upgrade is why the design tracks author replies as a first-class metric** — the raw numbers (300 likes by t=30) look like a nice post; the author being in the thread is the tell that it will compound.

## 1.5 The action loop (the part neither source document had)

- **09:35** — you reply (human, not automated): *"40 accounts is wild — what's your per-account break-even? We built ClipDeck to get this to 1 operator."* → `alert_actions` row: `(4123, 09:35, 'replied', text, reply_id)`.
- **30-day outcome (09/25)** — measured automatically:

```json
{"reply_engagement": 62,
 "author_replied_back": true,
 "post_reach_vs_author_median": 4.2,
 "became_viral": true,
 "value_flag": true}
```

`value_flag = TRUE`: the reply gained engagement AND the author replied back. This becomes one labeled training point for calibration. The reply also did its job — the author replied *to you*, which is the 75× event, now on *your* post.

## 1.6 Dedup: the format flood

Wednesday, 14 accounts (7 on watchlist) post "Nobody talks about X" riffs within 24h. SimHash fingerprints collapse 14 posts into **one** alert card:

```
FORMAT FLOOD — cluster #77 ("nobody talks about [cost]")
  14 posts, 7 on watchlist, 24h window
  members: @marcreyes (z 2.97 at alert, later 38.8 — original), @reelskate (z 2.1), @contentcowboy (z 1.6) ...
  action: reply to highest-z member only; flag format for swipe file
```

Without this, that's 14 Slack pings for one format — the exact alert-fatigue failure the spec's vector-dedup idea was for, solved here with a hash and a config line instead of Qdrant.

## 1.7 The false positive: the engagement pod

`@cryptokid99` (not on watchlist — caught by the "faceless automation" keyword stream) posts a giveaway. Snapshot at t=5 min: 12 likes, 0 replies, 0 bookmarks. **Velocity-floor trigger fires** (10 likes/5min, the only trigger available to a no-baseline author):

- Alert #4217, 09:47. You skip it (crypto giveaway, obvious).
- 30-day outcome: +3 likes total, no replies, reach ≈ author median. `value_flag = FALSE`.

Pods are why the floor trigger is `UNCALIBRATED` — and why calibration exists. By the October calibration run it has the data to act (Chapter 1.9).

## 1.8 TikTok: the sound spike (different signal, same loop)

`aurora_bass_2026` is tracked as a watchlist item. Thursday, the sound worker sees:

```
SOUND SPIKE — aurora_bass_2026
  cohort median: 40 new videos / 3h
  observed:      128 new videos / 3h   (3.2× cohort median)
  top rising: @soundkid_99 (41K views), @clipdeckshopper (12K), @facelessfan (8K)
```

One card, 09:12. Action: you check the top 3 rising accounts — one is a perfect ClipDeck use case → added to the **ICP watchlist** (Chapter 3). The sound itself goes into the swipe file as a format to ride. This is the cheapest signal in the system: no video analysis, just counts — and it catches the wave *before* the format peaks, which post-hoc trend boards can't.

## 1.9 Calibration run #1 (October 5 — after 137 resolved alerts)

The harness scores every acted alert against its 30-day outcome:

```
PRECISION/RECALL FIT — project ClipDeck, params_version 2 → candidate 3
  total alerts resolved:   137
  acted:                   61      (44%)
  value_flag TRUE:         27      → precision 44%
  missed virality (recall sweep): 11 posts crossed 10× author median without alerting;
                                  7 were alerted → recall 64% on watchlist population

  z-threshold grid search (precision, recall):
    z ≥ 2.0:  prec 38%, recall 71%
    z ≥ 2.5:  prec 44%, recall 64%   ← current
    z ≥ 3.0:  prec 57%, recall 55%
    z ≥ 3.5:  prec 61%, recall 41%
  → deploy z ≥ 3.0 (max precision with recall ≥ 50%); floor trigger analysis:
    floor alerts: 41 total, 3 valuable → 7% precision
    → floor threshold raised 10 → 25 likes/5min for accounts WITH baselines;
      kept at 10 for baseline-less authors only
  author_reply_back as standalone trigger: 19 fires, 17 valuable → 89% precision
    → promoted to TRUSTED trigger, kept at 75× weight
```

New `param_versions` row: `z.threshold = 3.0, status = calibrated, precision 57%, recall 55%`. From now on alerts say `TRUSTED` — but only for this project, only until the next fit. The spec's "Z ≥ 2.5" was a hope; this is a measurement.

## 1.10 Two drills: the miss and the vendor death

**The miss.** `@newcreator99` (not on watchlist) posts a thread that reaches 40× their median — only discovered in the weekly keyword sweep. Recall miss logged → the sweeper auto-suggests `@newcreator99` for the wide net (rule: any author with 3 keyword-stream hits in 30 days gets added). Watchlist is a living system, not a config file.

**Vendor death.** Tuesday 09:00–09:40, SocialData.tools (X wide-net provider) times out. Provider health: 3 consecutive failures → Slack page at 09:24 → automatic failover to ScrapeCreators X endpoints. 61 snapshots re-synced with `source_provider = 'scrapecreators'`. Cost meter shows the failover window cost $0.23. SocialData marked `DEGRADED`; the next weekly recon re-evaluates it (remember: Black Magic, Shield, Zopto, SwipeInsight, Xpoz, Twend all died in the last 12 months — this drill is not hypothetical).

---

# CHAPTER 2 — The ICP Engine: one project, intake to closed-won

## 2.1 Intake template (15 minutes, filled for real)

```
PROJECT: ClipDeck
1. One-liner: AI tool that turns long-form YouTube into faceless Shorts/TikToks and auto-publishes on schedule
2. Problem / who feels it: solo operators and small agencies drowning in manual faceless-channel ops
3. Seeds: Faceless.video users, Argil users, 2 agencies known to run 10+ faceless accounts
4. Competitors/adjacent: Faceless.video, FacelessReels, Argil, OpusClip, Creatify
5. Filters: 1–200 employees; anywhere; B2B or creator-econ; any funding; revenue ≥ $0
6. Buying committee: economic = founder/CEO (solo ops); champion = head of content / ops lead;
   evaluator = video editor; blocker = "we tried AI video, it looked bad" (usually the founder)
7. Triggers: job post "video ops" / "content ops"; hiring a "TikTok manager"; RB2B visits to clipdeck.ai;
   accounts that post faceless content at 5+ videos/day
8. Success metric: deal ≥ $50/mo, >3 months retained, or agency contract ≥ $500/mo
```

## 2.2 Discovery — Exa Websets (not a rebuilt vector DB; the red-team fix in action)

Query: *"companies and creators operating automated faceless social media accounts; AI-generated short-form video; video repurposing tool users; agencies managing creator accounts"* + 4 seed domains. Output: **142 candidates**, each with a natural-language reason. Five rows:

| Domain | Why surfaced | Est. size | Region |
|---|---|---|---|
| facelessstudio.io | "AI-generated content operation, 40+ TikTok accounts, affiliate program" | 1–10 | US |
| motionagency.io | "agency offering 'done-for-you faceless content' retainers" | 11–50 | UK |
| loopmedia.co | "faceless channel farm, 12 accounts, productized service" | 1–10 | US |
| quickclips.ai | "AI clips tool — sells to the same creators (adjacent, not customer)" | 11–50 | DE |
| soundkillerz.app | "audio licensing for faceless channels — adjacent market" | 1–10 | BR |

## 2.3 The hard-filter gate (zero spend on garbage — local code, no Clay credits burned)

142 → **87 accounts**: drops include 3 "companies" that are parked domains, 2 podcast networks (wrong segment), 11 creator-adjacent tools (competitors, moved to a separate list), 31 micro-accounts below the 1-employee/10K-follower floor.

## 2.4 Waterfall with the verification gate (the fix, in action)

The v4 change: cascade on **verification failure**, not on "first provider returned something."

**Case A — motionagency.io:** Apollo returns `john@motionagency.io` → ZeroBounce gate: `undeliverable/risky` → **result rejected, cascade continues** → Cognism returns `john@motionagency.io` (deliverable) → **accepted, cascade stops**. Under the spec's original design, Apollo's unverified email would have been accepted and John would have been emailed into the void.

**Case B — quickclips.ai:** Apollo returns `sara@quickclips.ai` → ZeroBounce: `deliverable` → **accepted**. One provider, one gate pass, $0.02 total.

Gate stats after the run: 87 accounts, 203 email attempts, 71 verified contacts, cascade triggered on 19 (11 rescued by provider B, 6 by C, 2 dropped as uncontactable).

## 2.5 The Fit×Intent matrix (thresholds from the constants table, pending calibration)

| Account | Fit | Intent | Tier | Routing |
|---|---|---|---|---|
| facelessstudio.io | 88 | 76 | **T1** | personalized outbound (human + AI draft) |
| motionagency.io | 84 | 58 | T2 | content nurture + LinkedIn warmth |
| loopmedia.co | 81 | 41 | T2 | nurture (posted 5 videos/day — set radar watch) |
| clipops.agency | 78 | 66 | T2→watch | close to T1; radar watchlist added |
| soundkillerz.app | 64 | 35 | T2-low | nurture, low priority |
| quickclips.ai | 36 | 82 | **T3** | 2-line manual test — **no ad spend** (red-team fix: an email costs $0; a retargeting test costs $500 and tests the wrong hypothesis) |
| datasilo-corp | 28 | 12 | **DQ** | dropped (fit < 50) |

18 of 87 land T1/T2 for outbound this month; the rest are T2-low/T3/DQ. Fit axis: firmographic + technographic + the buying-committee hypothesis. Intent axis: §2.7 signals with 30-day freshness decay.

## 2.6 The persona brief — $0.50 budget, spent once, only for T1/T2

For **facelessstudio.io** (the $0.50/account cap is enforced — this is the red-team fix for unbounded LLM cost):

```json
{"account": "facelessstudio.io",
 "budget_spent_usd": 0.42,
 "sources": ["careers page (2 posts, both >14 days old — ghost-posting filter applied)", "about page", "2 press mentions"],
 "roles": {
   "economic_buyer": "Founder/CEO (solo; runs the affiliate program personally)",
   "champion": "Content Ops Lead (job post: 'manage 30+ TikTok accounts, growth focus')",
   "evaluator": "Video editor (existing tools: CapCut, OpusClip, manual scheduling)",
   "blocker": "Founder history: tried AI video in 2025, 'quality was bad' (their own tweet, Oct 2025)"
 },
 "pain_notes": "Job post says 'churning 30+ accounts manually is unsustainable'; explicit ask for automation.",
 "openings": ["Mention per-account cost math (their CEO tweets about it — see radar alert 4123)"],
 "next_step": "AI SDR draft → human approval → send"}
```

## 2.7 Signals move accounts (the overlay, live)

- **RB2B:** `motionagency.io` — 3 visits to clipdeck.ai this week, 2 people identified (CTO + content lead). Intent 58 → **73** → moves T2 → **T1**, outbound queue. (Free tier: 150 resolutions/mo — this used 2.)
- **Hiring signal:** facelessstudio.io posts "Video Operations Lead" → intent 76 → **84**. Already T1; this just re-orders the queue.
- **Funding signal:** loopmedia.co closes a small pre-seed (news sweep) → intent 41 → 52. Still T2; the radar now watches their content (Chapter 3).

## 2.8 Closed loop, phase 2 (only now — after volume, per the playbook's demotion that the red team upheld)

Month 6 report: **18 closed-won** across ClipDeck projects:

| Tier | Count | Win rate | Verdict |
|---|---|---|---|
| T1 | 9 / 41 | 22% | keep — healthy |
| T2 | 6 / 63 | 9.5% | nurture is working slowly; keep |
| T3 | 3 / 74 | 4% | test pathway nearly useless → **demote T3 to nurture** |
| DQ | 0 / 31 | 0% | correct |

Fitted thresholds for this project: `fit ≥ 82` (was 80), `intent ≥ 70` (unchanged), T3 retired. And the 18 closed-won domains go into the **vector centroid** → Websets seed list refresh → next project's discovery starts from a sharper center. The tabular loop (win rates → thresholds) works before the vector loop exists — that ordering is the design.

---

# CHAPTER 3 — The compounding loop (radar ↔ ICP)

The thing neither source document had, demonstrated:

1. **ICP → radar.** 4 T1/T2 accounts (`facelessstudio.io`, `motionagency.io`, `clipops.agency`, `loopmedia.co`) were auto-added to the ClipDeck radar watchlist as `target_customer` entities, from the §2.5 matrix.
2. **Radar → ICP.** Thursday: `loopmedia.co`'s "How we run 12 faceless channels for $0/mo" post spikes — z 4.8, author replies twice. The radar alert carries `intent bump +15` → loopmedia.co intent 52 → **67** (approaching T1).
3. **Result:** your outbound for loopmedia.co now starts with *"saw your post on running 12 channels — here's the cost math you published, here's where ClipDeck changes it"* — a reply-guy entry that already proved itself in the 30-day outcome (Chapter 1.5). Warm, not cold. **The radar's alerts are also the ICP engine's intent data — one crawl, two systems.**

---

# CHAPTER 4 — Ops drills (the boring 10% that keeps it alive)

## 4.1 Cost meter, one week (real numbers)

```
DATA COST — week of 2026-09-01
  youtube official        $0.00   (quota-free tier)
  x official (30 critical) $38.21  (11,466 reads × $0.005)
  x scrapecreators (wide)  $7.84   (≈ 4,700 requests, cached results 61% free)
  bluesky atprotocol       $0.00
  tiktok sound worker      $3.12
  exa websets              $9.40   (1,344 searches)
  zero bounce              $4.10   (205 verifications)
  TOTAL                    $62.67  (cap: $75/day none hit; monthly pace ≈ $271 — under §7 budget)
```

## 4.2 Weekly recon checklist (calendar-blocked, 30 min)

- [ ] Re-check the dead-vendor list (Black Magic, Shield, Zopto, SwipeInsight, Xpoz, Twend, TrendPop — any new names?)
- [ ] `provider_logs` — any DEGRADED flag? (SocialData.tools in §1.10)
- [ ] Parameter expiry scan: 2 params hit calibration due-date → extended with `pending` re-labeled
- [ ] Watchlist hygiene: 5 stale entries auto-suspended → review queue

---

# CHAPTER 5 — The constants table: before vs. after 6 months

| # | Parameter | v0 (August) | v1 (February, fitted) | How it got there |
|---|---|---|---|---|
| 1 | x_weights.like | 0.5 | unchanged | provenance — survived both releases |
| 2 | x_weights.retweet | 1.0 | unchanged | provenance — survived both releases |
| 3 | x_weights.reply | 13.5 → **5.0** | unchanged since | replaced by primary source (xai-org/x-algorithm, Aug 13 2026) |
| 4 | x_weights.quote | (new) 5.0 | unchanged | provenance — released in 2026 config |
| 5 | x_weights.share | (new) 2.0 | unchanged | provenance — released in 2026 config |
| 6 | x_weights.bookmark / profile_click | 10 / 12 → **removed** | — | zeroed in 2026 config; bookmarks now only a dwell-regret-gate feature |
| 7 | decay.half_life 80 min | sourced (arXiv) | unchanged | provenance; x-algorithm AgeFilter adds a hard 48h cutoff |
| 8 | z.threshold | 2.5 → **3.0** | calibrated | precision/recall fit, §1.9 |
| 9 | velocity floor 10 likes/5min | → 25 (baselined authors) | calibrated | 7% precision, §1.9 |
| 12 | sound spike 3×/3h | → 2.5×/3h | calibrated | 11 spikes → 3 predicted formats |
| 13 | icp.fit ≥ 80 | → 82 | calibrated | win-rate fit, §2.8 |
| 14 | icp.intent ≥ 70 | unchanged | calibrated | win-rate fit, §2.8 |
| 15 | intent decay 30 days | → 45 days | calibrated | T2 conversions at day 30–40 |
| 16 | persona $0.50/account | unchanged | sourced (guard) | never hit the cap |

Seven months in: the **method** (provenance + calibration) held perfectly — and it got its hardest test when xAI replaced five of the six sourced weights overnight on Aug 13, 2026. The system didn't break: the constants table changed, the alert cards re-labeled their params_version, and calibration restarted from the new baseline. The calibrated parameters (rows 8–16) were fitted on *outcomes*, so they were unaffected by the weight change. **That asymmetry is the entire point of the architecture** — and the exact thing the playbook and the spec could not do, because neither of them had a primary source to anchor to or an outcome loop to learn from.

---

*Fictional entities: all tweets, accounts, companies, and numbers in this walkthrough are illustrative. The architecture, the corrections, and the costs are real.*
