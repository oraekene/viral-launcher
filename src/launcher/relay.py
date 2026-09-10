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
    Relay mappings carry no quote counts, so quotes price at zero here.
    """
    try:
        likes = int(tweet["favorite_count"])
        reposts = int(tweet["retweet_count"])
        replies = int(tweet["reply_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"tweet {tweet.get('id')!r} misses engagement counts: {exc}"
        ) from exc
    return (
        store.get_float("weight.reply") * replies
        + store.get_float("weight.repost") * reposts
        + store.get_float("weight.like") * likes
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

    z60 is each tweet's engagement multiple of the batch median —
    batch-scoped by design; the trailing window (#13), log scale (#14),
    and absolute floor (#12) refine it later.
    """
    if not tweets:
        raise ValueError("no relay tweets to normalize")
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
        z60 = round(value / baseline, 4) if baseline > 0 else 0.0
        rows.append(
            OutcomeRow(
                features=vector,
                z60=z60,
                value_flag=z60 >= threshold,
                fired_vetoes=vetoes,
            )
        )
    return rows


def bind_voice(
    session: Session, worker_user_id: str, screen_name: str, project_id: str
) -> VoiceBinding:
    """Bind (or rebind) a Worker user + account to a launcher project."""
    if not worker_user_id.strip() or not screen_name.strip() or not project_id.strip():
        raise ValueError("worker_user_id, screen_name, and project_id are all required")
    row = (
        session.query(VoiceBinding)
        .filter_by(worker_user_id=worker_user_id, screen_name=screen_name)
        .one_or_none()
    )
    if row is None:
        row = VoiceBinding(
            worker_user_id=worker_user_id,
            screen_name=screen_name,
            project_id=project_id,
        )
        session.add(row)
    else:
        row.project_id = project_id
    session.flush()
    return row


def resolve_project(
    session: Session, worker_user_id: str, screen_name: str
) -> str | None:
    """The launcher project bound to a Worker user + account, if any."""
    row = (
        session.query(VoiceBinding)
        .filter_by(worker_user_id=worker_user_id, screen_name=screen_name)
        .one_or_none()
    )
    return row.project_id if row is not None else None


@dataclass(frozen=True)
class RelaySyncResult:
    project_id: str
    staged: int
    report: CalibrationReport


def relay_sync(
    session: Session,
    worker_user_id: str,
    screen_name: str,
    tweets: list[dict[str, Any]],
    *,
    author_followers: int | None = None,
    mutuals_count: int | None = None,
) -> RelaySyncResult:
    """Full adapter loop: resolve voice, normalize, stage, calibrate."""
    project_id = resolve_project(session, worker_user_id, screen_name)
    if project_id is None:
        raise ValueError(
            f"no voice binding for user {worker_user_id!r} "
            f"account {screen_name!r}; bind it first"
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
