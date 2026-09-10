"""Relay adapter: own-post metrics read into staged outcomes (#2, ADR-0003).

The relay already reports own-post reads through the Worker results
endpoint in the ``Tweet.as_mapping()`` shape (id, text, favorite_count,
retweet_count, reply_count, ...); this module consumes that shape
read-only. It normalizes relay-observed tweets to outcome rows
(features + z60 + value flag) per voice, resolves the Worker user +
account to a launcher project (project equals voice, ADR-0001), stages
the rows, and reruns calibration — the same rails as
``POST /outcomes/import`` plus ``POST /calibration/run`` in one call.

Live enqueue (``POST /api/relays/:id/commands`` with a ``user_posts``
command for the voice's screen name) stays operator-driven until the
Worker exposes completed command results; this core is
transport-agnostic so the same sync runs on captured relay output
today and on a polled fetch later.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from launcher.calibration import CalibrationReport, run_calibration
from launcher.features import extract
from launcher.gate import load_engine
from launcher.models import VoiceBinding
from launcher.outcomes import OutcomeRow, StagedOutcomeSource, stage_radar_outcomes
from launcher.params import ParamStore
from launcher.predictor import active_model, feature_values
from launcher.similarity import max_swatch_similarity


def engagement_value(tweet: dict[str, Any], store: ParamStore) -> float:
    """Weighted engagement of one relay-observed tweet.

    Uses the production elicitation weights from params (reply 5.0,
    repost 1.0, like 0.5): the same scale the interim score prices
    elicitation at, so observed and predicted z stay comparable.
    Quote counts ride along when the relay sends them (xreader does
    not parse them yet, so they price at zero until then).
    """
    try:
        likes = int(tweet["favorite_count"])
        reposts = int(tweet["retweet_count"])
        replies = int(tweet["reply_count"])
        quotes = int(tweet.get("quote_count", 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"tweet {tweet.get('id')!r} misses engagement counts: {exc}"
        ) from exc
    return (
        store.get_float("weight.reply") * replies
        + store.get_float("weight.repost") * reposts
        + store.get_float("weight.like") * likes
        + store.get_float("weight.quote") * quotes
    )


@dataclass(frozen=True)
class VoiceKey:
    """Worker user + X account identity for one voice (ADR-0001)."""

    worker_user_id: str
    screen_name: str

    def __post_init__(self) -> None:
        user = self.worker_user_id.strip()
        handle = self.screen_name.strip().casefold()
        if not user or not handle:
            raise ValueError("worker_user_id and screen_name are both required")
        object.__setattr__(self, "worker_user_id", user)
        object.__setattr__(self, "screen_name", handle)


def _voice_row(session: Session, key: VoiceKey) -> VoiceBinding | None:
    return (
        session.query(VoiceBinding)
        .filter_by(worker_user_id=key.worker_user_id, screen_name=key.screen_name)
        .one_or_none()
    )


def _flag_threshold(session: Session, project_id: str) -> float:
    """Value-flag bar: the voice's calibrated trigger when fitted,
    else the house default. Per-voice override lands in #3."""
    model = active_model(session, project_id)
    if model is not None and model.calibrated_z_trigger is not None:
        return model.calibrated_z_trigger
    return ParamStore(session).get_float("z.trigger")


