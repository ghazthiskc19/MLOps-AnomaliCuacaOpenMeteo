"""Regression cases reproduced by the LK08 audit, through the serving interface."""
import numpy as np
import pandas as pd
import pytest

from src.weather_model import GuardedWeatherClassifier, model_frame, predict_latest
from src.validation import validation_decision


def history(n=120):
    h = np.arange(n)
    ts = pd.date_range("2026-10-01", periods=n, freq="h")
    return pd.DataFrame({"timestamp": ts, "temperature_2m_C": 24 + 3*np.sin(h/4),
        "humidity_percent": 70 + 5*np.cos(h/5), "precipitation_mm": np.zeros(n),
        "soil_moisture": .25, "radiation_wm2": [400. if 6<=t.hour<18 else 0. for t in ts],
        "wind_speed_kmh": 5.})


@pytest.fixture
def model():
    frame = model_frame(history())
    cols = [c for c in frame if c not in {"timestamp", "anomaly_class", "anomaly_reason"}]
    return GuardedWeatherClassifier(n_estimators=3).fit(frame[cols], np.arange(len(frame))%2*2)


@pytest.mark.parametrize("kind", ["negative_rain", "negative_wind", "negative_radiation", "temp_oob",
    "humidity_oob", "soil_oob", "night_radiation", "temperature_stuck", "humidity_stuck", "wind_stuck"])
def test_deterministic_faults_cannot_be_overruled_by_forest(model, kind):
    raw = history().iloc[-49:].reset_index(drop=True)
    if kind=="negative_rain": raw.loc[48,"precipitation_mm"]=-5.
    elif kind=="negative_wind": raw.loc[48,"wind_speed_kmh"]=-1.
    elif kind=="negative_radiation": raw.loc[48,"radiation_wm2"]=-1.
    elif kind=="temp_oob": raw.loc[48,"temperature_2m_C"]=-237.3
    elif kind=="humidity_oob": raw.loc[48,"humidity_percent"]=100.1
    elif kind=="soil_oob": raw.loc[48,"soil_moisture"]=.551
    elif kind=="night_radiation": raw.loc[48,"radiation_wm2"]=250.
    elif kind=="temperature_stuck": raw.loc[31:,"temperature_2m_C"]=24.
    elif kind=="humidity_stuck": raw.loc[25:,"humidity_percent"]=100.
    elif kind=="wind_stuck": raw.loc[1:,"wind_speed_kmh"]=0.
    result = predict_latest(model, raw)
    assert result["prediction"]==1
    assert result["decision_source"]=="safety_guard"
    assert result["rf_confidence"] is None


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf, "broken"])
def test_missing_or_invalid_current_sensor_has_explicit_quality_route(model, value):
    raw=history()
    raw["humidity_percent"]=raw.humidity_percent.astype(object)
    raw.loc[len(raw)-1,"humidity_percent"]=value
    result=predict_latest(model,raw)
    assert result["prediction"]==1 and result["decision_source"]=="input_quality"


def test_missing_history_abstains_instead_of_inventing_normal(model):
    raw=history()
    raw.loc[len(raw)-10,"humidity_percent"]=np.nan
    result=predict_latest(model,raw)
    assert result["prediction"] is None and result["status"]=="insufficient_history"


def test_time_gaps_still_fail_and_timezone_is_equivalent(model):
    raw=history()
    with pytest.raises(ValueError,match="interval|gap"):
        predict_latest(model,raw.drop(index=100))
    utc=raw.copy()
    utc.timestamp=utc.timestamp.dt.tz_localize("Asia/Jakarta").dt.tz_convert("UTC")
    assert predict_latest(model,utc)==predict_latest(model,raw)


def test_v2_features_are_causal_and_preserve_legacy_contract():
    from src.training_data import prepare_training_frame,feature_columns
    raw=history()
    assert len(feature_columns(prepare_training_frame(raw)))==37
    full=model_frame(raw)
    prefix=model_frame(raw.iloc[:100])
    pd.testing.assert_frame_equal(prefix,full.iloc[:len(prefix)])
    assert {"temp_std_12h","humidity_stuck_100_24h","wind_zero_48h"} <= set(full)


def test_processed_preview_tracks_source_and_does_not_overwrite_current(tmp_path,monkeypatch):
    import hashlib,json
    from src import data_preprocessing as preprocessing
    source=tmp_path/'clean.csv';destination=tmp_path/'features.csv';current=tmp_path/'current.csv'
    history().to_csv(source,index=False)
    current.write_text('preserve this unrelated cache',encoding='utf-8')
    monkeypatch.setattr(preprocessing,'DEFAULT_CURRENT_PROCESSED_PATH',current)
    preprocessing.WeatherPreprocessor().process_file(source,destination)
    metadata=json.loads(destination.with_suffix('.csv.metadata.json').read_text(encoding='utf-8'))
    assert metadata['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    assert metadata['output_sha256']==hashlib.sha256(destination.read_bytes()).hexdigest()
    assert current.read_text()=='preserve this unrelated cache'


def test_coverage_failure_is_not_low_performance_or_success():
    result=validation_decision([0]*10+[1]*10,[0]*10+[1]*10)
    assert not result["passed"] and result["status"]=="insufficient_coverage"
    assert "2" in result["under_supported_classes"]


def test_gate_accepts_adequate_perfect_predictions_and_rejects_missing_faults():
    actual=[0]*10+[1]*10+[2]*10
    assert validation_decision(actual,actual)["passed"]
    assert not validation_decision(actual,[0]*20+[2]*10)["passed"]


@pytest.mark.parametrize("bad", [float('nan'),float('inf'),-.1,1.1,True])
def test_gate_rejects_invalid_threshold(bad):
    with pytest.raises(ValueError): validation_decision([0,1,2],[0,1,2],threshold=bad)
