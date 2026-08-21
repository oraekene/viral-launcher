from __future__ import annotations

import argparse
import json
import sys

from launcher.config import Settings
from launcher.db import bootstrap
from launcher.features import extract
from launcher.gate import load_engine


def _gate_payload(settings: Settings, args: argparse.Namespace) -> dict[str, object]:
    factory = bootstrap(settings.database_url)
    with factory() as session:
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
            "lines": [
                {
                    "rule_id": line.rule_id,
                    "verdict": line.verdict,
                    "detail": line.detail,
                    "source_note": line.source_note,
                }
                for line in report.lines
            ],
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

    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.command == "init":
        bootstrap(settings.database_url)
        print(json.dumps({"ok": True, "database": settings.database_url}))
        return 0

    if args.command == "gate":
        print(json.dumps(_gate_payload(settings, args), indent=2))
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
