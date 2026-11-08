"""Real export/reload and registry transitions in a temporary, isolated store.

The passing fixture is intentionally an in-sample test harness, never evidence
for model quality. Project data and the real Production registry are untouched.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import mlflow
import mlflow.sklearn
import pytest

from src.automation import evaluate_candidate,register_candidate,record_predictions,sha,write_json,log_sources
from src.scenarios import scenario_suite,scenario_features
from src.weather_model import CONTRACT_VERSION,TRUSTED_TYPES,GuardedWeatherClassifier
from test_weather_model import history


@pytest.fixture(scope='module')
def exported(tmp_path_factory):
    root=tmp_path_factory.mktemp('registry-fixture')
    previous=mlflow.get_tracking_uri()
    mlflow.set_tracking_uri('sqlite:///:memory:')
    experiment=mlflow.create_experiment('lk08-isolated-fixture',artifact_location=(root/'tracking').as_uri())
    frame,_=scenario_suite(history(240),seed=101,contexts_per_kind=6,partition='test-fixture')
    model=GuardedWeatherClassifier(n_estimators=100,random_state=1).fit(scenario_features(frame),frame.anomaly_class)
    directory=root/'candidate';directory.mkdir()
    mlflow.sklearn.save_model(model,str(directory/'model'),serialization_format='skops',skops_trusted_types=TRUSTED_TYPES,
        code_paths=[str(Path(__file__).resolve().parents[1]/'src')],pip_requirements=[])
    record_predictions(directory/'temporal_predictions.csv',frame.drop(columns=['kind','event_id']),model)
    record_predictions(directory/'scenario_predictions.csv',frame,model,scenarios=True)
    with mlflow.start_run(experiment_id=experiment,tags={'scope':'in_sample_test_fixture_only'}) as run:
        mlflow.log_artifacts(str(directory/'model'),'candidate')
        summary={'contract_version':CONTRACT_VERSION,'config':{'model_name':'IsolatedTestWeather','validation':{
            'threshold':.85,'min_support':5,'min_fault_recall':.85,'max_false_alarm_rate':.05,'scenario_min_agreement':.8}},
            'tracking_uri':'sqlite:///:memory:','run_id':run.info.run_id,'candidate_uri':f'runs:/{run.info.run_id}/candidate',
            'evidence_sha256':{str(p.relative_to(directory)).replace('\\','/'):sha(p) for p in directory.rglob('*') if p.is_file() and p.suffix!='.pyc'}}
        write_json(directory/'summary.json',summary)
    yield directory
    mlflow.set_tracking_uri(previous)


def test_export_is_portable_without_original_tracking_store(exported,tmp_path):
    moved=tmp_path/'moved'
    shutil.copytree(exported,moved)
    assert evaluate_candidate(moved)['passed']
    code = """
import sys
from pathlib import Path
import mlflow.sklearn
import pandas as pd
folder=Path(sys.argv[1])
model=mlflow.sklearn.load_model(str(folder/'model'))
table=pd.read_csv(folder/'temporal_predictions.csv')
assert (model.predict(table[list(model.feature_names_in_)].astype(float))==table.prediction).all()
import src.weather_model
assert str(folder/'model'/'code') in str(Path(src.weather_model.__file__))
print('PACKAGED_CODE_RELOAD_OK')
"""
    result=subprocess.run([sys.executable,'-I','-c',code,str(moved)],cwd=tmp_path,capture_output=True,text=True,check=True)
    assert 'PACKAGED_CODE_RELOAD_OK' in result.stdout


def test_passed_candidate_reaches_staging_and_retry_does_not_duplicate(exported):
    first=register_candidate(exported)
    second=register_candidate(exported)
    assert first==second and first['stage']=='Staging'
    assert len(mlflow.MlflowClient().search_model_versions("name='IsolatedTestWeather'"))==1


def test_gate_blocks_registration_before_registry_write(exported,tmp_path,monkeypatch):
    import pandas as pd
    rejected=tmp_path/'rejected';shutil.copytree(exported,rejected)
    summary=json.loads((rejected/'summary.json').read_text())
    for name in ['temporal_predictions.csv','scenario_predictions.csv']:
        path=rejected/name
        frame=pd.read_csv(path);frame=frame[frame.anomaly_class.ne(2)];frame.to_csv(path,index=False)
        summary['evidence_sha256'][name]=sha(path)
    write_json(rejected/'summary.json',summary)
    writes=[]
    monkeypatch.setattr(mlflow,'register_model',lambda *a,**kw:writes.append(a))
    with pytest.raises(ValueError,match='insufficient_coverage'): register_candidate(rejected)
    assert not writes


def test_scenarios_cover_class_missing_from_temporal_holdout(exported,tmp_path):
    import pandas as pd
    partial=tmp_path/'partial';shutil.copytree(exported,partial)
    path=partial/'temporal_predictions.csv'
    frame=pd.read_csv(path);frame=frame[frame.anomaly_class.ne(2)];frame.to_csv(path,index=False)
    summary=json.loads((partial/'summary.json').read_text())
    summary['evidence_sha256']['temporal_predictions.csv']=sha(path)
    write_json(partial/'summary.json',summary)
    result=evaluate_candidate(partial)
    assert result['temporal']['under_supported_classes']==['2']
    assert result['passed'] and result['combined']['passed']


def test_modified_model_evidence_is_rejected(exported,tmp_path):
    changed=tmp_path/'changed';shutil.copytree(exported,changed)
    with (changed/'temporal_predictions.csv').open('a') as stream: stream.write('\n0,forged\n')
    with pytest.raises(ValueError,match='hash mismatch'): evaluate_candidate(changed)


def test_source_logging_accepts_repository_root_and_nested_paths(exported):
    root=Path(__file__).resolve().parents[1]
    summary=json.loads((exported/'summary.json').read_text())
    experiment=mlflow.MlflowClient().get_run(summary['run_id']).info.experiment_id
    with mlflow.start_run(experiment_id=experiment):
        log_sources([root/'train.py',root/'src/weather_model.py'])
        uri=mlflow.get_artifact_uri('source/train.py')
        assert Path(mlflow.artifacts.download_artifacts(artifact_uri=uri)).read_bytes()==(root/'train.py').read_bytes()


def test_unsuccessful_training_run_cannot_register(exported):
    summary=json.loads((exported/'summary.json').read_text())
    client=mlflow.MlflowClient()
    client.set_terminated(summary['run_id'],status='FAILED')
    try:
        with pytest.raises(ValueError,match='did not finish successfully'): register_candidate(exported)
    finally:
        client.set_terminated(summary['run_id'],status='FINISHED')
