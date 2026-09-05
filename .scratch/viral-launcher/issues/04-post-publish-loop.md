# 04 — Post-Publish Loop + protocols

**What to build:** After the operator launches a post, the Launcher snapshots it at t=10 minutes via the radar's own-account variant and compares the actual z against the Predictor's predicted band. Below the band → a double-down protocol card (self-reply suggestion, early-commenter engagement checklist, quote the post). Above the band → an escalate card (thread follow-up). Each card logs the intervention taken so the 30-day outcome loop can measure it. All interventions are human-paced — the system suggests, the operator acts.

**Blocked by:** 03 — Predictor v0. External edge: the radar's own-account variant snapshot pipeline must exist (radar build per the architecture doc).

**Status:** ready-for-human

- [x] A launched post appears in the Launcher with a t=10 snapshot and actual z
- [x] Below-band posts produce a double-down card; above-band posts produce an escalate card
- [x] Predicted band comes from the Predictor's prediction interval, not a fixed heuristic
- [x] Every card's intervention choice is logged to the outcome flow with the post's identity
- [x] No step of the protocol posts, replies, or quotes automatically

## Comments

Implemented in repo `viral-launcher`. Launch captures predicted z + band (predictor interval when an active model exists for the project; interim score with `band.interim_width` param otherwise, honestly labeled `scorer=interim`). Protocol evaluation is isolated in the launches module so the radar's own-account variant can call it directly when built.

Deviation honored from the external edge: t=10 snapshots are manual entry (`POST /launches/{id}/snapshot`) until the radar own-account pipeline exists; one snapshot per launch, repeat returns 409. Interventions are operator-logged only — nothing posts automatically.
