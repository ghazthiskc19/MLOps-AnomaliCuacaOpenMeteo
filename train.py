"""DVC snapshot -> temporal training -> portable evaluated MLflow candidate.

Run from the repository root: python train.py --output-dir artifacts/lk08
Use --legacy explicitly for the historical LK06 training protocol.
No API ingestion, data regeneration, clipping, random train/test split, or
hyperparameter selection on the final test set occurs here.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import mlflow.pyfunc
import mlflow.sklearn
from mlflow.models import infer_signature
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import ConfusionMatrixDisplay
from sklearn.utils.class_weight import compute_class_weight

from src.data_preprocessing import REPO_ROOT
from src.model_evaluation import LABELS, classification_metrics, chronological_folds
from src.training_data import (
    LOCAL_TIMEZONE, WARMUP_HOURS, feature_columns, latest_features,
    prepare_training_frame, verify_dataset,
)

EXPERIMENT_NAME = "LK06-Weather-RandomForest"
MODEL_NAME = "WeatherAnomalyRandomForest"
CONFIGURATIONS = [
    ("rf_baseline", {"n_estimators": 100, "max_depth": None, "min_samples_leaf": 1, "class_weight": None}),
    ("rf_balanced", {"n_estimators": 100, "max_depth": None, "min_samples_leaf": 1, "class_weight": "balanced"}),
    ("rf_balanced_depth10", {"n_estimators": 100, "max_depth": 10, "min_samples_leaf": 1, "class_weight": "balanced"}),
]


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def frame_metadata(frame):
    return {
        "rows": len(frame), "start_wib": str(frame.timestamp.iloc[0]),
        "end_wib": str(frame.timestamp.iloc[-1]),
        "class_counts": {str(c): int(frame.anomaly_class.eq(c).sum()) for c in LABELS},
    }


def evaluation_artifacts(directory, frame, predictions, title):
    """Portable evidence; undefined class metrics stay null in the report."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    metrics, report, matrix = classification_metrics(frame.anomaly_class, predictions)
    write_json(directory / "metrics.json", metrics)
    write_json(directory / "classification_report.json", report)
    pd.DataFrame(matrix, index=LABELS, columns=LABELS).to_csv(directory / "confusion_matrix.csv")
    output = frame[["timestamp", "anomaly_class", "anomaly_reason"]].copy()
    output["prediction"] = predictions
    output.to_csv(directory / "predictions.csv", index=False)
    fig, ax = plt.subplots(figsize=(5.4, 4.3))
    ConfusionMatrixDisplay(matrix, display_labels=LABELS).plot(ax=ax, colorbar=False, cmap="Blues")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(directory / "confusion_matrix.png", dpi=150)
    plt.close(fig)
    return metrics


def select_candidate(results):
    """Freeze selection policy before any final test predictions are made."""
    return min(results, key=lambda r: (-r["cv_val_f1_macro_mean"], r["cv_val_f1_macro_std"], r["config_index"]))


def log_trained_model(model, example, pip_requirements):
    """Export only this process's own fitted RF with a narrow skops type list."""
    return mlflow.sklearn.log_model(
        sk_model=model, name="model", input_example=example,
        signature=infer_signature(example, model.predict(example)),
        serialization_format="skops",
        skops_trusted_types=["sklearn.tree._tree.Tree"],
        pip_requirements=pip_requirements, code_paths=[str(REPO_ROOT / "src")],
    )


