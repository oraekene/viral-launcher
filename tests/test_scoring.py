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


def test_vetoed_features_are_never_scored_here_by_convention(
    session: Session,
) -> None:
    store = _store(session)
    bait = extract("Like if you agree!")
    result = interim_score(bait, store)
    assert result.score == 0.0
