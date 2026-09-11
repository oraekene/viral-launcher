"""CLI smoke harness (#10): subprocess runs against a temp database.

No network: the key is unset so the heuristic provider serves rewrites.
Each case asserts the exit code plus the payload shape of one command.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLEAN = (
    "We cut our release cycle from 14 days to 2 by deleting half the checklist. "
    "Speed was never the constraint. Fear was. What would you add?"
)


def _run(db: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["LAUNCHER_DATABASE_URL"] = f"sqlite:///{db}"
    env.pop("LAUNCHER_LLM_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-m", "launcher.cli", *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=env,
        timeout=180,
    )


def test_init_creates_database(tmp_path: Path) -> None:
    proc = _run(tmp_path / "cli.db", "init")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["ok"] is True


def test_gate_reports_verdict(tmp_path: Path) -> None:
    _run(tmp_path / "cli.db", "init")
    proc = _run(tmp_path / "cli.db", "gate", CLEAN)
    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert body["verdict"] == "passed"
    assert body["lines"] and all("source_note" in line for line in body["lines"])
    vetoed = _run(tmp_path / "cli.db", "gate", "Like if you agree!")
    assert vetoed.returncode == 0, vetoed.stderr
    assert json.loads(vetoed.stdout)["verdict"] == "vetoed"


def test_rewrite_returns_top(tmp_path: Path) -> None:
    _run(tmp_path / "cli.db", "init")
    proc = _run(tmp_path / "cli.db", "rewrite", CLEAN, "--n", "2")
    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert body["generated"] >= 1
    assert body["top"]
    assert all(v["score"] is not None for v in body["top"])


def test_batch_processes_file(tmp_path: Path) -> None:
    drafts = tmp_path / "drafts.json"
    drafts.write_text(
        json.dumps([{"text": CLEAN}, {"text": "Second draft about shipping fast."}]),
        encoding="utf-8",
    )
    _run(tmp_path / "cli.db", "init")
    proc = _run(tmp_path / "cli.db", "batch", str(drafts), "--rewrite", "--n", "2")
    assert proc.returncode == 0, proc.stderr
    results = json.loads(proc.stdout)["results"]
    assert len(results) == 2
    assert all(isinstance(r["draft_id"], int) and isinstance(r["top"], list) for r in results)


def test_unknown_command_exits_2(tmp_path: Path) -> None:
    proc = _run(tmp_path / "cli.db", "frobnicate")
    assert proc.returncode == 2


def test_batch_missing_file_exits_nonzero(tmp_path: Path) -> None:
    proc = _run(tmp_path / "cli.db", "batch", str(tmp_path / "absent.json"))
    assert proc.returncode != 0


def test_relay_commands_need_worker_config(tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    _run(db, "init")
    enqueue = _run(db, "relay-enqueue", "relay-1", "voicea")
    assert enqueue.returncode == 2
    assert "LAUNCHER_WORKER_BASE_URL" in enqueue.stderr
    collect = _run(db, "relay-collect", "relay-1", "user-a")
    assert collect.returncode == 2
    assert "LAUNCHER_WORKER_BASE_URL" in collect.stderr
