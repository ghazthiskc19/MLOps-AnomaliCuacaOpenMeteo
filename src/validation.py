"""Fail-closed validation: insufficient evidence never becomes a passing score."""
import math
import numpy as np
from src.model_evaluation import classification_metrics


def validation_decision(actual, predicted, *, threshold=.85, min_support=5,
                        min_fault_recall=.85, max_false_alarm_rate=.05):
    for value in [threshold, min_fault_recall, max_false_alarm_rate]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Threshold harus finite di [0,1].")
    if type(min_support) is not int or min_support < 1:
        raise ValueError("min_support harus integer positif.")
    metrics, report, matrix = classification_metrics(actual, predicted)
    under = [str(c) for c in (0,1,2) if metrics[f"support_class_{c}"] < min_support]
    normal = np.asarray(actual) == 0
    false_alarm = float(np.mean(np.asarray(predicted)[normal] != 0)) if normal.any() else None
    reasons = []
    if metrics["f1_macro"] <= threshold:
        reasons.append("macro_f1_not_strictly_above_threshold")
    if metrics.get("recall_class_1", 0.) < min_fault_recall:
        reasons.append("fault_recall_below_threshold")
    if false_alarm is None or false_alarm > max_false_alarm_rate:
        reasons.append("false_alarm_rate_unavailable_or_excessive")
    return {"passed": not under and not reasons,
        "status": "insufficient_coverage" if under else ("failed_performance" if reasons else "passed"),
        "under_supported_classes": under, "performance_failures": reasons,
        "metrics": metrics, "false_alarm_rate": false_alarm, "report": report,
        "confusion_matrix": matrix.tolist(), "policy": {"threshold": threshold,
        "comparison": ">", "min_support": min_support, "min_fault_recall": min_fault_recall,
        "max_false_alarm_rate": max_false_alarm_rate, "scope": "rule pseudo-label agreement, not field validation"}}
