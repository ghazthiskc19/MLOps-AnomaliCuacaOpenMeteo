"""
preprocess.py - Wrapper / entrypoint modul pemrosesan data cuaca (LK-04).
Mendelegasikan eksekusi ke src.data_preprocessing.
"""

import sys
from pathlib import Path

# Memastikan root repositori berada dalam sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data_preprocessing import (  # noqa: E402
    ANOMALY_CLASSES,
    DEFAULT_CURRENT_PROCESSED_PATH,
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_PROCESSED_DIR,
    RAW_COLUMNS,
    AnomalyLabeler,
    DataCleaner,
    FeatureEngineer,
    WeatherPreprocessor,
    main,
    preprocess_weather_data,
    resolve_path,
)

__all__ = [
    "ANOMALY_CLASSES",
    "RAW_COLUMNS",
    "DEFAULT_INPUT_PATH",
    "DEFAULT_OUTPUT_PATH",
    "DEFAULT_CURRENT_PROCESSED_PATH",
    "DEFAULT_PROCESSED_DIR",
    "resolve_path",
    "DataCleaner",
    "AnomalyLabeler",
    "FeatureEngineer",
    "WeatherPreprocessor",
    "preprocess_weather_data",
    "main",
]

if __name__ == "__main__":
    main()
