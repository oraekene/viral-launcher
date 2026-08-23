from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from launcher.api import create_app
from launcher.models import Base
from launcher.seed import seed_all


def _make_client() -> tuple[TestClient, sessionmaker[Session]]:
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
    return TestClient(create_app(factory)), factory


@pytest.fixture()
def client() -> TestClient:
    return _make_client()[0]


def test_record_label(client: TestClient) -> None:
    resp = client.post(
        "/labels",
        json={"label_name": "downranked_by_spam_heuristic", "meaning": "reach limited"},
    )
    assert resp.status_code == 201
    listed = client.get("/labels").json()
    assert len(listed) == 1
    assert listed[0]["source"] == "manual"
    assert listed[0]["label_name"] == "downranked_by_spam_heuristic"


def test_fresh_label_warns_on_draft(client: TestClient) -> None:
    client.post("/labels", json={"label_name": "limited_reach"})
    resp = client.post("/drafts", json={"text": "Some draft about shipping."})
    warnings = resp.json()["label_warnings"]
    assert len(warnings) == 1
    assert "limited_reach" in warnings[0]


def test_stale_label_does_not_warn(client: TestClient) -> None:
    client_obj, factory = _make_client()
    client_obj.post("/labels", json={"label_name": "old_flag"})

    from launcher.models import AccountLabel, utcnow

    with factory() as s:
        label = s.query(AccountLabel).one()
        label.observed_at = utcnow() - timedelta(days=45)
        s.commit()

    resp = client_obj.post("/drafts", json={"text": "Another draft entirely."})
    assert resp.json()["label_warnings"] == []


def test_label_free_account_gets_no_warnings(client: TestClient) -> None:
    resp = client.post("/drafts", json={"text": "Clean account draft."})
    assert resp.json()["label_warnings"] == []
