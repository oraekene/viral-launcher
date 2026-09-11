"""Live relay loop client tests (#18).

The Worker HTTP boundary stays behind a fake transport; relay_sync runs
for real against a seeded session so staging plus calibration is proven.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from launcher.relay import VoiceKey, bind_voice
from launcher.worker import (
    RelayCommandResult,
    WorkerClient,
    WorkerConfig,
    WorkerError,
    WorkerTransport,
    collect_relay_results,
)


CLEAN = (
    "We cut our release cycle from 14 days to 2 by deleting half the checklist. "
    "Speed was never the constraint. Fear was. What would you add?"
)


def _tweet(i: int, **counts: int) -> dict[str, Any]:
    return {
        "id": str(3000 + i),
        "author": "voicea",
        "text": CLEAN,
        "created_at": "Mon Sep 08 12:00:00 +0000 2026",
        "favorite_count": counts.get("likes", 10),
        "retweet_count": counts.get("reposts", 0),
        "reply_count": counts.get("replies", 0),
        "lang": "en",
        "in_reply_to_tweet_id": None,
        "in_reply_to_screen_name": None,
    }


class FakeTransport(WorkerTransport):
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.gets: list[tuple[str, dict[str, str]]] = []
        self.results: list[dict[str, Any]] = []
        self.fail: str | None = None

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.posts.append((path, body))
        if self.fail == "post":
            raise WorkerError("HTTP 401 from worker")
        return {"command_id": "cmd-1"}

    def get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        self.gets.append((path, params))
        if self.fail == "get":
            raise WorkerError("HTTP 500 from worker")
        return {"results": self.results}


def _client(transport: FakeTransport) -> WorkerClient:
    return WorkerClient(
        WorkerConfig(base_url="https://worker.test", api_token="tok"), transport
    )


def test_enqueue_posts_user_posts_command() -> None:
    transport = FakeTransport()
    command_id = _client(transport).enqueue_user_posts("relay-1", "voicea")
    assert command_id == "cmd-1"
    assert transport.posts == [
        (
            "/api/relays/relay-1/commands",
            {"type": "user_posts", "payload": {"screen_name": "voicea"}},
        )
    ]


def test_enqueue_surfaces_worker_errors() -> None:
    transport = FakeTransport()
    transport.fail = "post"
    with pytest.raises(WorkerError, match="401"):
        _client(transport).enqueue_user_posts("relay-1", "voicea")


def test_fetch_maps_results() -> None:
    transport = FakeTransport()
    transport.results = [
        {
            "command_id": "cmd-1",
            "type": "user_posts",
            "payload": {"screen_name": "voicea"},
            "status": "done",
            "output": {"tweets": []},
            "completed_at": 111,
        }
    ]
    results = _client(transport).fetch_results("relay-1", since=100)
    assert results == [
        RelayCommandResult(
            command_id="cmd-1",
            type="user_posts",
            screen_name="voicea",
            tweets=[],
            completed_at=111,
        )
    ]
    assert transport.gets == [
        ("/api/relays/relay-1/results", {"status": "done", "since": "100", "limit": "50"})
    ]


def test_fetch_pages_until_short_page() -> None:
    transport = FakeTransport()
    transport.results = []  # replaced per call below
    calls = {"n": 0}

    def paged(path: str, params: dict[str, str]) -> dict[str, object]:
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "results": [
                    {
                        "command_id": "cmd-1",
                        "type": "user_posts",
                        "payload": {"screen_name": "voicea"},
                        "status": "done",
                        "output": {"tweets": []},
                        "completed_at": 150,
                    }
                ]
            }
        return {"results": []}

    class PagedTransport(WorkerTransport):
        def post(self, path: str, body: object) -> dict[str, object]:
            raise AssertionError("no posts expected")

        def get(self, path: str, params: dict[str, str]) -> dict[str, object]:
            return paged(path, params)

    results = WorkerClient(
        WorkerConfig(base_url="https://worker.test", api_token="tok"),
        PagedTransport(),  # type: ignore[arg-type]
    ).fetch_results("relay-1", since=100, limit=1)
    assert [r.command_id for r in results] == ["cmd-1"]
    assert calls["n"] == 2


def test_collect_skips_boundary_reruns(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-a", "voicea"), "voice-a")
    transport = FakeTransport()
    transport.results = [
        {
            "command_id": "cmd-1",
            "type": "user_posts",
            "payload": {"screen_name": "voicea"},
            "status": "done",
            "output": {"tweets": [_tweet(0)]},
            "completed_at": 222,
        }
    ]
    first = collect_relay_results(seeded, _client(transport), "relay-1", "user-a", since=0)
    assert first.cursor == 222
    assert len(first.synced) == 1
    second = collect_relay_results(
        seeded, _client(transport), "relay-1", "user-a", since=first.cursor
    )
    assert second.synced == []
    assert second.skipped == 1
    assert second.cursor == 222


def test_collect_stages_and_calibrates(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-a", "voicea"), "voice-a")
    transport = FakeTransport()
    transport.results = [
        {
            "command_id": "cmd-1",
            "type": "user_posts",
            "payload": {"screen_name": "voicea"},
            "status": "done",
            "output": {"tweets": [_tweet(0), _tweet(1)]},
            "completed_at": 222,
        }
    ]
    collected = collect_relay_results(
        seeded, _client(transport), "relay-1", "user-a", since=0
    )
    assert collected.cursor == 222
    assert collected.skipped == 0
    assert len(collected.synced) == 1
    assert collected.synced[0].project_id == "voice-a"
    assert collected.synced[0].staged == 2


def test_collect_skips_non_voice_and_empty(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-a", "voicea"), "voice-a")
    transport = FakeTransport()
    transport.results = [
        {
            "command_id": "cmd-echo",
            "type": "echo",
            "payload": {},
            "status": "done",
            "output": {"echoed": "hi"},
            "completed_at": 100,
        },
        {
            "command_id": "cmd-empty",
            "type": "user_posts",
            "payload": {"screen_name": "voicea"},
            "status": "done",
            "output": {"tweets": []},
            "completed_at": 200,
        },
    ]
    collected = collect_relay_results(
        seeded, _client(transport), "relay-1", "user-a", since=0
    )
    assert collected.synced == []
    assert collected.skipped == 2
    assert collected.cursor == 200


def test_collect_raises_on_unbound_voice(seeded: Session) -> None:
    transport = FakeTransport()
    transport.results = [
        {
            "command_id": "cmd-1",
            "type": "user_posts",
            "payload": {"screen_name": "ghost"},
            "status": "done",
            "output": {"tweets": [_tweet(0)]},
            "completed_at": 300,
        }
    ]
    with pytest.raises(ValueError, match="no voice binding"):
        collect_relay_results(seeded, _client(transport), "relay-1", "user-a", since=0)
