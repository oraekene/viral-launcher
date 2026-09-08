# ADR-0007: Per-Voice Viral Threshold with a House Default

Status: accepted (2026-09-05).

## Context

Q2 of the owner questionnaire ("what do you call a viral post?") was never
answered, so the value 2.5 currently does triple duty everywhere: synthetic
flag rule, `z.trigger` default, and calibration search seed. Under
ADR-0001 (one project per voice) no single number can mean "viral" across
voices with different audience sizes and variances.

## Decision

1. Keep 2.5 as the house default, explicitly marked assumed/pending, so
   new voices score from day one.
2. Add a per-voice threshold override, set at voice onboarding (a z
   threshold or a reach multiple), stored per project, read everywhere the
   global 2.5 is read today.
3. Calibration keeps refitting the trigger per voice from outcomes, so the
   declared number converges to the measured one (declaration is the prior,
   refit is the posterior).

## Consequences

- Small ticket: per-project threshold param + onboarding/CLI surface +
  read-path swap; no model or calibration redesign (refit already lands
  per project as `calibrated_z_trigger`).
- Research backlog: replace the 2.5 house default with a literature-backed
  value (see virality research note).
