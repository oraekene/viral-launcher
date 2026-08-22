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


def _make_draft(client: TestClient, text: str = "Fear was the constraint. What would you add?") -> int:
    return client.post("/drafts", json={"text": text}).json()["id"]


def test_register_launch_interim_scorer(client: TestClient) -> None:
    draft_id = _make_draft(client)
    resp = client.post(
        "/launches",
        json={"draft_id": draft_id, "post_external_id": "178900000000000000"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["scorer"] == "interim"
    assert body["predicted_z"] >= 0.0
    assert body["band_width"] > 0.0
    assert body["protocol_fired"] is None


def test_register_launch_with_predictor(client: TestClient) -> None:
    client.post("/models/train", json={"project_id": "proj", "n": 250})
    created = client.post(
        "/drafts", json={"text": "Great hooks win. What would you add?", "project_id": "proj"}
    ).json()
    resp = client.post("/launches", json={"draft_id": created["id"]})
    assert resp.json()["scorer"] == "predictor"


def test_below_band_fires_double_down(client: TestClient) -> None:
    draft_id = _make_draft(client)
    launch = client.post("/launches", json={"draft_id": draft_id}).json()
    low_z = launch["predicted_z"] - launch["band_width"] - 1.0
    resp = client.post(f"/launches/{launch['id']}/snapshot", json={"actual_z_t10": low_z})
    assert resp.status_code == 200
    card = resp.json()
    assert card["protocol_fired"] == "double_down"
    checklist = " ".join(card["checklist"])
    assert "self-reply" in checklist.lower()
    assert "commenter" in checklist.lower()
    assert "quote" in checklist.lower()


def test_above_band_fires_escalate(client: TestClient) -> None:
    draft_id = _make_draft(client)
    launch = client.post("/launches", json={"draft_id": draft_id}).json()
    high_z = launch["predicted_z"] + launch["band_width"] + 2.0
    resp = client.post(f"/launches/{launch['id']}/snapshot", json={"actual_z_t10": high_z})
    assert resp.json()["protocol_fired"] == "escalate"
    checklist = " ".join(resp.json()["checklist"])
    assert "thread" in checklist.lower()


def test_within_band_holds(client: TestClient) -> None:
    draft_id = _make_draft(client)
    launch = client.post("/launches", json={"draft_id": draft_id}).json()
    mid_z = launch["predicted_z"]
    resp = client.post(f"/launches/{launch['id']}/snapshot", json={"actual_z_t10": mid_z})
    assert resp.json()["protocol_fired"] == "hold"


def test_double_snapshot_rejected(client: TestClient) -> None:
    draft_id = _make_draft(client)
    launch = client.post("/launches", json={"draft_id": draft_id}).json()
    first = client.post(f"/launches/{launch['id']}/snapshot", json={"actual_z_t10": 1.0})
    assert first.status_code == 200
    second = client.post(f"/launches/{launch['id']}/snapshot", json={"actual_z_t10": 2.0})
    assert second.status_code == 409


def test_interventions_logged_human_paced(client: TestClient) -> None:
    draft_id = _make_draft(client)
    launch = client.post("/launches", json={"draft_id": draft_id}).json()
    resp = client.post(
        f"/launches/{launch['id']}/interventions",
        json={"action": "self_reply", "note": "added the pricing angle"},
    )
    assert resp.status_code == 201
    fetched = client.get(f"/launches/{launch['id']}").json()
    assert len(fetched["interventions"]) == 1
    assert fetched["interventions"][0]["action"] == "self_reply"


def test_missing_launch_404(client: TestClient) -> None:
    assert client.get("/launches/9999").status_code == 404
    assert (
        client.post("/launches/9999/snapshot", json={"actual_z_t10": 1.0}).status_code
        == 404
    )
