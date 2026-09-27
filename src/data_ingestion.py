"""
data_ingestion.py - Modul untuk mengambil dan memperbarui data cuaca dari Open-Meteo API.

Modul ini bertanggung jawab untuk:
1. Mengambil data cuaca historis dan nowcast dari Open-Meteo API (wilayah Malang).
2. Menyediakan mekanisme ketahanan jaringan (fault-tolerant retry dengan exponential backoff).
3. Melakukan resolusi path dinamis berbasis pathlib.Path relatif terhadap root repositori.
4. Menyimpan data mentah ke data/raw/weather_raw_current.csv dengan buffer jendela geser 30 hari
   (720 baris per jam) disertai deduplikasi timestamp.
"""

import argparse
import logging
import os
from pathlib import Path
import time
from typing import Optional, Union

import pandas as pd
import requests

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("data_ingestion")

# Resolusi path dinamis relatif terhadap root repositori
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_OUTPUT_PATH = DEFAULT_RAW_DIR / "weather_raw_current.csv"


def resolve_path(path: Union[str, Path]) -> Path:
    """
    Melakukan resolusi path ke objek Path absolut.
    Jika path bersifat relatif, resolusi dilakukan relatif terhadap REPO_ROOT.
    """
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.resolve()


# Parameter default Open-Meteo untuk Malang
DEFAULT_LATITUDE = -7.95
DEFAULT_LONGITUDE = 112.61
DEFAULT_BUFFER_HOURS = 720  # 30 hari * 24 jam = 720 baris per jam

RAW_COLUMNS = [
    "timestamp",
    "temperature_2m_C",
    "humidity_percent",
    "precipitation_mm",
    "soil_moisture",
    "radiation_wm2",
    "wind_speed_kmh",
]


