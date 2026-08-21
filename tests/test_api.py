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


CLEAN_DRAFT = (
    "We cut our release cycle from 14 days to 2 by deleting half the checklist. "
    "Speed was never the constraint. Fear was.\n\nWhat would you add?"
)


def test_create_draft_returns_sourced_report(client: TestClient) -> None:
    resp = client.post("/drafts", json={"text": CLEAN_DRAFT})
    assert resp.status_code == 201
    body = resp.json()
    assert body["verdict"] == "passed"
    assert len(body["gate_report"]) > 0
    for line in body["gate_report"]:
        assert line["source_note"]


def test_vetoed_draft_is_persisted(client: TestClient) -> None:
    created = client.post("/drafts", json={"text": "Like if you agree!"}).json()
    fetched = client.get(f"/drafts/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["verdict"] == "vetoed"


def test_get_missing_draft_404(client: TestClient) -> None:
    assert client.get("/drafts/9999").status_code == 404


def test_rules_listing_and_toggle(client: TestClient) -> None:
    rules = client.get("/rules").json()
    names = {r["name"] for r in rules}
    assert "negative.engagement_bait" in names

    target = next(r for r in rules if r["name"] == "elicitation.question")
    toggled = client.post(f"/rules/{target['id']}/toggle").json()
    assert toggled["enabled"] is False

    resp = client.post("/drafts", json={"text": "Plain statement with no question at all."})
    rule_ids = {l["rule_id"] for l in resp.json()["gate_report"]}
    assert "elicitation.question" not in rule_ids


def test_params_endpoint_exposes_provenance(client: TestClient) -> None:
    params = {p["key"]: p for p in client.get("/params").json()}
    assert params["weight.reply"]["value"] == 5.0
    assert params["weight.reply"]["status"] == "sourced"
    assert params["z.trigger"]["status"] == "pending"


def test_costs_summary_starts_at_zero(client: TestClient) -> None:
    summary = client.get("/costs").json()
    assert summary["total_usd"] == 0.0
    assert summary["events"] == 0


def test_blank_draft_rejected(client: TestClient) -> None:
    assert client.post("/drafts", json={"text": ""}).status_code == 422
