# ADR-0005: Conversation Threads Are Parked for Future Elicitation Work

Status: accepted (2026-09-05).

## Context

The Worker already stores multi-turn conversations (Conversations/Messages
in D1, inbound replies via `inbound_scan`, deterministic + semantic
termination, every close logged with a reason). Those threads record which
reply framings earn continuations — the ideal future training signal for
the Gate's elicitation rules. Calibration, however, trains on post
outcomes (z60/value flag), for which threads are not an input.

## Decision

Threads stay out of calibration scope. A future elicitation ticket may
consume close reasons and continuation rates per framing; until then the
data accumulates untouched in the Worker.

## Consequences

- No schema or pipeline work needed today; the future ticket reads
  existing tables.
- Elicitation rules keep their assumed weights until that ticket lands.
