"""
ingest_data.py - Wrapper / entrypoint modul penarikan data cuaca (LK-04).
Mendelegasikan eksekusi ke src.data_ingestion.
"""

import sys
from pathlib import Path

# Memastikan root repositori berada dalam sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data_ingestion import (  # noqa: E402
    DEFAULT_BUFFER_HOURS,
    DEFAULT_LATITUDE,
    DEFAULT_LONGITUDE,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_RAW_DIR,
    RAW_COLUMNS,
    REPO_ROOT,
    _atomic_to_csv,
    fetch_weather_data,
    ingest_weather_data,
    main,
    resolve_path,
    save_weather_data,
)

__all__ = [
    "DEFAULT_BUFFER_HOURS",
    "DEFAULT_LATITUDE",
    "DEFAULT_LONGITUDE",
    "DEFAULT_OUTPUT_PATH",
    "DEFAULT_RAW_DIR",
    "RAW_COLUMNS",
    "REPO_ROOT",
    "resolve_path",
    "_atomic_to_csv",
    "fetch_weather_data",
    "save_weather_data",
    "ingest_weather_data",
    "main",
]

if __name__ == "__main__":
    main()
