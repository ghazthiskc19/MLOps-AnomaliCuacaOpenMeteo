"""
data_preprocessing.py - Modul pembersihan, pelabelan anomali, dan rekayasa fitur data cuaca.

Modul ini bertanggung jawab untuk tahapan ETL & Feature Engineering (LK-03 & LK-04):
1. Phase 1: Data Cleaning & Quality Gate (validasi timestamp, tipe data, deduplikasi, pengurutan).
2. Phase 2: Rule-Based Anomaly Labeling (3 kelas: Class 0: Normal, Class 1: Hardware Fault,
   Class 2: Extreme Environmental Anomaly) berbasis taksonomi LK-03 Bab 2 & 3.
3. Phase 3: Feature Engineering (siklus temporal sin/cos, selisih lag, statistik rolling window,
   serta parameter agrometeorologi seperti Vapor Pressure Deficit (VPD) dan Titik Embun / Dew Point).
4. Persistensi atomik ke direktori data/processed/ (misal weather_features_v1.0.csv).
"""

import argparse
from datetime import datetime
import logging
import math
import os
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("data_preprocessing")

# Resolusi path dinamis relatif terhadap root repositori
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DEFAULT_INPUT_PATH = DEFAULT_RAW_DIR / "weather_raw_current.csv"
DEFAULT_OUTPUT_PATH = DEFAULT_PROCESSED_DIR / "weather_features_v1.0.csv"
DEFAULT_CURRENT_PROCESSED_PATH = DEFAULT_PROCESSED_DIR / "weather_processed_current.csv"

# Skema kolom data mentah sesuai LK-03
RAW_COLUMNS = [
    "timestamp",
    "temperature_2m_C",
    "humidity_percent",
    "precipitation_mm",
    "soil_moisture",
    "radiation_wm2",
    "wind_speed_kmh",
]

# Definisi nama dan label kelas anomali
ANOMALY_CLASSES = {
    0: "Class 0: Normal State",
    1: "Class 1: Hardware Fault",
    2: "Class 2: Extreme Environmental",
}


def resolve_path(path: Union[str, Path]) -> Path:
    """
    Melakukan resolusi path ke objek Path absolut.
    Jika path bersifat relatif, resolusi dilakukan relatif terhadap REPO_ROOT.
    """
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.resolve()


def _atomic_to_csv(df: pd.DataFrame, target_path: Union[str, Path], index: bool = False) -> None:
    """
    Menyimpan DataFrame ke berkas CSV secara atomik menggunakan berkas temporer
    dan operasi rename sistem berkas (os.replace) untuk mencegah korupsi data.
    """
    resolved_target = resolve_path(target_path)
    resolved_target.parent.mkdir(parents=True, exist_ok=True)

    tmp_file = resolved_target.parent / f"{resolved_target.name}.{os.getpid()}_{int(time.time() * 1000)}.tmp"
    try:
        df.to_csv(tmp_file, index=index)
        os.replace(tmp_file, resolved_target)
    except Exception as e:
        if tmp_file.exists():
            try:
                os.remove(tmp_file)
            except OSError:
                pass
        raise e


