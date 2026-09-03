from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from launcher.params import PARAM_SEED, ParamStore, seed_params


@pytest.fixture()
def seeded(session: Session) -> Session:
    seed_params(session)
    session.commit()
    return session


def test_seed_inserts_all_params(seeded: Session) -> None:
    from launcher.models import ParamVersion

    rows = seeded.query(ParamVersion).all()
    assert len(rows) == len(PARAM_SEED)


def test_seed_is_idempotent(seeded: Session) -> None:
    from launcher.models import ParamVersion

    seed_params(seeded)
    seeded.commit()
    assert seeded.query(ParamVersion).count() == len(PARAM_SEED)


def test_published_weights_are_assumed_until_vendored(seeded: Session) -> None:
    store = ParamStore(seeded)
    pv = store.get("weight.reply")
    assert pv.value == 5.0
    assert pv.status == "assumed"
    assert "x-algorithm" in pv.source_note
    assert "not vendored" in pv.source_note


def test_negative_weights_present(seeded: Session) -> None:
    store = ParamStore(seeded)
    assert store.get_float("negative.report") == -234.0
    assert store.get_float("negative.mute") == -58.8
    assert store.get_float("negative.not_interested") == -43.2
    assert store.get_float("negative.block") == -31.2


def test_calibration_params_are_pending(seeded: Session) -> None:
    store = ParamStore(seeded)
    assert store.get("z.trigger").status == "pending"
    assert store.get("z.trigger").value == 2.5


def test_half_life_param_sourced_from_research(seeded: Session) -> None:
    store = ParamStore(seeded)
    pv = store.get("half_life.minutes")
    assert pv.value == 80.0
    assert "arXiv" in pv.source_note


def test_unknown_key_raises(seeded: Session) -> None:
    store = ParamStore(seeded)
    with pytest.raises(KeyError):
        store.get("nope.does_not_exist")
