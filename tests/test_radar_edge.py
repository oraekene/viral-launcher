from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from launcher.api import create_app
from launcher.models import Base
from launcher.outcomes import (
    StagedOutcomeSource,
    SyntheticOutcomeSource,
)
from launcher.seed import seed_all


@pytest.fixture()
def client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        seed_all(s)
        s.commit()
    return TestClient(create_app(factory))


def _valid_rows(n: int = 300) -> list[dict[str, object]]:
    return [
        {
            "features": r.features,
            "z60": r.z60,
            "value_flag": r.value_flag,
            "fired_vetoes": ["negative.pod_signature"] if i == 0 else [],
        }
        for i, r in enumerate(SyntheticOutcomeSource(n=n).load_outcomes("radar-proj"))
    ]


def _import(client: TestClient, project_id: str = "radar-proj", n: int = 300) -> object:
    return client.post(
        "/outcomes/import",
        json={"project_id": project_id, "rows": _valid_rows(n)},
    )


def test_import_stages_rows(client: TestClient) -> None:
    resp = _import(client)
    assert resp.status_code == 201
    assert resp.json()["imported"] == 300


def test_import_rejects_missing_feature_keys(client: TestClient) -> None:
    bad = [{"features": {"char_len": 100.0}, "z60": 1.0, "value_flag": False}]
    resp = client.post("/outcomes/import", json={"project_id": "p", "rows": bad})
    assert resp.status_code == 422


def test_train_with_radar_source_after_import(client: TestClient) -> None:
    _import(client, project_id="radar-proj", n=400)
    resp = client.post(
        "/models/train",
        json={"project_id": "radar-proj", "source": "radar", "n": 400},
    )
    assert resp.status_code == 201
    assert resp.json()["source"] == "StagedOutcomeSource"


def test_train_radar_source_empty_stage_is_422(client: TestClient) -> None:
    resp = client.post(
        "/models/train",
        json={"project_id": "nothing", "source": "radar"},
    )
    assert resp.status_code == 422
    assert "no radar outcomes" in resp.json()["detail"].lower()


def test_calibration_radar_source_after_import(client: TestClient) -> None:
    _import(client, project_id="cal-proj", n=250)
    resp = client.post(
        "/calibration/run",
        json={"project_id": "cal-proj", "source": "radar", "n": 250},
    )
    assert resp.status_code == 200
    assert resp.json()["calibrated"] is True


def test_radar_source_direct(session: Session) -> None:
    from launcher.outcomes import stage_radar_outcomes

    rows = SyntheticOutcomeSource(n=60).load_outcomes("direct-proj")
    staged = [
        {
            "features": r.features,
            "z60": r.z60,
            "value_flag": r.value_flag,
            "fired_vetoes": ("negative.engagement_bait",) if r.value_flag else (),
        }
        for r in rows
    ]
    count = stage_radar_outcomes(session, "direct-proj", staged)
    session.commit()
    assert count == 60

    loaded = StagedOutcomeSource(session).load_outcomes("direct-proj")
    assert len(loaded) == 60
    assert all(isinstance(r.features, dict) for r in loaded)

    with pytest.raises(ValueError, match="no radar outcomes"):
        StagedOutcomeSource(session).load_outcomes("empty-proj")


def test_staged_source_preserves_vetoes(session: Session) -> None:
    from launcher.outcomes import stage_radar_outcomes

    rows = SyntheticOutcomeSource(n=30).load_outcomes("launch-proj")
    stage_radar_outcomes(
        session,
        "launch-proj",
        [
            {
                "features": r.features,
                "z60": r.z60,
                "value_flag": r.value_flag,
                "fired_vetoes": ("negative.pod_signature",),
            }
            for r in rows
        ],
    )
    session.commit()

    launcher_rows = StagedOutcomeSource(session).load_outcomes("launch-proj")
    assert len(launcher_rows) == 30
    assert launcher_rows[0].fired_vetoes == ("negative.pod_signature",)
