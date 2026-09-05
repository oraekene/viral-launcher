# 01 — Launcher skeleton + Gate

**What to build:** The operator pastes a draft post into the Launcher and gets back a gate report — pass, pass-with-warnings, or vetoed — where every rule in the report names the published algorithm fact or calibrated parameter it references. The drafts, gate rules, and launcher parameter namespaces exist and are seeded from the Aug-13-2026 production weights (reply 5.0, quote 5.0, share 2.0, repost 1.0, like 0.5; negative-action vetoes; 48h freshness; new-author boost; out-of-network discount) as starting values with provenance. Negative-trigger patterns (engagement-pod signatures, mass same-text replies, link-bait with mismatched content) are hard vetoes.

**Blocked by:** None — can start immediately.

**Status:** ready-for-human

- [x] A pasted draft produces a gate report with a verdict and one line per rule, each line naming its source or calibration date
- [x] Draft and gate-rule records persist; rules can be enabled/disabled without code changes
- [x] Launcher constants live in the shared param namespace with sourced/pending/calibrated statuses
- [x] Negative-trigger patterns veto a draft; historically successful post styles pass without vetoes
- [x] The gate report is explainable enough that the operator can trace every decision to a documented fact

## Comments

Implemented in repo `viral-launcher` (commits 9b7221d, 01a2b0c). FastAPI + SQLAlchemy; SQLite default via `LAUNCHER_DATABASE_URL` (Postgres-compatible override). Params seeded from the Aug-13-2026 x-algorithm production weights as `sourced`; calibration-dependent values `pending`. Deviations: freshness is an info/warn on scheduling beyond the 48h AgeFilter window (AgeFilter governs serving, not publishing), not a veto; author diversity decay/floor surfaced as rule detail text. 64 tests, mypy --strict clean.
