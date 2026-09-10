"""Tenancy isolation tests (#5, ADR-0004).

Acceptance: user A cannot read, score, or calibrate user B projects.
Enforcement is active once any tenant token exists (open single-operator
mode before that). Cross-tenant resource access returns 404 (no leak);
payload owner mismatch returns 403; missing/invalid token returns 401.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from launcher.api import create_app
from launcher.models import Base
from launcher.relay import VoiceKey, bind_voice
from launcher.seed import seed_all
from launcher.tenancy import issue_token

CLEAN = (
    "We cut our release cycle from 14 days to 2 by deleting half the checklist. "
    "Speed was never the constraint. Fear was. What would you add?"
)


def _make_client() -> tuple[TestClient, sessionmaker[Session], dict[str, str], dict[str, str]]:
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
        token_a = issue_token(s, "user-a")
        token_b = issue_token(s, "user-b")
        bind_voice(s, VoiceKey("user-a", "voicea"), "voice-a")
        bind_voice(s, VoiceKey("user-b", "voiceb"), "voice-b")
        s.commit()
    client = TestClient(create_app(factory))
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    return client, factory, headers_a, headers_b


def test_cross_tenant_draft_read_denied() -> None:
    client, _, ha, hb = _make_client()
    created = client.post(
        "/drafts", json={"text": CLEAN, "project_id": "voice-a"}, headers=ha
    )
    assert created.status_code == 201, created.text
    draft_id = created.json()["id"]
    denied = client.get(f"/drafts/{draft_id}", headers=hb)
    assert denied.status_code == 404
    allowed = client.get(f"/drafts/{draft_id}", headers=ha)
    assert allowed.status_code == 200


def test_cross_tenant_score_denied() -> None:
    client, _, ha, hb = _make_client()
    created = client.post(
        "/drafts", json={"text": CLEAN, "project_id": "voice-a"}, headers=ha
    )
    draft_id = created.json()["id"]
    denied = client.post(f"/drafts/{draft_id}/score", headers=hb)
    assert denied.status_code == 404
    allowed = client.post(f"/drafts/{draft_id}/score", headers=ha)
    assert allowed.status_code == 200


def test_cross_tenant_calibrate_denied() -> None:
    client, _, ha, hb = _make_client()
    denied = client.post(
        "/calibration/run", json={"project_id": "voice-a"}, headers=hb
    )
    assert denied.status_code == 404
    allowed = client.post(
        "/calibration/run", json={"project_id": "voice-a"}, headers=ha
    )
    assert allowed.status_code == 200


def test_unauthenticated_denied_when_enforced() -> None:
    client, _, ha, _ = _make_client()
    assert client.get("/models", headers={}).status_code == 401
    assert client.get("/models", headers=ha).status_code == 200


def test_voices_scoped_to_caller() -> None:
    client, _, ha, hb = _make_client()
    listed_b = client.get("/voices", headers=hb).json()
    assert {v["project_id"] for v in listed_b} == {"voice-b"}
    forbidden = client.post(
        "/voices",
        json={"worker_user_id": "user-a", "screen_name": "evil", "project_id": "voice-evil"},
        headers=hb,
    )
    assert forbidden.status_code == 403


def test_relay_sync_enforces_owner() -> None:
    client, _, ha, hb = _make_client()
    tweet = {
        "id": "1",
        "author": "voiceb",
        "text": CLEAN,
        "favorite_count": 5,
        "retweet_count": 0,
        "reply_count": 0,
    }
    forbidden = client.post(
        "/outcomes/relay-sync",
        json={"worker_user_id": "user-a", "screen_name": "voicea", "tweets": [tweet]},
        headers=hb,
    )
    assert forbidden.status_code == 403


def test_shared_toggle_forbidden_when_enforced() -> None:
    client, _, ha, _ = _make_client()
    rules = client.get("/rules", headers=ha).json()
    assert rules
    denied = client.post(f"/rules/{rules[0]['id']}/toggle", headers=ha)
    assert denied.status_code == 403


def test_open_mode_allows_all() -> None:
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
    client = TestClient(create_app(factory))
    created = client.post("/drafts", json={"text": CLEAN, "project_id": "any"})
    assert created.status_code == 201
    assert client.get(f"/drafts/{created.json()['id']}").status_code == 200
