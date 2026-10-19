"""
simulate_data.py - Pembuat data cuaca simulasi dari data mentah Open-Meteo asli.

Data asli (data/raw/weather_raw_current.csv) tidak pernah diubah. Script ini membaca data asli,
menerapkan satu skenario, lalu menulis hasilnya ke data/simulated/ dengan skema kolom yang sama,
sehingga dapat langsung diproses oleh src/preprocess.py.

Skenario:
1. faults : merusak sebagian kecil baris (out-of-bounds, nilai negatif, spike, glitch radiasi malam,
            sensor stuck) untuk menyediakan contoh Class 1 (Hardware Fault). Open-Meteo adalah data
            model cuaca yang selalu bersih sehingga Class 1 tidak pernah muncul secara alami.
            Label tetap diberikan oleh AnomalyLabeler, bukan oleh script ini.
2. drift  : menggeser distribusi input (suhu, kelembaban, presipitasi) untuk meniru pergantian musim,
            dipakai untuk pengujian Data Drift.

Semua skenario deterministik terhadap --seed agar dataset dapat direproduksi.

Contoh:
    python src/simulate_data.py --scenario faults --fault-rate 0.05 --seed 42
    python src/simulate_data.py --scenario drift --temp-shift 3 --humidity-shift -15 --precip-scale 2
"""

import argparse
import logging
from pathlib import Path
import sys
from typing import Dict, Optional

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.data_preprocessing import RAW_COLUMNS, _atomic_to_csv, resolve_path  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("simulate_data")

DEFAULT_INPUT_PATH = REPO_ROOT / "data" / "raw" / "weather_raw_current.csv"
DEFAULT_SIMULATED_DIR = REPO_ROOT / "data" / "simulated"
SCENARIOS = ("faults", "drift")


class FaultInjector:
    """
    Simulasi kerusakan sensor IoT (Class 1: Hardware Fault).

    Menyisipkan satu blok sensor suhu stuck dan sejumlah fault titik (fault_rate x jumlah baris)
    pada baris acak. Input tidak diubah; hasil berupa salinan.
    """

    POINT_FAULTS = ("temp_oob", "humidity_oob", "soil_oob", "negative_value", "temp_spike", "night_radiation")
    STUCK_BLOCK_HOURS = 18  # > 12 jam agar rule "temperature stuck 12 jam" terpicu

    def __init__(self, fault_rate: float = 0.05, seed: int = 42):
        if not 0.0 <= fault_rate < 0.5:
            raise ValueError(f"fault_rate harus di rentang [0, 0.5): {fault_rate}")
        self.fault_rate = fault_rate
        self.seed = seed

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy().reset_index(drop=True)
        n = len(out)
        if self.fault_rate <= 0.0 or n < self.STUCK_BLOCK_HOURS + 48:
            return out

        # Kolom sensor bisa terbaca int64 dari CSV (misal kelembaban); nilai fault berupa float
        sensor_cols = [c for c in RAW_COLUMNS if c != "timestamp"]
        out[sensor_cols] = out[sensor_cols].astype(float)
        rng = np.random.default_rng(self.seed)
        counts: Dict[str, int] = {}

        # 1. Satu blok sensor suhu stuck (nilai konstan selama STUCK_BLOCK_HOURS jam)
        start = int(rng.integers(24, n - self.STUCK_BLOCK_HOURS - 24))
        block = range(start, start + self.STUCK_BLOCK_HOURS)
        out.loc[block, "temperature_2m_C"] = out.loc[start, "temperature_2m_C"]
        counts["temp_stuck_block"] = 1

        # 2. Fault titik pada baris acak (di luar blok stuck dan tetangganya)
        excluded = set(range(start - 1, start + self.STUCK_BLOCK_HOURS + 1))
        candidates = np.array([i for i in range(1, n - 1) if i not in excluded])
        n_point = max(1, int(round(n * self.fault_rate)))
        rows = rng.choice(candidates, size=min(n_point, len(candidates)), replace=False)
        kinds = rng.choice(self.POINT_FAULTS, size=len(rows))

        for i, kind in zip(rows, kinds):
            kind = self._apply_point_fault(out, int(i), str(kind), rng)
            counts[kind] = counts.get(kind, 0) + 1

        logger.info(f"Fault sintetis diinjeksikan (seed={self.seed}): {counts}")
        return out

    @staticmethod
    def _apply_point_fault(df: pd.DataFrame, i: int, kind: str, rng: np.random.Generator) -> str:
        """Merusak baris i sesuai jenis fault; mengembalikan jenis fault yang benar-benar dipakai."""
        hour = pd.Timestamp(df.loc[i, "timestamp"]).hour
        # Spike hanya terdeteksi saat tidak hujan, glitch radiasi hanya saat malam -> fallback ke OOB
        if kind == "temp_spike" and df.loc[i, "precipitation_mm"] != 0.0:
            kind = "temp_oob"
        if kind == "night_radiation" and not (hour >= 20 or hour < 4):
            kind = "temp_oob"

        if kind == "temp_oob":
            df.loc[i, "temperature_2m_C"] = rng.choice([rng.uniform(56.0, 70.0), rng.uniform(-30.0, -21.0)])
        elif kind == "humidity_oob":
            df.loc[i, "humidity_percent"] = rng.uniform(101.0, 130.0)
        elif kind == "soil_oob":
            df.loc[i, "soil_moisture"] = rng.uniform(0.56, 0.90)
        elif kind == "negative_value":
            col = rng.choice(["precipitation_mm", "radiation_wm2", "wind_speed_kmh"])
            df.loc[i, col] = -rng.uniform(0.5, 20.0)
        elif kind == "temp_spike":
            df.loc[i, "temperature_2m_C"] += rng.choice([-1.0, 1.0]) * rng.uniform(9.0, 15.0)
        elif kind == "night_radiation":
            df.loc[i, "radiation_wm2"] = rng.uniform(150.0, 600.0)
        return kind


