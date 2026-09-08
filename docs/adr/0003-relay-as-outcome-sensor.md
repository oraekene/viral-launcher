# ADR-0003: The Relay Is the Outcome Sensor; No Standalone Tracker Will Be Built

Status: accepted (2026-09-05).

## Context

Calibration needs per-voice outcome rows (features + z60 + value flag).
A standalone radar-side watcher was the presumed build until the relay
codebase showed the sensor already exists: `POST /api/relays/:id/results`
reports per-command outcomes, drafts record `result_tweet_id` and
`executed_at` scoped by `user_id`, and `xreader.py` already parses
favorite/retweet/reply counts from GraphQL (currently only for searched
candidates, not own posts).

## Decision

No watcher build. The remaining work is one adapter ticket: an own-post
metrics read (t=60 snapshot command type reusing the results endpoint),
relay-result → outcome-row normalization per voice, project mapping, and
scheduled staging plus calibration rerun.

## Consequences

- Tracker scope collapses from a phase to a ticket on existing rails
  (command types, results endpoint, catch-up queue all reused).
- The adapter ticket must define the missing piece explicitly: scheduled
  reads of engagement counts on the operator's own posts, which nothing
  performs today.
