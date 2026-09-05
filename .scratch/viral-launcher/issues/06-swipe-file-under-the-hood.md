# 06 — Swipe-file + Under-the-Hood integration

**What to build:** Launched posts that clear the operator's virality threshold are archived as swatches in the radar's swipe file with the winning variant's text and gate report, so they become format templates for future drafts. The format-similarity feature of the Predictor consumes this archive. Separately, a periodic check reads the operator's "Under the Hood" visibility labels (when available on the account) and surfaces a warning in the Launcher when an account-level label may be limiting reach, so the operator knows whether to invest in a post at all.

**Blocked by:** 04 — Post-Publish Loop + protocols.

**Status:** ready-for-human

- [x] A winner can be archived as a swatch with its text, gate report, and predicted-vs-actual z
- [x] Swatches are queryable as formats and feed the Predictor's format-similarity feature
- [ ] The periodic label check runs without per-draft cost and reports account-level labels in the Launcher
- [x] A labeled account sees a warning before scoring drafts, with the label name and its published meaning
- [x] Archive operations never alter radar alert records

## Comments

Swipe-file half implemented in repo `viral-launcher`: `POST /swatches` archives a winner from its own gate report or a ranked variant (score_kind records predictor vs interim), `GET /swatches?project_id=` lists formats per project.

Format-similarity half implemented (Edge A): token-Jaccard similarity against archived swatches joined the canonical feature vector as `swatch_similarity` (predictor v2); v1 artifacts keep scoring via per-artifact feature-name mapping; rewriter reasons surface the similarity score.

Under-the-Hood half: account_labels store with 30-day freshness, manual entry via POST/GET /labels, and fresh labels surface as warnings on every draft create/fetch (Edge C). Remaining gap: the X fetcher itself needs pilot access — entry stays manual until then; and the check currently runs per-draft rather than as a periodic job (same information, zero cost either way).
