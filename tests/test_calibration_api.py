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


def test_calibration_run_radar_not_implemented(client: TestClient) -> None:
    resp = client.post(
        "/calibration/run", json={"project_id": "p", "source": "radar"}
    )
    assert resp.status_code == 501


def test_calibration_run_refits_and_flips_status(client: TestClient) -> None:
    resp = client.post("/calibration/run", json={"project_id": "p", "n": 250})
    assert resp.status_code == 200
    body = resp.json()
    assert body["calibrated"] is True
    assert body["new_z_trigger"] is not None
    assert 1.0 <= body["new_z_trigger"] <= 4.0


def test_calibration_run_at_exact_evidence_boundary(client: TestClient) -> None:
    resp = client.post("/calibration/run", json={"project_id": "p", "n": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["calibrated"] is True
    assert body["n_outcomes"] == 100


def test_calibration_status_shows_calibrated_param(client: TestClient) -> None:
    client.post("/calibration/run", json={"project_id": "p", "n": 250})
    status = client.get("/calibration/status", params={"project_id": "p"}).json()
    params = {p["key"]: p for p in status["params"]}
    assert params["z.trigger"]["status"] == "calibrated"
    assert params["z.trigger"]["last_fit_at"] is not None
    assert params["band.interim_width"]["status"] == "pending"