def fetch_weather_data(
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    past_days: int = 1,
    forecast_days: int = 1,
    max_retries: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
    timeout: float = 10.0,
) -> pd.DataFrame:
    """
    Mengambil data cuaca per jam dari Open-Meteo API dengan mekanisme retry toleran galat jaringan.

    Parameters
    ----------
    latitude : float
        Koordinat lintang lokasi (default: Malang, -7.95).
    longitude : float
        Koordinat bujur lokasi (default: Malang, 112.61).
    past_days : int
        Jumlah hari ke belakang untuk data historis (default: 1).
    forecast_days : int
        Jumlah hari ke depan untuk data forecast/nowcast (default: 1).
    max_retries : int
        Jumlah maksimal percobaan ulang jika terjadi kegagalan jaringan (default: 3).
    initial_delay : float
        Waktu tunggu awal dalam detik sebelum retry pertama (default: 2.0).
    backoff_factor : float
        Faktor pengali jeda eksponensial (default: 2.0).
    timeout : float
        Batas waktu HTTP request dalam detik (default: 10.0).

    Returns
    -------
    pd.DataFrame
        DataFrame berisi kolom cuaca per jam dengan timestamp bertipe datetime64[ns].

    Raises
    ------
    ConnectionError
        Jika seluruh percobaan fetch gagal mencapai API atau menerima respons valid.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": [
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "soil_moisture_0_to_7cm",
            "shortwave_radiation",
            "wind_speed_10m",
        ],
        "timezone": "Asia/Jakarta",
        "past_days": past_days,
        "forecast_days": forecast_days,
    }

    last_exception: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"Mengambil data dari Open-Meteo (Percobaan {attempt}/{max_retries}) | "
                f"lat: {latitude}, lon: {longitude}, past_days: {past_days}, forecast_days: {forecast_days}"
            )
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            if "hourly" not in data or "time" not in data["hourly"]:
                raise ValueError("Payload respons API tidak memiliki komponen 'hourly.time'.")

            df = pd.DataFrame(
                {
                    "timestamp": data["hourly"]["time"],
                    "temperature_2m_C": data["hourly"]["temperature_2m"],
                    "humidity_percent": data["hourly"]["relative_humidity_2m"],
                    "precipitation_mm": data["hourly"]["precipitation"],
                    "soil_moisture": data["hourly"]["soil_moisture_0_to_7cm"],
                    "radiation_wm2": data["hourly"]["shortwave_radiation"],
                    "wind_speed_kmh": data["hourly"]["wind_speed_10m"],
                }
            )

            df["timestamp"] = pd.to_datetime(df["timestamp"])
            logger.info(f"Berhasil fetch {len(df)} baris data cuaca.")
            return df

        except requests.exceptions.HTTPError as e:
            last_exception = e
            status_code = e.response.status_code if e.response is not None else None
            # Jika HTTP 4xx (kecuali 429 Too Many Requests), ini adalah kesalahan klien (bad parameters)
            # yang tidak akan berhasil dengan retry. Fail-fast segera dengan ValueError.
            if status_code is not None and 400 <= status_code < 500 and status_code != 429:
                err_text = ""
                try:
                    err_json = e.response.json()
                    err_text = err_json.get("reason", "")
                except Exception:
                    err_text = e.response.text
                error_msg = f"Permintaan Open-Meteo gagal dengan client error HTTP {status_code}: {err_text or e}"
                logger.error(error_msg)
                raise ValueError(error_msg) from e

            logger.warning(f"Percobaan {attempt}/{max_retries} gagal dengan HTTP error: {e}")
            if attempt < max_retries:
                delay = initial_delay * (backoff_factor ** (attempt - 1))
                logger.info(f"Menunggu jeda backoff {delay:.1f} detik sebelum mencoba kembali...")
                time.sleep(delay)

        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            last_exception = e
            logger.warning(f"Percobaan {attempt}/{max_retries} gagal dengan error: {e}")
            if attempt < max_retries:
                delay = initial_delay * (backoff_factor ** (attempt - 1))
                logger.info(f"Menunggu jeda backoff {delay:.1f} detik sebelum mencoba kembali...")
                time.sleep(delay)

    error_msg = f"Gagal mengambil data dari Open-Meteo API setelah {max_retries} percobaan. Error terakhir: {last_exception}"
    logger.error(error_msg)
    raise ConnectionError(error_msg) from last_exception


def _atomic_to_csv(df: pd.DataFrame, target_path: Path) -> None:
    """
    Menyimpan DataFrame ke berkas CSV secara atomik dengan menulis ke berkas temporer
    terlebih dahulu di direktori yang sama sebelum melakukan atomic rename/replace.
    Mencegah korupsi data jika proses terhenti di tengah penulisan disk.
    """
    target_path = Path(target_path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = target_path.with_name(f"{target_path.name}.{os.getpid()}_{int(time.time() * 1000)}.tmp")
    try:
        df.to_csv(temp_file, index=False)
        os.replace(temp_file, target_path)
    except Exception:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise


def save_weather_data(
    df: pd.DataFrame,
    output_path: Union[str, Path] = DEFAULT_OUTPUT_PATH,
    buffer_size: int = DEFAULT_BUFFER_HOURS,
) -> pd.DataFrame:
    """
    Menyimpan DataFrame ke berkas CSV data mentah dengan mempertahankan buffer 30 hari
    (default 720 baris) dan melakukan deduplikasi timestamp.
    Resolusi output_path dilakukan secara dinamis relatif terhadap root repositori.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame data cuaca baru yang akan digabungkan dan disimpan.
    output_path : Union[str, Path]
        Path berkas CSV tujuan (default: data/raw/weather_raw_current.csv).
        Jika relatif, akan diresolusikan terhadap root repositori.
    buffer_size : int
        Kapasitas maksimum baris buffer jendela geser (default: 720 baris).

    Returns
    -------
    pd.DataFrame
        DataFrame buffer akhir yang telah terurut dan tersimpan.
    """
    if df is None or df.empty:
        logger.warning("DataFrame masukan kosong. Tidak ada data yang disimpan.")
        return df

    if "timestamp" not in df.columns:
        raise ValueError("DataFrame masukan harus memiliki kolom 'timestamp'.")

    target_path = resolve_path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    new_data = df.copy()
    new_data["timestamp"] = pd.to_datetime(new_data["timestamp"], errors="coerce")

    # Kontrak LK-03: timestamp bersifat Non-Nullable. Buang baris dengan timestamp invalid/NaT
    invalid_ts_count = new_data["timestamp"].isna().sum()
    if invalid_ts_count > 0:
        logger.warning(
            f"Ditemukan {invalid_ts_count} baris dengan timestamp tidak valid (NaT). Baris dibuang."
        )
        new_data = new_data.dropna(subset=["timestamp"])

    if new_data.empty:
        logger.warning("Tidak ada data dengan timestamp valid yang dapat disimpan.")
        return df

    if target_path.exists() and target_path.stat().st_size > 0:
        try:
            existing_df = pd.read_csv(target_path)
            if not existing_df.empty and "timestamp" in existing_df.columns:
                existing_df["timestamp"] = pd.to_datetime(existing_df["timestamp"], errors="coerce")
                existing_df = existing_df.dropna(subset=["timestamp"])
                combined = pd.concat([existing_df, new_data], ignore_index=True)
                logger.info(
                    f"Menggabungkan {len(new_data)} data baru dengan {len(existing_df)} data eksisting."
                )
            else:
                combined = new_data
        except Exception as e:
            logger.warning(f"Gagal membaca file eksisting {target_path} ({e}), menggunakan data baru.")
            combined = new_data
    else:
        combined = new_data

    # Deduplikasi timestamp: prioritaskan data terbaru yang baru di-fetch (keep='last')
    deduped = combined.drop_duplicates(subset=["timestamp"], keep="last")

    # Pastikan data terurut secara kronologis
    sorted_df = deduped.sort_values(by="timestamp").reset_index(drop=True)

    # Batasi buffer hingga buffer_size baris (30 hari x 24 jam = 720 baris)
    if len(sorted_df) > buffer_size:
        final_df = sorted_df.tail(buffer_size).reset_index(drop=True)
        logger.info(
            f"Buffer melebihi kapasitas {buffer_size} baris. Memotong {len(sorted_df) - buffer_size} data terlama."
        )
    else:
        final_df = sorted_df

    # Memastikan susunan skema memuat seluruh RAW_COLUMNS secara konsisten
    for col in RAW_COLUMNS:
        if col not in final_df.columns:
            final_df[col] = pd.NA
    final_df = final_df[RAW_COLUMNS]

    _atomic_to_csv(final_df, target_path)
    logger.info(
        f"Berhasil menyimpan {len(final_df)} baris ke {target_path} "
        f"(Rentang: {final_df['timestamp'].min()} s.d. {final_df['timestamp'].max()})"
    )
    return final_df


def ingest_weather_data(
    output_path: Union[str, Path] = DEFAULT_OUTPUT_PATH,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    past_days: Optional[int] = None,
    forecast_days: int = 1,
    buffer_size: int = DEFAULT_BUFFER_HOURS,
    max_retries: int = 3,
    timeout: float = 10.0,
) -> pd.DataFrame:
    """
    Fungsi orkestrasi lengkap: Fetch data cuaca dari API lalu simpan ke buffer CSV.

    Jika past_days tidak dispesifikasikan (None):
    - Jika berkas target belum ada atau barisnya kurang dari buffer_size: past_days = 30
      (inisialisasi penuh buffer 30 hari).
    - Jika berkas target sudah ada dan terisi penuh: past_days = 1
      (pengambilan reguler micro-batch per jam).

    Parameters
    ----------
    output_path : Union[str, Path]
        Path berkas CSV tujuan. Resolusi dinamis relatif terhadap root repositori.
    latitude : float
        Koordinat lintang.
    longitude : float
        Koordinat bujur.
    past_days : Optional[int]
        Jumlah hari ke belakang. Jika None, ditentukan secara adaptif.
    forecast_days : int
        Jumlah hari ramalan/nowcast ke depan.
    buffer_size : int
        Ukuran buffer jendela geser.
    max_retries : int
        Maksimal percobaan ulang permintaan API.
    timeout : float
        Batas waktu HTTP request.

    Returns
    -------
    pd.DataFrame
        DataFrame buffer akhir yang tersimpan.
    """
    target_path = resolve_path(output_path)

    if past_days is None:
        if target_path.exists() and target_path.stat().st_size > 0:
            try:
                with open(target_path, encoding="utf-8") as f:
                    row_count = max(0, sum(1 for line in f if line.strip()) - 1)
                if row_count >= buffer_size:
                    past_days = 1
                    logger.info(f"Target file terisi {row_count} baris. Mode pembaruan reguler: past_days=1.")
                else:
                    past_days = 30
                    logger.info(f"Target file hanya berisi {row_count} baris. Mengisi buffer: past_days=30.")
            except Exception:
                past_days = 30
        else:
            past_days = 30
            logger.info("Target file belum ada. Inisialisasi awal buffer 30 hari: past_days=30.")

    new_df = fetch_weather_data(
        latitude=latitude,
        longitude=longitude,
        past_days=past_days,
        forecast_days=forecast_days,
        max_retries=max_retries,
        timeout=timeout,
    )

    buffer_df = save_weather_data(
        df=new_df,
        output_path=target_path,
        buffer_size=buffer_size,
    )

    return buffer_df


def main() -> None:
    """Entry point untuk menjalankan modul ingestion secara mandiri via CLI."""
    parser = argparse.ArgumentParser(
        description="Ingest weather data dari Open-Meteo API ke raw buffer CSV."
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=str(DEFAULT_OUTPUT_PATH),
        help=f"Path berkas CSV tujuan (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--latitude",
        type=float,
        default=DEFAULT_LATITUDE,
        help=f"Koordinat lintang (default: {DEFAULT_LATITUDE})",
    )
    parser.add_argument(
        "--longitude",
        type=float,
        default=DEFAULT_LONGITUDE,
        help=f"Koordinat bujur (default: {DEFAULT_LONGITUDE})",
    )
    parser.add_argument(
        "--past-days",
        type=int,
        default=None,
        help="Jumlah hari historis (default: auto, 30 jika file belum ada, 1 jika update berkala)",
    )
    parser.add_argument(
        "--forecast-days",
        type=int,
        default=1,
        help="Jumlah hari forecast/nowcast (default: 1)",
    )
    parser.add_argument(
        "--buffer-size",
        type=int,
        default=DEFAULT_BUFFER_HOURS,
        help=f"Ukuran buffer maksimum dalam baris jam (default: {DEFAULT_BUFFER_HOURS})",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Jumlah maksimal percobaan fetch API jika gagal (default: 3)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("[START] Memulai Data Ingestion Cuaca Open-Meteo (MLOps Pipeline)")
    print(f"[CONFIG] Lokasi: lat={args.latitude}, lon={args.longitude}")
    print(f"[CONFIG] Target Output: {args.output_path}")
    print(f"[CONFIG] Buffer Maksimal: {args.buffer_size} baris (30 hari)")
    print("=" * 60)

    try:
        final_df = ingest_weather_data(
            output_path=args.output_path,
            latitude=args.latitude,
            longitude=args.longitude,
            past_days=args.past_days,
            forecast_days=args.forecast_days,
            buffer_size=args.buffer_size,
            max_retries=args.max_retries,
        )
        print("\n[SUCCESS] Ingestion Berhasil!")
        print(f"Total baris dalam buffer: {len(final_df)}")
        print(f"Rentang waktu: {final_df['timestamp'].min()} s.d. {final_df['timestamp'].max()}")
        print("\nContoh 5 baris data teratas:")
        print(final_df.head())
        print("\nContoh 5 baris data terbawah:")
        print(final_df.tail())
    except Exception as e:
        logger.error(f"[ERROR] Ingestion Gagal: {e}")
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
