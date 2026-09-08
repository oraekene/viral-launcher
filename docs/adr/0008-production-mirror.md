# ADR-0008: Production Values Mirrored, Experiments Acknowledged

Status: accepted (2026-09-05).

## Context

The xAI x-algorithm repository (read 2026-09: `home-mixer/params/param.rs`,
`home-mixer/scorers/ranking_scorer.rs`, bidirectional-boost change doc)
confirms all 16 seeded constants exactly, but corrects three mechanisms
(cold start keys off impressions, the +15 needs mutual originals, OON
discount also hits in-network replies) and documents weight semantics
(weights scale predicted probabilities, never counts) plus a config system
under active experimentation.

## Decision

1. Rule copy corrected to the verified mechanics; new elicitation rules
   for DM/copy-link shares and follows (with a bait-vs-genuine
   distinction); dwell-time scoring stays qualitative — no honest
   pre-publish proxy for seconds-of-dwell exists, and fabricating one
   repeats the failure the red-team report convicted.
2. `assumed` statuses now cite the specific param path and read date, and
   additionally cite config-drift (experiments can move production values
   without notice), not just missing vendoring.
3. 2023-fitted virality constants (Elmas thresholds et al.) are never
   installed: method travels (relative-to-self, log scale), numbers do
   not, because they were fitted under a retired ranking regime.

## Consequences

- Recheck seeded values against upstream on a cadence; any drift is a
  copy update, never a redesign (tunables-over-facts, as before).
- The interim scorer remains an elicitation-surface proxy, explicitly
  not a rank predictor: production scores Σw·P(action) plus offsets,
  diversity, cold-start, and DPP reranking, none of which a pre-publish
  heuristic can reproduce.
