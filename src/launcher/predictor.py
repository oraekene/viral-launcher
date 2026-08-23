from __future__ import annotations

import math
import pickle
from dataclasses import dataclass

from sklearn.ensemble import GradientBoostingRegressor
from sqlalchemy.orm import Session

from launcher.features import DraftFeatures
from launcher.models import PredictorModel
from launcher.outcomes import OutcomeRow, OutcomeSource
from launcher.params import ParamStore

FEATURE_NAMES: tuple[str, ...] = (
    "char_len",
    "word_count",
    "question_count",
    "has_question",
    "has_cta",
    "quotable_claim",
    "link_count",
    "hashtag_count",
    "mention_count",
    "exclamation_count",
    "thread_marker",
    "bait_hits",
    "mass_markers",
    "pod_hits",
    "log_followers",
    "mutuals",
    "premium_length",
    "swatch_similarity",
)

ALGORITHM = "gradient_boosting_regressor.v2"
MIN_EVENTS = 200


def feature_values(
    features: DraftFeatures, swatch_similarity: float = 0.0
) -> dict[str, float]:
    return {
        "char_len": float(features.char_len),
        "word_count": float(features.word_count),
        "question_count": float(features.question_count),
        "has_question": 1.0 if features.has_question else 0.0,
        "has_cta": 1.0 if features.has_cta else 0.0,
        "quotable_claim": 1.0 if features.quotable_claim else 0.0,
        "link_count": float(features.link_count),
        "hashtag_count": float(features.hashtag_count),
        "mention_count": float(features.mention_count),
        "exclamation_count": float(features.exclamation_count),
        "thread_marker": 1.0 if features.thread_marker else 0.0,
        "bait_hits": float(len(features.engagement_bait_hits)),
        "mass_markers": float(len(features.mass_reply_markers)),
        "pod_hits": float(len(features.pod_signature_hits)),
        "log_followers": (
            math.log1p(features.author_followers)
            if features.author_followers is not None
            else 0.0
        ),
        "mutuals": (
            float(features.mutuals_count) if features.mutuals_count is not None else 0.0
        ),
        "premium_length": 1.0 if features.allow_premium_length else 0.0,
        "swatch_similarity": swatch_similarity,
    }


def feature_vector(
    features: DraftFeatures, swatch_similarity: float = 0.0
) -> list[float]:
    values = feature_values(features, swatch_similarity)
    return [values[name] for name in FEATURE_NAMES]


@dataclass(frozen=True)
class Prediction:
    predicted_z: float
    band_width: float
    model_id: int
    model_status: str


@dataclass(frozen=True)
class ModelArtifact:
    row: PredictorModel
    fitted: GradientBoostingRegressor


def load_artifact(session: Session, project_id: str | None) -> ModelArtifact | None:
    if not project_id:
        return None
    row = active_model(session, project_id)
    if row is None:
        return None
    return ModelArtifact(row=row, fitted=pickle.loads(bytes(row.model_blob)))


def active_model(session: Session, project_id: str) -> PredictorModel | None:
    return (
        session.query(PredictorModel)
        .filter_by(project_id=project_id)
        .order_by(PredictorModel.trained_at.desc(), PredictorModel.id.desc())
        .first()
    )


def train_predictor(
    session: Session,
    project_id: str,
    source: OutcomeSource,
) -> PredictorModel:
    rows = source.load_outcomes(project_id)
    if len(rows) < MIN_EVENTS:
        raise ValueError(
            f"need >= {MIN_EVENTS} labeled events, got {len(rows)}"
        )

    store = ParamStore(session)
    trigger = store.get_float("z.trigger")

    X = [[row.features[name] for name in FEATURE_NAMES] for row in rows]
    y_z = [row.z60 for row in rows]
    y_flag = [row.value_flag for row in rows]

    split = int(len(rows) * 0.8)
    holdout = GradientBoostingRegressor(random_state=7)
    holdout.fit(X[:split], y_z[:split])
    held_pred = list(holdout.predict(X[split:]))

    tp = fp = fn = 0
    residuals: list[float] = []
    for pred, actual_z, flag in zip(held_pred, y_z[split:], y_flag[split:], strict=True):
        residuals.append(pred - actual_z)
        pred_flag = pred >= trigger
        if pred_flag and flag:
            tp += 1
        elif pred_flag and not flag:
            fp += 1
        elif not pred_flag and flag:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    final = GradientBoostingRegressor(random_state=7)
    final.fit(X, y_z)
    raw_importances = final.feature_importances_
    total = sum(raw_importances) or 1.0
    importances = {
        name: round(float(imp) / total, 4)
        for name, imp in zip(FEATURE_NAMES, raw_importances, strict=True)
    }

    mean_residual = sum(residuals) / len(residuals) if residuals else 0.0
    variance = sum((r - mean_residual) ** 2 for r in residuals) / len(residuals) if residuals else 0.0

    row = PredictorModel(
        project_id=project_id,
        n_events=len(rows),
        training_winner_share=round(sum(y_flag) / len(y_flag), 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
        band_width=round(max(variance**0.5, 0.25), 4),
        status="pending",
        algorithm=ALGORITHM,
        source=getattr(source, "__class__").__name__,
        feature_names=list(FEATURE_NAMES),
        feature_importances=importances,
        model_blob=pickle.dumps(final),
    )
    session.add(row)
    session.flush()
    return row


def predict_z(
    session: Session,
    project_id: str | None,
    features: DraftFeatures,
    swatch_similarity: float = 0.0,
) -> Prediction | None:
    artifact = load_artifact(session, project_id)
    if artifact is None:
        return None
    values = feature_values(features, swatch_similarity)
    names = list(artifact.row.feature_names or FEATURE_NAMES)
    x = [[values[name] for name in names]]
    z = max(0.0, float(artifact.fitted.predict(x)[0]))
    return Prediction(
        predicted_z=round(z, 4),
        band_width=artifact.row.band_width,
        model_id=artifact.row.id,
        model_status=artifact.row.status,
    )
