# ADR-0009: Research-Backed Viral Flag Shape

Status: accepted (2026-09-09).

## Context

Q2's house default (raw z ≥ 2.5) is statistically naïve on heavy-tailed
engagement data. A literature pass (Elmas et al. ACM 2023 on Twitter's own
Viral Tweets labels; Garimella hot streaks; Hasan micro-viral; Polito
trailing-100 boxplot rule; Dartmouth log-engagement thesis; 2026
playersells 70k-account measurement: median best post 22.65× own median)
plus the current x-algorithm source (per-viewer probabilities, retired
HeavyRanker regime) converge on one shape with three slots.

## Decision

A voice's viral flag takes three independently-built slots:

1. Absolute floor per voice (Hasan-style): blocks tiny-denominator fake
   virality where a raw multiple explodes on near-zero baselines.
2. Relative anomaly on a trailing window (top ~5% of trailing 100,
   Polito α≈2 style): distribution-free, per-voice by construction.
3. Log-scale engagement in z computation (Dartmouth/log-Elmas style):
   z-scores regain meaning once the tail is de-tailed.

2023-fitted constants (Elmas 2.16/0.772 et al.) are never installed
(ADR-0008): method travels, numbers do not, because they were fitted
under a retired ranking regime. Calibration refit remains the
convergence mechanism per ADR-0007.

## Consequences

- Three build tickets (floor, trailing window, log scale), each testable
  alone, composable into the flag rule.
- The rejected alternative — one global fixed flag — is parked (P-002).
