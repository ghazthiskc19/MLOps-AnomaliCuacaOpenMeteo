"""Verify actual candidate rejection and preserve the original registry state.

Run after pytest and train.py. Expected CLI exit 1 is asserted for insufficient
coverage; it is evidence that the gate works, not a claim that promotion passed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.automation import evaluate_candidate,write_json


def main(directory,junit):
    directory=Path(directory).resolve()
    database=ROOT/'mlflow.db'
    before=hashlib.sha256(database.read_bytes()).hexdigest()
    connection=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    versions=connection.execute('SELECT name,version,current_stage,source,run_id FROM model_versions ORDER BY version').fetchall()
    connection.close()
    commands={}
    for name in ['evaluate_candidate','register_candidate']:
        result=subprocess.run([sys.executable,str(ROOT/'scripts'/f'{name}.py'),'--candidate-dir',str(directory)],cwd=ROOT,capture_output=True,text=True)
        (directory/f'{name}.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        commands[name]={'exit_code':result.returncode,'expected_exit_code':1}
        assert result.returncode==1, f'{name} should reject the current uncovered holdout'
    gate=evaluate_candidate(directory)
    assert not gate['passed'] and gate['status']=='insufficient_coverage'
    assert gate['temporal']['under_supported_classes']==['2']
    connection=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    after_versions=connection.execute('SELECT name,version,current_stage,source,run_id FROM model_versions ORDER BY version').fetchall()
    connection.close()
    assert versions==after_versions and before==hashlib.sha256(database.read_bytes()).hexdigest()
    assert [(v[0],v[1]) for v in versions if v[2]=='Production']==[('WeatherAnomalyRandomForest',1)]
    tree=ET.parse(junit)
    suites=tree.getroot().findall('testsuite')
    test_counts={k:sum(int(s.get(k,'0')) for s in suites) for k in ['tests','errors','failures','skipped']}
    assert test_counts['tests']>0 and test_counts['errors']==test_counts['failures']==0
    summary=json.loads((directory/'summary.json').read_text(encoding='utf-8'))
    candidate_db=ROOT/'mlruns/lk08/mlflow.db'
    connection=sqlite3.connect(candidate_db.as_uri()+'?mode=ro',uri=True)
    status=connection.execute('SELECT status FROM runs WHERE run_uuid=?',(summary['run_id'],)).fetchone()[0]
    registered=connection.execute('SELECT COUNT(*) FROM model_versions').fetchone()[0]
    connection.close()
    assert status=='FINISHED' and registered==0
    record={'candidate_directory':str(directory.relative_to(ROOT)), 'training_run_id':summary['run_id'],
        'training_status':status,'tests':test_counts,'cli_checks':commands,
        'temporal_metrics':gate['temporal']['metrics'],'synthetic_metrics':gate['synthetic']['metrics'],
        'scenario_types':len(gate['scenarios']),'scenario_types_passed':sum(r['passed'] for r in gate['scenarios'].values()),
        'gate_status':gate['status'],'original_registry_unchanged':True,'original_production_version':1,
        'actual_candidate_versions_registered':registered,
        'limitations':['no real-world sensor ground truth','natural temporal holdout lacks class 2','GitHub Actions not executed by this local verification','dependency dry-run is not a clean-environment runtime test']}
    write_json(ROOT/'Documentation/LK08/verification.json',record)
    print(json.dumps(record,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-dir',type=Path,required=True)
    parser.add_argument('--junit',type=Path,default=ROOT/'artifacts/lk08-tests.xml')
    args=parser.parse_args()
    main(args.candidate_dir,args.junit)
