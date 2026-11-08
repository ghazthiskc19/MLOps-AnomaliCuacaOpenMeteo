"""Versioned hybrid classifier: deterministic fault guards + learned environment.

Legacy 37-feature artifacts remain supported by src.training_data. This v2
contract has 41 features. RF learns normal/extreme only; guard agreement is
reported separately and must never be described as learned RF accuracy.
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import RandomForestClassifier
from sklearn.utils.validation import check_is_fitted

from src.data_preprocessing import AnomalyLabeler, FeatureEngineer, RAW_COLUMNS
from src.training_data import feature_columns, normalize_raw

CONTRACT_VERSION = "weather-guarded-v2"
INDICATORS = ("temp_std_12h", "humidity_stuck_100_24h", "wind_zero_48h", "soil_waterlogged_48h")
TRUSTED_TYPES = ["sklearn.tree._tree.Tree", "src.weather_model.GuardedWeatherClassifier"]


def model_frame(raw):
    """Causal numeric features, 48-hour warm-up, strict finite training data.

    Physical raw values are preserved. Only biophysical formula inputs are
    bounded to the declared operating range; guards handle OOB observations.
    """
    normalized = normalize_raw(raw)
    if len(normalized) < 49:
        raise ValueError("Butuh minimal 49 baris histori hourly.")
    labeler, engineer = AnomalyLabeler(), FeatureEngineer()
    labelled = labeler.label(normalized)
    with np.errstate(all="ignore"):
        frame = engineer.transform(labelled)
    bounded_temp = normalized.temperature_2m_C.clip(-20., 55.)
    frame["vpd_kpa"] = engineer.calculate_vpd(bounded_temp, normalized.humidity_percent)
    frame["dew_point_C"] = engineer.calculate_dew_point(bounded_temp, normalized.humidity_percent)
    indicators = labeler.compute_anomaly_indicators(normalized)
    for name in INDICATORS:
        frame[name] = indicators[name].astype(float)
    frame = frame.iloc[48:].copy().reset_index(drop=True)
    values = frame[feature_columns(frame)].to_numpy(float)
    if not np.isfinite(values).all() or (np.abs(values) > np.finfo(np.float32).max).any():
        raise ValueError("Fitur v2 harus finite dan muat float32.")
    return frame


def fault_for_features(row):
    row = row.copy()
    row["timestamp"] = pd.Timestamp("2000-01-01") + pd.Timedelta(hours=float(row["hour"]))
    return AnomalyLabeler().classify_fault(row)


class GuardedWeatherClassifier(ClassifierMixin, BaseEstimator):
    def __init__(self, n_estimators=100, max_depth=None, min_samples_leaf=1,
                 class_weight=None, random_state=42):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.class_weight = class_weight
        self.random_state = random_state

    def fit(self, X, y):
        if not isinstance(X, pd.DataFrame) or X.columns.duplicated().any():
            raise ValueError("Model v2 memerlukan DataFrame fitur bernama unik.")
        required = set(RAW_COLUMNS[1:]) | set(INDICATORS) | {"hour", "temp_diff_1h", "soil_diff_1h"}
        if not required <= set(X.columns) or not np.isfinite(X.to_numpy(float)).all():
            raise ValueError("Kontrak fitur v2 tidak lengkap atau nonfinite.")
        y = np.asarray(y)
        if y.shape != (len(X),) or not set(np.unique(y)) <= {0, 1, 2}:
            raise ValueError("Target di luar kontrak 0/1/2.")
        environment = y != 1
        if set(y[environment]) != {0, 2}:
            raise ValueError("RF membutuhkan contoh normal dan extreme pada development.")
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = len(X.columns)
        self.classes_ = np.array([0, 1, 2])
        self.forest_ = RandomForestClassifier(n_estimators=self.n_estimators,
            max_depth=self.max_depth, min_samples_leaf=self.min_samples_leaf,
            class_weight=self.class_weight, random_state=self.random_state, n_jobs=1)
        # Environmental labels are instantaneous; calendar/contaminated rolling
        # features are unnecessary shortcuts for this explicitly scoped task.
        self.forest_.fit(X.loc[environment, RAW_COLUMNS[1:]], y[environment])
        return self

    def predict_details(self, X):
        check_is_fitted(self, "forest_")
        if not isinstance(X, pd.DataFrame) or list(X.columns) != list(self.feature_names_in_):
            raise ValueError("Nama/urutan fitur berbeda dari kontrak v2.")
        if not np.isfinite(X.to_numpy(float)).all():
            raise ValueError("Fitur nonfinite; gunakan raw input quality route.")
        guards = [fault_for_features(row) for _, row in X.iterrows()]
        result = pd.DataFrame(index=np.arange(len(X)), columns=["prediction", "decision_source", "reason", "rf_confidence"])
        learned = np.array([guard is None for guard in guards])
        if learned.any():
            environment_features = X.iloc[learned][RAW_COLUMNS[1:]]
            result.loc[learned, "prediction"] = self.forest_.predict(environment_features)
            result.loc[learned, "rf_confidence"] = self.forest_.predict_proba(environment_features).max(axis=1)
            result.loc[learned, "decision_source"] = "random_forest"
            result.loc[learned, "reason"] = "RF normal/extreme prediction; confidence is uncalibrated"
        for i, guard in enumerate(guards):
            if guard is not None:
                result.loc[i] = [1, "safety_guard", guard[1], None]
        result["prediction"] = result.prediction.astype(int)
        return result

    def predict(self, X):
        return self.predict_details(X).prediction.to_numpy(dtype=int)


def predict_latest(model, raw_history):
    """Public raw serving entry point. No invented values or normal fallback.

    Invalid current sensor => explicit input-quality fault. Invalid past context
    => abstain until 49 valid consecutive observations are available. Time/schema
    errors remain validation errors. Confidence is absent for deterministic routes.
    """
    check_is_fitted(model, "forest_")
    incoming = raw_history.copy()
    if len(incoming.columns) != len(RAW_COLUMNS) or set(incoming.columns) != set(RAW_COLUMNS):
        raise ValueError("Skema raw tidak sesuai kontrak.")
    for column in RAW_COLUMNS[1:]:
        incoming[column] = pd.to_numeric(incoming[column], errors="coerce")
    normalized = normalize_raw(incoming, allow_nonfinite=True)
    if len(normalized) < 49:
        raise ValueError("Butuh minimal 49 baris histori hourly.")
    normalized = normalized.iloc[-49:].reset_index(drop=True)
    if not np.isfinite(normalized.iloc[-1, 1:].to_numpy(float)).all():
        return {"status": "fault", "prediction": 1, "decision_source": "input_quality",
                "reason": "Current sensor is missing, nonnumeric or nonfinite", "rf_confidence": None}
    if not np.isfinite(normalized.iloc[:, 1:].to_numpy(float)).all():
        return {"status": "insufficient_history", "prediction": None,
                "decision_source": "input_quality", "reason": "Missing/nonfinite history; no imputation", "rf_confidence": None}
    indicators = AnomalyLabeler().compute_anomaly_indicators(normalized)
    guard = AnomalyLabeler().classify_fault(indicators.iloc[-1])
    if guard is not None:
        return {"status": "fault", "prediction": 1, "decision_source": "safety_guard",
                "reason": guard[1], "rf_confidence": None}
    frame = model_frame(normalized)
    result = model.predict_details(frame[feature_columns(frame)].astype(float)).iloc[0].to_dict()
    return {"status": "predicted", **result}
