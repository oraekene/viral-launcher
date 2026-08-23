from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from launcher.api import create_app
from launcher.models import Base
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


DRAFT = "Distribution beats marketing every single time. What would you add?"


def test_train_and_list_models(client: TestClient) -> None:
    resp = client.post(
        "/models/train", json={"project_id": "proj-a", "n": 250}
    )
    assert resp.status_code == 201
    model = resp.json()
    assert model["project_id"] == "proj-a"
    assert model["n_events"] == 250
    assert model["status"] == "pending"
    assert 0.0 <= model["precision"] <= 1.0
    assert 0.0 <= model["recall"] <= 1.0

    listed = client.get("/models", params={"project_id": "proj-a"}).json()
    assert len(listed) == 1


def test_train_below_min_events_rejected(client: TestClient) -> None:
    resp = client.post("/models/train", json={"project_id": "p", "n": 100})
    assert resp.status_code == 422


def test_train_radar_source_empty_stage_is_422(client: TestClient) -> None:
    resp = client.post(
        "/models/train", json={"project_id": "p", "source": "radar"}
    )
    assert resp.status_code == 422
    assert "no radar outcomes" in resp.json()["detail"].lower()


def test_score_uses_predictor_when_model_exists(client: TestClient) -> None:
    created = client.post("/drafts", json={"text": DRAFT, "project_id": "proj"}).json()
    before = client.post(f"/drafts/{created['id']}/score").json()
    assert before["scorer"] == "interim"
    assert before["predicted_z"] is None

    client.post("/models/train", json={"project_id": "proj", "n": 300})
    after = client.post(f"/drafts/{created['id']}/score").json()
    assert after["scorer"] == "predictor"
    assert after["predicted_z"] >= 0.0
    assert after["band_width"] > 0.0
    assert after["model_status"] == "pending"


def test_score_missing_draft_404(client: TestClient) -> None:
    assert client.post("/drafts/9999/score").status_code == 404
