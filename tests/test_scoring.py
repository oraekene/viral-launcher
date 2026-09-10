from __future__ import annotations

from sqlalchemy.orm import Session

from launcher.features import extract
from launcher.params import ParamStore, seed_params
from launcher.scoring import interim_score


def _store(session: Session) -> ParamStore:
    seed_params(session)
    session.commit()
    return ParamStore(session)


def test_eliciting_draft_outscores_plain_statement(session: Session) -> None:
    store = _store(session)
    rich = extract(
        "Most startups do not have a marketing problem. They have a "
        "distribution habit problem.\n\nWhat would you add?"
    )
    plain = extract("Wrote some code today, it went fine.")
    assert interim_score(rich, store).score > interim_score(plain, store).score


def test_reasons_reference_published_weights(session: Session) -> None:
    store = _store(session)
    result = interim_score(
        extract(
            "Distribution beats marketing every single time. What would you add?"
        ),
        store,
    )
    assert result.score > 0
    joined = " ".join(result.reasons)
    assert "weight.reply" in joined
    assert "weight.quote" in joined


def test_shareable_claim_adds_share_weight(session: Session) -> None:
    store = _store(session)
    shareable = extract("Distribution beats marketing every single time.")
    linked = extract("Distribution beats marketing https://example.com")
    s_share = interim_score(shareable, store).score
    s_link = interim_score(linked, store).score
    assert s_share > s_link >= 0


def test_save_follow_and_link_cues_add_weights(session: Session) -> None:
    store = _store(session)
    base = interim_score(extract("Distribution beats marketing."), store).score
    assert (
        interim_score(extract("Save this for later. Distribution wins."), store).score
        > base
    )
    assert (
        interim_score(extract("Follow for daily notes. Distribution wins."), store).score
        > base
    )
    assert (
        interim_score(
            extract("Distribution beats marketing https://example.com/long-read-here"),
            store,
        ).score
        > base
    )
def test_vetoed_features_are_never_scored_here_by_convention(
    session: Session,
) -> None:
    store = _store(session)
    bait = extract("Like if you agree!")
    result = interim_score(bait, store)
    assert result.score == 0.0


def test_photo_and_video_add_expansion_weights(session: Session) -> None:
    store = _store(session)
    base = interim_score(extract("Distribution beats marketing."), store)
    photo = interim_score(
        extract("Distribution beats marketing.", media=["photo"]), store
    )
    video = interim_score(
        extract("Distribution beats marketing.", media=["video"]), store
    )
    assert photo.score == base.score + 0.05
    assert video.score == base.score + 0.05
    joined = " ".join(photo.reasons)
    assert "weight.photo_expand" in joined
    assert "weight.video_open" in " ".join(video.reasons)


def test_absent_media_scores_exactly_as_before(session: Session) -> None:
    store = _store(session)
    assert (
        interim_score(extract("Distribution beats marketing."), store).score
        == interim_score(
            extract("Distribution beats marketing.", media=[], topics=[]), store
        ).score
    )


def test_topic_factor_only_discounts_disjoint_declared_lanes(
    session: Session,
) -> None:
    from launcher.scoring import resolve_score, topic_factor

    store = _store(session)
    assert topic_factor(extract("Hello."), store) == 1.0
    assert (
        topic_factor(
            extract("Hello.", topics=["ai"], voice_topics=["cooking"]), store
        )
        == 0.5
    )
    assert (
        topic_factor(extract("Hello.", topics=["ai"], voice_topics=["ai"]), store)
        == 1.0
    )
    plain = resolve_score(session, None, extract("Distribution beats marketing every single time. What would you add?"), "t")
    assert plain.scorer == "interim"
    off_lane = resolve_score(
        session,
        None,
        extract(
            "Distribution beats marketing every single time. What would you add?",
            topics=["dating"],
            voice_topics=["ai"],
        ),
        "t",
    )
    assert off_lane.score == round(plain.score * 0.5, 4)
    assert any("oon.topic_discount" in r for r in off_lane.reasons)
