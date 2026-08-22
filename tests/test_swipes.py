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


def test_archive_draft_as_swatch(client: TestClient) -> None:
    created = client.post("/drafts", json={"text": DRAFT, "project_id": "proj"}).json()
    resp = client.post("/swatches", json={"draft_id": created["id"]})
    assert resp.status_code == 201
    swatch = resp.json()
    assert swatch["text"] == DRAFT
    assert swatch["project_id"] == "proj"
    assert len(swatch["gate_lines"]) > 0
    assert all(l["source_note"] for l in swatch["gate_lines"])


def test_archive_variant_uses_variant_text(client: TestClient) -> None:
    created = client.post("/drafts", json={"text": DRAFT}).json()
    rewrite = client.post(f"/drafts/{created['id']}/rewrite", json={"n": 2}).json()
    top_variant = rewrite["top"][0]
    resp = client.post(
        "/swatches",
        json={"draft_id": created["id"], "variant_id": top_variant["id"]},
    )
    assert resp.status_code == 201
    swatch = resp.json()
    assert swatch["text"] == top_variant["text"]
    assert swatch["score"] == top_variant["score"]
    assert len(swatch["gate_lines"]) > 0


def test_archive_missing_draft_404(client: TestClient) -> None:
    assert client.post("/swatches", json={"draft_id": 9999}).status_code == 404


def test_list_swatches_filters_by_project(client: TestClient) -> None:
    a = client.post("/drafts", json={"text": DRAFT, "project_id": "alpha"}).json()
    b = client.post(
        "/drafts", json={"text": "Second winner here.", "project_id": "beta"}
    ).json()
    client.post("/swatches", json={"draft_id": a["id"]})
    client.post("/swatches", json={"draft_id": b["id"]})
    alpha = client.get("/swatches", params={"project_id": "alpha"}).json()
    assert len(alpha) == 1
    assert alpha[0]["project_id"] == "alpha"
    everything = client.get("/swatches").json()
    assert len(everything) == 2
