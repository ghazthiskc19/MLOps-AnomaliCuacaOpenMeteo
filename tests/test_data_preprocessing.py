"""
test_data_preprocessing.py - Unit tests untuk modul src/data_preprocessing.py dan src/preprocess.py.

Menguji secara mendalam:
1. DataCleaner (Quality Gate): parsing timestamp, pembuangan NaT, deduplikasi, skema kolom.
2. AnomalyLabeler (Taksonomi LK-03):
   - Class 0: Baseline Normal State
   - Class 1: Hardware Fault & Sensor Failure (Null, OOB, Night Glitch, Discordance, Spiking, Stuck Values)
   - Class 2: Extreme Environmental Anomaly (Heatwave, Frost, Dry Air, Torrential Rain, Drought, Waterlogging, High Wind)
3. FeatureEngineer: siklus temporal (sin/cos), VPD, Dew Point, lag differences, rolling statistics.
4. WeatherPreprocessor: eksekusi end-to-end, penulisan atomik CSV, dan integrasi CLI/facade.
"""

from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from src.data_preprocessing import (
    ANOMALY_CLASSES,
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    RAW_COLUMNS,
    AnomalyLabeler,
    DataCleaner,
    FeatureEngineer,
    WeatherPreprocessor,
    preprocess_weather_data,
    resolve_path,
)


class TestDataCleaner(unittest.TestCase):
    def setUp(self):
        self.cleaner = DataCleaner()

    def test_clean_normal_data(self):
        """Verifikasi pembersihan data cuaca yang normal dan berurutan."""
        df = pd.DataFrame({
            "timestamp": ["2026-09-20 02:00:00", "2026-09-20 01:00:00"],
            "temperature_2m_C": ["22.5", 21.0],
            "humidity_percent": [85, 90.0],
            "precipitation_mm": [0.0, "0.1"],
            "soil_moisture": [0.25, 0.26],
            "radiation_wm2": [0.0, 0.0],
            "wind_speed_kmh": [5.0, 4.5],
        })
        cleaned = self.cleaner.clean(df)
        self.assertEqual(len(cleaned), 2)
        # Harus terurut secara kronologis
        self.assertEqual(cleaned.iloc[0]["timestamp"], pd.Timestamp("2026-09-20 01:00:00"))
        self.assertEqual(cleaned.iloc[1]["timestamp"], pd.Timestamp("2026-09-20 02:00:00"))
        self.assertTrue(pd.api.types.is_float_dtype(cleaned["temperature_2m_C"]))

    def test_clean_deduplication(self):
        """Verifikasi bahwa duplikat timestamp dibuang dan menyisakan data terbaru."""
        df = pd.DataFrame({
            "timestamp": ["2026-09-20 01:00:00", "2026-09-20 01:00:00"],
            "temperature_2m_C": [20.0, 25.0],
            "humidity_percent": [80.0, 85.0],
            "precipitation_mm": [0.0, 0.0],
            "soil_moisture": [0.25, 0.25],
            "radiation_wm2": [0.0, 0.0],
            "wind_speed_kmh": [5.0, 5.0],
        })
        cleaned = self.cleaner.clean(df)
        self.assertEqual(len(cleaned), 1)
        # Nilai terakhir (25.0) yang harus dipertahankan
        self.assertEqual(cleaned.iloc[0]["temperature_2m_C"], 25.0)

    def test_clean_invalid_timestamps(self):
        """Verifikasi bahwa timestamp NaT atau string acak dibuang."""
        df = pd.DataFrame({
            "timestamp": ["2026-09-20 01:00:00", "invalid_time_string", None],
            "temperature_2m_C": [21.0, 22.0, 23.0],
            "humidity_percent": [80.0, 80.0, 80.0],
            "precipitation_mm": [0.0, 0.0, 0.0],
            "soil_moisture": [0.25, 0.25, 0.25],
            "radiation_wm2": [0.0, 0.0, 0.0],
            "wind_speed_kmh": [5.0, 5.0, 5.0],
        })
        cleaned = self.cleaner.clean(df)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned.iloc[0]["timestamp"], pd.Timestamp("2026-09-20 01:00:00"))

    def test_clean_missing_columns_raises(self):
        """Verifikasi bahwa ketiadaan kolom wajib melempar ValueError."""
        df = pd.DataFrame({
            "timestamp": ["2026-09-20 01:00:00"],
            "temperature_2m_C": [21.0],
        })
        with self.assertRaises(ValueError):
            self.cleaner.clean(df)

    def test_clean_empty_dataframe(self):
        """Verifikasi bahwa DataFrame kosong ditangani tanpa galat."""
        df = pd.DataFrame(columns=RAW_COLUMNS)
        cleaned = self.cleaner.clean(df)
        self.assertTrue(cleaned.empty)
        for col in RAW_COLUMNS:
            self.assertIn(col, cleaned.columns)


