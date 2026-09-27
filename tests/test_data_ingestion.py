"""
Unit tests untuk src/data_ingestion.py.

Menguji:
1. Path resolution berbasis pathlib.Path relatif terhadap root repositori.
2. Ingestion dan parsing format respon Open-Meteo.
3. Fault-tolerant network retry logic dengan backoff.
4. Mekanisme deduplikasi timestamp.
5. Pemeliharaan buffer 30 hari (720 baris per jam).
6. Penanganan berkas kosong/rusak.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import requests

from src.data_ingestion import (
    DEFAULT_BUFFER_HOURS,
    DEFAULT_OUTPUT_PATH,
    RAW_COLUMNS,
    REPO_ROOT,
    _atomic_to_csv,
    fetch_weather_data,
    ingest_weather_data,
    resolve_path,
    save_weather_data,
)


class TestDataIngestion(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_csv_path = Path(self.temp_dir.name) / "test_weather_raw.csv"

        # Mock sample payload API Open-Meteo
        self.sample_api_response = {
            "latitude": -7.95,
            "longitude": 112.61,
            "timezone": "Asia/Jakarta",
            "hourly": {
                "time": ["2026-09-20T00:00", "2026-09-20T01:00", "2026-09-20T02:00"],
                "temperature_2m": [22.1, 21.8, 21.5],
                "relative_humidity_2m": [85.0, 87.0, 89.0],
                "precipitation": [0.0, 0.1, 0.0],
                "soil_moisture_0_to_7cm": [0.25, 0.25, 0.26],
                "shortwave_radiation": [0.0, 0.0, 0.0],
                "wind_speed_10m": [5.2, 4.8, 4.5],
            },
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_path_resolution(self):
        """Verifikasi bahwa REPO_ROOT dan DEFAULT_OUTPUT_PATH teresolusi dengan benar."""
        self.assertTrue(REPO_ROOT.is_dir(), f"REPO_ROOT {REPO_ROOT} harus merupakan direktori")
        self.assertTrue((REPO_ROOT / "src").is_dir(), "Direktori src harus berada di dalam REPO_ROOT")
        self.assertEqual(
            DEFAULT_OUTPUT_PATH,
            REPO_ROOT / "data" / "raw" / "weather_raw_current.csv",
        )

    @patch("src.data_ingestion.requests.get")
    def test_fetch_weather_data_success(self, mock_get):
        """Verifikasi parsing data yang berhasil dari respon API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.sample_api_response
        mock_get.return_value = mock_response

        df = fetch_weather_data(past_days=1, forecast_days=1, max_retries=1)

        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 3)
        for col in RAW_COLUMNS:
            self.assertIn(col, df.columns)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["timestamp"]))

    @patch("src.data_ingestion.requests.get")
    def test_fetch_weather_data_retry_on_failure_then_succeed(self, mock_get):
        """Verifikasi retry logic saat panggilan awal gagal dan panggilan berikutnya berhasil."""
        fail_response = MagicMock()
        fail_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.raise_for_status.return_value = None
        success_response.json.return_value = self.sample_api_response

        # Percobaan 1 gagal, percobaan 2 berhasil
        mock_get.side_effect = [fail_response, success_response]

        df = fetch_weather_data(max_retries=2, initial_delay=0.01, backoff_factor=1.0)
        self.assertEqual(len(df), 3)
        self.assertEqual(mock_get.call_count, 2)

    @patch("src.data_ingestion.requests.get")
    def test_fetch_weather_data_exhaust_retries_raises_connection_error(self, mock_get):
        """Verifikasi ConnectionError dilempar jika semua retry gagal."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Network unreachable")

        with self.assertRaises(ConnectionError):
            fetch_weather_data(max_retries=3, initial_delay=0.01, backoff_factor=1.0)
        self.assertEqual(mock_get.call_count, 3)

    def test_save_weather_data_new_file(self):
        """Menyimpan data ke berkas baru yang belum ada."""
        dates = pd.date_range("2026-09-01 00:00", periods=10, freq="h")
        df = pd.DataFrame({
            "timestamp": dates,
            "temperature_2m_C": [25.0] * 10,
            "humidity_percent": [80.0] * 10,
            "precipitation_mm": [0.0] * 10,
            "soil_moisture": [0.3] * 10,
            "radiation_wm2": [100.0] * 10,
            "wind_speed_kmh": [5.0] * 10,
        })

        saved_df = save_weather_data(df, output_path=self.test_csv_path, buffer_size=720)
        self.assertTrue(self.test_csv_path.exists())
        self.assertEqual(len(saved_df), 10)

        # Verifikasi konten dari pembacaan ulang
        disk_df = pd.read_csv(self.test_csv_path)
        self.assertEqual(len(disk_df), 10)

    def test_save_weather_data_deduplication(self):
        """Verifikasi deduplikasi timestamp ketika data bertumpuk."""
        dates1 = pd.date_range("2026-09-01 00:00", periods=5, freq="h")
        df1 = pd.DataFrame({
            "timestamp": dates1,
            "temperature_2m_C": [20.0, 21.0, 22.0, 23.0, 24.0],
            "humidity_percent": [80.0] * 5,
            "precipitation_mm": [0.0] * 5,
            "soil_moisture": [0.3] * 5,
            "radiation_wm2": [100.0] * 5,
            "wind_speed_kmh": [5.0] * 5,
        })
        save_weather_data(df1, output_path=self.test_csv_path)

        # Batch kedua dengan 3 data lama (nilai diperbarui) dan 2 data baru
        dates2 = pd.date_range("2026-09-01 02:00", periods=5, freq="h")
        df2 = pd.DataFrame({
            "timestamp": dates2,
            "temperature_2m_C": [99.0, 99.0, 99.0, 25.0, 26.0],  # 3 jam tumpang tindih bernilai 99.0
            "humidity_percent": [70.0] * 5,
            "precipitation_mm": [0.0] * 5,
            "soil_moisture": [0.3] * 5,
            "radiation_wm2": [100.0] * 5,
            "wind_speed_kmh": [5.0] * 5,
        })
        saved_df = save_weather_data(df2, output_path=self.test_csv_path)

        # Total baris unik: 7 (dari 00:00 hingga 06:00)
        self.assertEqual(len(saved_df), 7)
        # Nilai baris jam 02:00 harus 99.0 (keep='last')
        row_02 = saved_df[saved_df["timestamp"] == pd.Timestamp("2026-09-01 02:00:00")]
        self.assertEqual(row_02["temperature_2m_C"].values[0], 99.0)

    def test_save_weather_data_buffer_cap(self):
        """Verifikasi bahwa buffer dipangkas hingga kapasitas maksimum (default 720 baris)."""
        # Buat 800 baris jam
        dates = pd.date_range("2026-08-01 00:00", periods=800, freq="h")
        df = pd.DataFrame({
            "timestamp": dates,
            "temperature_2m_C": range(800),
            "humidity_percent": [70.0] * 800,
            "precipitation_mm": [0.0] * 800,
            "soil_moisture": [0.3] * 800,
            "radiation_wm2": [100.0] * 800,
            "wind_speed_kmh": [5.0] * 800,
        })

        buffer_limit = 720
        saved_df = save_weather_data(df, output_path=self.test_csv_path, buffer_size=buffer_limit)

        self.assertEqual(len(saved_df), buffer_limit)
        # Data yang tersisa harus merupakan 720 data paling mutakhir
        self.assertEqual(saved_df["timestamp"].iloc[-1], dates[-1])
        self.assertEqual(saved_df["timestamp"].iloc[0], dates[80])

    def test_save_weather_data_handles_corrupt_or_empty_file(self):
        """Verifikasi ketahanan saat file eksisting kosong atau korup."""
        # Buat file kosong 0 bytes
        self.test_csv_path.touch()

        dates = pd.date_range("2026-09-01 00:00", periods=3, freq="h")
        df = pd.DataFrame({
            "timestamp": dates,
            "temperature_2m_C": [25.0] * 3,
            "humidity_percent": [80.0] * 3,
            "precipitation_mm": [0.0] * 3,
            "soil_moisture": [0.3] * 3,
            "radiation_wm2": [100.0] * 3,
            "wind_speed_kmh": [5.0] * 3,
        })

        saved_df = save_weather_data(df, output_path=self.test_csv_path)
        self.assertEqual(len(saved_df), 3)

    @patch("src.data_ingestion.fetch_weather_data")
    def test_ingest_weather_data_adaptive_past_days(self, mock_fetch):
        """Verifikasi bahwa past_days ditentukan secara adaptif (30 jika file belum ada, 1 jika sudah penuh)."""
        dates = pd.date_range("2026-08-01 00:00", periods=720, freq="h")
        mock_df = pd.DataFrame({
            "timestamp": dates,
            "temperature_2m_C": [25.0] * 720,
            "humidity_percent": [80.0] * 720,
            "precipitation_mm": [0.0] * 720,
            "soil_moisture": [0.3] * 720,
            "radiation_wm2": [100.0] * 720,
            "wind_speed_kmh": [5.0] * 720,
        })
        mock_fetch.return_value = mock_df

        # Kasus 1: File belum ada -> past_days harus 30
        ingest_weather_data(output_path=self.test_csv_path, buffer_size=720)
        mock_fetch.assert_called_with(
            latitude=-7.95,
            longitude=112.61,
            past_days=30,
            forecast_days=1,
            max_retries=3,
            timeout=10.0,
        )

        # Kasus 2: File sudah terisi 720 baris -> past_days berikutnya harus 1
        mock_fetch.reset_mock()
        mock_fetch.return_value = mock_df.iloc[:24]
        ingest_weather_data(output_path=self.test_csv_path, buffer_size=720)
        mock_fetch.assert_called_with(
            latitude=-7.95,
            longitude=112.61,
            past_days=1,
            forecast_days=1,
            max_retries=3,
            timeout=10.0,
        )

    def test_resolve_path_relative_and_absolute(self):
        """Verifikasi bahwa resolve_path meresolusikan relative path terhadap REPO_ROOT."""
        rel_path = "data/raw/weather_raw_current.csv"
        resolved_rel = resolve_path(rel_path)
        self.assertEqual(resolved_rel, REPO_ROOT / "data" / "raw" / "weather_raw_current.csv")

        # Path absolut tidak boleh dimodifikasi
        abs_path = Path(self.temp_dir.name) / "custom.csv"
        resolved_abs = resolve_path(abs_path)
        self.assertEqual(resolved_abs, abs_path.resolve())

    def test_save_weather_data_missing_timestamp_raises_value_error(self):
        """Verifikasi bahwa save_weather_data melempar ValueError jika kolom timestamp tidak ada."""
        df_no_timestamp = pd.DataFrame({"temperature_2m_C": [25.0, 26.0]})
        with self.assertRaises(ValueError) as ctx:
            save_weather_data(df_no_timestamp, output_path=self.test_csv_path)
        self.assertIn("timestamp", str(ctx.exception))

    def test_save_weather_data_drops_nat_timestamps(self):
        """Verifikasi bahwa baris dengan timestamp invalid atau NaT dibuang sesuai kontrak non-nullable."""
        df_with_nat = pd.DataFrame({
            "timestamp": [pd.NaT, "2026-09-01 00:00:00", "invalid_date_format"],
            "temperature_2m_C": [20.0, 21.0, 22.0],
            "humidity_percent": [80.0, 81.0, 82.0],
            "precipitation_mm": [0.0, 0.0, 0.0],
            "soil_moisture": [0.3, 0.3, 0.3],
            "radiation_wm2": [100.0, 100.0, 100.0],
            "wind_speed_kmh": [5.0, 5.0, 5.0],
        })
        saved_df = save_weather_data(df_with_nat, output_path=self.test_csv_path)

        # Hanya 1 baris valid yang tersimpan ("2026-09-01 00:00:00")
        self.assertEqual(len(saved_df), 1)
        self.assertFalse(saved_df["timestamp"].isna().any())

        # Verifikasi dari berkas CSV mentah yang tersimpan
        read_df = pd.read_csv(self.test_csv_path)
        self.assertEqual(len(read_df), 1)
        self.assertFalse(read_df["timestamp"].isna().any())

    def test_save_weather_data_guarantees_raw_columns_schema(self):
        """Verifikasi bahwa CSV selalu memuat seluruh RAW_COLUMNS meskipun input hanya memuat sebagian."""
        partial_df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-09-01 00:00:00")],
            "temperature_2m_C": [24.5],
        })
        saved_df = save_weather_data(partial_df, output_path=self.test_csv_path)

        # Kolom harus memuat seluruh RAW_COLUMNS
        self.assertEqual(list(saved_df.columns), RAW_COLUMNS)

        read_df = pd.read_csv(self.test_csv_path)
        self.assertEqual(list(read_df.columns), RAW_COLUMNS)
        self.assertTrue(pd.isna(read_df["humidity_percent"].iloc[0]))

    @patch("src.data_ingestion.requests.get")
    def test_fetch_weather_data_fast_fail_on_400_client_error(self, mock_get):
        """Verifikasi bahwa HTTP 400 Bad Request fail-fast langsung tanpa retry sia-sia."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": True, "reason": "Latitude must be between -90 and 90"}
        mock_response.text = '{"error": true, "reason": "Latitude must be between -90 and 90"}'
        mock_get.return_value = mock_response

        http_err = requests.exceptions.HTTPError("400 Client Error: Bad Request", response=mock_response)
        mock_response.raise_for_status.side_effect = http_err

        with self.assertRaises(ValueError) as ctx:
            fetch_weather_data(latitude=999.0, max_retries=3, initial_delay=0.01)

        # Harus fail-fast tanpa mengulang retry (call_count == 1)
        self.assertEqual(mock_get.call_count, 1)
        self.assertIn("Latitude must be between -90 and 90", str(ctx.exception))

    def test_atomic_write_leaves_valid_file(self):
        """Verifikasi penulisan atomik menghasilkan file CSV yang valid dan tidak meninggalkan file tmp."""
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-09-01 00:00:00")],
            "temperature_2m_C": [25.0],
        })
        _atomic_to_csv(df, self.test_csv_path)

        self.assertTrue(self.test_csv_path.exists())
        read_df = pd.read_csv(self.test_csv_path)
        self.assertEqual(len(read_df), 1)

        # Pastikan tidak ada file sementara (.tmp) yang tertinggal
        tmp_files = list(self.test_csv_path.parent.glob("*.tmp"))
        self.assertEqual(len(tmp_files), 0)


if __name__ == "__main__":
    unittest.main()
