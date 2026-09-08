"""
data_ingestion.py - Modul untuk mengambil data cuaca dari Open-Meteo API.

Modul ini berisi fungsi-fungsi untuk:
- Fetch data cuaca real-time dari Open-Meteo API
- Transformasi JSON response ke Pandas DataFrame
- Validasi dan penyimpanan data ke format CSV

Akan diimplementasikan lengkap pada pertemuan selanjutnya.
"""

import requests
import pandas as pd


def fetch_weather_data(latitude: float = -7.95, longitude: float = 112.61,
                       past_days: int = 1, forecast_days: int = 1) -> pd.DataFrame:
    """
    Mengambil data cuaca dari Open-Meteo API.

    Parameters
    ----------
    latitude : float
        Koordinat latitude lokasi (default: Malang, -7.95)
    longitude : float
        Koordinat longitude lokasi (default: Malang, 112.61)
    past_days : int
        Jumlah hari ke belakang untuk data historis
    forecast_days : int
        Jumlah hari ke depan untuk data forecast

    Returns
    -------
    pd.DataFrame
        DataFrame berisi data cuaca per jam
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
        ],
        "timezone": "Asia/Jakarta",
        "past_days": past_days,
        "forecast_days": forecast_days,
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame({
            "timestamp": data["hourly"]["time"],
            "temperature_2m_C": data["hourly"]["temperature_2m"],
            "humidity_percent": data["hourly"]["relative_humidity_2m"],
            "precipitation_mm": data["hourly"]["precipitation"],
            "soil_moisture": data["hourly"]["soil_moisture_0_to_7cm"],
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    else:
        raise ConnectionError(f"Gagal mengambil data. Status code: {response.status_code}")


if __name__ == "__main__":
    df = fetch_weather_data()
    print(f"Data berhasil di-fetch: {len(df)} baris")
    print(df.head())
