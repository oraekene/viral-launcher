from __future__ import annotations

from typing import Sequence


def precision_recall(pred_flags: Sequence[bool], flags: Sequence[bool]) -> tuple[float, float]:
    tp = fp = fn = 0
    for pred, actual in zip(pred_flags, flags, strict=True):
        if pred and actual:
            tp += 1
        elif pred and not actual:
            fp += 1
        elif not pred and actual:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall
