# System 3: The Launcher — spec

**Status:** ready-for-agent

---

## Problem Statement

The operator has a working radar (System 1) that detects posts about to blow up, and an ICP engine (System 2). But the operator is on the *creating* side too: drafts get written, posted, and mostly die silently — most posts never generate the early weighted engagement the X algorithm demonstrably rewards (replies 5.0, quotes 5.0, shares 2.0, reposts 1.0, likes 0.5 per the Aug-13-2026 published production weights), and an unlucky few trip negative actions (report −234, mute −58.8, not-interested −43.2) that damage reach.

The operator wants the same rigor the radar applies *after* posting, applied *before* posting: a system that checks a draft against what the algorithm rewards, predicts its first-hour performance, and rewrites it to maximize predicted early velocity — plus an early-response protocol for the moment it goes live. Success metric: a higher fraction of posts clear the operator's virality threshold (10× author median reach), and fewer posts die without a logged reason.

## Solution

**The Launcher is System 3: the radar, inverted.** It shares the same Postgres instance, provider abstraction, `param_versions` constants table, and cost meter. It has four parts:

1. **The Gate** — a deterministic pre-publish checklist whose rules are derived from the published algorithm weights and the calibrated parameters. No ML; every rule is a row in the gate rules table with a source or calibration date.
2. **The Predictor** — a small gradient-boosted model, trained on the radar's own outcome data (`alert_events` × `action_outcomes`), that scores a draft's predicted z at t=60. This is the moat: no tool on the market has outcome labels from the operator's own niche.
3. **The Rewriter** — an LLM generates N variants of a draft; the Gate vetoes, the Predictor scores, and the top-3 are presented with their predicted-z and a reason breakdown.
4. **The Post-Publish Loop** — the radar's own-account variant snapshots the live post at t=10; if z is below the predicted band, the double-down protocol triggers (self-reply, engage every early commenter, quote the post). Human-paced; no automation of the replying act itself.

Honest limits are encoded as first-class constraints: the system optimizes *elicitation* of weighted actions and avoidance of negative actions — it cannot control retrieval (whether Phoenix/simclusters serve the post), and it never attempts to game the published anti-spam systems (bdsm inauthentic-behavior detection, user-cred PageRank, botmaker/scarecrow labels), which are active and auditable via X's "Under the Hood" tool.

## User Stories

1. As an operator, I want to paste a draft tweet into the Launcher, so that I get a predicted-z score and a reason breakdown before I post.
2. As an operator, I want the Gate to veto drafts that would elicit negative actions (report/mute/not-interested patterns, click/dwell bait), so that I never damage my own reach.
3. As an operator, I want the Gate to report which published algorithm facts each veto or pass references, so that I can audit every decision back to a source.
4. As an operator, I want the Gate to check freshness fit (the 48h AgeFilter and ~80-minute half-life), so that I don't waste drafts outside their effective window.
5. As an operator, I want the Gate to check my author state (new-author boost eligibility ≤1,000 followers, author diversity decay), so that my posting plan respects the mechanics that apply to my account size.
6. As an operator, I want the Gate to check the reply/quote elicitation design of my draft (question, open loop, thread structure, quotable claim), so that the draft is built around the two highest-weighted actions.
7. As an operator, I want the Gate to include a network plan requirement (which mutuals engage first, leveraging the bidirectional-follow +15 boost and the ×0.75 out-of-network discount), so that follower engagement precedes stranger engagement.
8. As an operator, I want the Predictor to train on my radar's own alert outcomes, so that the score reflects my niche's actual viral events rather than generic heuristics.
9. As an operator, I want per-project predictor models, so that different niches get different scoring.
10. As an operator, I want the Predictor to report its calibration status (sourced / pending / calibrated with precision and recall), so that I know how much to trust each score.
11. As an operator, I want the Predictor to surface feature importances, so that I can see which draft properties actually drive predicted velocity.
12. As an operator, I want the Rewriter to generate N variants of my draft, so that I can choose between different framings rather than one attempt.
13. As an operator, I want the Rewriter to respect Gate vetoes, so that no variant that trips a negative-trigger rule is ever offered.
14. As an operator, I want the Rewriter to rank variants by predicted-z with a reason breakdown per variant, so that I can see why one framing beats another.
15. As an operator, I want per-draft cost metering for Rewriter LLM calls, so that the Launcher's spend stays visible in the same cost meter as the radar.
16. As an operator, I want a per-draft rewrite budget cap, so that a single draft can never blow the month's spend.
17. As an operator, I want the Post-Publish Loop to snapshot my live post at t=10 via the radar's own-account variant, so that I get a first signal within minutes of posting.
18. As an operator, I want a double-down protocol (self-reply, engage every early commenter, quote my post) when t=10 z is below the predicted band, so that I can rescue a slow start while the algorithm is still deciding.
19. As an operator, I want an escalate protocol (thread follow-up) when t=10 z is above the predicted band, so that I add fuel to an already-accelerating post.
20. As an operator, I want every post-publish intervention logged with its 30-day outcome through the existing action-loop, so that the Launcher's own rules get calibrated like everything else.
21. As an operator, I want the Launcher's thresholds and gate rules to live in `param_versions`, so that they carry provenance and calibration dates like every other constant in the system.
22. As an operator, I want the Gate to reject engagement-pod patterns and mass same-text reply patterns, so that I never get caught by the published inauthentic-behavior labeling systems.
23. As an operator, I want the Launcher to read my "Under the Hood" labels when available, so that I can see whether account-level labels are limiting my reach before I invest in a post.
24. As an operator, I want to mark a launched post as a swatch in the radar's swipe file, so that winners are archived as formats for future drafts.
25. As an operator, I want the Launcher to work for draft batches (e.g., 10 drafts at once), so that I can plan a week of posts in one session.
26. As an operator, I want to see the Launcher's monthly cost in the existing cost dashboard, so that the whole system's economics stay in one place.
27. As an operator, I want an honest-limits note on every score (retrieval not controllable, no virality guarantee), so that I never mistake a prediction for a promise.

