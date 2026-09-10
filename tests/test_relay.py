from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.models import RadarOutcomeStage
from launcher.outcomes import StagedOutcomeSource
from launcher.predictor import FEATURE_NAMES
from launcher.relay import VoiceKey, bind_voice, engagement_value, normalize_own_posts, relay_sync, resolve_project
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


def test_z60_is_log_multiple_of_median(seeded: Session) -> None:
    import math

    rows = normalize_own_posts(
        seeded, "voice-a", [_tweet(0, CLEAN, likes=10), _tweet(1, CLEAN, likes=50)]
    )
    assert rows[0].z60 == pytest.approx(math.log(5.0 / 15.0), abs=1e-3)
    assert rows[1].z60 == pytest.approx(math.log(25.0 / 15.0), abs=1e-3)


def test_small_variance_stays_compressed(seeded: Session) -> None:
    rows = normalize_own_posts(
        seeded, "voice-a", [_tweet(0, CLEAN, likes=10), _tweet(1, CLEAN, likes=12)]
    )
    assert all(r.z60 < 2.5 for r in rows)
    assert [r.value_flag for r in rows] == [False, False]


def test_normalize_rejects_empty_and_malformed(seeded: Session) -> None:
    with pytest.raises(ValueError):
        normalize_own_posts(seeded, "voice-a", [])
    bad = _tweet(0, CLEAN)
    del bad["favorite_count"]
    with pytest.raises(ValueError):
        normalize_own_posts(seeded, "voice-a", [bad])


def test_voice_binding_roundtrip_and_rebind(seeded: Session) -> None:
    assert resolve_project(seeded, VoiceKey("user-1", "ascully789")) is None
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a")
    assert resolve_project(seeded, VoiceKey("user-1", "ascully789")) == "voice-a"
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-b")
    assert resolve_project(seeded, VoiceKey("user-1", "ascully789")) == "voice-b"


