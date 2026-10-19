"""Numbered filenames preserve isolated imports and offline CLI entrypoints."""

from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent


class TestSourceEntrypoints(unittest.TestCase):
    def test_ingestion_import_does_not_load_training_dependencies(self):
        subprocess.run(
            [sys.executable, "-c", "import sys; from src.data_ingestion import fetch_weather_data; assert callable(fetch_weather_data); assert 'sklearn' not in sys.modules; assert 'mlflow' not in sys.modules"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )

    def test_numbered_cli_help_runs_without_fetching_or_training(self):
        for name in [
            "0_data_ingestion.py", "1_data_preprocessing.py", "2_r2_sync.py",
            "3_simulate_data.py", "6_ingest_data.py", "7_preprocess.py",
        ]:
            with self.subTest(script=name):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "src" / name), "--help"],
                    cwd=ROOT, check=True, capture_output=True, text=True,
                )
                self.assertIn("--help", result.stdout)


if __name__ == "__main__":
    unittest.main()
