from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ParamVersion(Base):
    __tablename__ = "param_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    system: Mapped[str] = mapped_column(String(32), default="launcher")
    key: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16))
    source_note: Mapped[str] = mapped_column(String(512))


class GateRule(Base):
    __tablename__ = "gate_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    position: Mapped[int] = mapped_column(Integer)
    param_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_note: Mapped[str] = mapped_column(String(512))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text: Mapped[str] = mapped_column(String(4000))
    author_followers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mutuals_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allow_premium_length: Mapped[bool] = mapped_column(Boolean, default=False)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gate_report: Mapped[list[dict[str, str]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DraftVariant(Base):
    __tablename__ = "draft_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"))
    text: Mapped[str] = mapped_column(String(4000))
    variant_index: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    gate_lines: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    vetoed: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PredictorModel(Base):
    __tablename__ = "predictor_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    n_events: Mapped[int] = mapped_column(Integer)
    precision: Mapped[float] = mapped_column(Float)
    recall: Mapped[float] = mapped_column(Float)
    band_width: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    algorithm: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32))
    feature_names: Mapped[list[str]] = mapped_column(JSON)
    feature_importances: Mapped[dict[str, float]] = mapped_column(JSON)
    model_blob: Mapped[bytes] = mapped_column(LargeBinary)


class CostEvent(Base):
    __tablename__ = "cost_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id"))
    kind: Mapped[str] = mapped_column(String(32))
    usd: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
