# ADR-0002: Real Exports Upgrade One Project Only and Cannot Damage Others

Status: accepted (2026-09-05).

## Context

The operator holds a historical tweet export and feared that staging it
could damage calibration quality, either for their own voices or others'.

## Decision

Staged imports are namespaced by project and only ever affect that
project's model and trigger. The synthetic corpus remains the fallback for
every project without real data. Small or poor exports fail loudly
(`insufficient evidence` below 100 rows; precision/recall printed on the
model) instead of silently degrading anything.

## Consequences

- Importing a personal export is always safe to try; worst case is a
  visibly poor model for that voice, fixed by adding rows.
- No global weight is ever mutated by calibration (see Phase 0 fix:
  per-project `calibrated_z_trigger`, global `z.trigger` untouched).
