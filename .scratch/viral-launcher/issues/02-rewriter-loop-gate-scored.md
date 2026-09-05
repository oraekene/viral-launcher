# 02 — Rewriter loop (gate-scored ranking)

**What to build:** The operator pastes a draft and the Rewriter generates N variants, runs every variant through the Gate, and presents the top-3 survivors ranked with a per-variant reason breakdown. Variants that trip a hard veto never appear in results. Each draft's LLM spend is metered into the shared cost dashboard with a configurable per-draft cap, and drafts can be processed in batches (e.g., a week of posts in one session). Until the Predictor lands (03), ranking uses the gate-derived score.

**Blocked by:** 01 — Launcher skeleton + Gate.

**Status:** ready-for-human

- [x] N variants are generated for a draft; vetoed variants are excluded from results
- [x] Top-3 ranked variants each show a score and a readable reason breakdown
- [x] Per-draft spend is metered and a configurable cap stops generation mid-batch when hit
- [x] A batch of drafts completes in one session with results grouped per draft
- [x] The same gate report shown for the original draft is shown for each surviving variant

## Comments

Implemented in repo `viral-launcher` (commits 52a07f9, 01a2b0c). Providers: HeuristicProvider (deterministic, offline default) and OpenAICompatProvider (any chat-completions endpoint via `LAUNCHER_LLM_API_KEY`, with top-up retry when fewer than N parse). Cap enforced on projected spend before paid calls; single rewrite over cap -> 402, batch items over cap -> per-item `error` field, request continues. Gate verdicts ride on every ranked variant (`gate_lines`). Interim scorer blends published action weights as a stand-in utility model — explicitly interim until the predictor (ticket 03) replaces it; seam isolated in scoring module.
