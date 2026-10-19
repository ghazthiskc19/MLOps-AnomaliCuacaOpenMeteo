"""Behavioral contracts for LK06 data, chronological evaluation and tracking."""

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.training_data import (
    WARMUP_HOURS,
    feature_columns,
    latest_features,
    normalize_raw,
    prepare_training_frame,
    verify_dataset,
)
from src.model_evaluation import classification_metrics, chronological_folds


def weather_frame(n=120):
    hours = np.arange(n)
    timestamps = pd.date_range("2026-09-01", periods=n, freq="h")
    return pd.DataFrame({
        "timestamp": timestamps,
        "temperature_2m_C": 24 + 4 * np.sin(hours * np.pi / 12),
        "humidity_percent": 70 + 10 * np.cos(hours * np.pi / 12),
        "precipitation_mm": np.zeros(n),
        "soil_moisture": np.full(n, 0.25),
        "radiation_wm2": [500 if 6 <= t.hour < 18 else 0 for t in timestamps],
        "wind_speed_kmh": np.full(n, 5.0),
    })


class TestTrainingData(unittest.TestCase):
    def test_timezone_normalization_gives_same_features(self):
        local = weather_frame()
        utc = local.copy()
        utc["timestamp"] = utc.timestamp.dt.tz_localize("Asia/Jakarta").dt.tz_convert("UTC")
        pd.testing.assert_frame_equal(
            prepare_training_frame(local), prepare_training_frame(utc)
        )

    def test_gap_duplicate_and_reverse_order_are_rejected(self):
        raw = weather_frame()
        cases = [raw.drop(index=20), pd.concat([raw, raw.iloc[[-1]]]), raw.iloc[::-1]]
        for frame in cases:
            with self.subTest(case=len(frame)), self.assertRaises(ValueError):
                normalize_raw(frame)

    def test_invalid_timestamp_and_missing_sensor_are_not_silently_dropped(self):
        for column, value in [("timestamp", pd.NaT), ("humidity_percent", np.nan)]:
            raw = weather_frame()
            raw.loc[20, column] = value
            with self.subTest(column=column), self.assertRaises(ValueError):
                normalize_raw(raw)

    def test_warmup_is_context_and_never_appears_in_training(self):
        raw = weather_frame()
        result = prepare_training_frame(raw)
        self.assertEqual(len(result), len(raw) - WARMUP_HOURS)
        self.assertEqual(result.timestamp.iloc[0], raw.timestamp.iloc[WARMUP_HOURS])
        self.assertEqual(len(feature_columns(result)), 37)
        with self.assertRaisesRegex(ValueError, "49|warm|histori"):
            prepare_training_frame(raw.iloc[:48])

    def test_context_inference_matches_batch_and_does_not_use_future(self):
        raw = weather_frame()
        batch = prepare_training_frame(raw)
        columns = feature_columns(batch)
        for last in [60, 90]:
            # Exactly 48 prior hours plus the current observation.
            context = raw.iloc[last - 48:last + 1]
            expected = batch.loc[batch.timestamp.eq(raw.timestamp.iloc[last]), columns]
            actual = latest_features(context, columns)
            np.testing.assert_allclose(actual.to_numpy(), expected.to_numpy(), atol=1e-8)
            prefix = prepare_training_frame(raw.iloc[:last + 1])
            pd.testing.assert_frame_equal(prefix, batch.iloc[:len(prefix)])
        with self.assertRaises(ValueError):
            latest_features(raw.iloc[[-1]], columns)
        with self.assertRaises(ValueError):
            latest_features(raw, columns[::-1])

    def test_extreme_valid_fault_is_preserved_but_undefined_features_rejected(self):
        raw = weather_frame()
        raw.loc[60, "temperature_2m_C"] = 65.0
        result = prepare_training_frame(raw)
        fault = result.loc[result.timestamp.eq(raw.timestamp.iloc[60])].iloc[0]
        self.assertEqual(fault.anomaly_class, 1)
        self.assertEqual(fault.temperature_2m_C, 65.0)
        raw.loc[60, "temperature_2m_C"] = -237.3
        with np.errstate(all="ignore"), self.assertRaisesRegex(ValueError, "finite|dew_point"):
            prepare_training_frame(raw)

    def test_dataset_pointer_and_git_tag_are_both_verified(self):
        raw = Path("data/simulated/weather_faults_s42.csv")
        info = verify_dataset(raw, "dataset-v3.0.0")
        self.assertEqual(info["md5"], hashlib.md5(raw.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):
            verify_dataset(raw, "dataset-v2.0.0")
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "unknown.csv"
            copy.write_bytes(raw.read_bytes())
            with self.assertRaises(ValueError):
                verify_dataset(copy, "dataset-v3.0.0")


class TestChronologicalEvaluation(unittest.TestCase):
    def test_final_holdout_and_folds_have_no_future_training(self):
        frame = prepare_training_frame(weather_frame(720))
        # Build known support independently of the weather rule labeler.
        frame["anomaly_class"] = np.arange(len(frame)) % 3
        development, test, folds = chronological_folds(frame)
        self.assertEqual(len(development) + len(test), len(frame))
        self.assertEqual(len(test), 135)  # ceil(672 * .2)
        self.assertEqual(len(folds), 3)
        self.assertLess(development.timestamp.max(), test.timestamp.min())
        for train, validation in folds:
            self.assertLess(train[-1], validation[0])
            self.assertLess(validation[-1], len(development))
        self.assertEqual(len({len(v) for _, v in folds}), 1)

    def test_missing_training_class_or_too_little_data_fails(self):
        frame = prepare_training_frame(weather_frame())
        with self.assertRaisesRegex(ValueError, "kelas|class"):
            chronological_folds(frame)
        with self.assertRaises(ValueError):
            chronological_folds(frame.iloc[:3])

    def test_absent_evaluation_class_is_explicit_not_invented_recall(self):
        metrics, report, matrix = classification_metrics([0, 0], [0, 0])
        self.assertEqual(matrix.shape, (3, 3))
        self.assertAlmostEqual(metrics["f1_macro"], 1 / 3)
        self.assertEqual(metrics["accuracy"], 1.0)
        self.assertEqual(report["classes"]["1"]["support"], 0)
        self.assertIsNone(report["classes"]["1"]["recall"])
        self.assertEqual(report["absent_true_classes"], [1, 2])


class TestMlflowRoundTrip(unittest.TestCase):
    def test_exported_forest_and_pyfunc_preserve_predictions(self):
        import mlflow
        import mlflow.pyfunc
        import mlflow.sklearn
        from sklearn.ensemble import RandomForestClassifier
        from train import log_trained_model

        previous = mlflow.get_tracking_uri()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mlflow.set_tracking_uri("sqlite:///:memory:")
                experiment_id = mlflow.create_experiment(
                    "forest-roundtrip", artifact_location=Path(tmp).as_uri(),
                )
                X = pd.DataFrame({"sensor": np.arange(30, dtype=float)})
                y = np.arange(30) % 3
                model = RandomForestClassifier(n_estimators=5, random_state=42).fit(X, y)
                with mlflow.start_run(experiment_id=experiment_id):
                    exported = log_trained_model(model, X.head(3), [])
                expected = model.predict(X)
                np.testing.assert_array_equal(mlflow.sklearn.load_model(exported.model_uri).predict(X), expected)
                np.testing.assert_array_equal(mlflow.pyfunc.load_model(exported.model_uri).predict(X), expected)
        finally:
            mlflow.set_tracking_uri(previous)

    def test_selection_never_needs_test_scores_and_has_stable_ties(self):
        from train import select_candidate

        rows = [
            {"name": "a", "cv_val_f1_macro_mean": .8, "cv_val_f1_macro_std": .1, "config_index": 0},
            {"name": "b", "cv_val_f1_macro_mean": .8, "cv_val_f1_macro_std": .05, "config_index": 1},
            {"name": "c", "cv_val_f1_macro_mean": .8, "cv_val_f1_macro_std": .05, "config_index": 2},
        ]
        self.assertEqual(select_candidate(rows)["name"], "b")


if __name__ == "__main__":
    unittest.main()