class DriftSimulator:
    """
    Simulasi Data Drift: menggeser distribusi input seperti pergantian musim.

    Nilai hasil geseran dijaga tetap dalam batas fisik (kelembaban 0-100%, presipitasi >= 0)
    agar drift tidak salah terdeteksi sebagai Hardware Fault. Noise kecil ditambahkan pada suhu
    agar distribusi baru tidak sekadar translasi sempurna dari data asli.
    """

    def __init__(
        self,
        temp_shift: float = 3.0,
        humidity_shift: float = -15.0,
        precip_scale: float = 2.0,
        seed: int = 42,
    ):
        if precip_scale < 0.0:
            raise ValueError(f"precip_scale tidak boleh negatif: {precip_scale}")
        self.temp_shift = temp_shift
        self.humidity_shift = humidity_shift
        self.precip_scale = precip_scale
        self.seed = seed

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy().reset_index(drop=True)
        rng = np.random.default_rng(self.seed)

        noise = rng.normal(0.0, 0.3, size=len(out))
        out["temperature_2m_C"] = (out["temperature_2m_C"] + self.temp_shift + noise).round(1)
        out["humidity_percent"] = (out["humidity_percent"] + self.humidity_shift).clip(0.0, 100.0).round(0)
        out["precipitation_mm"] = (out["precipitation_mm"] * self.precip_scale).clip(lower=0.0).round(2)

        logger.info(
            f"Drift diterapkan (seed={self.seed}): suhu {self.temp_shift:+.1f}°C, "
            f"kelembaban {self.humidity_shift:+.1f}%, presipitasi x{self.precip_scale}"
        )
        return out


def load_raw(input_path: Path) -> pd.DataFrame:
    """Membaca CSV mentah, memvalidasi skema, dan mengurutkan kronologis."""
    if not input_path.exists():
        raise FileNotFoundError(f"Berkas masukan tidak ditemukan: {input_path}")
    df = pd.read_csv(input_path)
    missing_cols = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Kolom wajib tidak ditemukan dalam DataFrame: {missing_cols}")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df[RAW_COLUMNS].sort_values("timestamp").reset_index(drop=True)


def default_output_path(scenario: str, seed: int) -> Path:
    return DEFAULT_SIMULATED_DIR / f"weather_{scenario}_s{seed}.csv"


def simulate(
    scenario: str,
    input_path: Path = DEFAULT_INPUT_PATH,
    output_path: Optional[Path] = None,
    seed: int = 42,
    fault_rate: float = 0.05,
    temp_shift: float = 3.0,
    humidity_shift: float = -15.0,
    precip_scale: float = 2.0,
) -> pd.DataFrame:
    """Menjalankan satu skenario simulasi dan menyimpan hasilnya (data asli tidak diubah)."""
    if scenario == "faults":
        simulator = FaultInjector(fault_rate=fault_rate, seed=seed)
    elif scenario == "drift":
        simulator = DriftSimulator(temp_shift, humidity_shift, precip_scale, seed=seed)
    else:
        raise ValueError(f"Skenario tidak dikenal: {scenario} (pilihan: {SCENARIOS})")

    resolved_in = resolve_path(input_path)
    resolved_out = resolve_path(output_path or default_output_path(scenario, seed))
    if resolved_in == resolved_out:
        raise ValueError("Output tidak boleh menimpa data asli")

    simulated = simulator.apply(load_raw(resolved_in))
    _atomic_to_csv(simulated, resolved_out, index=False)
    logger.info(f"Data simulasi '{scenario}' ({len(simulated)} baris) disimpan ke: {resolved_out}")
    return simulated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pembuat data cuaca simulasi (faults / drift) dari data asli")
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--input-path", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument(
        "--output-path", type=Path, default=None,
        help="Default: data/simulated/weather_<scenario>_s<seed>.csv",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fault-rate", type=float, default=0.05, help="[faults] proporsi baris yang dirusak")
    parser.add_argument("--temp-shift", type=float, default=3.0, help="[drift] pergeseran suhu (°C)")
    parser.add_argument("--humidity-shift", type=float, default=-15.0, help="[drift] pergeseran kelembaban (%%)")
    parser.add_argument("--precip-scale", type=float, default=2.0, help="[drift] pengali presipitasi")
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    simulate(
        scenario=args.scenario,
        input_path=args.input_path,
        output_path=args.output_path,
        seed=args.seed,
        fault_rate=args.fault_rate,
        temp_shift=args.temp_shift,
        humidity_shift=args.humidity_shift,
        precip_scale=args.precip_scale,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