def run_training(
    input_path=REPO_ROOT / "data/simulated/weather_faults_s42.csv",
    dataset_tag="dataset-v3.0.0", tracking_uri=None,
    output_dir=REPO_ROOT / "Documentation/LK06/results",
    experiment_name=EXPERIMENT_NAME, model_name=MODEL_NAME, seed=42,
    n_estimators=None, register=False,
):
    if n_estimators is not None and (type(n_estimators) is not int or n_estimators < 1):
        raise ValueError("n_estimators harus integer positif.")
    output_dir = Path(output_dir)
    input_path = Path(input_path).resolve()
    identity = verify_dataset(input_path, dataset_tag)
    raw = pd.read_csv(input_path)
    # Verify again after reading so a live ingestion rewrite cannot slip in.
    if verify_dataset(input_path, dataset_tag) != identity:
        raise ValueError("Dataset berubah selama dibaca.")
    prepared = prepare_training_frame(raw)
    development, test, folds = chronological_folds(prepared)
    columns = feature_columns(prepared)
    X = development[columns].astype("float64")
    y = development.anomaly_class
    provenance = {
        "dataset": identity, "git_commit": git("rev-parse", "HEAD"),
        "git_branch": git("branch", "--show-current"),
        "git_dirty": bool(git("status", "--porcelain")),
        "git_tracked_diff_sha256": hashlib.sha256(git("diff", "HEAD").encode()).hexdigest(),
        "source_sha256": {
            p: hashlib.sha256((REPO_ROOT / p).read_bytes()).hexdigest()
            for p in ["train.py", "src/__init__.py", "src/4_training_data.py", "src/5_model_evaluation.py", "src/1_data_preprocessing.py", "requirements.txt"]
        },
        "versions": {p: importlib.metadata.version(p) for p in ["mlflow", "pandas", "numpy", "scikit-learn", "scipy", "cloudpickle", "PyYAML", "skops"]},
        "python_version": sys.version.split()[0],
        "label_source": "deterministic rule pseudo-labels; synthetic hardware faults",
        "snapshot_note": "Open-Meteo forecast endpoint; revisions/forecast tail possible",
        "test_note": "Class support inspected during EDA; no test scores used in selection",
    }
    contract = {
        "feature_names": columns, "feature_dtype": "float64",
        "labels": {"0": "normal", "1": "hardware fault", "2": "extreme weather"},
        "input": "37 engineered numeric features; not raw single-row weather",
        "raw_history_helper": "src.training_data.latest_features",
        "minimum_raw_history_rows": WARMUP_HOURS + 1,
        "timezone": LOCAL_TIMEZONE, "naive_timestamp_means": LOCAL_TIMEZONE,
        "raw_interval": "1 hour, ordered, unique, finite sensor values",
        "warmup_policy": "first 48 raw hours context only, never fit/scored",
        "missing_policy": "reject raw missing/nonfinite and derived nonfinite explicitly",
        "fault_priority": "hardware fault overrides extreme weather",
        "limitations": ["rule agreement is not independent field accuracy", "one location, 30 days, fault seed 42", "some fault subtypes absent from validation/test", "not approved for actuator control"],
    }
    split_metadata = {
        "raw_rows": len(raw), "context_rows": WARMUP_HOURS,
        "eligible": frame_metadata(prepared), "development": frame_metadata(development),
        "test": frame_metadata(test), "test_fraction": 0.2,
        "selection": "highest mean fold val macro F1, then lower std, then configuration order",
        "folds": [
            {"fold": i, "train": frame_metadata(development.iloc[tr]),
             "validation": frame_metadata(development.iloc[va]),
             "train_indices": tr.tolist(), "validation_indices": va.tolist()}
            for i, (tr, va) in enumerate(folds, 1)
        ],
    }
    tracking_uri = tracking_uri or f"sqlite:///{(REPO_ROOT / 'mlflow.db').as_posix()}"
    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.MlflowClient()
    artifact_root = REPO_ROOT / "mlruns/artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    experiment = client.get_experiment_by_name(experiment_name)
    experiment_id = experiment.experiment_id if experiment else client.create_experiment(experiment_name, artifact_location=artifact_root.as_uri())
    session_name = datetime.now(timezone.utc).strftime("lk06-%Y%m%dT%H%M%SZ")
    tags = {"dataset_tag": dataset_tag, "dataset_md5": identity["md5"], "label_source": "rule_pseudo_labels", "git_commit": provenance["git_commit"], "session": session_name}
    output_dir.mkdir(parents=True, exist_ok=True)
    model_cache, results = {}, []
    with mlflow.start_run(experiment_id=experiment_id, run_name=session_name, tags={**tags, "role": "session"}) as parent:
        parent_id = parent.info.run_id
        mlflow.log_dict(provenance, "provenance.json")
        mlflow.log_dict(contract, "feature_contract.json")
        mlflow.log_dict(split_metadata, "split.json")
        mlflow.log_params({"warmup_hours": WARMUP_HOURS, "development_rows": len(development), "test_rows": len(test), "folds": len(folds), "feature_count": len(columns), "random_state": seed})
        mlflow.log_artifact(str(input_path) + ".dvc", "data_pointer")
        for source in provenance["source_sha256"]:
            mlflow.log_artifact(str(REPO_ROOT / source), "source")
        with tempfile.TemporaryDirectory(prefix="lk06-") as scratch:
            rf_configurations = [
                (name, {**params, **({"n_estimators": n_estimators} if n_estimators is not None else {})})
                for name, params in CONFIGURATIONS
            ]
            configurations = [("dummy_normal", {})] + rf_configurations
            for config_index, (name, params) in enumerate(configurations):
                with mlflow.start_run(experiment_id=experiment_id, run_name=name, nested=True, tags={**tags, "role": "baseline" if not params else "candidate"}) as run:
                    mlflow.log_params(params or {"strategy": "constant", "constant": 0})
                    mlflow.log_params({"random_state": seed, "feature_count": len(columns), "fit_scope": "development only; test excluded", "warmup_hours": WARMUP_HOURS})
                    mlflow.log_dict(provenance, "provenance.json")
                    mlflow.log_dict(contract, "feature_contract.json")
                    mlflow.log_dict(split_metadata, "split.json")
                    fold_scores, fold_train_scores, frames, predictions = [], [], [], []
                    for number, (tr, va) in enumerate(folds, 1):
                        model = RandomForestClassifier(**params, random_state=seed, n_jobs=-1) if params else DummyClassifier(strategy="constant", constant=0)
                        model.fit(X.iloc[tr], y.iloc[tr])
                        predicted = model.predict(X.iloc[va])
                        metrics, report, _ = classification_metrics(y.iloc[va], predicted)
                        train_metrics, _, _ = classification_metrics(y.iloc[tr], model.predict(X.iloc[tr]))
                        mlflow.log_metrics({f"fold_{number}_val_{k}": v for k, v in metrics.items()})
                        mlflow.log_metrics({"val_f1_macro": metrics["f1_macro"], "train_f1_macro": train_metrics["f1_macro"]}, step=number)
                        mlflow.log_dict(report, f"folds/{number}/classification_report.json")
                        weights = compute_class_weight("balanced", classes=np.array(LABELS), y=y.iloc[tr]) if params.get("class_weight") == "balanced" else np.ones(3)
                        mlflow.log_dict({str(c): float(w) for c, w in zip(LABELS, weights)}, f"folds/{number}/class_weights.json")
                        fold_scores.append(metrics["f1_macro"])
                        fold_train_scores.append(train_metrics["f1_macro"])
                        frames.append(development.iloc[va])
                        predictions.extend(predicted.tolist())
                    pooled = pd.concat(frames)
                    evidence_dir = Path(scratch) / name
                    pooled_metrics = evaluation_artifacts(evidence_dir, pooled, predictions, f"{name}: walk-forward predictions")
                    mlflow.log_artifacts(str(evidence_dir), "cv_evaluation")
                    cv_metrics = {
                        "cv_val_f1_macro_mean": float(np.mean(fold_scores)),
                        "cv_val_f1_macro_std": float(np.std(fold_scores)),
                        "cv_train_f1_macro_mean": float(np.mean(fold_train_scores)),
                        **{f"cv_pooled_{k}": v for k, v in pooled_metrics.items()},
                    }
                    mlflow.log_metrics(cv_metrics)
                    result = {"name": name, "config_index": config_index, "run_id": run.info.run_id, "parameters": params, "fold_val_f1_macro": fold_scores, **cv_metrics}
                    if params:
                        # Candidate artifact is fitted on all development, never test.
                        final_model = RandomForestClassifier(**params, random_state=seed, n_jobs=-1).fit(X, y)
                        dev_metrics, _, _ = classification_metrics(y, final_model.predict(X))
                        mlflow.log_metrics({f"development_train_{k}": v for k, v in dev_metrics.items()})
                        pip_requirements = [f"{p}=={v}" for p, v in provenance["versions"].items()]
                        model_info = log_trained_model(final_model, X.head(3), pip_requirements)
                        result["model_uri"] = model_info.model_uri
                        model_cache[name] = final_model
                        results.append(result)
                    else:
                        baseline = result
                    print(f"{name}: CV macro F1={cv_metrics['cv_val_f1_macro_mean']:.4f} +/- {cv_metrics['cv_val_f1_macro_std']:.4f}", flush=True)

            winner = select_candidate(results)
            selected = model_cache[winner["name"]]
            X_test = test[columns].astype("float64")
            # First and only final test predictions; configuration is now frozen.
            test_predictions = selected.predict(X_test)
            final_dir = Path(scratch) / "final"
            test_metrics = evaluation_artifacts(final_dir, test, test_predictions, "Final held-out test (pseudo-labels)")
            mlflow.log_metrics({f"test_{k}": v for k, v in test_metrics.items()})
            mlflow.log_artifacts(str(final_dir), "final_test")
            for key, value in test_metrics.items():
                client.log_metric(winner["run_id"], f"test_{key}", value)
            client.set_tag(winner["run_id"], "selected", "true")
            reloaded = mlflow.sklearn.load_model(winner["model_uri"])
            np.testing.assert_array_equal(reloaded.predict(X_test), test_predictions)
            pyfunc = mlflow.pyfunc.load_model(winner["model_uri"])
            np.testing.assert_array_equal(pyfunc.predict(X_test), test_predictions)
            context_features = latest_features(raw.iloc[-49:], columns)
            np.testing.assert_allclose(context_features.to_numpy(), X_test.iloc[[-1]].to_numpy(), atol=1e-8)
            np.testing.assert_array_equal(reloaded.predict(context_features), test_predictions[-1:])
            # Detect concurrent data changes before declaring the experiment valid.
            if verify_dataset(input_path, dataset_tag) != identity:
                raise ValueError("Dataset berubah selama eksperimen; jangan gunakan hasil ini.")
            from src.validation import validation_decision
            validation = validation_decision(test.anomaly_class, test_predictions)
            write_json(output_dir / "validation.json", validation)
            version, registry_uri = None, None
            if register:
                if not validation["passed"]:
                    raise ValueError(f"Registry blocked: {validation['status']}")
                version = mlflow.register_model(winner["model_uri"], model_name)
                registry_uri = f"models:/{model_name}/{version.version}"
                registered = mlflow.sklearn.load_model(registry_uri)
                np.testing.assert_array_equal(registered.predict(X_test), test_predictions)
                client.set_model_version_tag(model_name, version.version, "validation_status", "academic_rule_agreement_passed")
                client.set_model_version_tag(model_name, version.version, "dataset_tag", dataset_tag)
                client.transition_model_version_stage(model_name, version.version, "Staging", archive_existing_versions=False)
            summary = {
                "experiment_name": experiment_name, "experiment_id": experiment_id,
                "session_run_id": parent_id, "tracking_uri": tracking_uri,
                "baseline": baseline, "candidates": results, "best": winner,
                "test_metrics": test_metrics, "model_name": model_name,
                "model_version": str(version.version) if version else None, "registry_uri": registry_uri,
                "validation": validation,
                "provenance": provenance, "feature_contract": contract, "split": split_metadata,
                "reload_checks": {"sklearn": True, "pyfunc": True, "registry": bool(version), "raw_history_matches_batch": True},
                "beats_dummy_cv": winner["cv_val_f1_macro_mean"] > baseline["cv_val_f1_macro_mean"],
                "deployment_status": "academic candidate; not field validated",
            }
            mlflow.log_dict(summary, "summary.json")
            for name in ["metrics.json", "classification_report.json", "predictions.csv", "confusion_matrix.csv", "confusion_matrix.png"]:
                (output_dir / f"test_{name}").write_bytes((final_dir / name).read_bytes())
            write_json(output_dir / "summary.json", summary)
            write_json(output_dir / "best_model_metadata.json", {
                "name": model_name, "version": str(version.version) if version else None, "registry_uri": registry_uri,
                "run_id": winner["run_id"], "model_uri": winner["model_uri"],
                "parameters": {**winner["parameters"], "random_state": seed, "n_jobs": -1},
                "selection_metric": "cv_val_f1_macro_mean", "cv_value": winner["cv_val_f1_macro_mean"],
                "test_metrics": test_metrics, "fit_scope": frame_metadata(development),
                "dataset": identity, "feature_contract": contract, "source_sha256": provenance["source_sha256"],
            })
            pd.DataFrame([{k: v for k, v in r.items() if k not in {"parameters", "fold_val_f1_macro"}} for r in [baseline] + results]).to_csv(output_dir / "run_comparison.csv", index=False)
    print(f"Selected {winner['name']}; test macro F1={test_metrics['f1_macro']:.4f}; registry={registry_uri}", flush=True)
    return summary


