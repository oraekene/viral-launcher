from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.outcomes import StagedOutcomeSource
from launcher.predictor import FEATURE_NAMES
from launcher.relay import bind_voice, normalize_own_posts, relay_sync, resolve_project
from launcher.seed import seed_all


@pytest.fixture()
def seeded(session: Session) -> Session:
    seed_all(session)
    session.commit()
    return session


def _tweet(
    i: int,
    text: str,
    *,
    likes: int = 10,
    reposts: int = 0,
    replies: int = 0,
) -> dict[str, object]:
    return {
        "id": str(1000 + i),
        "author": "ascully789",
        "text": text,
        "created_at": "Mon Sep 08 12:00:00 +0000 2026",
        "favorite_count": likes,
        "retweet_count": reposts,
        "reply_count": replies,
        "lang": "en",
        "in_reply_to_tweet_id": None,
        "in_reply_to_screen_name": None,
    }


CLEAN = (
    "We cut our release cycle from 14 days to 2 by deleting half the checklist. "
    "Speed was never the constraint. Fear was. What would you add?"
)
BAIT = "Like if you agree! Tag someone who needs this."


def test_normalize_flags_relative_winner(seeded: Session) -> None:
    tweets = [_tweet(0, CLEAN), _tweet(1, CLEAN), _tweet(2, CLEAN)]
    tweets.append(_tweet(3, CLEAN, likes=200, reposts=5, replies=10))
    rows = normalize_own_posts(seeded, "voice-a", tweets)
    assert len(rows) == 4
    assert [r.value_flag for r in rows] == [False, False, False, True]
    assert rows[3].z60 > 2.5
    for row in rows:
        assert set(row.features) == set(FEATURE_NAMES)


def test_normalize_captures_gate_vetoes(seeded: Session) -> None:
    rows = normalize_own_posts(seeded, "voice-a", [_tweet(0, BAIT)])
    assert "negative.engagement_bait" in rows[0].fired_vetoes
    clean = normalize_own_posts(seeded, "voice-a", [_tweet(1, CLEAN)])
    assert clean[0].fired_vetoes == ()


def test_normalize_replies_outweigh_likes(seeded: Session) -> None:
    chatty = normalize_own_posts(
        seeded, "voice-a", [_tweet(0, CLEAN, replies=10), _tweet(1, CLEAN, likes=50)]
    )
    assert chatty[0].z60 > chatty[1].z60


def test_normalize_rejects_empty_and_malformed(seeded: Session) -> None:
    with pytest.raises(ValueError):
        normalize_own_posts(seeded, "voice-a", [])
    bad = _tweet(0, CLEAN)
    del bad["favorite_count"]
    with pytest.raises(ValueError):
        normalize_own_posts(seeded, "voice-a", [bad])


def test_voice_binding_roundtrip_and_rebind(seeded: Session) -> None:
    assert resolve_project(seeded, "user-1", "ascully789") is None
    bind_voice(seeded, "user-1", "ascully789", "voice-a")
    assert resolve_project(seeded, "user-1", "ascully789") == "voice-a"
    bind_voice(seeded, "user-1", "ascully789", "voice-b")
    assert resolve_project(seeded, "user-1", "ascully789") == "voice-b"


def test_relay_sync_stages_and_runs_calibration(seeded: Session) -> None:
    bind_voice(seeded, "user-1", "ascully789", "voice-a")
    tweets = [_tweet(i, CLEAN) for i in range(9)]
    tweets += [_tweet(9 + i, CLEAN, likes=200, reposts=5, replies=10) for i in range(3)]
    result = relay_sync(seeded, "user-1", "ascully789", tweets)
    assert result.project_id == "voice-a"
    assert result.staged == 12
    assert len(StagedOutcomeSource(seeded).load_outcomes("voice-a")) == 12
    assert result.report.n_outcomes == 12
    assert result.report.calibrated is False
    assert "insufficient evidence" in result.report.reason


def test_relay_sync_calibrates_on_evidence(seeded: Session) -> None:
    bind_voice(seeded, "user-1", "ascully789", "voice-a")
    tweets = [_tweet(i, CLEAN) for i in range(90)]
    tweets += [_tweet(90 + i, CLEAN, likes=200, reposts=5, replies=10) for i in range(30)]
    result = relay_sync(seeded, "user-1", "ascully789", tweets)
    assert result.staged == 120
    assert result.report.calibrated is True
    assert result.report.winner_share == pytest.approx(0.25)


def test_relay_sync_without_binding_raises(seeded: Session) -> None:
    with pytest.raises(ValueError, match="no voice binding"):
        relay_sync(seeded, "user-1", "ascully789", [_tweet(0, CLEAN)])


def test_relay_sync_rejects_foreign_author(seeded: Session) -> None:
    bind_voice(seeded, "user-1", "ascully789", "voice-a")
    foreign = _tweet(0, CLEAN)
    foreign["author"] = "someone-else"
    with pytest.raises(ValueError, match="do not belong to voice"):
        relay_sync(seeded, "user-1", "ascully789", [foreign])


def test_bind_refuses_project_owned_by_another_voice(seeded: Session) -> None:
    bind_voice(seeded, "user-1", "ascully789", "voice-a")
    with pytest.raises(ValueError, match="already belongs to"):
        bind_voice(seeded, "user-1", "oraekene1", "voice-a")


def test_handles_match_case_insensitively(seeded: Session) -> None:
    bind_voice(seeded, "user-1", "AsCully789", "voice-a")
    assert resolve_project(seeded, "user-1", "ascully789") == "voice-a"
    result = relay_sync(seeded, "user-1", "ASCULLY789", [_tweet(0, CLEAN)])
    assert result.project_id == "voice-a"
    assert result.staged == 1
