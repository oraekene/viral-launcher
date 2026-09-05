# 05 — Launcher calibration + action-loop closure

**What to build:** The Launcher's own decisions become calibrated, not asserted. Every gate threshold and predictor hyperparameter lives in the shared param namespace and flips from pending to calibrated as 30-day outcomes accumulate through the action loop. Gate thresholds re-fit from launcher outcomes (vetoes that later produced winners are relaxed; passes that produced negative outcomes are tightened), and the Predictor retrains monthly or when the outcome distribution drifts. The operator sees each rule's calibration status and last-fit date.

**Blocked by:** 04 — Post-Publish Loop + protocols. External edge: the radar's action loop must be running so launcher outcomes flow through the same 30-day outcome pipeline (radar build per the architecture doc).

**Status:** ready-for-human

- [x] Gate thresholds and predictor parameters re-fit from launcher outcome events
- [x] Parameters flip sourced → pending → calibrated as evidence accumulates, visible per rule
- [x] Predictor retrains monthly or on >20% outcome-distribution drift, with the trigger logged
- [x] A veto that historically blocked a winner is flagged for review, not silently kept
- [ ] Calibration runs on the same outcome pipeline as the radar's calibration harness

## Comments

2026-08-23: Mechanism implemented in repo `viral-launcher` (b67229d + review fixes 82c1946), reversing the earlier "nothing to implement yet" note — same pattern as ticket 03: build the machinery, prove it on synthetic streams, keep production statuses honest.

Post-review correction: the refit threshold is per-project. It lands as `calibrated_z_trigger` on the project's active model and never mutates the global `z.trigger` param (calibrating one niche must not rescore another). Only staged/real outcome sources flip a model's status to `calibrated`; synthetic runs report refits but write nothing. Vetoes that fired on eventual winners are flagged for human review, never auto-disabled. Predictor retrains on >20% relative winner-share drift or 30-day age.

Caveats: outcomes come from staging (`POST /outcomes/import`) until the radar action loop connects; `calibrated` therefore means "calibrated against that source". Last AC (same pipeline as the radar harness) stays open until that connection exists.

Caveats: outcomes come from SyntheticLauncherOutcomeSource until the radar action loop connects (`source=radar` returns 501); calibrated status therefore means "calibrated against this source" — swap the adapter and re-run when real outcomes flow. Last AC stays open until that connection exists. Also corrected ticket 06's over-ticked format-similarity checkbox in the same session.
