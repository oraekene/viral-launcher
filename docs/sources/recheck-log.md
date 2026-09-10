# Upstream recheck log (#7, recurring)

Production weights move without notice (xAI syncs `param.rs` defaults
from a config system, and experiments can serve other values), so this
log records each re-read: what was checked, what changed, what did not.
A drift is a copy update, never a redesign. Suggested cadence: monthly,
or whenever launcher scores visibly disagree with served outcomes.

## 2026-09-10

- `home-mixer/params/param.rs` (xai-org/x-algorithm, head branch):
  ReplyWeight 5.0, FavoriteWeight 0.5, ReportWeight -234.0, all
  unchanged against the seeded `assumed` values. No copy update needed.
- Nuance confirmed from the repo README and third-party read-through:
  weights scale predicted per-viewer action probabilities, not raw
  engagement counts, so the launcher's weight-times-counts math stays
  what it always claimed to be: an elicitation proxy, not production
  arithmetic. No redesign; the `assumed` markings stand.
- A `weighted_scorer.rs` (PhoenixScores-based) path exists alongside the
  probability-weight path; no evidence of a value-model flip that would
  obsolete the interim proxy was found in this pass. A full mode audit
  means reading the repo, not the highlights; scheduled for a later pass.
- Half-life excerpt vendored at
  `docs/sources/2302.09654-half-life-excerpt.md`; `half_life.minutes`
  provenance now cites it. No other cited source lacks vendored evidence.
- Next recheck due: 2026-10-10.
