# Pilot X access, confirmed 2026-09-11

Relay `whoami` authenticates against X as @AScully789
(rest_id 1370357840674758657). This unblocks viral-launcher #15 and #18.
Single-operator open mode is unaffected; nothing here changes the launcher.

## Symptom chain (all in the x-automation relay, real folder)

1. HTTP 403 on every X call. Cause: no `Authorization` header.
   Fix: one line in `twitter_request_headers` (`relay/xclient.py`).
2. HTTP 404 on `UserByScreenName`. Cause: `client.json` held the
   `LtX94E3zViT9Db4Z9Xs8g` placeholder. Fix: real id
   `KybxDj9RrADIITXlGG8kpw` captured from browser DevTools Network tab.
3. `whoami response lacks a user result` with HTTP 200. Cause: bare
   variables/features. Fix: full variable set (`withGrokTranslatedBio`),
   full `features` map, and `fieldToggles` from a live browser capture,
   in both `whoami` (`xclient.py`) and `profile_lookup` (`xreader.py`).
4. Same error persisted. Cause: two missing browser headers.
   Fix: `X-Twitter-Auth-Type: OAuth2Session` and
   `X-Twitter-Client-Language: en` in `twitter_request_headers`.
5. Same error persisted. Cause: response schema moved; the user now
   nests under `data.user.result` (not `data.result`) with `core`,
   `relationship_counts`, and `profile_bio` instead of `legacy`.
   Fix: `_unwrap_user` reads both nestings; `user_from_result` reads
   both shapes; new `_decode_user_id` recovers the numeric rest_id
   from the base64 `id` field (needed as `userId` by UserTweets).

## Still placeholder (next step)

`SearchTimeline` and `UserTweets` ids in `relay/client.json` are still
`...Fb` placeholders. Capture them from DevTools the same way before
own-post reads (`relay search`, `user_posts`) can work.

## Hygiene

- Cookie values passed through chat during debugging; rotate the X
  session after confirming (log out all sessions, store fresh pair
  with `relay cookies set`, never paste values into chat).
- The x-automation edits above are uncommitted local changes; commit
  them in that repo with the bearer value as-is (it is X's public web
  client token, not a personal secret).

## Viral-launcher side (this repo, no code changed)

- #16 closed: all Q1-Q9 answers recorded.
- #15 commented: pilot confirmed, ticket buildable.
- #18 commented: pilot confirmed; remaining work is the Worker
  command-results read route plus schedule.
