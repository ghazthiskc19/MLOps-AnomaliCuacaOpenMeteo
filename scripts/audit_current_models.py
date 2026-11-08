"""Read-only audit of frozen data and existing models; outputs only audit evidence.

Run: .venv/Scripts/python.exe scripts/audit_current_models.py
No API fetch, MLflow write, registry transition, or persisted model fitting.
The optional-in-spirit factorial diagnostic fits four forests in memory only.
All challenge cases are exploratory rule-agreement tests, not field validation.
"""

import hashlib
import ast
import json
import logging
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.parse import unquote, urlparse

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import skops.io as sio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_preprocessing import WeatherPreprocessor
from src.model_evaluation import classification_metrics, chronological_folds
from src.simulate_data import FaultInjector
from src.training_data import feature_columns, latest_features, prepare_training_frame, verify_dataset

OUT = ROOT / "artifacts/lk08-audit"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False, default=str) + "\n", encoding="utf-8")


def counts(frame):
    return {str(c): int(frame.anomaly_class.eq(c).sum()) for c in (0, 1, 2)}


def reasons(frame):
    # Remove numeric values, retaining the stable taxonomy prefix.
    return frame.anomaly_reason.str.split(" (", regex=False).str[0].value_counts().to_dict()


def metrics(frame, predicted):
    m, report, cm = classification_metrics(frame.anomaly_class, predicted)
    return {"metrics": m, "report": report, "confusion_matrix": cm.tolist()}


