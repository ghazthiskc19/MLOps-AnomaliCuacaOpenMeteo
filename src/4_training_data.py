"""Strict hourly-data and history contract shared by training and inference.

LK04 calculation code is reused unchanged. Naive timestamps mean WIB. Missing
raw readings and undefined derived features fail explicitly in this version;
they are never silently dropped, clipped to normal, or filled from the future.
"""

import hashlib
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.data_preprocessing import RAW_COLUMNS, REPO_ROOT, WeatherPreprocessor

WARMUP_HOURS = 48
LOCAL_TIMEZONE = "Asia/Jakarta"
EXCLUDED_COLUMNS = {"timestamp", "anomaly_class", "anomaly_reason"}


def normalize_raw(frame: pd.DataFrame) -> pd.DataFrame:
    """Require unambiguous, finite, unique, ordered hourly observations."""
    if frame.empty or len(frame.columns) != len(RAW_COLUMNS) or set(frame.columns) != set(RAW_COLUMNS):
        raise ValueError(f"Input harus nonempty dengan tepat kolom raw: {RAW_COLUMNS}")
    result = frame.loc[:, RAW_COLUMNS].copy().reset_index(drop=True)
    timestamps = []
    for value in result["timestamp"]:
        try:
            ts = pd.Timestamp(value)
            if pd.isna(ts):
                raise ValueError("timestamp kosong")
            ts = ts.tz_localize(LOCAL_TIMEZONE) if ts.tzinfo is None else ts.tz_convert(LOCAL_TIMEZONE)
            timestamps.append(ts.tz_localize(None))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"Timestamp tidak valid: {value!r}") from exc
    result["timestamp"] = pd.DatetimeIndex(timestamps)
    if result.timestamp.duplicated().any():
        raise ValueError("Timestamp duplikat: selesaikan konflik sebelum training.")
    if not result.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Timestamp harus terurut dengan interval tepat satu jam; ada gap/urutan salah.")
    sensors = RAW_COLUMNS[1:]
    try:
        result[sensors] = result[sensors].apply(pd.to_numeric, errors="raise").astype("float64")
    except (ValueError, TypeError) as exc:
        raise ValueError("Sensor harus numerik; tidak mengubah nilai rusak menjadi nol.") from exc
    if not np.isfinite(result[sensors].to_numpy()).all():
        raise ValueError("Sensor memiliki NaN/inf; dukungan missing memerlukan kebijakan eksplisit.")
    return result


def feature_columns(frame: pd.DataFrame) -> list[str]:
    return [name for name in frame.columns if name not in EXCLUDED_COLUMNS]


def prepare_training_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep the first 48 hours as context only; all later rows are eligible."""
    normalized = normalize_raw(raw)
    if len(normalized) <= WARMUP_HOURS:
        raise ValueError("Butuh minimal 49 baris: 48 jam histori + satu observasi.")
    processed = WeatherPreprocessor().process(normalized)
    columns = feature_columns(processed)
    values = processed[columns].to_numpy(dtype=np.float64)
    invalid = ~np.isfinite(values) | (np.abs(values) > np.finfo(np.float32).max)
    if invalid.any():
        bad_columns = np.asarray(columns)[invalid.any(axis=0)].tolist()
        raise ValueError(f"Fitur harus finite dan muat float32 setelah engineering: {bad_columns}")
    return processed.iloc[WARMUP_HOURS:].copy().reset_index(drop=True)


def latest_features(raw_history: pd.DataFrame, expected_columns: list[str]) -> pd.DataFrame:
    """Build one current feature row from >=49 ordered hourly raw observations.

    Pass real history, including previous training/validation observations when
    available. Do not call this on a lone row or synthetically pad history.
    """
    prepared = prepare_training_frame(raw_history)
    if feature_columns(prepared) != list(expected_columns):
        raise ValueError("Nama/urutan fitur berbeda dari kontrak model.")
    return prepared.loc[:, expected_columns].iloc[[-1]].astype("float64").reset_index(drop=True)


def verify_dataset(path: Path, dataset_tag: str) -> dict:
    """Verify bytes against both the workspace pointer and the chosen Git tag."""
    path = Path(path).resolve()
    try:
        relative = path.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("Dataset harus berada di repository dan memiliki pointer DVC.") from exc
    pointer = Path(str(path) + ".dvc")
    if not pointer.is_file():
        raise ValueError(f"Pointer DVC tidak ditemukan: {relative.as_posix()}.dvc")
    try:
        tagged_text = subprocess.check_output(
            ["git", "show", f"{dataset_tag}:{relative.as_posix()}.dvc"],
            cwd=REPO_ROOT, text=True, stderr=subprocess.PIPE,
        )
        tag_commit = subprocess.check_output(
            ["git", "rev-parse", f"{dataset_tag}^{{commit}}"], cwd=REPO_ROOT, text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Dataset/pointer tidak tersedia pada tag {dataset_tag}.") from exc
    workspace = yaml.safe_load(pointer.read_text(encoding="utf-8"))["outs"][0]
    tagged = yaml.safe_load(tagged_text)["outs"][0]
    content = path.read_bytes()
    digest = hashlib.md5(content).hexdigest()
    for name, metadata in [("workspace", workspace), (dataset_tag, tagged)]:
        if metadata.get("md5") != digest or metadata.get("size") != len(content):
            raise ValueError(f"Isi dataset berbeda dari pointer {name}: {relative.as_posix()}")
    return {
        "path": relative.as_posix(), "md5": digest, "bytes": len(content),
        "dataset_tag": dataset_tag, "dataset_tag_commit": tag_commit,
        "pointer_sha256": hashlib.sha256(pointer.read_bytes()).hexdigest(),
    }