## Implementation Decisions

### Seams (all existing — no new data sources in v1)

- **Seam 1 — Outcome data:** the Predictor trains on the radar's `alert_events` joined with `action_outcomes` (`value_flag`, measured z at t=60). No new labeling effort; the action loop already produces the ground truth.
- **Seam 2 — Constants:** all Gate rule values and Predictor hyperparameters live in `param_versions` (system = `launcher`), carrying the same sourced/pending/calibrated contract as the radar's.
- **Seam 3 — Own-account radar variant:** the Post-Publish Loop reuses the radar's own-account snapshot pipeline and provider abstraction (official X API owned reads at the reduced rate for the operator's own posts).

### Module design

- A new `launcher` module in the same service; no new workers framework, no new storage engine. Shares the existing Postgres schema namespace, cron workers, Slack routing, and cost meter.
- **Gate:** a rule engine over draft features, rules stored in a `gate_rules` table (rule id, feature expression, threshold reference into `param_versions`, verdict veto/pass/warn, source note). Rules are evaluated in order; the first veto ends evaluation, mirroring the algorithm's own filter ordering. A draft gets a gate report: vetoed / passed-with-warnings / passed.
- **Predictor:** gradient-boosted tree model (XGBoost/LightGBM class), one model per project, trained on ≥200 labeled events, retrained monthly or when the outcome distribution drifts >20%. Features are strictly pre-publish observable: text length, hook type classifier output, thread length, media presence/type, link count, question/CTA presence, time-of-day and day-of-week, author follower count band, mutual count, trailing-30-post performance, and format-similarity to past alerted posts (from the radar's swipe file). Label: z at t=60; `value_flag` as a fallback when z is missing. Feature importances are persisted and surfaced.
- **Rewriter:** LLM call generating N variants (default 10) under a per-draft budget cap; every variant passes through the Gate before scoring; the Predictor scores survivors; top-3 are ranked with predicted-z, gate verdicts, and the per-variant reason breakdown. No fine-tuned model in v1 — the predictor, not the generator, is the proprietary layer.
- **Post-Publish Loop:** after launch, the radar own-account variant snapshots at t=10; expected band comes from the Predictor's prediction interval; below band → double-down protocol card (self-reply suggestion, commenter engagement checklist, quote option); above band → escalate card (thread follow-up); all interventions logged as `alert_actions` on a launcher-owned alert so the 30-day outcome loop measures them.
- **Anti-gaming rules** are Gate rules, not advice: engagement-pod signatures (synchronized low-variance engagement), mass same-text reply patterns, and link-bait-with-mismatched-content patterns are hard vetoes. Reply volume is human-paced with a per-account daily cap.

### Schema changes

- `drafts` (id, project_id, text, gate_report, status, created_at)
- `draft_variants` (id, draft_id, text, variant_index, predictor_score, gate_verdicts, llm_cost_usd, created_at)
- `gate_rules` (id, name, feature_expression, param_reference, verdict, source_note, enabled)
- `predictor_models` (id, project_id, trained_at, n_events, precision, recall, feature_importances_json, status)
- `launch_events` (id, draft_id, post_external_id, predicted_z, predicted_band, actual_z_t10, protocol_fired, outcome_action_id)

### Cost model

- Gate: $0 (deterministic). Predictor inference: ~$0. Rewriter: LLM tokens per variant × N variants, metered per draft with a configurable cap (default $0.10/draft). Post-publish snapshots ride the existing own-account read budget. No new subscriptions.

### Platform scope

- v1: X only (complete published weights + the radar's richest data). YouTube Shorts and TikTok variants are future work with different signal sets (completion rate / V-S ratio; sound-hook design) — same four-part structure, different gate rules.

## Testing Decisions

- **What makes a good test:** external behavior only — (a) the Gate's veto/pass decisions against a labeled corpus of past radar alerts (posts that produced `value_flag = TRUE` must never be vetoed — recall floor; posts that tripped negative outcomes must be vetoed); (b) the Predictor's held-out precision/recall, measured with the same protocol as the radar's calibration harness; (c) the Rewriter's output consistency — variants are always gate-compliant and scored deterministically; (d) the Post-Publish Loop fires the correct protocol card given a t=10 z relative to the predicted band.
- **Modules tested:** gate rule engine (unit tests per rule semantics), predictor (backtest on held-out radar outcomes), rewriter integration (determinism + gate enforcement), post-publish check (reuses the radar's snapshot tests).
- **Prior art:** the radar's calibration harness (precision/recall on 30-day outcomes — the exact protocol the Predictor's quality bar inherits), the illustrated walkthrough's worked examples (the numeric scenario the Gate's initial rule values are taken from), and the existing `param_versions` sourced/pending/calibrated lifecycle.

## Out of Scope

- Guaranteeing virality or optimizing retrieval/serving (Phoenix/simclusters behavior is not controllable from the publishing side).
- Paid amplification or boost-spend optimization.
- Auto-posting, scheduling integration, or any automation of the reply act (human-paced replies only).
- Engagement pods, purchased engagement, or any pattern that maps to the published inauthentic-behavior systems — explicitly rejected by the Gate, not just discouraged.
- LinkedIn launcher (no radar outcome data exists for it yet).
- Content idea generation from scratch (input is a human draft; the Rewriter improves, doesn't invent).
- YouTube Shorts / TikTok launcher variants (future work; different signals).
- A/B testing infrastructure beyond variant ranking.

## Further Notes

- **The moat is the outcome data.** Tweet Hunter's TweetPredict, Hypefury's viral scores, and Postwise's repurposing all use generic heuristics. The Launcher's Predictor is fitted on the operator's own niche's actual viral events and 30-day outcomes — nobody else has that dataset.
- **The Aug-13-2026 weight release is the v0 constants source** (reply 5.0, quote 5.0, share 2.0, repost 1.0, like 0.5; bookmarks/profile-clicks removed; author-reply +15 bidirectional boost; OON ×0.75; author diversity ×0.5; new-author boost ≤1,000 followers; 48h AgeFilter) — as starting parameters with the same provenance contract; calibration replaces them as outcomes accumulate.
- **Relationship to the existing architecture:** System 3 extends `working-system-architecture-v4.md`; Systems 1 (radar) and 2 (ICP) are unchanged. The radar↔ICP compounding loop now has a third participant: Launcher winners become swipe-file formats, and the radar's own-account variant becomes the Launcher's post-publish loop — one pipeline, three directions.
- **External verification surface:** X's "Under the Hood" label tool (accounts with 10+ posts/month in the pilot) gives the operator a way to check whether visibility labels are interfering — worth integrating as a periodic check rather than per-draft.