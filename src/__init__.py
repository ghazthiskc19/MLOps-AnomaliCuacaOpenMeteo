"""
Source code package untuk MLOps-AnomaliCuacaOpenMeteo.

Nama file bernomor membantu navigasi. Nama import tetap valid dan stabil,
misalnya ``from src.data_ingestion import fetch_weather_data``. LazyLoader
mencegah import utilitas ingestion ikut memuat sklearn atau seluruh pipeline.
"""

from importlib.util import LazyLoader, module_from_spec, spec_from_file_location
from pathlib import Path
import sys

_MODULE_FILES = {
    "data_ingestion": "0_data_ingestion.py",
    "data_preprocessing": "1_data_preprocessing.py",
    "r2_sync": "2_r2_sync.py",
    "simulate_data": "3_simulate_data.py",
    "training_data": "4_training_data.py",
    "model_evaluation": "5_model_evaluation.py",
    "ingest_data": "6_ingest_data.py",
    "preprocess": "7_preprocess.py",
}

for _name, _filename in _MODULE_FILES.items():
    _fullname = f"{__name__}.{_name}"
    if _fullname not in sys.modules:
        _spec = spec_from_file_location(_fullname, Path(__file__).with_name(_filename))
        _spec.loader = LazyLoader(_spec.loader)
        _module = module_from_spec(_spec)
        sys.modules[_fullname] = _module
        _spec.loader.exec_module(_module)
    globals()[_name] = sys.modules[_fullname]

__all__ = list(_MODULE_FILES)