def normalize_own_posts(
    session: Session,
    project_id: str,
    tweets: list[dict[str, Any]],
    *,
    author_followers: int | None = None,
    mutuals_count: int | None = None,
) -> list[OutcomeRow]:
    """Relay tweet mappings to outcome rows for one voice.

    z60 is the natural log of each tweet's engagement multiple of the
    batch median (#14, Dartmouth style): log-scale de-tails the
    heavy-tailed counts so z-scores regain meaning, while the 2.5-scale
    threshold stays meaningful (ln needs ~12x median). Zero engagement
    or zero baseline yields 0.0. Relay rows are log-scale; do not mix
    synthetic (raw-scale) rows into one voice's calibration.
    The trailing window (#13) and absolute floor (#12) refine this later.
    Repeat tweet ids in one batch stage once (cross-sync repeats stay
    append-only, like import).
    """
    if not tweets:
        raise ValueError("no relay tweets to normalize")
    seen: set[Any] = set()
    unique: list[dict[str, Any]] = []
    for tweet in tweets:
        tweet_id = tweet.get("id")
        if tweet_id is not None:
            if tweet_id in seen:
                continue
            seen.add(tweet_id)
        unique.append(tweet)
    tweets = unique
    store = ParamStore(session)
    engine = load_engine(session)
    threshold = _flag_threshold(session, project_id)
    prepared: list[tuple[dict[str, float], tuple[str, ...]]] = []
    values: list[float] = []
    for tweet in tweets:
        text = tweet.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"tweet {tweet.get('id')!r} has no text")
        values.append(engagement_value(tweet, store))
        features = extract(
            text,
            author_followers=author_followers,
            mutuals_count=mutuals_count,
        )
        vetoes = tuple(
            line.rule_id for line in engine.evaluate(features).lines if line.verdict == "veto"
        )
        prepared.append(
            (feature_values(features, max_swatch_similarity(session, project_id, text)), vetoes)
        )
    baseline = statistics.median(values)
    rows: list[OutcomeRow] = []
    for (vector, vetoes), value in zip(prepared, values):
        z60 = round(math.log(value / baseline), 4) if value > 0 and baseline > 0 else 0.0
        rows.append(
            OutcomeRow(
                features=vector,
                z60=z60,
                value_flag=z60 >= threshold,
                fired_vetoes=vetoes,
            )
        )
    return rows


def bind_voice(session: Session, key: VoiceKey, project_id: str) -> VoiceBinding:
    """Bind (or rebind) a Worker user + account to a launcher project.

    Voice to project stays 1:1 both ways (ADR-0001): a project already
    bound to another voice refuses the bind instead of silently merging.
    """
    if not project_id.strip():
        raise ValueError("project_id is required")
    taken = (
        session.query(VoiceBinding)
        .filter(
            VoiceBinding.project_id == project_id,
            (VoiceBinding.worker_user_id != key.worker_user_id)
            | (VoiceBinding.screen_name != key.screen_name),
        )
        .one_or_none()
    )
    if taken is not None:
        raise ValueError(
            f"project {project_id!r} already belongs to "
            f"user {taken.worker_user_id!r} account {taken.screen_name!r}"
        )
    row = _voice_row(session, key)
    if row is None:
        row = VoiceBinding(
            worker_user_id=key.worker_user_id,
            screen_name=key.screen_name,
            project_id=project_id,
        )
        session.add(row)
    else:
        row.project_id = project_id
    session.flush()
    return row


def resolve_project(session: Session, key: VoiceKey) -> str | None:
    """The launcher project bound to a Worker user + account, if any."""
    row = _voice_row(session, key)
    return row.project_id if row is not None else None


@dataclass(frozen=True)
class RelaySyncResult:
    project_id: str
    staged: int
    report: CalibrationReport


def relay_sync(
    session: Session,
    key: VoiceKey,
    tweets: list[dict[str, Any]],
    *,
    author_followers: int | None = None,
    mutuals_count: int | None = None,
) -> RelaySyncResult:
    """Full adapter loop: resolve voice, normalize, stage, calibrate."""
    project_id = resolve_project(session, key)
    if project_id is None:
        raise ValueError(
            f"no voice binding for user {key.worker_user_id!r} "
            f"account {key.screen_name!r}; bind it first"
        )
    strangers = sorted(
        {str(t.get("author")) for t in tweets if str(t.get("author") or "").casefold() != key.screen_name}
    )
    if strangers:
        raise ValueError(
            f"tweets by {strangers} do not belong to voice {key.screen_name!r}"
        )
    rows = normalize_own_posts(
        session,
        project_id,
        tweets,
        author_followers=author_followers,
        mutuals_count=mutuals_count,
    )
    staged = stage_radar_outcomes(
        session,
        project_id,
        [
            {
                "features": row.features,
                "z60": row.z60,
                "value_flag": row.value_flag,
                "fired_vetoes": list(row.fired_vetoes),
            }
            for row in rows
        ],
    )
    report = run_calibration(session, project_id, StagedOutcomeSource(session))
    return RelaySyncResult(project_id=project_id, staged=staged, report=report)
