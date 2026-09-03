# viral-launcher

System 3: The Launcher — the radar, inverted. Pre-publish gate, interim scoring,
and a rewriter loop for short social posts, with every decision traceable to a
published algorithm fact or a calibration parameter.

Implements tickets 01–02 of `.scratch/viral-launcher/` (spec:
`.scratch/viral-launcher/spec.md`).

## What it does

- **Gate** — deterministic rule engine over draft features. Negative-trigger
  patterns (engagement bait, mass-reply templates, pod signatures) are hard
  vetoes evaluated first; elicitation (replies weigh 5.0, quotes weigh 5.0),
  freshness (~80 min half-life), author state (new-author boost ≤1000 followers),
  and network plan (bidirectional +15 boost, out-of-network ×0.75) follow.
  Every report line names its source.
- **Rewriter** — generates N variants (heuristic provider offline, any
  OpenAI-compatible chat endpoint when `LAUNCHER_LLM_API_KEY` is set), vetoes
  non-compliant variants, ranks survivors by an interim weighted score, and
  returns the top-3 with reason breakdowns. The predictor (ticket 03) will
  replace the interim scorer once radar outcome data exists.
- **Cost metering** — per-draft budget cap (default $0.10) enforced on
  *projected* spend before any paid call; all spend lands in one ledger.

Constants live in `param_versions` with `sourced` / `assumed` / `pending` /
`calibrated` statuses. The Aug-13-2026 x-algorithm production weights are
seeded as `assumed` (primary source not vendored in-repo — verify before
citing); calibration-dependent values (`z.trigger`, cost caps) start
`pending`.

## Install

```
uv venv
uv pip install -e ".[dev]"
```

## Use

CLI:

```
launcher init
launcher gate "Like if you agree!"                  # vetoed, with sources
launcher rewrite "Draft text here." --n 5 --followers 800 --mutuals 4
launcher batch drafts.json --rewrite --n 3
launcher serve --port 8000
```

HTTP API (see `/docs` when serving):

```
POST /drafts                    paste a draft -> gate report
POST /drafts/{id}/rewrite       N variants -> top-3 ranked + reasons
GET  /drafts/{id}/variants      persisted variants incl. vetoed ones
GET  /drafts/{id}/costs         per-draft spend ledger
GET  /costs                     global summary
GET  /rules | POST /rules/{id}/toggle
GET  /params                    constants with provenance
```

Environment: `LAUNCHER_DATABASE_URL` (default `sqlite:///./launcher.db`),
`LAUNCHER_LLM_API_KEY`, `LAUNCHER_LLM_BASE_URL`, `LAUNCHER_LLM_MODEL`.

## Development

```
.venv\Scripts\python.exe -m pytest -q     # full suite
.venv\Scripts\mypy.exe src                # strict typecheck
```

## Honest limits

The gate and interim score optimize *elicitation* of weighted actions and
avoidance of negative actions. Retrieval (whether the algorithm serves the
post at all) is not controllable from the publishing side; nothing here is a
virality guarantee. Anti-gaming rules are vetoes, not advice.

## Radar-dependent status

All launcher-side edges are code-complete; only real data remains external:

- **Predictor** trains on staged radar outcomes (`POST /outcomes/import`,
  then `source=radar`) or on the deterministic synthetic corpus for dev.
  Metrics from synthetic data say nothing about real-world quality.
- **Post-publish loop** uses manual t=10 snapshot entry until the radar
  own-account variant exists; protocol evaluation is isolated so the
  radar adapter can call it directly.
- **Calibration** runs against staged outcomes via `source=radar`;
  `calibrated` status means "calibrated against that source" — re-run
  when real outcomes replace staged dev data.
- **Under-the-Hood labels** are manual entry today; X's fetcher plugs
  into the same store when pilot access is granted. Fresh labels warn
  on every draft before you invest in it.
