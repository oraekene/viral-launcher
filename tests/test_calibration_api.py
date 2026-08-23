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


def test_calibration_run_radar_empty_stage_is_422(client: TestClient) -> None:
    resp = client.post(
        "/calibration/run", json={"project_id": "p", "source": "radar"}
    )
    assert resp.status_code == 422
    assert "no radar outcomes" in resp.json()["detail"].lower()


def test_calibration_run_refits_and_flips_status(client: TestClient) -> None:
    resp = client.post("/calibration/run", json={"project_id": "p", "n": 250})
    assert resp.status_code == 200
    body = resp.json()
    assert body["calibrated"] is True
    assert body["applied"] is False
    assert 1.0 <= body["new_z_trigger"] <= 4.0


def test_calibration_run_at_exact_evidence_boundary(client: TestClient) -> None:
    resp = client.post("/calibration/run", json={"project_id": "p", "n": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["calibrated"] is True
    assert body["n_outcomes"] == 100


def test_calibration_status_after_run(client: TestClient) -> None:
    client.post("/models/train", json={"project_id": "p", "n": 300})
    client.post("/calibration/run", json={"project_id": "p", "n": 250})
    status = client.get("/calibration/status", params={"project_id": "p"}).json()
    params = {p["key"]: p for p in status["params"]}
    assert params["z.trigger"]["status"] == "pending"
    assert params["z.trigger"]["last_fit_at"] is None
    assert status["active_model"] is not None
    assert status["active_model"]["status"] == "pending"
    assert status["active_model"]["feature_importances"]
