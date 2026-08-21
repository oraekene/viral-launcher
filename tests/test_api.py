from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from launcher.api import create_app
from launcher.models import Base
from launcher.rewriter import GenerationResult, HeuristicProvider
from launcher.seed import seed_all


class StaticPaidProvider(HeuristicProvider):
    def __init__(self, usd: float) -> None:
        self._usd = usd

    def generate(self, draft_text: str, n: int) -> GenerationResult:
        texts = tuple(
            f"{draft_text.rstrip('.')}. Variant {i}.\n\nWhat would you add?"
            for i in range(1, max(n, 1))
        )
        return GenerationResult(texts=texts, usd=self._usd, tokens_in=10, tokens_out=20)

    def estimate_cost(self, draft_text: str, n: int) -> float:
        return self._usd


def _make_client(provider: object | None = None) -> TestClient:
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
    return TestClient(create_app(factory, provider=provider))  # type: ignore[arg-type]


@pytest.fixture()
def client() -> TestClient:
    return _make_client()


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


def test_rewrite_returns_ranked_top3(client: TestClient) -> None:
    created = client.post("/drafts", json={"text": CLEAN_DRAFT}).json()
    resp = client.post(f"/drafts/{created['id']}/rewrite", json={"n": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["draft_id"] == created["id"]
    assert 1 <= len(body["top"]) <= 3
    scores = [v["score"] for v in body["top"]]
    assert scores == sorted(scores, reverse=True)
    assert all(v["reasons"] for v in body["top"])
    assert body["cost_usd"] == 0.0
    assert body["vetoed_count"] >= 0


def test_rewrite_missing_draft_404(client: TestClient) -> None:
    assert client.post("/drafts/9999/rewrite", json={"n": 3}).status_code == 404


def test_rewrite_excludes_vetoed_variants() -> None:
    class BaitProvider(HeuristicProvider):
        def generate(self, draft_text: str, n: int) -> GenerationResult:
            return GenerationResult(
                texts=(
                    "Like if you agree! Tag someone who needs this.",
                    "Fear was the constraint. What would you add?",
                ),
                usd=0.0,
                tokens_in=0,
                tokens_out=0,
            )

        def estimate_cost(self, draft_text: str, n: int) -> float:
            return 0.0

    client = _make_client(BaitProvider())
    created = client.post(
        "/drafts", json={"text": "We cut onboarding from 14 days to 2."}
    ).json()
    body = client.post(f"/drafts/{created['id']}/rewrite", json={"n": 2}).json()
    assert body["vetoed_count"] == 1
    assert all("Like if" not in v["text"] for v in body["top"])


def test_per_draft_cap_blocks_second_paid_rewrite_with_402() -> None:
    client = _make_client(StaticPaidProvider(usd=0.06))
    created = client.post("/drafts", json={"text": CLEAN_DRAFT}).json()
    first = client.post(f"/drafts/{created['id']}/rewrite", json={"n": 2})
    assert first.status_code == 200
    second = client.post(f"/drafts/{created['id']}/rewrite", json={"n": 2})
    assert second.status_code == 402
    assert "cap" in second.json()["detail"].lower()


def test_variants_persisted_and_queryable(client: TestClient) -> None:
    created = client.post("/drafts", json={"text": CLEAN_DRAFT}).json()
    client.post(f"/drafts/{created['id']}/rewrite", json={"n": 4})
    variants = client.get(f"/drafts/{created['id']}/variants").json()
    assert len(variants) >= 2
    original_rows = [v for v in variants if v["text"] == CLEAN_DRAFT]
    assert len(original_rows) == 1
    for row in variants:
        assert isinstance(row["vetoed"], bool)
        assert row["gate_lines"]


def test_batch_creates_drafts_without_rewrite(client: TestClient) -> None:
    resp = client.post(
        "/drafts/batch",
        json={"items": [{"text": CLEAN_DRAFT}, {"text": "Short one https://x.com"}]},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    assert results[0]["draft"]["verdict"] == "passed"
    assert results[0]["rewrite"] is None


def test_batch_with_rewrite_populates_results(client: TestClient) -> None:
    resp = client.post(
        "/drafts/batch",
        json={
            "items": [{"text": CLEAN_DRAFT}, {"text": "Second draft about shipping fast."}],
            "rewrite": True,
            "n": 3,
        },
    )
    results = resp.json()["results"]
    assert all(r["rewrite"] is not None for r in results)
    assert all(r["rewrite"]["cost_usd"] == 0.0 for r in results)


def test_draft_costs_listing(client: TestClient) -> None:
    created = client.post("/drafts", json={"text": CLEAN_DRAFT}).json()
    client.post(f"/drafts/{created['id']}/rewrite", json={"n": 2})
    events = client.get(f"/drafts/{created['id']}/costs").json()
    assert len(events) == 1
    assert events[0]["kind"] == "heuristic"


def test_top3_includes_gate_verdicts(client: TestClient) -> None:
    created = client.post("/drafts", json={"text": CLEAN_DRAFT}).json()
    body = client.post(f"/drafts/{created['id']}/rewrite", json={"n": 3}).json()
    assert body["top"]
    for variant in body["top"]:
        assert variant["gate_lines"]
        assert all(l["source_note"] for l in variant["gate_lines"])


def test_batch_continues_past_budget_block() -> None:
    client = _make_client(StaticPaidProvider(usd=0.50))
    resp = client.post(
        "/drafts/batch",
        json={
            "items": [{"text": CLEAN_DRAFT}, {"text": "Second draft about shipping."}],
            "rewrite": True,
            "n": 2,
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    for r in results:
        rewrite = r["rewrite"]
        assert rewrite is not None
        assert rewrite["error"] is not None
        assert "cap" in rewrite["error"].lower()
        assert rewrite["top"] == []


def test_scheduling_beyond_48h_warns(client: TestClient) -> None:
    from datetime import datetime, timedelta, timezone

    future = datetime.now(timezone.utc) + timedelta(hours=72)
    resp = client.post(
        "/drafts",
        json={"text": CLEAN_DRAFT, "scheduled_at": future.isoformat()},
    )
    lines = {l["rule_id"]: l for l in resp.json()["gate_report"]}
    timing = lines["timing.engagement_window"]
    assert timing["verdict"] == "warn"
    assert "48" in timing["detail"]
