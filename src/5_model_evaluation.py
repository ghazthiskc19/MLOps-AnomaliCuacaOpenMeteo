"""Fixed-label metrics and chronological holdout/folds for LK06."""

import math

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import TimeSeriesSplit

LABELS = [0, 1, 2]


def chronological_folds(frame: pd.DataFrame, test_fraction: float = 0.2, n_splits: int = 3):
    """Last 20% held out; expanding equal-duration folds in development only."""
    if len(frame) < 20 or not 0 < test_fraction < 0.5 or n_splits < 2:
        raise ValueError("Data terlalu sedikit atau konfigurasi split tidak valid.")
    if not frame.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Split memerlukan timestamp hourly yang terurut dan unik.")
    test_size = math.ceil(len(frame) * test_fraction)
    development = frame.iloc[:-test_size].copy().reset_index(drop=True)
    test = frame.iloc[-test_size:].copy().reset_index(drop=True)
    folds = list(TimeSeriesSplit(n_splits=n_splits).split(development))
    for number, (train, validation) in enumerate(folds, 1):
        classes = set(development.anomaly_class.iloc[train].unique())
        if classes != set(LABELS):
            raise ValueError(f"Train fold {number} tidak memiliki seluruh kelas {LABELS}: {sorted(classes)}")
        if development.timestamp.iloc[train[-1]] >= development.timestamp.iloc[validation[0]]:
            raise ValueError("Train tidak boleh melampaui waktu validation.")
    return development, test, folds


def classification_metrics(y_true, y_pred):
    """Return finite loggable metrics, honest support/undefined values, 3x3 CM.

    Fixed-3-class macro F1 uses zero_division=0. Missing true classes have no
    measurable recall, represented as null in the report, not asserted failures.
    """
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    if len(y_true) == 0 or y_true.shape != y_pred.shape:
        raise ValueError("Target/prediksi harus nonempty dengan ukuran sama.")
    if not set(np.unique(y_true)).issubset(LABELS) or not set(np.unique(y_pred)).issubset(LABELS):
        raise ValueError(f"Label di luar kontrak {LABELS}.")
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, zero_division=0,
    )
    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)),
        "balanced_accuracy": float(np.mean(recall[support > 0])),
    }
    classes = {}
    for i, label in enumerate(LABELS):
        predicted = int(np.count_nonzero(y_pred == label))
        classes[str(label)] = {
            "precision": float(precision[i]) if predicted else None,
            "recall": float(recall[i]) if support[i] else None,
            "f1": float(f1[i]) if support[i] or predicted else None,
            "support": int(support[i]), "predicted_count": predicted,
        }
        metrics[f"support_class_{label}"] = float(support[i])
        metrics[f"f1_class_{label}"] = float(f1[i])
        if support[i]:
            metrics[f"recall_class_{label}"] = float(recall[i])
        if predicted:
            metrics[f"precision_class_{label}"] = float(precision[i])
    report = {
        "classes": classes,
        "absent_true_classes": [label for i, label in enumerate(LABELS) if not support[i]],
        "macro_f1_policy": "fixed labels [0,1,2]; undefined terms contribute 0",
        "balanced_accuracy_policy": "mean recall over classes present in y_true",
    }
    return metrics, report, confusion_matrix(y_true, y_pred, labels=LABELS)