def test_relay_sync_stages_and_runs_calibration(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a")
    tweets = [_tweet(i, CLEAN) for i in range(9)]
    tweets += [_tweet(9 + i, CLEAN, likes=200, reposts=5, replies=10) for i in range(3)]
    result = relay_sync(seeded, VoiceKey("user-1", "ascully789"), tweets)
    assert result.project_id == "voice-a"
    assert result.staged == 12
    assert len(StagedOutcomeSource(seeded).load_outcomes("voice-a")) == 12
    assert result.report.n_outcomes == 12
    assert result.report.calibrated is False
    assert "insufficient evidence" in result.report.reason


def test_relay_sync_calibrates_on_evidence(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a")
    tweets = [_tweet(i, CLEAN) for i in range(90)]
    tweets += [_tweet(90 + i, CLEAN, likes=200, reposts=5, replies=10) for i in range(30)]
    result = relay_sync(seeded, VoiceKey("user-1", "ascully789"), tweets)
    assert result.staged == 120
    assert result.report.calibrated is True
    assert result.report.winner_share == pytest.approx(0.25)


def test_relay_sync_without_binding_raises(seeded: Session) -> None:
    with pytest.raises(ValueError, match="no voice binding"):
        relay_sync(seeded, VoiceKey("user-1", "ascully789"), [_tweet(0, CLEAN)])


def test_relay_sync_rejects_foreign_author(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a")
    foreign = _tweet(0, CLEAN)
    foreign["author"] = "someone-else"
    with pytest.raises(ValueError, match="do not belong to voice"):
        relay_sync(seeded, VoiceKey("user-1", "ascully789"), [foreign])


def test_bind_refuses_project_owned_by_another_voice(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a")
    with pytest.raises(ValueError, match="already belongs to"):
        bind_voice(seeded, VoiceKey("user-1", "oraekene1"), "voice-a")


def test_repeat_ids_stage_once(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a")
    tweets = [_tweet(0, CLEAN), _tweet(0, CLEAN), _tweet(1, CLEAN)]
    result = relay_sync(seeded, VoiceKey("user-1", "ascully789"), tweets)
    assert result.staged == 2


def test_quote_counts_price_when_present(seeded: Session) -> None:
    from launcher.params import ParamStore

    store = ParamStore(seeded)
    plain = _tweet(0, CLEAN, likes=10)
    quoted = _tweet(1, CLEAN, likes=10)
    quoted["quote_count"] = 4
    assert engagement_value(quoted, store) == engagement_value(plain, store) + 4 * store.get_float("weight.quote")


def test_handles_match_case_insensitively(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-1", "AsCully789"), "voice-a")
    assert resolve_project(seeded, VoiceKey("user-1", "ascully789")) == "voice-a"
    result = relay_sync(seeded, VoiceKey("user-1", "ASCULLY789"), [_tweet(0, CLEAN)])
    assert result.project_id == "voice-a"
    assert result.staged == 1


def test_floor_blocks_sub_floor_peaks(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a", viral_floor=200.0)
    tweets = [_tweet(0, CLEAN), _tweet(1, CLEAN), _tweet(2, CLEAN)]
    tweets.append(_tweet(3, CLEAN, likes=200, reposts=5, replies=10))
    rows = normalize_own_posts(seeded, "voice-a", tweets)
    assert [r.value_flag for r in rows] == [False, False, False, False]


def test_floor_passes_above_floor_hits(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a", viral_floor=100.0)
    tweets = [_tweet(0, CLEAN), _tweet(1, CLEAN), _tweet(2, CLEAN)]
    tweets.append(_tweet(3, CLEAN, likes=200, reposts=5, replies=10))
    rows = normalize_own_posts(seeded, "voice-a", tweets)
    assert [r.value_flag for r in rows] == [False, False, False, True]


def test_negative_floor_rejected(seeded: Session) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a", viral_floor=-1.0)


def _mixed_batch() -> list[dict[str, object]]:
    tweets = [_tweet(0, CLEAN), _tweet(1, CLEAN)]
    tweets.append(_tweet(2, CLEAN, likes=50))
    tweets.append(_tweet(3, CLEAN, likes=400, reposts=10, replies=20))
    return tweets


def test_two_voices_hold_different_thresholds(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a", viral_threshold=0.5)
    bind_voice(seeded, VoiceKey("user-1", "oraekene1"), "voice-b", viral_threshold=99.0)
    loose = normalize_own_posts(seeded, "voice-a", _mixed_batch())
    strict = normalize_own_posts(seeded, "voice-b", _mixed_batch())
    assert [r.value_flag for r in loose] == [False, False, True, True]
    assert [r.value_flag for r in strict] == [False, False, False, False]


def test_override_beats_house_default(seeded: Session) -> None:
    bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a", viral_threshold=0.5)
    house = normalize_own_posts(seeded, "voice-c", _mixed_batch())
    declared = normalize_own_posts(seeded, "voice-a", _mixed_batch())
    assert [r.value_flag for r in house] == [False, False, False, True]
    assert [r.value_flag for r in declared] == [False, False, True, True]


def test_non_positive_threshold_rejected(seeded: Session) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        bind_voice(seeded, VoiceKey("user-1", "ascully789"), "voice-a", viral_threshold=0.0)


def _hot(i: int) -> dict[str, object]:
    return _tweet(i, CLEAN, likes=200, reposts=50, replies=10)


def test_window_flags_voice_outliers(seeded: Session) -> None:
    key = VoiceKey("user-1", "ascully789")
    bind_voice(seeded, key, "voice-a")
    first = relay_sync(seeded, key, [_tweet(i, CLEAN) for i in range(100)])
    assert first.staged == 100
    engaged = [
        r.engagement
        for r in seeded.query(RadarOutcomeStage).filter_by(project_id="voice-a").all()
    ]
    assert engaged and all(e == 5.0 for e in engaged)
    batch = [_hot(1000), _hot(1001), _hot(1002), _tweet(1003, CLEAN)]
    result = relay_sync(seeded, key, batch)
    assert result.staged == 4
    rows = StagedOutcomeSource(seeded).load_outcomes("voice-a")[-4:]
    assert [r.value_flag for r in rows] == [True, True, True, False]


def test_thin_history_falls_back_to_batch(seeded: Session) -> None:
    key = VoiceKey("user-1", "ascully789")
    bind_voice(seeded, key, "voice-a")
    relay_sync(seeded, key, [_tweet(i, CLEAN) for i in range(10)])
    rows = normalize_own_posts(seeded, "voice-a", _mixed_batch())
    assert [r.value_flag for r in rows] == [False, False, False, True]


def test_migration_adds_missing_columns() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from launcher.db import init_db

    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE radar_outcomes_stage (id INTEGER PRIMARY KEY, "
            "project_id VARCHAR(64), z60 FLOAT, value_flag BOOLEAN, "
            "fired_vetoes JSON, features JSON, imported_at DATETIME)"
        )
        conn.commit()
    init_db(engine)
    with engine.connect() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(radar_outcomes_stage)").all()]
    assert "engagement" in cols
    session = sessionmaker(bind=engine)()
    session.add(
        RadarOutcomeStage(
            project_id="p", z60=1.0, value_flag=False, fired_vetoes=[], features={}, engagement=7.5
        )
    )
    session.commit()
