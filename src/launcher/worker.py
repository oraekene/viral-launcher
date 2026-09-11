"""Live relay loop client (#18): own-post reads without manual JSON.

The Worker owns the command channel (enqueue user_posts per voice, relay
executes, results land back on the Worker). This module is the launcher
side: enqueue reads, fetch completed results through the user-facing
results route, and run each voice's tweets through the same
normalize-stage-calibrate rails as the dev sync (#2). Transport is a
one-method-per-verb seam so tests inject fakes and no HTTP client
dependency joins the runtime (stdlib urllib only).

Live use needs three things outside this file: a relay paired to the
operator's Worker, the operator's Cloudflare Access JWT as the bearer
token, and real SearchTimeline/UserTweets queryIds in the relay's
client.json (placeholders 404). Schedule `launcher relay-collect`
per voice on cron; pass back the printed cursor as --since next run.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from launcher.relay import RelaySyncResult, VoiceKey, relay_sync


class WorkerError(Exception):
    """The Worker answered badly or not at all."""


@dataclass(frozen=True)
class WorkerConfig:
    base_url: str
    api_token: str


class WorkerTransport(Protocol):
    def get(self, path: str, params: dict[str, str]) -> dict[str, Any]: ...

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]: ...


class UrllibWorkerTransport:
    """Stdlib HTTP transport for the Worker API."""

    def __init__(self, config: WorkerConfig, timeout: float = 30.0) -> None:
        self._config = config
        self._timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._config.base_url.rstrip("/") + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._config.api_token}",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                parsed: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                return parsed
        except urllib.error.HTTPError as e:
            raise WorkerError(
                f"HTTP {e.code} from worker: {e.read().decode('utf-8', 'replace')}"
            ) from e
        except urllib.error.URLError as e:
            raise WorkerError(f"worker unreachable: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise WorkerError("worker returned non-JSON") from e

    def get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, body=body)


@dataclass(frozen=True)
class RelayCommandResult:
    command_id: str
    type: str
    screen_name: str
    tweets: list[dict[str, Any]]
    completed_at: int


class WorkerClient:
    """Enqueue own-post reads and fetch their results for one Worker."""

    def __init__(self, config: WorkerConfig, transport: WorkerTransport | None = None) -> None:
        self._transport = transport or UrllibWorkerTransport(config)

    def enqueue_user_posts(self, relay_id: str, screen_name: str) -> str:
        """Ask the relay to read an account's own posts; returns command_id.

        The relay executes on its next poll; results arrive later, so this
        never blocks on X. Pair with fetch_results on the next schedule tick.
        """
        try:
            body = self._transport.post(
                f"/api/relays/{relay_id}/commands",
                {"type": "user_posts", "payload": {"screen_name": screen_name}},
            )
            return str(body["command_id"])
        except (KeyError, TypeError) as exc:
            raise WorkerError(f"worker answered without command_id: {exc}") from exc

    def fetch_results(
        self, relay_id: str, *, status: str = "done", since: int = 0, limit: int = 50
    ) -> list[RelayCommandResult]:
        """All matching results, paging until a short page (capped)."""
        out: list[RelayCommandResult] = []
        cursor = since
        for _ in range(20):
            body = self._transport.get(
                f"/api/relays/{relay_id}/results",
                {"status": status, "since": str(cursor), "limit": str(limit)},
            )
            try:
                items = body["results"]
                assert isinstance(items, list)
            except (KeyError, TypeError, AssertionError) as exc:
                raise WorkerError(f"worker answered without results: {exc}") from exc
            if not items:
                break
            page = [self._parse_result(item) for item in items]
            out.extend(page)
            cursor = max([cursor, *(r.completed_at for r in page)])
            if len(items) < limit:
                break
        return out

    @staticmethod
    def _parse_result(item: Any) -> RelayCommandResult:
        try:
            tweets = item["output"].get("tweets", [])
            return RelayCommandResult(
                command_id=str(item["command_id"]),
                type=str(item["type"]),
                screen_name=str(item["payload"].get("screen_name", "")),
                tweets=list(tweets) if isinstance(tweets, list) else [],
                completed_at=int(item.get("completed_at") or 0),
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise WorkerError(f"worker answered a malformed result: {exc}") from exc


@dataclass(frozen=True)
class RelayCollectResult:
    cursor: int
    synced: list[RelaySyncResult] = field(default_factory=list)
    skipped: int = 0


def collect_relay_results(
    session: Session,
    client: WorkerClient,
    relay_id: str,
    worker_user_id: str,
    *,
    since: int = 0,
) -> RelayCollectResult:
    """Fetch completed own-post reads and sync each bound voice (#18).

    Non-voice commands and empty reads skip (counted); an unbound voice
    raises like a direct relay_sync so misconfiguration stays loud.
    Results at or before the cursor skip (the cursor is inclusive), so a
    rerun never restages the boundary. Returns the cursor to pass as
    since next run.
    """
    cursor = since
    synced: list[RelaySyncResult] = []
    skipped = 0
    seen: set[str] = set()
    for result in client.fetch_results(relay_id, since=since):
        cursor = max(cursor, result.completed_at)
        if (
            result.type != "user_posts"
            or not result.tweets
            or result.completed_at <= since
            or result.command_id in seen
        ):
            skipped += 1
            continue
        seen.add(result.command_id)
        synced.append(
            relay_sync(
                session, VoiceKey(worker_user_id, result.screen_name), result.tweets
            )
        )
    return RelayCollectResult(cursor=cursor, synced=synced, skipped=skipped)
