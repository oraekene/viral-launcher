# Parked notes

Work deliberately not being done, with the reason, so it never becomes
mystery scope. Accepted decisions live in `docs/adr/`; live work lives in
GitHub issues; this file is the third home: declined, conditional, or
superseded items. Reopen by filing an issue that references the entry.

## P-001: Full-tree code review skipped (declined 2026-09-09)
Offered before Phase 4 as a redundancy check over `origin/main...HEAD`.
Declined: every diff since the teardown has had two-axis review
(Standards + Spec) before commit, full suite green throughout, so a
whole-tree pass was judged low-value. Reopen if a change lands without
per-diff review.

## P-002: Single global viral flag rejected (declined 2026-09-09)

Any one fixed number (raw z ≥ 2.5, 100k likes, 500k views) as the
cross-voice definition of viral. Declined: heavy-tailed engagement makes
fixed bars meaningless across voices (a 43× median peak under 1k
followers vs ~15× at 100k–1M), and 2023-fitted constants were tuned under
a retired ranking regime. Replaced by the three-slot per-voice rule
(ADR-0009). Reopen only with per-voice evidence for a global value.
