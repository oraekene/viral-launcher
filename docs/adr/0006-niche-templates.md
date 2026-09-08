# ADR-0006: Named Niche Template Library for Synthetic Seeding

Status: accepted (2026-09-05).

## Context

The generic synthetic corpus teaches a plausible but arbitrary shape
(fixed share, fixed bands). Voices in different X verticals (crypto,
fitness, indie-hacking) have genuinely different winner shares and
engagement mixes, and calibrating from a wrong-shaped prior wastes the
first 100 real rows dragging the model across.

## Decision

A small library of named, versioned niche templates for X verticals,
selected by the voice owner at onboarding (one template per voice, alongside
its project). Each template pins winner share, band geometry, and veto
rates; each is covered by a test asserting its metrics. No cross-platform
metrics (TikTok/Reels/Shorts mechanics differ; spec scopes v1 to X). No
opaque on-the-spot generation: niche detection may later *recommend* a
template ("your first 20 posts look like template B — switch?"), with the
human confirming.

## Consequences

- Seeding is deterministic, reviewable, and pinned in tests — the
  provenance standard the red-team report demands.
- Templates need real niche aggregates to be worth anything; until then
  they are documented priors, still retired automatically the moment a
  voice stages ≥100 real rows (pending→calibrated lifecycle unchanged).
- Template metrics are seeded from funnel candidate aggregates (other
  people's viral posts per niche), never copied rows.
