"""
tests/test_simulate_data.py - Pengujian src/3_simulate_data.py (skenario faults dan drift).
"""

from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from src.data_preprocessing import AnomalyLabeler, WeatherPreprocessor
from src.simulate_data import DriftSimulator, FaultInjector, default_output_path, main, simulate


def make_normal_df(periods: int = 240) -> pd.DataFrame:
    """Data normal per jam tanpa hujan (default 10 hari)."""
    timestamps = pd.date_range("2026-09-01 00:00:00", periods=periods, freq="h")
    hours = timestamps.hour.to_numpy()
    return pd.DataFrame({
        "timestamp": timestamps,
        "temperature_2m_C": 24.0 + 4.0 * np.sin(2 * np.pi * hours / 24.0),
        "humidity_percent": 75.0,
        "precipitation_mm": 0.0,
        "soil_moisture": 0.25,
        "radiation_wm2": np.where((hours >= 6) & (hours < 18), 500.0, 0.0),
        "wind_speed_kmh": 5.0,
    })


class TestFaultInjector(unittest.TestCase):
    def setUp(self):
        self.df = make_normal_df()

    def test_zero_rate_returns_unchanged_copy(self):
        """Verifikasi fault_rate=0 tidak mengubah data sama sekali."""
        out = FaultInjector(fault_rate=0.0).apply(self.df)
        pd.testing.assert_frame_equal(out, self.df)

    def test_injection_produces_class_1_without_mutating_input(self):
        """Verifikasi injeksi menghasilkan baris Class 1 dan tidak mengubah DataFrame input."""
        original = self.df.copy()
        injected = FaultInjector(fault_rate=0.05, seed=7).apply(self.df)
        pd.testing.assert_frame_equal(self.df, original)

        self.assertEqual((AnomalyLabeler().label(self.df)["anomaly_class"] == 1).sum(), 0)
        n_class_1 = (AnomalyLabeler().label(injected)["anomaly_class"] == 1).sum()
        self.assertGreaterEqual(n_class_1, 12)  # 5% x 240 baris titik + blok stuck

    def test_same_seed_is_deterministic(self):
        """Verifikasi seed yang sama menghasilkan dataset identik (reproducible)."""
        a = FaultInjector(fault_rate=0.05, seed=42).apply(self.df)
        b = FaultInjector(fault_rate=0.05, seed=42).apply(self.df)
        c = FaultInjector(fault_rate=0.05, seed=43).apply(self.df)
        pd.testing.assert_frame_equal(a, b)
        self.assertFalse(a.equals(c))

    def test_invalid_rate_raises(self):
        """Verifikasi fault_rate di luar rentang ditolak."""
        with self.assertRaises(ValueError):
            FaultInjector(fault_rate=0.6)


class TestDriftSimulator(unittest.TestCase):
    def setUp(self):
        self.df = make_normal_df()
        self.df.loc[10:20, "precipitation_mm"] = 1.5

    def test_shifts_distribution(self):
        """Verifikasi rata-rata suhu, kelembaban, dan presipitasi bergeser sesuai parameter."""
        out = DriftSimulator(temp_shift=3.0, humidity_shift=-15.0, precip_scale=2.0).apply(self.df)
        self.assertAlmostEqual(out["temperature_2m_C"].mean() - self.df["temperature_2m_C"].mean(), 3.0, delta=0.1)
        self.assertAlmostEqual(out["humidity_percent"].mean(), 60.0)
        self.assertAlmostEqual(out["precipitation_mm"].sum(), 2.0 * self.df["precipitation_mm"].sum())

    def test_stays_within_physical_bounds(self):
        """Verifikasi drift ekstrem tidak menghasilkan Hardware Fault palsu."""
        out = DriftSimulator(temp_shift=0.0, humidity_shift=50.0, precip_scale=0.0).apply(self.df)
        self.assertLessEqual(out["humidity_percent"].max(), 100.0)
        self.assertGreaterEqual(out["precipitation_mm"].min(), 0.0)

    def test_negative_precip_scale_raises(self):
        with self.assertRaises(ValueError):
            DriftSimulator(precip_scale=-1.0)


class TestSimulateIO(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw_path = Path(self.tmp.name) / "raw.csv"
        make_normal_df().to_csv(self.raw_path, index=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_simulate_writes_output_and_keeps_original(self):
        """Verifikasi file simulasi ditulis, data asli utuh, dan hasil bisa diproses preprocessing."""
        before = self.raw_path.read_bytes()
        out_path = Path(self.tmp.name) / "sim" / "faults.csv"
        simulate("faults", input_path=self.raw_path, output_path=out_path, seed=1)

        self.assertEqual(self.raw_path.read_bytes(), before)
        self.assertTrue(out_path.exists())
        processed = WeatherPreprocessor().process(pd.read_csv(out_path))
        self.assertGreater((processed["anomaly_class"] == 1).sum(), 0)

    def test_refuses_to_overwrite_original(self):
        with self.assertRaises(ValueError):
            simulate("drift", input_path=self.raw_path, output_path=self.raw_path)

    def test_unknown_scenario_raises(self):
        with self.assertRaises(ValueError):
            simulate("concept", input_path=self.raw_path, output_path=Path(self.tmp.name) / "x.csv")

    def test_cli_main(self):
        out_path = Path(self.tmp.name) / "drift.csv"
        code = main(["--scenario", "drift", "--input-path", str(self.raw_path), "--output-path", str(out_path)])
        self.assertEqual(code, 0)
        self.assertTrue(out_path.exists())

    def test_default_output_path(self):
        self.assertEqual(default_output_path("faults", 42).name, "weather_faults_s42.csv")
        self.assertEqual(default_output_path("faults", 42).parent.name, "simulated")


if __name__ == "__main__":
    unittest.main()
