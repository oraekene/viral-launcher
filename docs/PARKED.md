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