def local_artifact_path(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc:
        raise ValueError("This read-only audit expects local file artifacts")
    path = unquote(parsed.path)
    return Path(path.lstrip("/") if sys.platform == "win32" else path)


def main():
    logging.disable(logging.INFO)
    OUT.mkdir(parents=True, exist_ok=True)
    sources = [ROOT / "mlflow.db", ROOT / "train.py", ROOT / "requirements.txt"] + list((ROOT / "data").rglob("*.csv")) + list((ROOT / "src").glob("*.py"))
    before = {str(p.relative_to(ROOT)): digest(p) for p in sources}
    connection = sqlite3.connect((ROOT / "mlflow.db").as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    registry = [dict(r) for r in connection.execute("SELECT name,version,current_stage,source,run_id FROM model_versions ORDER BY version")]
    locations = dict(connection.execute("SELECT model_id,artifact_location FROM logged_models"))
    connection.close()
    report = {"git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "registry": registry}
    models, summaries, datasets, artifacts = {}, {}, {}, {}
    for version, lk in [(1, "LK06"), (2, "LK07")]:
        summary = json.loads((ROOT / f"Documentation/{lk}/results/summary.json").read_text(encoding="utf-8"))
        summaries[version] = summary
        entry = next(r for r in registry if r["version"] == version)
        assert entry["source"] == summary["best"]["model_uri"] and entry["run_id"] == summary["best"]["run_id"]
        location = local_artifact_path(locations[entry["source"].split("/")[-1]])
        model_file = location / "model.skops"
        before[str(model_file.relative_to(ROOT))] = digest(model_file)
        models[version] = sio.load(model_file, trusted=["sklearn.tree._tree.Tree"])
        artifacts[version] = {"model_sha256": digest(model_file), "artifact_directory": str(location.relative_to(ROOT)), "trees": models[version].n_estimators}

    report["artifacts"] = artifacts
    report["datasets"] = {}
    error_frames, score_rows, injection_rows = [], [], []
    for version, raw_name, simulated_name, tag in [
        (1, "weather_raw_current.csv", "weather_faults_s42.csv", "dataset-v3.0.0"),
        (2, "weather_lk07_history.csv", "weather_lk07_faults_s42.csv", "dataset-v4.0.0"),
    ]:
        summary = summaries[version]
        sim_path = ROOT / "data/simulated" / simulated_name
        identity = verify_dataset(sim_path, tag)
        raw_path = ROOT / "data/raw" / raw_name
        raw_identity = verify_dataset(raw_path, tag)
        raw, sim = pd.read_csv(raw_path), pd.read_csv(sim_path)
        assert raw.timestamp.equals(sim.timestamp)
        traced = []

        class TraceInjector(FaultInjector):
            @staticmethod
            def _apply_point_fault(frame, i, kind, rng):
                actual = FaultInjector._apply_point_fault(frame, i, kind, rng)
                traced.append({"dataset": tag, "row": i, "timestamp": frame.timestamp.iloc[i], "kind": actual})
                return actual

        replay = TraceInjector(seed=42).apply(raw)
        np.testing.assert_allclose(replay.iloc[:, 1:].to_numpy(float), sim.iloc[:, 1:].to_numpy(float), rtol=1e-12, atol=1e-12)
        injection_rows.extend(traced)
        changed = (~np.isclose(raw.iloc[:, 1:].to_numpy(float), sim.iloc[:, 1:].to_numpy(float), rtol=0, atol=1e-10)).any(axis=1)
        prepared, base = prepare_training_frame(sim), prepare_training_frame(raw)
        dev, test, folds = chronological_folds(prepared)
        columns = feature_columns(prepared)
        assert counts(dev) == summary["split"]["development"]["class_counts"]
        assert counts(test) == summary["split"]["test"]["class_counts"]
        changed_eligible = changed[48:]
        feature_changed = ~np.isclose(prepared[columns].to_numpy(float), base[columns].to_numpy(float), rtol=1e-10, atol=1e-10)
        start = int(np.random.default_rng(42).integers(24, len(raw) - FaultInjector.STUCK_BLOCK_HOURS - 24))
        record = {"identity": identity, "raw_identity": raw_identity, "raw_rows": len(raw), "start": raw.timestamp.iloc[0], "end": raw.timestamp.iloc[-1],
                  "schema": list(raw.columns), "missing": int(raw.isna().sum().sum()), "duplicate_times": int(raw.timestamp.duplicated().sum()),
                  "max_interval_hours": float(pd.to_datetime(raw.timestamp).diff().dt.total_seconds().max()/3600),
                  "raw_ranges": {c: {"min": float(raw[c].min()), "max": float(raw[c].max())} for c in raw.columns[1:]},
                  "raw_rule_counts": counts(base), "raw_rule_reasons": reasons(base), "simulated_counts": counts(prepared),
                  "changed_raw_rows": int(changed.sum()), "point_injections": pd.Series([r['kind'] for r in traced]).value_counts().to_dict(),
                  "stuck_block": {"start_row": start, "start": raw.timestamp.iloc[start], "hours": 18},
                  "fault_labels_with_unchanged_current_raw": int((prepared.anomaly_class.eq(1).to_numpy() & ~changed_eligible).sum()),
                  "feature_changed_rows": int(feature_changed.any(axis=1).sum()),
                  "normal_rows_with_changed_features": int((prepared.anomaly_class.eq(0).to_numpy() & feature_changed.any(axis=1)).sum()),
                  "feature_changes": dict(zip(columns, feature_changed.sum(axis=0).astype(int).tolist())),
                  "development": {"counts": counts(dev), "reasons": reasons(dev)}, "test": {"counts": counts(test), "reasons": reasons(test)},
                  "folds": [{"train_counts": counts(dev.iloc[tr]), "validation_counts": counts(dev.iloc[va]), "validation_reasons": reasons(dev.iloc[va])} for tr, va in folds]}
        record['last_extreme_label'] = str(prepared.loc[prepared.anomaly_class.eq(2), 'timestamp'].max())
        record['feature_importance'] = sorted(zip(columns, models[version].feature_importances_.tolist()), key=lambda v: -v[1])
        model = models[version]
        X = test[columns].astype(float)
        own_predictions = model.predict(X)
        saved = pd.read_csv(ROOT / f"Documentation/{'LK06' if version==1 else 'LK07'}/results/test_predictions.csv")
        np.testing.assert_array_equal(own_predictions, saved.prediction)
        assert np.allclose([metrics(test, own_predictions)['metrics'][k] for k in summary['test_metrics']],list(summary['test_metrics'].values()))
        # Check every holdout observation against the 49-hour serving helper.
        max_delta = 0.0
        for row in range(len(sim)-len(test), len(sim)):
            context = latest_features(sim.iloc[row-48:row+1], columns)
            expected = X.iloc[[row-(len(sim)-len(test))]]
            max_delta = max(max_delta, float(np.max(np.abs(context.to_numpy()-expected.to_numpy()))))
        record['all_test_context_max_abs_delta'] = max_delta
        assert max_delta < 1e-8, 'Serving feature history differs from batch features'
        record['stored_predictions_reproduced'] = True
        record['causality_checks'] = {}
        for stop in [48+len(dev)//2, 48+len(dev), len(sim)-1]:
            prefix = prepare_training_frame(sim.iloc[:stop])
            np.testing.assert_allclose(prefix[columns], prepared.iloc[:len(prefix)][columns], rtol=1e-10, atol=1e-10)
            np.testing.assert_array_equal(prefix.anomaly_class, prepared.iloc[:len(prefix)].anomaly_class)
            record['causality_checks'][str(stop)] = True
        datasets[version] = (raw, sim, prepared, dev, test, columns)
        for model_version, forest in models.items():
            predicted = forest.predict(X)
            m = metrics(test, predicted)
            score_rows.append({"dataset": tag, "model_version": model_version, **m['metrics'], "confusion_matrix": m['confusion_matrix'], "scope": "own_holdout" if model_version==version else ("forward_holdout" if model_version==1 else "overlaps_v2_development_not_independent")})
            errors = test.loc[predicted != test.anomaly_class, ['timestamp','anomaly_class','anomaly_reason', *columns]].copy()
            errors['prediction'] = predicted[predicted != test.anomaly_class]
            errors['confidence'] = forest.predict_proba(X).max(axis=1)[predicted != test.anomaly_class]
            errors['model_version'], errors['dataset'] = model_version, tag
            error_frames.append(errors)
        report['datasets'][tag] = record
        print(f'{tag}: {len(raw)} raw rows, test classes {counts(test)}, stored predictions reproduced', flush=True)

    report['holdout_scores'] = score_rows
    old_raw,new_raw=datasets[1][0],datasets[2][0]
    overlap=old_raw.merge(new_raw,on='timestamp',suffixes=('_old','_new'))
    report['snapshot_overlap']={'rows':len(overlap),'start':overlap.timestamp.min(),'end':overlap.timestamp.max(),
        'changed_values':{c:int((~np.isclose(overlap[c+'_old'],overlap[c+'_new'])).sum()) for c in old_raw.columns[1:]}}
    report['processed_caches']=[]
    for path in (ROOT/'data/processed').glob('*.csv'):
        frame=pd.read_csv(path)
        report['processed_caches'].append({'path':str(path.relative_to(ROOT)),'rows':len(frame),'start':frame.timestamp.iloc[0],'end':frame.timestamp.iloc[-1],
            'classes':counts(frame) if 'anomaly_class' in frame else None})
    pd.concat(error_frames).to_csv(OUT/'errors.csv',index=False)
    pd.DataFrame(injection_rows).to_csv(OUT/'injections.csv',index=False)
    # Same new holdout, one variable at a time. These fits never reach MLflow.
    factorial = []
    common = datasets[2][4]
    columns = datasets[2][5]
    for dataset_version in (1,2):
        development = datasets[dataset_version][3]
        for trees in (100,150):
            forest = RandomForestClassifier(n_estimators=trees,random_state=42,n_jobs=-1).fit(development[columns].astype(float),development.anomaly_class)
            predicted = forest.predict(common[columns].astype(float))
            factorial.append({'dataset_version':dataset_version,'trees':trees,**metrics(common,predicted)})
            if trees==models[dataset_version].n_estimators:
                np.testing.assert_array_equal(predicted,models[dataset_version].predict(common[columns].astype(float)))
    report['exploratory_factorial_common_v4_holdout'] = factorial

    # Isolated synthetic challenge, selected from rule-normal raw v4 contexts.
    raw = datasets[2][0]
    raw_prepared = prepare_training_frame(raw)
    candidates = raw_prepared.index[raw_prepared.anomaly_class.eq(0)].to_numpy()+48
    selected = candidates[np.linspace(0,len(candidates)-1,24,dtype=int)]
    challenge = []
    for kind in ['clean','temp_oob','humidity_oob','soil_oob','negative_rain','temp_spike','night_radiation','temp_stuck_18h','humidity_stuck_24h','wind_stuck_48h','heat_36C','soil_drought']:
        for row in selected:
            history = raw.iloc[row-48:row+1].copy().reset_index(drop=True)
            if kind=='temp_oob': history.loc[48,'temperature_2m_C']=65.0
            elif kind=='humidity_oob': history.loc[48,'humidity_percent']=115.0
            elif kind=='soil_oob': history.loc[48,'soil_moisture']=0.7
            elif kind=='negative_rain': history.loc[48,'precipitation_mm']=-5.0
            elif kind=='temp_spike':
                history.loc[48,'temperature_2m_C']=float(history.loc[47,'temperature_2m_C'])+10.0
                history.loc[48,'precipitation_mm']=0.0
            elif kind=='night_radiation':
                if not (pd.Timestamp(history.timestamp.iloc[-1]).hour>=20 or pd.Timestamp(history.timestamp.iloc[-1]).hour<4): continue
                history.loc[48,'radiation_wm2']=250.0
            elif kind=='temp_stuck_18h': history.loc[31:,'temperature_2m_C']=history.loc[31,'temperature_2m_C']
            elif kind=='humidity_stuck_24h': history.loc[25:,'humidity_percent']=100.0
            elif kind=='wind_stuck_48h': history.loc[1:,'wind_speed_kmh']=0.0
            elif kind=='heat_36C': history.loc[48,'temperature_2m_C']=36.0
            elif kind=='soil_drought': history.loc[48,'soil_moisture']=0.05
            prepared = prepare_training_frame(history)
            X = prepared[columns].astype(float)
            for version,forest in models.items():
                predicted = int(forest.predict(X)[0])
                challenge.append({'kind':kind,'timestamp':history.timestamp.iloc[-1],'model_version':version,'rule_label':int(prepared.anomaly_class.iloc[0]),'rule_reason':prepared.anomaly_reason.iloc[0],'prediction':predicted,'confidence':float(forest.predict_proba(X).max()),'correct':bool(predicted==prepared.anomaly_class.iloc[0])})
    challenge = pd.DataFrame(challenge)
    challenge.to_csv(OUT/'exploratory_challenges.csv',index=False)
    report['challenge_summary'] = challenge.groupby(['model_version','kind','rule_label']).agg(n=('correct','size'),correct=('correct','sum'),agreement=('correct','mean')).reset_index().to_dict('records')
    probes = {}
    for kind in ['missing','infinite','singular_dewpoint','time_gap','reverse_time','utc_equivalence']:
        data = raw.iloc[-120:].copy()
        if kind=='missing': data.loc[data.index[-1],'humidity_percent']=np.nan
        elif kind=='infinite': data.loc[data.index[-1],'temperature_2m_C']=np.inf
        elif kind=='singular_dewpoint': data.loc[data.index[-1],'temperature_2m_C']=-237.3
        elif kind=='time_gap': data=data.drop(data.index[50])
        elif kind=='reverse_time': data=data.iloc[::-1]
        elif kind=='utc_equivalence': data['timestamp']=pd.to_datetime(data.timestamp).dt.tz_localize('Asia/Jakarta').dt.tz_convert('UTC')
        try:
            with np.errstate(all='ignore'): result=latest_features(data,columns)
            if kind=='utc_equivalence': np.testing.assert_allclose(result,latest_features(raw.iloc[-120:],columns))
            probes[kind]={'accepted':True}
        except ValueError as exc: probes[kind]={'accepted':False,'message':str(exc)}
    report['contract_probes']=probes
    report['source_hash_comparison'] = {}
    for version,summary in summaries.items():
        record=[]
        for name,expected in summary['provenance']['source_sha256'].items():
            p=ROOT/name
            record.append({'path':name,'exists_now':p.exists(),'matches_now':digest(p)==expected if p.exists() else False})
        report['source_hash_comparison'][version]=record
    report['v1_exported_preprocessing_semantics']={}
    old_source=ROOT/artifacts[1]['artifact_directory']/'code/src'
    for old,new in [('data_preprocessing.py','1_data_preprocessing.py'),('training_data.py','4_training_data.py'),('model_evaluation.py','5_model_evaluation.py')]:
        # Ignore the module docstring, which changed when files were numbered.
        left,right=ast.parse((old_source/old).read_text(encoding='utf-8')),ast.parse((ROOT/'src'/new).read_text(encoding='utf-8'))
        left.body=left.body[1:];right.body=right.body[1:]
        report['v1_exported_preprocessing_semantics'][new]=ast.dump(left)==ast.dump(right)
        # AST changes are evidence to inspect, not an automatic failure after
        # refactoring. Stored predictions and serving/batch checks above remain
        # the behavioral reproduction contract for historical models.
    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    x=np.arange(3)
    for offset,version in [(-.18,1),(.18,2)]:
        frame=datasets[version][4]
        axes[0].bar(x+offset,[counts(frame)[str(c)] for c in range(3)],width=.36,label=f'LK0{version+5} holdout')
    axes[0].set(xticks=x,xticklabels=['Normal','Hardware fault','Extreme weather'],ylabel='Observations',title='Frozen holdout class support')
    axes[0].legend()
    chosen=['temp_oob','soil_oob','temp_stuck_18h','negative_rain','night_radiation','soil_drought']
    for offset,version in [(-.18,1),(.18,2)]:
        subset=challenge[(challenge.model_version==version)&challenge.kind.isin(chosen)].groupby('kind').correct.mean()
        axes[1].bar(np.arange(len(chosen))+offset,[subset[k] for k in chosen],width=.36,label=f'V{version}')
    axes[1].set(xticks=np.arange(len(chosen)),xticklabels=['Temp OOB','Soil OOB','Temp stuck','Negative rain','Night radiation','Soil drought'],ylim=(0,1.08),ylabel='Agreement with rule label',title='Exploratory isolated synthetic challenges')
    axes[1].tick_params(axis='x',labelrotation=35)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(OUT/'audit_overview.png',dpi=160)
    plt.close(fig)
    report['source_bytes_unchanged'] = all(digest(ROOT/name)==value for name,value in before.items())
    assert report['source_bytes_unchanged'], 'Audit must not mutate registry, data, or saved models'
    write_json('audit_results.json',report)
    print('PASS: data, SQLite registry and saved model bytes unchanged',flush=True)
    print('Evidence:',OUT.relative_to(ROOT),flush=True)


if __name__=='__main__':
    main()
