# 03 — Predictor v0 (train, score, swap in)

**What to build:** A per-project predictive model trains on the radar's own outcome data — posts the radar alerted on joined with their 30-day outcomes (z at t=60, value flag) — using pre-publish-observable features only (text, hook type, thread length, media, link count, time, author state, trailing performance, format similarity to past alerted posts). Each project gets a model once it has at least 200 labeled events. The operator sees a held-out precision/recall report and the feature importances that explain what actually drives predicted velocity. Once a model exists for a project, the Rewriter's ranking switches from gate-score to predictor score.

**Blocked by:** 01 — Launcher skeleton + Gate; 02 — Rewriter loop. External edge: the radar's outcome pipeline must have accumulated ≥200 labeled events (radar build + collection per the architecture doc).

**Status:** ready-for-human

- [x] A model trains per project from radar outcome data and produces a score for any draft
- [x] Held-out precision/recall is computed with the same protocol as the radar's calibration harness
- [x] Feature importances are persisted and displayed
- [x] Models report calibration status (sourced / pending / calibrated); uncalibrated models are visibly flagged
- [x] Rewriter ranking uses predictor scores once a project has a model, falling back to gate score otherwise

## Comments

Implemented in repo `viral-launcher` (commit after 01a2b0c). Canonical 17-feature pre-publish vector shared by training and scoring. GradientBoostingRegressor, 80/20 holdout precision/recall at `z.trigger`, residual-std band width, artifact + importances persisted in `predictor_models`. Rewriter ranking switches to predicted z per project automatically.

Caveat honored from the ticket's external edge: real radar outcome data does not exist yet, so v0 trains on `SyntheticOutcomeSource` — a deterministic correlated corpus that proves the pipeline end to end. Metrics on synthetic data say nothing about real-world quality. The swap point is `RadarOutcomeSource.load_outcomes`, which raises NotImplementedError until the radar exposes alert_events x action_outcomes mapped into the canonical feature schema; training via API returns 501 for source=radar until then.