class TestAnomalyLabeler(unittest.TestCase):
    def setUp(self):
        self.labeler = AnomalyLabeler()

    def _create_base_row(self, **kwargs):
        row = {
            "timestamp": pd.Timestamp("2026-09-20 12:00:00"),
            "temperature_2m_C": 26.0,
            "humidity_percent": 70.0,
            "precipitation_mm": 0.0,
            "soil_moisture": 0.28,
            "radiation_wm2": 650.0,
            "wind_speed_kmh": 10.0,
            "temp_diff_1h": 0.5,
            "temp_std_12h": 1.2,
            "humidity_stuck_100_24h": False,
            "wind_zero_48h": False,
            "soil_diff_1h": 0.0,
            "soil_waterlogged_48h": False,
        }
        row.update(kwargs)
        return pd.Series(row)

    def test_class_0_normal_state(self):
        """Verifikasi data normal diklasifikasikan sebagai Class 0."""
        # Siang hari
        row_day = self._create_base_row()
        cls, reason = self.labeler.classify_row(row_day)
        self.assertEqual(cls, 0)
        self.assertEqual(reason, "Normal State")

        # Malam hari (radiasi 0)
        row_night = self._create_base_row(
            timestamp=pd.Timestamp("2026-09-20 22:00:00"),
            temperature_2m_C=20.5,
            humidity_percent=85.0,
            radiation_wm2=0.0,
            wind_speed_kmh=5.0,
        )
        cls, reason = self.labeler.classify_row(row_night)
        self.assertEqual(cls, 0)

    def test_class_1_missing_value(self):
        """Verifikasi missing value (NaN) diklasifikasikan sebagai Class 1 Hardware Fault."""
        for col in self.labeler.required_sensor_cols:
            row = self._create_base_row(**{col: np.nan})
            cls, reason = self.labeler.classify_row(row)
            self.assertEqual(cls, 1)
            self.assertIn(f"Missing / NaN in '{col}'", reason)

    def test_class_1_temperature_oob(self):
        """Verifikasi suhu out-of-bounds (< -20 atau > 55) sebagai Class 1."""
        row_low = self._create_base_row(temperature_2m_C=-25.0)
        cls, reason = self.labeler.classify_row(row_low)
        self.assertEqual(cls, 1)
        self.assertIn("Temperature OOB", reason)

        row_high = self._create_base_row(temperature_2m_C=60.0)
        cls, reason = self.labeler.classify_row(row_high)
        self.assertEqual(cls, 1)
        self.assertIn("Temperature OOB", reason)

    def test_class_1_humidity_oob(self):
        """Verifikasi kelembaban out-of-bounds (< 0 atau > 100) sebagai Class 1."""
        row_neg = self._create_base_row(humidity_percent=-5.0)
        cls, reason = self.labeler.classify_row(row_neg)
        self.assertEqual(cls, 1)
        self.assertIn("Humidity OOB", reason)

        row_over = self._create_base_row(humidity_percent=105.0)
        cls, reason = self.labeler.classify_row(row_over)
        self.assertEqual(cls, 1)
        self.assertIn("Humidity OOB", reason)

    def test_class_1_negative_precipitation_radiation_wind(self):
        """Verifikasi presipitasi, radiasi, atau angin negatif sebagai Class 1."""
        cls, reason = self.labeler.classify_row(self._create_base_row(precipitation_mm=-1.0))
        self.assertEqual(cls, 1)
        self.assertIn("Negative precipitation", reason)

        cls, reason = self.labeler.classify_row(self._create_base_row(radiation_wm2=-10.0))
        self.assertEqual(cls, 1)
        self.assertIn("Negative radiation", reason)

        cls, reason = self.labeler.classify_row(self._create_base_row(wind_speed_kmh=-2.0))
        self.assertEqual(cls, 1)
        self.assertIn("Negative wind speed", reason)

    def test_class_1_soil_oob(self):
        """Verifikasi kelembaban tanah OOB (< 0.0 atau > 0.55 m3/m3) sebagai Class 1."""
        cls, reason = self.labeler.classify_row(self._create_base_row(soil_moisture=-0.05))
        self.assertEqual(cls, 1)
        self.assertIn("Soil moisture OOB", reason)

        cls, reason = self.labeler.classify_row(self._create_base_row(soil_moisture=0.62))
        self.assertEqual(cls, 1)
        self.assertIn("Soil moisture OOB", reason)

    def test_class_1_night_radiation_glitch(self):
        """Verifikasi radiasi matahari di malam hari (20:00 s.d. 04:00 WIB) sebagai Class 1."""
        row_night_glitch = self._create_base_row(
            timestamp=pd.Timestamp("2026-09-20 23:00:00"),
            radiation_wm2=85.0,
        )
        cls, reason = self.labeler.classify_row(row_night_glitch)
        self.assertEqual(cls, 1)
        self.assertIn("Night radiation glitch", reason)

    def test_class_1_cross_feature_discordance(self):
        """Verifikasi kontradiksi fisika antar-sensor sebagai Class 1."""
        # Hujan deras di tengah radiasi terik ekstrem
        row_rain_sun = self._create_base_row(
            precipitation_mm=20.0,
            radiation_wm2=900.0,
        )
        cls, reason = self.labeler.classify_row(row_rain_sun)
        self.assertEqual(cls, 1)
        self.assertIn("Discordance", reason)

        # Lonjakan kelembaban tanah > 0.3 tanpa hujan di bawah sinar terik
        row_soil_surge = self._create_base_row(
            precipitation_mm=0.0,
            radiation_wm2=850.0,
            soil_diff_1h=0.35,
        )
        cls, reason = self.labeler.classify_row(row_soil_surge)
        self.assertEqual(cls, 1)
        self.assertIn("Soil moisture surge", reason)

        # Hujan sangat lebat > 20 mm tapi sensor tanah tidak merespon sama sekali
        row_soil_dead = self._create_base_row(
            precipitation_mm=22.0,
            soil_diff_1h=0.0,
            radiation_wm2=100.0,
        )
        cls, reason = self.labeler.classify_row(row_soil_dead)
        self.assertEqual(cls, 1)
        self.assertIn("Soil probe unresponsive", reason)

    def test_class_1_gradient_spiking(self):
        """Verifikasi lonjakan suhu drastis > 8°C/jam tanpa presipitasi sebagai Class 1."""
        # Lonjakan positif (+9.5°C/jam)
        row_spike_pos = self._create_base_row(
            temp_diff_1h=9.5,
            precipitation_mm=0.0,
        )
        cls, reason = self.labeler.classify_row(row_spike_pos)
        self.assertEqual(cls, 1)
        self.assertIn("Temperature spike", reason)

        # Penurunan drastis negatif (-9.5°C/jam) tanpa presipitasi
        row_spike_neg = self._create_base_row(
            temp_diff_1h=-9.5,
            precipitation_mm=0.0,
        )
        cls, reason = self.labeler.classify_row(row_spike_neg)
        self.assertEqual(cls, 1)
        self.assertIn("Temperature spike", reason)

    def test_class_1_stuck_values(self):
        """Verifikasi sensor macet (stuck value) sebagai Class 1."""
        # Suhu konstan 12 jam (std == 0.0)
        row_temp_stuck = self._create_base_row(temp_std_12h=0.0)
        cls, reason = self.labeler.classify_row(row_temp_stuck)
        self.assertEqual(cls, 1)
        self.assertIn("Temperature sensor stuck", reason)

        # Kelembaban 100% jenuh selama >24 jam
        row_hum_stuck = self._create_base_row(humidity_stuck_100_24h=True)
        cls, reason = self.labeler.classify_row(row_hum_stuck)
        self.assertEqual(cls, 1)
        self.assertIn("Humidity saturated 100% stuck", reason)

        # Angin 0.0 km/h macet selama >48 jam
        row_wind_stuck = self._create_base_row(wind_zero_48h=True)
        cls, reason = self.labeler.classify_row(row_wind_stuck)
        self.assertEqual(cls, 1)
        self.assertIn("Anemometer stuck at 0.0 km/h", reason)

    def test_class_1_stuck_temperature_float_precision(self):
        """Verifikasi ketahanan terhadap floating-point roundoff (std non-zero misal 3.71e-15 untuk 25.1°C konstan)."""
        series_float = pd.Series([25.1] * 12)
        std_val = float(series_float.std())
        # Pastikan std_val adalah float non-zero kecil (IEEE 754 epsilon)
        row_stuck_float = self._create_base_row(temp_std_12h=std_val)
        cls, reason = self.labeler.classify_row(row_stuck_float)
        self.assertEqual(cls, 1)
        self.assertIn("Temperature sensor stuck", reason)

    def test_class_1_night_radiation_timezone_aware(self):
        """Verifikasi konversi timezone pada deteksi night radiation glitch (UTC 16:00 = 23:00 WIB)."""
        ts_utc = pd.Timestamp("2026-09-20 16:00:00+00:00")  # 16:00 UTC == 23:00 WIB
        row_utc = self._create_base_row(
            timestamp=ts_utc,
            radiation_wm2=50.0,
        )
        cls, reason = self.labeler.classify_row(row_utc)
        self.assertEqual(cls, 1)
        self.assertIn("Night radiation glitch", reason)

    def test_class_1_numpy_bool_indicators(self):
        """Verifikasi bahwa numpy.bool_(True) dievaluasi dengan benar tanpa galat 'is True' pointer check."""
        row_np_bool = self._create_base_row(
            humidity_stuck_100_24h=np.bool_(True),
            wind_zero_48h=np.bool_(True),
        )
        cls, reason = self.labeler.classify_row(row_np_bool)
        self.assertEqual(cls, 1)
        self.assertTrue("Humidity" in reason or "Anemometer" in reason)

    def test_class_2_extreme_weather(self):
        """Verifikasi kondisi iklim ekstrem agrikultur diklasifikasikan sebagai Class 2."""
        # Panas ekstrem > 33.5°C
        cls, reason = self.labeler.classify_row(self._create_base_row(temperature_2m_C=35.0))
        self.assertEqual(cls, 2)
        self.assertIn("Heatwave / Heat Stress", reason)

        # Dingin ekstrem < 15.0°C
        cls, reason = self.labeler.classify_row(self._create_base_row(temperature_2m_C=13.5))
        self.assertEqual(cls, 2)
        self.assertIn("Severe Cold / Frost Risk", reason)

        # Udara kering ekstrem < 40.0%
        cls, reason = self.labeler.classify_row(self._create_base_row(humidity_percent=32.0))
        self.assertEqual(cls, 2)
        self.assertIn("Severe Dry Air", reason)

        # Badai hujan ekstrem > 25.0 mm/jam (dengan respons sensor tanah normal)
        cls, reason = self.labeler.classify_row(
            self._create_base_row(precipitation_mm=32.0, radiation_wm2=50.0, soil_diff_1h=0.05)
        )
        self.assertEqual(cls, 2)
        self.assertIn("Torrential Rainfall", reason)

        # Kekeringan kritis < 0.08 m3/m3
        cls, reason = self.labeler.classify_row(self._create_base_row(soil_moisture=0.06))
        self.assertEqual(cls, 2)
        self.assertIn("Critical Drought / Wilting Point", reason)

        # Kejenuhan air / waterlogging > 0.48 m3/m3
        cls, reason = self.labeler.classify_row(self._create_base_row(soil_moisture=0.51))
        self.assertEqual(cls, 2)
        self.assertIn("Waterlogging / Root Anoxia", reason)

        # Radiasi matahari ekstrem > 1100 W/m2
        cls, reason = self.labeler.classify_row(self._create_base_row(radiation_wm2=1250.0))
        self.assertEqual(cls, 2)
        self.assertIn("Extreme Solar Radiation", reason)

        # Angin kencang / badai > 40.0 km/h
        cls, reason = self.labeler.classify_row(self._create_base_row(wind_speed_kmh=48.0))
        self.assertEqual(cls, 2)
        self.assertIn("High Gale Wind", reason)

    def test_label_dataframe_sequence(self):
        """Verifikasi bahwa labeler bekerja secara akurat pada DataFrame beruntun."""
        dates = pd.date_range("2026-09-20 00:00", periods=50, freq="h")
        df = pd.DataFrame({
            "timestamp": dates,
            "temperature_2m_C": [25.0] * 50,  # Konstan -> akan trigger stuck value setelah 12 jam
            "humidity_percent": [70.0] * 50,
            "precipitation_mm": [0.0] * 50,
            "soil_moisture": [0.30] * 50,
            "radiation_wm2": [0.0 if d.hour >= 20 or d.hour < 4 else 500.0 for d in dates],
            "wind_speed_kmh": [10.0] * 50,
        })
        labeled = self.labeler.label(df)
        self.assertIn("anomaly_class", labeled.columns)
        self.assertIn("anomaly_reason", labeled.columns)
        # Jam ke-0 s.d. 10 (belum 12 baris) masih normal
        self.assertEqual(labeled.iloc[5]["anomaly_class"], 0)
        # Jam ke-12 ke atas harus terdeteksi sebagai stuck value (Class 1)
        self.assertEqual(labeled.iloc[15]["anomaly_class"], 1)
        self.assertIn("stuck", labeled.iloc[15]["anomaly_reason"])


