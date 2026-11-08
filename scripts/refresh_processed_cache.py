"""Rebuild correctly named legacy preview caches from explicit DVC identities.

These files are previews with the initial warm-up still present. Training always
rebuilds its versioned feature contract from DVC source rather than these caches.
"""
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.data_preprocessing import REPO_ROOT, WeatherPreprocessor
from src.training_data import verify_dataset


def refresh():
    destinations = [
        ('data/raw/weather_raw_current.csv','dataset-v3.0.0','weather_features_v1.0.csv'),
        ('data/simulated/weather_faults_s42.csv','dataset-v3.0.0','weather_features_faults_s42.csv'),
        ('data/raw/weather_lk07_history.csv','dataset-v4.0.0','weather_processed_current.csv'),
    ]
    manifest = {"note":"Legacy 37-feature preview caches; first 48 rows are context, not training observations.","files":[]}
    for source,tag,name in destinations:
        identity=verify_dataset(REPO_ROOT/source,tag)
        path=REPO_ROOT/'data/processed'/name
        frame=WeatherPreprocessor().process_file(REPO_ROOT/source,path,secondary_output_path=None)
        record={"path":str(path.relative_to(REPO_ROOT)),"source":identity,"rows":len(frame),
            "start":str(frame.timestamp.min()),"end":str(frame.timestamp.max()),
            "classes":{str(c):int(frame.anomaly_class.eq(c).sum()) for c in [0,1,2]},
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
        manifest['files'].append(record)
    text=json.dumps(manifest,indent=2,ensure_ascii=False)+'\n'
    (REPO_ROOT/'data/processed/cache_manifest.json').write_text(text,encoding='utf-8')
    report=REPO_ROOT/'Documentation/LK08/cache-refresh.json'
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(text,encoding='utf-8')
    print(text)


if __name__=='__main__': refresh()
