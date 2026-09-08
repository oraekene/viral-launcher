# ADR-0004: Launcher Tenancy Enforcement Is Deferred, Partitioning Is Not

Status: accepted (2026-09-05).

## Context

The Worker side already enforces tenancy (`relayOwnedBy` guard,
bearer relay tokens, `user_id` on relays/drafts, `getUser` boundary,
per-user accounts). The launcher side partitions by free-form
`project_id` with no auth, no isolation, and a default shared SQLite
file. Cross-voice leakage today requires only typing another voice's
project id.

## Decision

Ship partitioning now (ADR-0001), enforce tenancy at the multi-user
hardening step: authenticated project scoping on the launcher API plus
per-tenant storage. The adapter ticket (ADR-0003) carries the Worker
identity (`user_id` + account → voice → project) through, so the mapping
exists before enforcement does.

## Consequences

- Single-operator use is unaffected; the gap only matters with mutually
  untrusted users sharing one launcher service.
- Until enforcement lands, project ids are capability strings: unguessable
  per-voice ids (UUIDs) instead of readable names.