def legacy_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-path", type=Path, default=REPO_ROOT / "data/simulated/weather_faults_s42.csv")
    parser.add_argument("--dataset-tag", default="dataset-v3.0.0")
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "Documentation/LK06/results")
    parser.add_argument("--experiment-name", default=EXPERIMENT_NAME)
    parser.add_argument("--model-name", default=MODEL_NAME)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-estimators", type=int, default=None,
                        help="Override jumlah pohon seluruh kandidat RF; default mengikuti konfigurasi LK06.")
    parser.add_argument("--register", action="store_true", help="Register Staging only after validation passes")
    args = parser.parse_args()
    run_training(args.input_path, args.dataset_tag, args.tracking_uri, args.output_dir, args.experiment_name, args.model_name, args.seed, n_estimators=args.n_estimators, register=args.register)


def main():
    if "--legacy" in sys.argv:
        sys.argv.remove("--legacy")
        return legacy_main()
    from datetime import datetime, timezone
    from src.automation import train_candidate
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=REPO_ROOT/"configs/lk08.yaml")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT/"Documentation/LK08/runs"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--n-estimators", type=int, default=None)
    args = parser.parse_args()
    return train_candidate(args.config,args.output_dir,tracking_uri=args.tracking_uri,n_estimators=args.n_estimators)


if __name__ == "__main__":
    main()