class TestFeatureEngineer(unittest.TestCase):
    def setUp(self):
        self.engineer = FeatureEngineer()

    def test_temporal_cyclical_features(self):
        """Verifikasi fitur sinus dan kosinus untuk jam dan bulan."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01 00:00", periods=24, freq="h"),
            "temperature_2m_C": [22.0] * 24,
            "humidity_percent": [80.0] * 24,
            "precipitation_mm": [0.0] * 24,
            "soil_moisture": [0.25] * 24,
            "radiation_wm2": [0.0] * 24,
            "wind_speed_kmh": [5.0] * 24,
        })
        feat = self.engineer.transform(df)

        self.assertIn("hour_sin", feat.columns)
        self.assertIn("hour_cos", feat.columns)
        self.assertIn("month_sin", feat.columns)
        self.assertIn("month_cos", feat.columns)
        self.assertIn("is_weekend", feat.columns)

        # Nilai sin/cos harus berada dalam batas [-1.0, 1.0]
        self.assertTrue((feat["hour_sin"] >= -1.0).all() and (feat["hour_sin"] <= 1.0).all())
        self.assertTrue((feat["hour_cos"] >= -1.0).all() and (feat["hour_cos"] <= 1.0).all())

    def test_biophysical_features(self):
        """Verifikasi perhitungan VPD (Vapor Pressure Deficit) dan Titik Embun (Dew Point)."""
        temp = pd.Series([25.0, 30.0, 35.0])
        hum = pd.Series([60.0, 40.0, 20.0])

        vpd = self.engineer.calculate_vpd(temp, hum)
        self.assertTrue((vpd >= 0.0).all(), "VPD tidak boleh bernilai negatif")
        # Semakin panas dan kering, VPD harus semakin tinggi
        self.assertTrue(vpd.iloc[2] > vpd.iloc[0])

        dew_point = self.engineer.calculate_dew_point(temp, hum)
        # Titik embun tidak boleh melebihi suhu udara
        self.assertTrue((dew_point <= temp).all())

    def test_rolling_and_lag_features(self):
        """Verifikasi fitur selisih waktu dan statistik rolling window."""
        df = pd.DataFrame({
            "timestamp": pd.date_range("2026-09-01 00:00", periods=48, freq="h"),
            "temperature_2m_C": np.linspace(20.0, 30.0, 48),
            "humidity_percent": np.linspace(90.0, 60.0, 48),
            "precipitation_mm": [0.5] * 48,
            "soil_moisture": [0.25] * 48,
            "radiation_wm2": [100.0] * 48,
            "wind_speed_kmh": [5.0] * 48,
        })
        feat = self.engineer.transform(df)

        self.assertIn("temp_diff_1h", feat.columns)
        self.assertIn("temp_rolling_mean_3h", feat.columns)
        self.assertIn("temp_rolling_mean_24h", feat.columns)
        self.assertIn("precip_rolling_sum_24h", feat.columns)

        # Pastikan tidak ada NaN pada kolom diff setelah difill
        self.assertFalse(feat["temp_diff_1h"].isna().any())
        self.assertFalse(feat["temp_rolling_mean_3h"].isna().any())


class TestWeatherPreprocessor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.preprocessor = WeatherPreprocessor()

        # Buat dataset mentah sintetis
        dates = pd.date_range("2026-09-01 00:00", periods=72, freq="h")
        self.raw_df = pd.DataFrame({
            "timestamp": dates,
            "temperature_2m_C": 24.0 + 5.0 * np.sin(np.linspace(0, 6 * np.pi, 72)),
            "humidity_percent": 75.0 + 15.0 * np.cos(np.linspace(0, 6 * np.pi, 72)),
            "precipitation_mm": [0.0 if i % 12 != 0 else 5.0 for i in range(72)],
            "soil_moisture": 0.28,
            "radiation_wm2": [0.0 if d.hour >= 20 or d.hour < 4 else 600.0 for d in dates],
            "wind_speed_kmh": 8.0,
        })
        self.raw_csv_path = Path(self.temp_dir.name) / "raw.csv"
        self.out_csv_path = Path(self.temp_dir.name) / "features.csv"
        self.sec_csv_path = Path(self.temp_dir.name) / "features_curr.csv"
        self.raw_df.to_csv(self.raw_csv_path, index=False)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_process_file_io(self):
        """Verifikasi bahwa eksekusi file IO menghasilkan file CSV yang lengkap dan valid."""
        result = self.preprocessor.process_file(
            input_path=self.raw_csv_path,
            output_path=self.out_csv_path,
            secondary_output_path=self.sec_csv_path,
        )
        self.assertTrue(self.out_csv_path.exists())
        self.assertTrue(self.sec_csv_path.exists())
        self.assertEqual(len(result), 72)
        self.assertEqual(len(result.columns), 40)

        # Baca kembali berkas untuk memastikan formatnya valid
        loaded_df = pd.read_csv(self.out_csv_path)
        self.assertEqual(len(loaded_df), 72)
        self.assertIn("anomaly_class", loaded_df.columns)
        self.assertIn("vpd_kpa", loaded_df.columns)

    def test_missing_input_file_raises(self):
        """Verifikasi bahwa input path yang tidak ada melempar FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            self.preprocessor.process_file(input_path="non_existent_file.csv")

    def test_facade_function(self):
        """Verifikasi fungsi preprocess_weather_data berjalan dengan mulus."""
        df = preprocess_weather_data(
            input_path=self.raw_csv_path,
            output_path=self.out_csv_path,
            secondary_output_path=None,
        )
        self.assertEqual(len(df), 72)


if __name__ == "__main__":
    unittest.main()
