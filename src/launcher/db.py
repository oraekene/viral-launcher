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


def bootstrap(database_url: str) -> sessionmaker[Session]:
    engine = make_engine(database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        seed_all(session)
        session.commit()
    return factory
