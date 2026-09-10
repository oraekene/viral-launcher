from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session

from launcher.config import Settings
from launcher.db import bootstrap
from launcher.features import extract
from launcher.gate import load_engine
from launcher.models import Draft
from launcher.params import ParamStore
from launcher.rewriter import default_provider, rewrite_flow, try_rewrite_flow


@contextmanager
def session_scope(settings: Settings) -> Iterator[Session]:
    factory = bootstrap(settings.database_url)
    with factory() as session:
        yield session


def _gate_payload(settings: Settings, args: argparse.Namespace) -> dict[str, object]:
    with session_scope(settings) as session:
        engine = load_engine(session)
        features = extract(
            args.text,
            author_followers=args.followers,
            mutuals_count=args.mutuals,
            allow_premium_length=args.premium,
        )
        report = engine.evaluate(features)
        return {
            "verdict": report.verdict,
            "lines": [line.as_dict() for line in report.lines],
        }


def _rewrite_payload(settings: Settings, args: argparse.Namespace) -> dict[str, object]:
    with session_scope(settings) as session:
        draft = Draft(
            text=args.text,
            author_followers=args.followers,
            mutuals_count=args.mutuals,
        )
        session.add(draft)
        session.flush()
        provider = default_provider(settings, ParamStore(session))
        result = rewrite_flow(session, draft.id, provider, n=args.n)
        session.commit()
        return {
            "draft_id": result.draft_id,
            "generated": result.generated,
            "vetoed_count": result.vetoed_count,
            "cost_usd": result.cost_usd,
            "top": [
                {
                    "id": v.id,
                    "text": v.text,
                    "score": v.score,
                    "reasons": list(v.reasons),
                }
                for v in result.top
            ],
        }


def _batch_payload(settings: Settings, args: argparse.Namespace) -> dict[str, object]:
    items: list[dict[str, object]] = json.loads(
        Path(args.path).read_text(encoding="utf-8")
    )
    results: list[dict[str, object]] = []
    with session_scope(settings) as session:
        provider = default_provider(settings, ParamStore(session))
        for item in items:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            draft = Draft(text=text)
            session.add(draft)
            session.flush()
            entry: dict[str, object] = {"draft_id": draft.id}
            if args.rewrite:
                attempt = try_rewrite_flow(session, draft.id, provider, n=args.n)
                if attempt.result is not None:
                    result = attempt.result
                    entry["top"] = [
                        {"id": v.id, "text": v.text, "score": v.score}
                        for v in result.top
                    ]
                    entry["vetoed_count"] = result.vetoed_count
                    entry["cost_usd"] = result.cost_usd
                    entry["error"] = None
                else:
                    entry["top"] = []
                    entry["vetoed_count"] = 0
                    entry["cost_usd"] = 0.0
                    entry["error"] = attempt.error
            else:
                engine = load_engine(session)
                report = engine.evaluate(extract(text))
                entry["verdict"] = report.verdict
            results.append(entry)
        session.commit()
    return {"results": results}


def _relay_sync_payload(settings: Settings, args: argparse.Namespace) -> dict[str, object]:
    from launcher.relay import VoiceKey, relay_sync
    from launcher.relay_routes import RelaySyncIn

    data = RelaySyncIn.model_validate(json.loads(Path(args.path).read_text(encoding="utf-8")))
    with session_scope(settings) as session:
        result = relay_sync(
            session,
            VoiceKey(data.worker_user_id, data.screen_name),
            [t.model_dump() for t in data.tweets],
            author_followers=data.author_followers,
            mutuals_count=data.mutuals_count,
        )
        session.commit()
    report = result.report
    return {
        "project_id": result.project_id,
        "staged": result.staged,
        "calibrated": report.calibrated,
        "applied": report.applied,
        "n_outcomes": report.n_outcomes,
        "winner_share": report.winner_share,
        "new_z_trigger": report.new_z_trigger,
        "reason": report.reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="launcher")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database and seed params + rules")

    p_gate = sub.add_parser("gate", help="evaluate a draft through the gate")
    p_gate.add_argument("text")
    p_gate.add_argument("--followers", type=int, default=None)
    p_gate.add_argument("--mutuals", type=int, default=None)
    p_gate.add_argument("--premium", action="store_true")

    p_serve = sub.add_parser("serve", help="run the HTTP API")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    p_rewrite = sub.add_parser("rewrite", help="create a draft and rewrite it")
    p_rewrite.add_argument("text")
    p_rewrite.add_argument("--n", type=int, default=None)
    p_rewrite.add_argument("--followers", type=int, default=None)
    p_rewrite.add_argument("--mutuals", type=int, default=None)

    p_batch = sub.add_parser("batch", help="process a JSON file of drafts")
    p_batch.add_argument("path")
    p_batch.add_argument("--rewrite", action="store_true")
    p_batch.add_argument("--n", type=int, default=None)

    p_sync = sub.add_parser(
        "relay-sync", help="stage relay-observed own posts and rerun calibration"
    )
    p_sync.add_argument("path", help="JSON file: worker_user_id, screen_name, tweets")

    p_token = sub.add_parser(
        "tenant-token", help="issue a bearer token for a tenant (#5)"
    )
    p_token.add_argument("worker_user_id", help="Worker user id owning the token")

    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.command == "init":
        bootstrap(settings.database_url)
        print(json.dumps({"ok": True, "database": settings.database_url}))
        return 0

    if args.command == "gate":
        print(json.dumps(_gate_payload(settings, args), indent=2))
        return 0

    if args.command == "rewrite":
        print(json.dumps(_rewrite_payload(settings, args), indent=2))
        return 0

    if args.command == "batch":
        print(json.dumps(_batch_payload(settings, args), indent=2))
        return 0

    if args.command == "relay-sync":
        print(json.dumps(_relay_sync_payload(settings, args), indent=2))
        return 0

    if args.command == "tenant-token":
        from launcher.tenancy import issue_token

        with session_scope(settings) as session:
            token = issue_token(session, args.worker_user_id)
            session.commit()
        print(json.dumps({"worker_user_id": args.worker_user_id, "token": token}))
        return 0

    if args.command == "serve":
        import uvicorn

        from launcher.api import create_app

        factory = bootstrap(settings.database_url)
        uvicorn.run(create_app(factory), host=args.host, port=args.port)
        return 0

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
