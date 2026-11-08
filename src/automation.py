"""LK08 training, portable candidate evaluation, and gated Staging registration."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess

import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
import numpy as np
import pandas as pd
import yaml

from src.data_preprocessing import REPO_ROOT
from src.model_evaluation import chronological_folds, classification_metrics
from src.scenarios import KINDS, scenario_suite, scenario_features
from src.training_data import feature_columns, normalize_raw, verify_dataset
from src.validation import validation_decision
from src.weather_model import CONTRACT_VERSION, TRUSTED_TYPES, GuardedWeatherClassifier, model_frame

CONFIGURATIONS = [
    {"n_estimators":150,"max_depth":None,"min_samples_leaf":1,"class_weight":None},
    {"n_estimators":150,"max_depth":10,"min_samples_leaf":2,"class_weight":None},
    {"n_estimators":150,"max_depth":10,"min_samples_leaf":1,"class_weight":"balanced"},
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False,default=str)+"\n",encoding="utf-8")


def log_sources(paths):
    for path in paths:
        artifact_path = (Path('source')/path.parent.relative_to(REPO_ROOT)).as_posix()
        mlflow.log_artifact(str(path),artifact_path)


def record_predictions(path, frame, model, *, scenarios=False):
    X = scenario_features(frame) if scenarios else frame[feature_columns(frame)].astype(float)
    detail = model.predict_details(X)
    columns = ["timestamp","anomaly_class","anomaly_reason"] + (["event_id","kind"] if scenarios else [])
    pd.concat([frame[columns].reset_index(drop=True), detail, X.reset_index(drop=True)],axis=1).to_csv(path,index=False)


def evaluate_candidate(directory):
    directory = Path(directory)
    summary = json.loads((directory/"summary.json").read_text(encoding="utf-8"))
    if summary["contract_version"] != CONTRACT_VERSION:
        raise ValueError("Candidate contract version is unsupported")
    for name, expected in summary["evidence_sha256"].items():
        target = (directory/name).resolve()
        if not target.is_relative_to(directory.resolve()) or sha(target) != expected:
            raise ValueError(f"Candidate evidence hash mismatch: {name}")
    model = mlflow.sklearn.load_model(str(directory/"model"))
    policy = summary["config"]["validation"].copy()
    scenario_min = policy.pop("scenario_min_agreement")
    if isinstance(scenario_min,bool) or not isinstance(scenario_min,(int,float)) or not np.isfinite(scenario_min) or not 0<=scenario_min<=1:
        raise ValueError("scenario_min_agreement invalid")
    temporal = pd.read_csv(directory/"temporal_predictions.csv")
    scenarios = pd.read_csv(directory/"scenario_predictions.csv")
    cols = list(model.feature_names_in_)
    for table in (temporal, scenarios):
        np.testing.assert_array_equal(model.predict(table[cols].astype(float)),table.prediction)
    natural = validation_decision(temporal.anomaly_class,temporal.prediction,**policy)
    synthetic = validation_decision(scenarios.anomaly_class,scenarios.prediction,**policy)
    # Gate basis: temporal holdout + held-out scenario test (separate seed and partition).
    # The natural holdout has no class 2, so its 3-class macro F1 cannot reach the threshold;
    # coverage and macro F1 are judged on the combined evaluation set, while the natural
    # holdout must still meet fault recall and false-alarm limits on its own.
    combined = validation_decision(pd.concat([temporal.anomaly_class,scenarios.anomaly_class],ignore_index=True),
        pd.concat([temporal.prediction,scenarios.prediction],ignore_index=True),**policy)
    temporal_failures = [r for r in natural["performance_failures"] if r != "macro_f1_not_strictly_above_threshold"]
    by_kind = {}
    for kind in KINDS:
        group = scenarios[scenarios.kind.eq(kind)]
        agreement = float(group.prediction.eq(group.anomaly_class).mean()) if len(group) else None
        by_kind[kind] = {"events":len(group),"agreement":agreement,
            "passed":len(group)>=policy["min_support"] and agreement is not None and agreement>=scenario_min}
    scenarios_ok = all(g["passed"] for g in by_kind.values())
    passed = combined["passed"] and not temporal_failures and scenarios_ok
    status = ("passed" if passed else combined["status"] if not combined["passed"]
        else "failed_temporal_performance" if temporal_failures else "failed_scenarios")
    result = {"passed":passed,"status":status,"gate_basis":"combined temporal holdout + held-out scenario test",
        "combined":combined,"temporal_performance_failures":temporal_failures,
        "temporal":natural,"synthetic":synthetic,"scenarios":by_kind,
        "note":"Class 2 coverage comes from held-out synthetic scenarios; this is rule pseudo-label agreement, not field validation."}
    write_json(directory/"validation.json",result)
    return result


def register_candidate(directory):
    """Recompute predictions/gate before any model-version write. Never Production."""
    directory = Path(directory)
    result = evaluate_candidate(directory)
    if not result["passed"]:
        raise ValueError(f"Registration blocked: {result['status']}")
    summary = json.loads((directory/"summary.json").read_text(encoding="utf-8"))
    mlflow.set_tracking_uri(summary["tracking_uri"])
    client = mlflow.MlflowClient()
    if client.get_run(summary['run_id']).info.status != 'FINISHED':
        raise ValueError('Registration blocked: training run did not finish successfully')
    remote_candidate = Path(mlflow.artifacts.download_artifacts(artifact_uri=summary['candidate_uri']))
    for name,expected in summary['evidence_sha256'].items():
        if name.startswith('model/') and sha(remote_candidate/name[len('model/'):]) != expected:
            raise ValueError('Tracked candidate differs from validated portable model')
    name = summary["config"]["model_name"]
    expected_source = client.get_run(summary["run_id"]).info.artifact_uri.rstrip('/')+'/candidate'
    matches = [v for v in client.search_model_versions(f"name='{name}'") if v.run_id==summary["run_id"]]
    if len(matches)>1: raise ValueError("Duplicate versions for this run; resolve explicitly")
    if matches and matches[0].source.rstrip('/') != expected_source:
        raise ValueError("Existing version source differs from validated run artifact")
    version = matches[0] if matches else mlflow.register_model(summary["candidate_uri"],name)
    if version.current_stage == "Production":
        raise ValueError("This command cannot change a Production version")
    if version.current_stage != "Staging":
        client.transition_model_version_stage(name,version.version,"Staging",archive_existing_versions=False)
    client.set_model_version_tag(name,version.version,"validation_status","academic_rule_agreement_passed")
    client.set_model_version_tag(name,version.version,"contract_version",CONTRACT_VERSION)
    checked = client.get_model_version(name,version.version)
    if checked.current_stage != "Staging": raise ValueError("Registry stage verification failed")
    original = mlflow.sklearn.load_model(str(directory/"model"))
    registered = mlflow.sklearn.load_model(f"models:/{name}/{version.version}")
    sample = pd.read_csv(directory/"temporal_predictions.csv")[list(original.feature_names_in_)].astype(float)
    np.testing.assert_array_equal(original.predict(sample),registered.predict(sample))
    record = {"name":name,"version":str(version.version),"stage":checked.current_stage,"run_id":checked.run_id}
    write_json(directory/"registry.json",record)
    return record


def train_candidate(config_path, output_dir, *, tracking_uri=None, n_estimators=None):
    config_path, output_dir = Path(config_path), Path(output_dir).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config["protocol"] != CONTRACT_VERSION: raise ValueError("Unsupported training protocol")
    if n_estimators is not None and (type(n_estimators) is not int or n_estimators<1):
        raise ValueError("n_estimators harus integer positif")
    if (output_dir/"model").exists(): raise ValueError("Use a new output directory; candidate artifacts are immutable")
    output_dir.mkdir(parents=True,exist_ok=True)
    source_files = [REPO_ROOT/'train.py',REPO_ROOT/'requirements.txt',config_path.resolve(),*sorted((REPO_ROOT/'src').glob('*.py'))]
    source_hashes = {str(p.relative_to(REPO_ROOT)):sha(p) for p in source_files}
    identities = {k:verify_dataset(REPO_ROOT/config[k],config["dataset_tag"]) for k in ("input_path","scenario_input_path")}
    raw = pd.read_csv(REPO_ROOT/config["input_path"])
    clean = normalize_raw(pd.read_csv(REPO_ROOT/config["scenario_input_path"]))
    if list(pd.to_datetime(raw.timestamp)) != list(clean.timestamp): raise ValueError("Raw and simulated time axes differ")
    frame = model_frame(raw)
    development,test,folds = chronological_folds(frame)
    columns = feature_columns(frame)
    settings = config["scenarios"]

    def suite(partition,seed,n,label):
        # No scenario's 49-hour context crosses its source partition boundary.
        source = clean[clean.timestamp.between(partition.timestamp.min(),partition.timestamp.max())]
        return scenario_suite(source,seed=seed,contexts_per_kind=n,partition=label)

    fold_data,manifest = [],[]
    for index,(tr,va) in enumerate(folds,1):
        training,validation = development.iloc[tr],development.iloc[va]
        augmented,tm = suite(training,settings["train_seed"]+index,settings["train_contexts_per_kind"],f"fold-{index}-train")
        challenge,vm = suite(validation,settings["validation_seed"]+index,settings["evaluation_contexts_per_kind"],f"fold-{index}-validation")
        fold_data.append((training,validation,augmented,challenge))
        manifest.extend(tm+vm)
    results = []
    for index,parameters in enumerate(CONFIGURATIONS):
        parameters = {**parameters,**({"n_estimators":n_estimators} if n_estimators is not None else {})}
        scores, diagnostics = [],[]
        for training,validation,augmented,challenge in fold_data:
            X = pd.concat([training[columns],scenario_features(augmented)],ignore_index=True).astype(float)
            y = np.r_[training.anomaly_class,augmented.anomaly_class]
            model = GuardedWeatherClassifier(**parameters,random_state=config["seed"]).fit(X,y)
            actual = np.r_[validation.anomaly_class,challenge.anomaly_class]
            predicted = np.r_[model.predict(validation[columns].astype(float)),model.predict(scenario_features(challenge))]
            combined_metrics,_,_ = classification_metrics(actual,predicted)
            scores.append(combined_metrics["f1_macro"])
            diagnostics.append({"temporal":classification_metrics(validation.anomaly_class,model.predict(validation[columns].astype(float)))[0],
                "scenario":classification_metrics(challenge.anomaly_class,model.predict(scenario_features(challenge)))[0]})
        results.append({"config_index":index,"parameters":parameters,"cv_mean":float(np.mean(scores)),"cv_std":float(np.std(scores)),"fold_scores":scores,"diagnostics":diagnostics})
        print(f"Candidate {index}: combined development CV macro F1={np.mean(scores):.4f}",flush=True)
    best = min(results,key=lambda r:(-r["cv_mean"],r["cv_std"],r["config_index"]))
    # Configuration is now frozen. Test data never participate in selection/fitting.
    augmented,tm = suite(development,settings["train_seed"],settings["train_contexts_per_kind"],"final-development")
    model = GuardedWeatherClassifier(**best["parameters"],random_state=config["seed"]).fit(
        pd.concat([development[columns],scenario_features(augmented)],ignore_index=True).astype(float),
        np.r_[development.anomaly_class,augmented.anomaly_class])
    challenge,vm = suite(test,settings["test_seed"],settings["evaluation_contexts_per_kind"],"final-test")
    manifest.extend(tm+vm)
    record_predictions(output_dir/"temporal_predictions.csv",test,model)
    record_predictions(output_dir/"scenario_predictions.csv",challenge,model,scenarios=True)
    write_json(output_dir/"scenario_manifest.json",manifest)
    contract = {"version":CONTRACT_VERSION,"features":columns,"dtype":"float64","raw_history_rows":49,
        "timezone":"Asia/Jakarta","raw_entrypoint":"src.weather_model.predict_latest",
        "learned_features":list(model.forest_.feature_names_in_),"target":"rule pseudo-labels, synthetic faults; not field truth",
        "current_invalid":"input_quality fault","history_invalid":"abstain",
        "fault_policy":"deterministic safety guard; no RF confidence assigned",
        "environment_policy":"learned RF normal/extreme; uncalibrated confidence",
        "biophysical_formula_policy":"temperature bounded [-20,55] for dew point/VPD only; raw readings preserved"}
    write_json(output_dir/"feature_contract.json",contract)
    versions = {p:importlib.metadata.version(p) for p in ["mlflow","pandas","numpy","scikit-learn","scipy","cloudpickle","PyYAML","skops"]}
    mlflow.sklearn.save_model(model,str(output_dir/"model"),serialization_format="skops",skops_trusted_types=TRUSTED_TYPES,
        signature=infer_signature(development[columns].head(3).astype(float),model.predict(development[columns].head(3).astype(float))),
        input_example=development[columns].head(3).astype(float),code_paths=[str(REPO_ROOT/"src")],
        pip_requirements=[f"{p}=={v}" for p,v in versions.items()])
    reloaded = mlflow.sklearn.load_model(str(output_dir/"model"))
    np.testing.assert_array_equal(reloaded.predict(test[columns].astype(float)),model.predict(test[columns].astype(float)))
    tracking_uri = tracking_uri or f"sqlite:///{(REPO_ROOT/'mlruns/lk08/mlflow.db').as_posix()}"
    (REPO_ROOT/'mlruns/lk08').mkdir(parents=True,exist_ok=True)
    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.MlflowClient()
    experiment = client.get_experiment_by_name(config["experiment_name"])
    exp_id = experiment.experiment_id if experiment else client.create_experiment(config["experiment_name"],artifact_location=(REPO_ROOT/'mlruns/lk08/artifacts').as_uri())
    with mlflow.start_run(experiment_id=exp_id,tags={"contract_version":CONTRACT_VERSION,"dataset_tag":config["dataset_tag"]}) as run:
        summary = {"contract_version":CONTRACT_VERSION,"config":config,"config_sha256":sha(config_path),
            "tracking_uri":tracking_uri,"run_id":run.info.run_id,"candidate_uri":f"runs:/{run.info.run_id}/candidate",
            "datasets":identities,"best":best,"candidates":results,"versions":versions,
            "git_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO_ROOT,text=True).strip(),
            "git_dirty":bool(subprocess.check_output(["git","status","--porcelain"],cwd=REPO_ROOT,text=True).strip()),
            "source_sha256":source_hashes,"fit_scope":{"start":str(development.timestamp.min()),"end":str(development.timestamp.max()),"natural_rows":len(development),"synthetic_events":len(augmented)},
            "test_scope":{"start":str(test.timestamp.min()),"end":str(test.timestamp.max()),"natural_rows":len(test),"synthetic_events":len(challenge)},
            "selection":"highest combined temporal+synthetic development CV macro F1, then std/index; no test tuning",
            "limitations":["previous natural holdout inspected during audit","synthetic events may share source contexts","no field validation","Production not changed"],
            "evidence_sha256":{str(p.relative_to(output_dir)).replace('\\','/'):sha(p) for p in output_dir.rglob('*') if p.is_file() and p.suffix!='.pyc'}}
        write_json(output_dir/"summary.json",summary)
        gate = evaluate_candidate(output_dir)
        mlflow.log_params(best["parameters"])
        mlflow.log_metrics({"cv_f1_macro":best["cv_mean"],"temporal_f1_macro":gate["temporal"]["metrics"]["f1_macro"],
            "scenario_f1_macro":gate["synthetic"]["metrics"]["f1_macro"],"validation_passed":float(gate["passed"])})
        mlflow.log_artifacts(str(output_dir/"model"),"candidate")
        for name in ["summary.json","validation.json","feature_contract.json","scenario_manifest.json","temporal_predictions.csv","scenario_predictions.csv"]:
            mlflow.log_artifact(str(output_dir/name),"evidence")
        log_sources(source_files)
        for key,identity in identities.items():
            if verify_dataset(REPO_ROOT/config[key],config['dataset_tag'])!=identity: raise ValueError("Dataset changed during training")
        if any(sha(REPO_ROOT/p)!=value for p,value in source_hashes.items()): raise ValueError("Source changed during training")
    print(f"Training completed; gate={gate['status']}; no model registered",flush=True)
    return summary
