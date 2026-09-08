# ADR-0001: Calibration Is Partitioned per Voice, Not per User

Status: accepted (2026-09-05, supersedes the "project = user" phrasing).

## Context

Users of the X automation tool always run multiple voices (accounts with
distinct audiences). A model trained on blended voices would learn an
average audience that resembles none of them.

## Decision

A launcher `project_id` maps 1:1 to a single voice (one X account's posts).
A Worker user owns many projects, one per voice. The shared layer (gate
weights, half-life, costs) stays global assumptions; the learning layer
(predictor models, `calibrated_z_trigger`, winner shares) is per project.

## Consequences

- Per-voice models stay sharp; cross-voice pollution is impossible by
  construction, not by discipline.
- The Worker must pass voice identity (account) alongside user identity
  when staging outcomes, so rows land in the right project.
- Cost: projects proliferate (voices × users); each needs ≥100 rows to
  calibrate and ≥200 to retrain, so thin voices stay synthetic-backed.
