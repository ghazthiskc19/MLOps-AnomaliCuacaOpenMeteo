"""Versioned scenario contracts. Independent copies, never blended into holdout.

Each scored observation is one synthetic event with a 49-hour source context.
Source partitions must be cut before calling this module. These events may
share source contexts; their counts are not independent field incidents.
"""
import hashlib
import numpy as np
import pandas as pd
from src.training_data import feature_columns, normalize_raw
from src.weather_model import model_frame

SCENARIO_VERSION = "weather-scenarios-v2"
KINDS = ("normal", "temp_oob", "humidity_oob", "soil_oob", "negative_rain",
    "negative_radiation", "negative_wind", "temp_spike", "night_radiation",
    "temp_stuck", "humidity_stuck", "wind_stuck", "discordance", "soil_surge",
    "soil_unresponsive", "heat", "cold", "dry_air", "torrential_rain",
    "drought", "waterlogging", "solar_extreme", "high_wind")
ENVIRONMENT_KINDS = KINDS[15:]


def inject(history, kind, rng):
    out = history.copy().reset_index(drop=True)
    for col in out.columns[1:]: out[col] = out[col].astype(float)
    if kind == "normal": return out
    if kind == "temp_oob": out.loc[48,"temperature_2m_C"] = rng.choice([rng.uniform(55.1,70),rng.uniform(-35,-20.1)])
    elif kind == "humidity_oob": out.loc[48,"humidity_percent"] = rng.choice([rng.uniform(100.1,130),rng.uniform(-20,-.1)])
    elif kind == "soil_oob": out.loc[48,"soil_moisture"] = rng.choice([rng.uniform(.551,.9),rng.uniform(-.2,-.001)])
    elif kind.startswith("negative_"):
        col = {"negative_rain":"precipitation_mm","negative_radiation":"radiation_wm2","negative_wind":"wind_speed_kmh"}[kind]
        out.loc[48,col] = -rng.uniform(.1,20)
    elif kind == "temp_spike":
        out.loc[48,"temperature_2m_C"] = out.loc[47,"temperature_2m_C"] + rng.choice([-1.,1.])*rng.uniform(8.1,15)
        out.loc[48,"precipitation_mm"] = 0.
    elif kind == "night_radiation": out.loc[48,"radiation_wm2"] = rng.uniform(.1,600)
    elif kind == "temp_stuck": out.loc[31:,"temperature_2m_C"] = out.loc[31,"temperature_2m_C"]
    elif kind == "humidity_stuck": out.loc[25:,"humidity_percent"] = 100.
    elif kind == "wind_stuck": out.loc[1:,"wind_speed_kmh"] = 0.
    elif kind == "discordance":
        out.loc[48,"precipitation_mm"] = rng.uniform(16,25)
        out.loc[48,"radiation_wm2"] = rng.uniform(801,1050)
    elif kind == "soil_surge":
        out.loc[47,"soil_moisture"] = .1
        out.loc[48,"soil_moisture"] = .45
        out.loc[48,"precipitation_mm"] = 0.
        out.loc[48,"radiation_wm2"] = 900.
    elif kind == "soil_unresponsive":
        out.loc[47:48,"soil_moisture"] = .25
        out.loc[48,"precipitation_mm"] = 23.
        out.loc[48,"radiation_wm2"] = 0.
    elif kind in ("heat","cold"):
        target = rng.uniform(33.6,39) if kind=="heat" else rng.uniform(8,14.9)
        # Gradual trajectory prevents an extreme scenario becoming a spike fault.
        out.loc[40:48,"temperature_2m_C"] = np.linspace(out.loc[40,"temperature_2m_C"],target,9)
    elif kind == "dry_air": out.loc[48,"humidity_percent"] = rng.uniform(20,39.9)
    elif kind == "torrential_rain":
        out.loc[48,"precipitation_mm"] = rng.uniform(25.1,45)
        out.loc[48,"radiation_wm2"] = 0.
        out.loc[48,"soil_moisture"] = min(.47,out.loc[47,"soil_moisture"]+.01)
    elif kind == "drought": out.loc[48,"soil_moisture"] = rng.uniform(.02,.079)
    elif kind == "waterlogging":
        out.loc[48,"soil_moisture"] = rng.uniform(.481,.549)
        out.loc[47,"soil_moisture"] = out.loc[48,"soil_moisture"]-.005
    elif kind == "solar_extreme":
        out.loc[48,"radiation_wm2"] = rng.uniform(1101,1400)
        out.loc[48,"precipitation_mm"] = 0.
    elif kind == "high_wind": out.loc[48,"wind_speed_kmh"] = rng.uniform(40.1,70)
    else: raise ValueError(f"Unknown scenario: {kind}")
    return out


def scenario_suite(raw_partition, *, seed, contexts_per_kind=12, partition):
    if type(contexts_per_kind) is not int or contexts_per_kind < 1:
        raise ValueError("contexts_per_kind harus integer positif.")
    raw = normalize_raw(raw_partition)
    base = model_frame(raw)
    candidates = base.index[base.anomaly_class.eq(0)].to_numpy()+48
    if not len(candidates): raise ValueError("Tidak ada konteks normal dalam partition.")
    rng = np.random.default_rng(seed)
    frames, manifest = [], []
    for kind in KINDS:
        pool = candidates
        hours = raw.timestamp.iloc[pool].dt.hour.to_numpy()
        if kind == "night_radiation": pool = pool[(hours>=20)|(hours<4)]
        if kind in ("solar_extreme","discordance","soil_surge"): pool = pool[(hours>=7)&(hours<17)]
        if len(pool) < contexts_per_kind:
            raise ValueError(f"Partition {partition} tidak cukup konteks unik untuk {kind}: {len(pool)}")
        rows = rng.choice(pool,size=contexts_per_kind,replace=False)
        for number,row in enumerate(rows):
            history = raw.iloc[row-48:row+1].copy().reset_index(drop=True)
            injected = inject(history,kind,rng)
            frame = model_frame(injected).iloc[[-1]].copy()
            expected = 0 if kind=="normal" else (2 if kind in ENVIRONMENT_KINDS else 1)
            if int(frame.anomaly_class.iloc[0]) != expected:
                raise ValueError(f"Scenario {kind} violates label contract: {frame.anomaly_reason.iloc[0]}")
            event_id = f"{partition}-{seed}-{kind}-{number}"
            edits = []
            for i,col in zip(*np.where(~np.isclose(history.iloc[:,1:].to_numpy(float),injected.iloc[:,1:].to_numpy(float),rtol=0,atol=1e-12))):
                name = history.columns[col+1]
                edits.append({"timestamp":str(history.timestamp.iloc[i]),"column":name,
                    "original":float(history[name].iloc[i]),"injected":float(injected[name].iloc[i])})
            manifest.append({"event_id":event_id,"scenario_version":SCENARIO_VERSION,"partition":partition,
                "seed":seed,"kind":kind,"source_start":str(history.timestamp.iloc[0]),
                "source_end":str(history.timestamp.iloc[-1]),"source_sha256":hashlib.sha256(history.to_csv(index=False).encode()).hexdigest(),
                "label":expected,"reason":frame.anomaly_reason.iloc[0],"edits":edits})
            frame['event_id'],frame['kind'] = event_id,kind
            frames.append(frame)
    result = pd.concat(frames,ignore_index=True)
    return result, manifest


def scenario_features(frame):
    return frame[[c for c in feature_columns(frame) if c not in {'kind','event_id'}]].astype(float)
