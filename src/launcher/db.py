from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from launcher.models import Base
from launcher.seed import seed_all


def make_engine(database_url: str) -> Engine:
    kwargs: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    if engine.url.drivername.startswith("sqlite"):
        ensure_column(engine, "voice_bindings", "viral_floor", "REAL")
        ensure_column(engine, "voice_bindings", "viral_threshold", "REAL")
        ensure_column(engine, "radar_outcomes_stage", "engagement", "REAL")
        ensure_column(engine, "account_labels", "worker_user_id", "VARCHAR(64)")


def ensure_column(engine: Engine, table: str, column: str, ddl: str) -> None:
    """Add a column to an existing sqlite table when absent.

    Fresh installs get everything from create_all; this only migrates
    dev databases created before the column existed. No backfill:
    new voice columns stay NULL (house default) until set.
    """
    with engine.connect() as conn:
        cols = [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").all()]
        if column not in cols:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            conn.commit()


def bootstrap(database_url: str) -> sessionmaker[Session]:
    engine = make_engine(database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        seed_all(session)
        session.commit()
    return factory
