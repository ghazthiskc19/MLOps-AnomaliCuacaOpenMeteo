"""Verify existing LK07 registry versions without training or changing stages.

Run from the repository root. Refreshes comparison evidence and the metadata
snapshot; run dvc add again if intentionally refreshing tracked metadata.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import mlflow
import mlflow.pyfunc
from mlflow import MlflowClient
import numpy as np
import pandas as pd
import yaml

from src.model_evaluation import chronological_folds, classification_metrics
from src.training_data import latest_features, prepare_training_frame, verify_dataset

OUT = ROOT / "Documentation/LK07"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def verify(tracking_uri=None):
    mlflow.set_tracking_uri(tracking_uri or "sqlite:///" + (ROOT / "mlflow.db").as_posix())
    client = MlflowClient()
    name = "WeatherAnomalyRandomForest"
    versions = sorted(client.search_model_versions(f"name='{name}'"), key=lambda v: int(v.version))
    production = [v for v in versions if v.current_stage == "Production"]
    if len(production) != 1 or str(production[0].version) != "1":
        raise ValueError("Snapshot LK07 mengharuskan tepat satu Production, yaitu v1; periksa registry.")
    old = json.loads((ROOT / "Documentation/LK06/results/best_model_metadata.json").read_text(encoding="utf-8"))
    new = json.loads((OUT / "results/best_model_metadata.json").read_text(encoding="utf-8"))
    columns = old["feature_contract"]["feature_names"]
    if columns != new["feature_contract"]["feature_names"]:
        raise ValueError("Kontrak fitur v1 dan v2 berbeda.")
    identities = {}
    for meta in (old, new):
        identities[meta["version"]] = verify_dataset(ROOT / meta["dataset"]["path"], meta["dataset"]["dataset_tag"])
    raw = pd.read_csv(ROOT / new["dataset"]["path"])
    prepared = prepare_training_frame(raw)
    _, test, _ = chronological_folds(prepared)
    for meta in (old, new):
        if test.timestamp.min() <= pd.Timestamp(meta["fit_scope"]["end_wib"]):
            raise ValueError("Holdout melintasi periode fitting model.")
    X = test[columns].astype("float64")
    predictions = test[["timestamp", "anomaly_class", "anomaly_reason"]].copy()
    comparison = []
    matrices = {}
    expected_sources = {"1": old, "2": new}
    registry = []
    for version in versions:
        prior = next((v for v in registry if v["source"] == version.source and v["run_id"] == version.run_id), None)
        registry.append({"version": str(version.version), "stage": version.current_stage,
                         "run_id": version.run_id, "source": version.source,
                         "duplicate_of": prior["version"] if prior else None})
    for number, meta in expected_sources.items():
        version = next(v for v in versions if str(v.version) == number)
        if version.run_id != meta["run_id"] or version.source != meta["model_uri"]:
            raise ValueError(f"Registry v{number} berbeda dari metadata eksperimen.")
        model = mlflow.pyfunc.load_model(f"models:/{name}/{number}")
        predicted = model.predict(X)
        metrics, report, matrix = classification_metrics(test.anomaly_class, predicted)
        comparison.append({"version": number, **metrics})
        matrices[number] = {"matrix": matrix.tolist(), "report": report}
        predictions[f"prediction_v{number}"] = predicted
    original = pd.read_csv(OUT / "results/test_predictions.csv")
    np.testing.assert_array_equal(original.prediction, predictions.prediction_v2)
    uri = f"models:/{name}/Production"
    deployed = mlflow.pyfunc.load_model(uri)
    np.testing.assert_array_equal(deployed.predict(X), predictions.prediction_v1)
    features = latest_features(raw.iloc[-49:], columns)
    latest_prediction = [int(v) for v in deployed.predict(features)]
    active = production[0]
    artifact_dir = Path(mlflow.artifacts.download_artifacts(artifact_uri=active.source))
    artifact_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [artifact_dir / "MLmodel", artifact_dir / "model.skops"]}
    if client.get_model_version(name, "1").current_stage != "Production":
        raise ValueError("Stage berubah selama verifikasi; ulangi pemeriksaan.")
    timestamp = datetime.now(timezone.utc).isoformat()
    evidence = {
        "verified_at_utc": timestamp, "model_name": name,
        "registry_versions": registry,
        "evaluation_dataset": identities["2"],
        "test": {"rows": len(test), "start_wib": str(test.timestamp.min()),
                 "end_wib": str(test.timestamp.max()),
                 "class_counts": {str(c): int(test.anomaly_class.eq(c).sum()) for c in (0, 1, 2)}},
        "comparison": comparison, "confusion_matrices": matrices,
        "production_inference": {"uri": uri, "resolved_version": str(active.version),
            "input_shape": list(features.shape), "history_rows": 49,
            "timestamp_wib": str(raw.timestamp.iloc[-1]), "prediction": latest_prediction,
            "matches_explicit_v1_on_all_test_rows": True,
            "v2_matches_original_test_predictions": True},
        "policy": "fixed labels [0,1,2]; absent-class F1 contributes zero; balanced accuracy averages present classes",
        "limitations": ["pseudo-labels and synthetic faults", "test has no extreme-weather class",
                        "comparison informed deployment selection; no independent post-selection test",
                        "data and tree count changed together; no causal attribution to n_estimators"],
    }
    metadata = {
        "schema_version": 1, "recorded_at_utc": timestamp,
        "registered_model": {"name": name, "version": "1", "stage": "Production",
            "inference_uri": uri, "pinned_uri": f"models:/{name}/1",
            "run_id": active.run_id, "source_model_uri": active.source,
            "artifact_sha256": artifact_hashes},
        "parameters": old["parameters"], "training_dataset": identities["1"],
        "training_fit_scope": old["fit_scope"],
        "evaluation_dataset": identities["2"], "evaluation_period": evidence["test"],
        "selection": {"decision": "retain_v1", "reason": "v1 beats v2 on the same LK07 holdout",
            "comparison": comparison, "limitations": evidence["limitations"]},
        "feature_contract": old["feature_contract"],
        "verification": evidence["production_inference"],
        "registry_versions": registry,
        "portability": "References require the matching MLflow store and artifacts; DVC metadata is not a backup of the model or registry.",
    }
    result_dir = OUT / "results"
    result_dir.mkdir(parents=True, exist_ok=True)
    write_json(result_dir / "registry_verification.json", evidence)
    pd.DataFrame(comparison).to_csv(result_dir / "version_comparison.csv", index=False)
    predictions.to_csv(result_dir / "common_holdout_predictions.csv", index=False)
    (OUT / "production_model.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True), encoding="utf-8")
    lines = [f"Verified at UTC: {timestamp}"]
    lines += [f"Version {v['version']}: {v['stage']}; duplicate_of={v['duplicate_of']}" for v in registry]
    lines += [f"V{v['version']}: accuracy={v['accuracy']:.4f}; macro F1={v['f1_macro']:.4f}; fault recall={v['recall_class_1']:.4f}" for v in comparison]
    lines += [f"URI: {uri}", "Resolved version: 1", f"Input shape: {tuple(features.shape)}",
              f"Prediction: {latest_prediction}", f"Production matches explicit V1 on all {len(test)} holdout rows: PASS",
              "V2 matches original training test predictions: PASS", "VERIFIKASI INFERENSI BERHASIL"]
    output = "\n".join(lines) + "\n"
    (result_dir / "registry_verification.txt").write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-uri")
    verify(parser.parse_args().tracking_uri)