class DataCleaner:
    """
    Komponen pembersihan data mentah (Phase 1 Quality Gate).
    Menangani validasi skema, parsing timestamp, deduplikasi, dan pengurutan kronologis.
    """

    def __init__(self, raw_columns: Optional[List[str]] = None):
        self.raw_columns = raw_columns or RAW_COLUMNS

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Membersihkan DataFrame mentah:
        - Validasi keberadaan kolom wajib
        - Konversi timestamp ke datetime64[ns]
        - Pembuangan baris dengan timestamp NaT/invalid
        - Pengurutan kronologis & deduplikasi baris
        - Pemastian tipe numerik float64 pada kolom fitur
        """
        if df.empty:
            logger.warning("DataFrame masukan kosong.")
            # Kembalikan DataFrame kosong dengan skema kolom yang tepat
            empty_df = pd.DataFrame(columns=self.raw_columns)
            empty_df["timestamp"] = pd.to_datetime(empty_df["timestamp"])
            return empty_df

        # Cek kolom wajib
        missing_cols = [c for c in self.raw_columns if c not in df.columns]
        if missing_cols:
            raise ValueError(f"Kolom wajib tidak ditemukan dalam DataFrame: {missing_cols}")

        cleaned = df.copy()

        # 1. Parsing timestamp
        cleaned["timestamp"] = pd.to_datetime(cleaned["timestamp"], errors="coerce")
        invalid_ts_count = cleaned["timestamp"].isna().sum()
        if invalid_ts_count > 0:
            logger.warning(
                f"Ditemukan {invalid_ts_count} baris dengan timestamp tidak valid (NaT). Baris dibuang."
            )
            cleaned = cleaned.dropna(subset=["timestamp"])

        if cleaned.empty:
            logger.warning("Seluruh baris dibuang karena timestamp tidak valid.")
            return pd.DataFrame(columns=self.raw_columns)

        # 2. Pengurutan kronologis dan deduplikasi
        initial_len = len(cleaned)
        cleaned = cleaned.sort_values("timestamp")
        cleaned = cleaned.drop_duplicates(subset=["timestamp"], keep="last")
        dedup_diff = initial_len - len(cleaned)
        if dedup_diff > 0:
            logger.info(f"Deduplikasi: {dedup_diff} baris duplikat timestamp dibuang.")

        # 3. Pemastian tipe data numerik
        numeric_cols = [c for c in self.raw_columns if c != "timestamp"]
        for col in numeric_cols:
            cleaned[col] = pd.to_numeric(cleaned[col], errors="coerce")

        cleaned = cleaned.reset_index(drop=True)
        return cleaned


class AnomalyLabeler:
    """
    Komponen pelabelan anomali berbasis aturan deterministik (Phase 2 Rule-Based Labeling).
    Menerapkan taksonomi kegagalan sensor IoT dan ambang batas cuaca ekstrem
    sesuai Bab 2 dan 3 LK-03.
    """

    def __init__(self):
        self.required_sensor_cols = [
            "temperature_2m_C",
            "humidity_percent",
            "precipitation_mm",
            "soil_moisture",
            "radiation_wm2",
            "wind_speed_kmh",
        ]

    def compute_anomaly_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Menghitung indikator temporal yang diperlukan untuk mendeteksi anomali multi-baris:
        - temp_diff_1h (perubahan suhu absolut 1 jam)
        - temp_std_12h (stuck temperature 12 jam)
        - humidity_stuck_100_24h (kelembaban 100% konstan >= 24 jam)
        - wind_zero_48h (angin 0.0 km/h macet >= 48 jam)
        - soil_diff_1h (perubahan kelembaban tanah 1 jam)
        - soil_waterlogged_48h (tanah jenuh > 0.48 m3/m3 >= 48 jam)
        """
        df_ind = df.copy()

        # Delta suhu 1 jam
        if "temperature_2m_C" in df_ind.columns:
            df_ind["temp_diff_1h"] = df_ind["temperature_2m_C"].diff().abs()
            # Standar deviasi suhu 12 jam (stuck value jika std == 0)
            df_ind["temp_std_12h"] = df_ind["temperature_2m_C"].rolling(12, min_periods=12).std()
        else:
            df_ind["temp_diff_1h"] = np.nan
            df_ind["temp_std_12h"] = np.nan

        # Kelembaban jenuh 100% stuck 24 jam
        if "humidity_percent" in df_ind.columns:
            df_ind["humidity_stuck_100_24h"] = (
                (df_ind["humidity_percent"] >= 100.0).rolling(24, min_periods=24).min() == 1
            )
        else:
            df_ind["humidity_stuck_100_24h"] = False

        # Angin macet 0.0 km/h 48 jam
        if "wind_speed_kmh" in df_ind.columns:
            df_ind["wind_zero_48h"] = (
                (df_ind["wind_speed_kmh"] <= 0.0).rolling(48, min_periods=48).min() == 1
            )
        else:
            df_ind["wind_zero_48h"] = False

        # Delta tanah 1 jam
        if "soil_moisture" in df_ind.columns:
            df_ind["soil_diff_1h"] = df_ind["soil_moisture"].diff()
            # Waterlogging 48 jam
            df_ind["soil_waterlogged_48h"] = (
                (df_ind["soil_moisture"] > 0.48).rolling(48, min_periods=48).min() == 1
            )
        else:
            df_ind["soil_diff_1h"] = np.nan
            df_ind["soil_waterlogged_48h"] = False

        return df_ind

    def classify_row(self, row: pd.Series) -> Tuple[int, str]:
        """
        Mengklasifikasikan 1 baris observasi ke dalam 3 kelas anomali.

        Hierarki Evaluasi:
        1. Class 1: Hardware Fault (Prioritas tertinggi - integritas instrumen)
        2. Class 2: Extreme Environmental Anomaly (Kondisi iklim ekstrem agrikultur)
        3. Class 0: Normal State (Baseline operasional)

        Returns
        -------
        Tuple[int, str]
            (anomaly_class, anomaly_reason)
        """
        # =====================================================================
        # CLASS 1: HARDWARE FAULT & DATA INGESTION ERROR (Prioritas 1)
        # =====================================================================

        # 1.1 Null / Missing Data (Packet Loss / Sensor Dead)
        for col in self.required_sensor_cols:
            val = row.get(col)
            if val is None or pd.isna(val):
                return 1, f"Hardware Fault: Missing / NaN in '{col}' (Packet Loss)"

        temp = float(row["temperature_2m_C"])
        hum = float(row["humidity_percent"])
        precip = float(row["precipitation_mm"])
        soil = float(row["soil_moisture"])
        rad = float(row["radiation_wm2"])
        wind = float(row["wind_speed_kmh"])

        # 1.2 Out-of-Bounds (OOB) Sensor Limits
        if temp < -20.0 or temp > 55.0:
            return 1, f"Hardware Fault: Temperature OOB ({temp:.1f}°C, range: -20 s.d. 55°C)"
        if hum < 0.0 or hum > 100.0:
            return 1, f"Hardware Fault: Humidity OOB ({hum:.1f}%, range: 0 s.d. 100%)"
        if precip < 0.0:
            return 1, f"Hardware Fault: Negative precipitation ({precip:.2f} mm)"
        if soil < 0.00 or soil > 0.55:
            return 1, f"Hardware Fault: Soil moisture OOB ({soil:.3f} m³/m³, range: 0.0 s.d. 0.55)"
        if rad < 0.0:
            return 1, f"Hardware Fault: Negative radiation ({rad:.1f} W/m²)"
        if wind < 0.0:
            return 1, f"Hardware Fault: Negative wind speed ({wind:.1f} km/h)"

        # 1.3 Night Radiation Glitch (Kebocoran fotodioda antara 20:00 - 04:00 WIB)
        ts = row.get("timestamp")
        if ts is not None and not pd.isna(ts):
            ts_dt = ts if isinstance(ts, (pd.Timestamp, datetime)) else pd.to_datetime(ts)
            if hasattr(ts_dt, "tzinfo") and ts_dt.tzinfo is not None:
                # Konversi ke waktu lokal WIB (Asia/Jakarta / UTC+7) jika timestamp timezone-aware
                ts_dt = ts_dt.tz_convert("Asia/Jakarta") if hasattr(ts_dt, "tz_convert") else ts_dt
            hour = ts_dt.hour
            if (hour >= 20 or hour < 4) and rad > 0.0:
                return 1, f"Hardware Fault: Night radiation glitch ({rad:.1f} W/m² at {hour:02d}:00 WIB)"

        # 1.4 Cross-Feature Discordance (Kontradiksi fisik antar sensor)
        if precip > 15.0 and rad > 800.0:
            return 1, f"Hardware Fault: Discordance (Heavy rain {precip:.1f} mm with extreme radiation {rad:.1f} W/m²)"

        soil_diff = row.get("soil_diff_1h")
        if soil_diff is not None and not pd.isna(soil_diff):
            if soil_diff > 0.30 and precip == 0.0 and rad > 800.0:
                return 1, f"Hardware Fault: Soil moisture surge (+{soil_diff:.2f}) under hot sun without rain"
            if precip > 20.0 and abs(soil_diff) < 0.0001:
                return 1, f"Hardware Fault: Soil probe unresponsive (Δsoil=0.0 during rain {precip:.1f} mm)"

        # 1.5 Gradient Spiking (Transient Jump tanpa presipitasi)
        temp_diff = row.get("temp_diff_1h")
        if temp_diff is not None and not pd.isna(temp_diff):
            if abs(float(temp_diff)) > 8.0 and precip == 0.0:
                return 1, f"Hardware Fault: Temperature spike (|ΔT|={abs(float(temp_diff)):.1f}°C/hr without rain)"

        # 1.6 Stuck Value (Zero Variance / Sensor Macet)
        temp_std = row.get("temp_std_12h")
        if temp_std is not None and not pd.isna(temp_std) and abs(float(temp_std)) < 1e-4:
            return 1, "Hardware Fault: Temperature sensor stuck (constant value for 12 hours)"

        hum_stuck = row.get("humidity_stuck_100_24h")
        if hum_stuck is not None and not pd.isna(hum_stuck) and bool(hum_stuck):
            return 1, "Hardware Fault: Humidity saturated 100% stuck for >24 hours"

        wind_stuck = row.get("wind_zero_48h")
        if wind_stuck is not None and not pd.isna(wind_stuck) and bool(wind_stuck):
            return 1, "Hardware Fault: Anemometer stuck at 0.0 km/h for >48 hours"

        # =====================================================================
        # CLASS 2: EXTREME ENVIRONMENTAL ANOMALY (Prioritas 2)
        # =====================================================================

        # 2.1 Suhu Panas Ekstrem (> 33.5°C) -> Heat Stress Tanaman
        if temp > 33.5:
            return 2, f"Extreme Weather: Heatwave / Heat Stress ({temp:.1f}°C > 33.5°C)"

        # 2.2 Suhu Dingin Ekstrem (< 15.0°C) -> Frost Risk / Embun Upas
        if temp < 15.0:
            return 2, f"Extreme Weather: Severe Cold / Frost Risk ({temp:.1f}°C < 15.0°C)"

        # 2.3 Udara Kering Ekstrem (< 40.0%) -> Acute Transpiration Shock (VPD spike)
        if hum < 40.0:
            return 2, f"Extreme Weather: Severe Dry Air ({hum:.1f}% < 40.0%)"

        # 2.4 Badai Hujan Tropis Ekstrem (> 25.0 mm/jam) -> Erosi & Waterlogging
        if precip > 25.0:
            return 2, f"Extreme Weather: Torrential Rainfall ({precip:.1f} mm/hr > 25.0 mm/hr)"

        # 2.5 Kekeringan Kritis / Titik Layu Permanen (< 0.08 m³/m³)
        if soil < 0.08:
            return 2, f"Extreme Weather: Critical Drought / Wilting Point ({soil:.3f} m³/m³ < 0.08)"

        # 2.6 Kejenuhan Berlebih / Waterlogging (> 0.48 m³/m³)
        soil_waterlogged = row.get("soil_waterlogged_48h")
        is_waterlogged = (
            soil_waterlogged is not None and not pd.isna(soil_waterlogged) and bool(soil_waterlogged)
        )
        if is_waterlogged or soil > 0.48:
            return 2, f"Extreme Weather: Waterlogging / Root Anoxia ({soil:.3f} m³/m³ > 0.48)"

        # 2.7 Radiasi Matahari Ekstrem (> 1100.0 W/m²) -> Sunscald & Klorosis
        if rad > 1100.0:
            return 2, f"Extreme Weather: Extreme Solar Radiation ({rad:.1f} W/m² > 1100 W/m²)"

        # 2.8 Angin Kencang / Badai (> 40.0 km/h) -> Strong Breeze / Kerusakan Fisik
        if wind > 40.0:
            return 2, f"Extreme Weather: High Gale Wind ({wind:.1f} km/h > 40.0 km/h)"

        # =====================================================================
        # CLASS 0: NORMAL STATE (Default)
        # =====================================================================
        return 0, "Normal State"

    def label(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Menjalankan pelabelan anomali pada DataFrame:
        Menambahkan kolom `anomaly_class` (int) dan `anomaly_reason` (str).
        """
        if df.empty:
            df_out = df.copy()
            df_out["anomaly_class"] = pd.Series(dtype=int)
            df_out["anomaly_reason"] = pd.Series(dtype=str)
            return df_out

        df_prepared = self.compute_anomaly_indicators(df)
        labels_and_reasons = df_prepared.apply(self.classify_row, axis=1)

        result_df = df.copy()
        result_df["anomaly_class"] = labels_and_reasons.apply(lambda x: x[0]).astype(int)
        result_df["anomaly_reason"] = labels_and_reasons.apply(lambda x: x[1]).astype(str)
        return result_df


class FeatureEngineer:
    """
    Komponen rekayasa fitur temporal dan agrometeorologi (Phase 3 Feature Engineering).
    Mengekstraksi fitur siklis, lag temporal, statistik jendela geser,
    serta metrik biofisik seperti VPD dan Dew Point.
    """

    @staticmethod
    def calculate_vpd(temp_c: pd.Series, humidity_pct: pd.Series) -> pd.Series:
        """
        Menghitung Vapor Pressure Deficit (VPD dalam kPa):
        e_s (Tekanan Uap Jenuh) = 0.61078 * exp((17.27 * T) / (T + 237.3))
        e_a (Tekanan Uap Aktual) = e_s * (RH / 100.0)
        VPD = max(0.0, e_s - e_a)
        """
        # Batasi kelembaban di rentang realistis [0, 100] untuk kalkulasi rumus
        clipped_hum = humidity_pct.clip(lower=0.0, upper=100.0)
        # Saturated vapor pressure (kPa)
        es = 0.61078 * np.exp((17.27 * temp_c) / (temp_c + 237.3))
        # Actual vapor pressure (kPa)
        ea = es * (clipped_hum / 100.0)
        vpd = (es - ea).clip(lower=0.0)
        return vpd

    @staticmethod
    def calculate_dew_point(temp_c: pd.Series, humidity_pct: pd.Series) -> pd.Series:
        """
        Menghitung Titik Embun / Dew Point (°C) menggunakan aproksimasi Magnus-Tetens:
        alpha = (17.27 * T) / (237.3 + T) + ln(max(RH, 0.01) / 100)
        T_dew = (237.3 * alpha) / (17.27 - alpha)
        """
        clipped_hum = humidity_pct.clip(lower=0.01, upper=100.0)
        alpha = ((17.27 * temp_c) / (237.3 + temp_c)) + np.log(clipped_hum / 100.0)
        dew_point = (237.3 * alpha) / (17.27 - alpha)
        return dew_point

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Merekayasa seluruh set fitur pada DataFrame cuaca.
        """
        if df.empty:
            return df.copy()

        feat_df = df.copy()

        # Pastikan timestamp adalah datetime
        if not pd.api.types.is_datetime64_any_dtype(feat_df["timestamp"]):
            feat_df["timestamp"] = pd.to_datetime(feat_df["timestamp"])

        # 1. Fitur Kalender dan Siklis Temporal (Diurnal & Annual Cycles)
        hours = feat_df["timestamp"].dt.hour
        feat_df["hour"] = hours
        feat_df["hour_sin"] = np.sin(2.0 * np.pi * hours / 24.0)
        feat_df["hour_cos"] = np.cos(2.0 * np.pi * hours / 24.0)

        dow = feat_df["timestamp"].dt.dayofweek
        feat_df["day_of_week"] = dow
        feat_df["is_weekend"] = (dow >= 5).astype(int)

        months = feat_df["timestamp"].dt.month
        feat_df["month"] = months
        feat_df["month_sin"] = np.sin(2.0 * np.pi * (months - 1) / 12.0)
        feat_df["month_cos"] = np.cos(2.0 * np.pi * (months - 1) / 12.0)

        # 2. Metrik Biofisik / Agrometeorologi
        if "temperature_2m_C" in feat_df.columns and "humidity_percent" in feat_df.columns:
            feat_df["vpd_kpa"] = self.calculate_vpd(
                feat_df["temperature_2m_C"], feat_df["humidity_percent"]
            )
            feat_df["dew_point_C"] = self.calculate_dew_point(
                feat_df["temperature_2m_C"], feat_df["humidity_percent"]
            )

        # 3. Fitur Selisih Waktu (Temporal Lag Differences)
        if "temperature_2m_C" in feat_df.columns:
            feat_df["temp_diff_1h"] = feat_df["temperature_2m_C"].diff().fillna(0.0)
            feat_df["temp_diff_24h"] = feat_df["temperature_2m_C"].diff(24).fillna(0.0)

        if "humidity_percent" in feat_df.columns:
            feat_df["humidity_diff_1h"] = feat_df["humidity_percent"].diff().fillna(0.0)

        if "soil_moisture" in feat_df.columns:
            feat_df["soil_diff_1h"] = feat_df["soil_moisture"].diff().fillna(0.0)
            feat_df["soil_diff_24h"] = feat_df["soil_moisture"].diff(24).fillna(0.0)

        if "radiation_wm2" in feat_df.columns:
            feat_df["radiation_diff_1h"] = feat_df["radiation_wm2"].diff().fillna(0.0)

        # 4. Statistik Jendela Geser (Rolling Window Statistics)
        # Suhu
        if "temperature_2m_C" in feat_df.columns:
            feat_df["temp_rolling_mean_3h"] = (
                feat_df["temperature_2m_C"].rolling(3, min_periods=1).mean()
            )
            feat_df["temp_rolling_std_3h"] = (
                feat_df["temperature_2m_C"].rolling(3, min_periods=1).std().fillna(0.0)
            )
            feat_df["temp_rolling_mean_6h"] = (
                feat_df["temperature_2m_C"].rolling(6, min_periods=1).mean()
            )
            feat_df["temp_rolling_std_6h"] = (
                feat_df["temperature_2m_C"].rolling(6, min_periods=1).std().fillna(0.0)
            )
            feat_df["temp_rolling_mean_24h"] = (
                feat_df["temperature_2m_C"].rolling(24, min_periods=1).mean()
            )
            feat_df["temp_rolling_std_24h"] = (
                feat_df["temperature_2m_C"].rolling(24, min_periods=1).std().fillna(0.0)
            )
            feat_df["temp_rolling_min_24h"] = (
                feat_df["temperature_2m_C"].rolling(24, min_periods=1).min()
            )
            feat_df["temp_rolling_max_24h"] = (
                feat_df["temperature_2m_C"].rolling(24, min_periods=1).max()
            )

        # Kelembaban
        if "humidity_percent" in feat_df.columns:
            feat_df["humidity_rolling_mean_6h"] = (
                feat_df["humidity_percent"].rolling(6, min_periods=1).mean()
            )
            feat_df["humidity_rolling_mean_24h"] = (
                feat_df["humidity_percent"].rolling(24, min_periods=1).mean()
            )

        # Presipitasi Akumulatif
        if "precipitation_mm" in feat_df.columns:
            feat_df["precip_rolling_sum_6h"] = (
                feat_df["precipitation_mm"].rolling(6, min_periods=1).sum()
            )
            feat_df["precip_rolling_sum_24h"] = (
                feat_df["precipitation_mm"].rolling(24, min_periods=1).sum()
            )

        # Kelembaban Tanah
        if "soil_moisture" in feat_df.columns:
            feat_df["soil_rolling_mean_24h"] = (
                feat_df["soil_moisture"].rolling(24, min_periods=1).mean()
            )

        # Angin
        if "wind_speed_kmh" in feat_df.columns:
            feat_df["wind_rolling_mean_6h"] = (
                feat_df["wind_speed_kmh"].rolling(6, min_periods=1).mean()
            )
            feat_df["wind_rolling_max_24h"] = (
                feat_df["wind_speed_kmh"].rolling(24, min_periods=1).max()
            )

        return feat_df


class WeatherPreprocessor:
    """
    Fasad utama pipeline pemrosesan data cuaca (Cleaning -> Labeling -> Feature Engineering).
    """

    def __init__(self):
        self.cleaner = DataCleaner()
        self.labeler = AnomalyLabeler()
        self.engineer = FeatureEngineer()

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Mengeksekusi pipeline komprehensif pada DataFrame.
        """
        # Phase 1: Data Cleaning & Quality Gate
        cleaned_df = self.cleaner.clean(df)
        if cleaned_df.empty:
            return cleaned_df

        # Phase 2: Rule-Based Anomaly Labeling
        labeled_df = self.labeler.label(cleaned_df)

        # Phase 3: Feature Engineering
        feature_df = self.engineer.transform(labeled_df)

        return feature_df

    def process_file(
        self,
        input_path: Union[str, Path] = DEFAULT_INPUT_PATH,
        output_path: Union[str, Path] = DEFAULT_OUTPUT_PATH,
        secondary_output_path: Optional[Union[str, Path]] = DEFAULT_CURRENT_PROCESSED_PATH,
    ) -> pd.DataFrame:
        """
        Membaca data mentah dari CSV input, memproses, dan menyimpan hasilnya ke CSV output.
        """
        resolved_in = resolve_path(input_path)
        resolved_out = resolve_path(output_path)

        if not resolved_in.exists():
            raise FileNotFoundError(f"Berkas masukan tidak ditemukan: {resolved_in}")

        logger.info(f"Membaca berkas mentah dari: {resolved_in}")
        raw_df = pd.read_csv(resolved_in)
        logger.info(f"Jumlah baris terbaca: {len(raw_df)}")

        processed_df = self.process(raw_df)

        logger.info(f"Menyimpan data hasil pemrosesan ({len(processed_df)} baris) ke: {resolved_out}")
        _atomic_to_csv(processed_df, resolved_out, index=False)

        if secondary_output_path:
            resolved_sec = resolve_path(secondary_output_path)
            logger.info(f"Menyimpan salinan dataset terkini ke: {resolved_sec}")
            _atomic_to_csv(processed_df, resolved_sec, index=False)

        return processed_df


def preprocess_weather_data(
    input_path: Union[str, Path] = DEFAULT_INPUT_PATH,
    output_path: Union[str, Path] = DEFAULT_OUTPUT_PATH,
    secondary_output_path: Optional[Union[str, Path]] = DEFAULT_CURRENT_PROCESSED_PATH,
) -> pd.DataFrame:
    """
    Fungsi fasad tingkat tinggi untuk eksekusi preprocessing data cuaca.
    """
    preprocessor = WeatherPreprocessor()
    return preprocessor.process_file(
        input_path=input_path,
        output_path=output_path,
        secondary_output_path=secondary_output_path,
    )


def main():
    """
    Fungsi antarmuka baris perintah (CLI) untuk menjalankan preprocessing data cuaca.
    """
    parser = argparse.ArgumentParser(
        description="Pipeline Preprocessing, Pelabelan Anomali, dan Rekayasa Fitur Cuaca (LK-04)"
    )
    parser.add_argument(
        "--input-path",
        type=str,
        default=str(DEFAULT_INPUT_PATH),
        help=f"Path berkas CSV data mentah (default: {DEFAULT_INPUT_PATH})",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=str(DEFAULT_OUTPUT_PATH),
        help=f"Path berkas CSV fitur utama (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--current-path",
        type=str,
        default=str(DEFAULT_CURRENT_PROCESSED_PATH),
        help=f"Path berkas CSV fitur terkini (default: {DEFAULT_CURRENT_PROCESSED_PATH})",
    )

    args = parser.parse_args()

    print("=" * 65)
    print("[START] Memulai Pipeline Data Preprocessing (MLOps LK-04)")
    print(f"  Input Path   : {args.input_path}")
    print(f"  Output Path  : {args.output_path}")
    print(f"  Current Path : {args.current_path}")
    print("=" * 65)

    try:
        processed_df = preprocess_weather_data(
            input_path=args.input_path,
            output_path=args.output_path,
            secondary_output_path=args.current_path,
        )

        print("\n[SUCCESS] Preprocessing Berhasil Selesai!")
        print(f"Total baris diproses: {len(processed_df)}")
        print(f"Total kolom fitur: {len(processed_df.columns)}")
        print(f"Daftar kolom: {list(processed_df.columns)}")

        print("\n[SUMMARY] Ringkasan Distribusi Anomali (Ground Truth):")
        counts = processed_df["anomaly_class"].value_counts().to_dict()
        for cls_code, cls_name in ANOMALY_CLASSES.items():
            cnt = counts.get(cls_code, 0)
            pct = cnt / len(processed_df) * 100 if len(processed_df) > 0 else 0
            print(f"  - {cls_name}: {cnt} baris ({pct:.2f}%)")

        print("\nContoh 3 Baris Teratas:")
        print(processed_df.head(3))
    except Exception as e:
        logger.error(f"[ERROR] Preprocessing Gagal: {e}")
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
