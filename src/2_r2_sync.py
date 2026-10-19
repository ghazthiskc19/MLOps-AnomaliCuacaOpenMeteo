"""
src/2_r2_sync.py - Sinkronisasi data mentah cuaca antara VPS (Airflow) dan Cloudflare R2.

Fungsi utama:
1. upload   : mengunggah CSV mentah ke bucket R2 sebagai snapshot bertimestamp
              (raw/weather_raw_<UTC>.csv) sekaligus menimpa raw/latest.csv.
2. download : mengunduh raw/latest.csv (atau key tertentu) ke lokal.
3. list     : menampilkan snapshot yang tersimpan di bucket.

Kredensial dibaca dari environment variable atau file .env di root repo (tidak di-commit):
    R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET

Contoh:
    python src/2_r2_sync.py upload
    python src/2_r2_sync.py download --dest data/raw/weather_raw_current.csv
    python src/2_r2_sync.py list
"""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_PATH = REPO_ROOT / "data" / "raw" / "weather_raw_current.csv"
RAW_PREFIX = "raw"
LATEST_KEY = f"{RAW_PREFIX}/latest.csv"
REQUIRED_ENV = ("R2_ENDPOINT_URL", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")


def load_env_file(path: Optional[Path] = None) -> None:
    """
    Memuat pasangan KEY=VALUE dari file .env ke os.environ.

    Nilai yang sudah ada di environment tidak ditimpa. File yang tidak ada diabaikan.
    """
    env_path = path or REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_client():
    """Membuat klien S3 (boto3) yang mengarah ke endpoint R2. Error jika kredensial belum lengkap."""
    import boto3

    load_env_file()
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Environment variable belum diset: {', '.join(missing)}")
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def build_snapshot_key(now: Optional[datetime] = None) -> str:
    """Membuat key snapshot bertimestamp UTC, mis. raw/weather_raw_20261013T020000Z.csv."""
    moment = now or datetime.now(timezone.utc)
    return f"{RAW_PREFIX}/weather_raw_{moment:%Y%m%dT%H%M%SZ}.csv"


def upload(local_path: Path = DEFAULT_LOCAL_PATH, client=None) -> List[str]:
    """Mengunggah file ke key snapshot dan raw/latest.csv. Mengembalikan daftar key yang ditulis."""
    local_path = Path(local_path)
    if not local_path.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {local_path}")
    s3 = client or get_client()
    bucket = os.environ["R2_BUCKET"]
    keys = [build_snapshot_key(), LATEST_KEY]
    for key in keys:
        s3.upload_file(str(local_path), bucket, key)
    return keys


def download(dest: Path = DEFAULT_LOCAL_PATH, key: str = LATEST_KEY, client=None) -> Path:
    """Mengunduh key dari bucket ke dest (folder induk dibuat bila belum ada)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    s3 = client or get_client()
    s3.download_file(os.environ["R2_BUCKET"], key, str(dest))
    return dest


def list_snapshots(client=None) -> List[str]:
    """Mengembalikan key di bawah prefix raw/ (urut menurut nama, terbaru di akhir)."""
    s3 = client or get_client()
    keys: List[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=os.environ["R2_BUCKET"], Prefix=f"{RAW_PREFIX}/"):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))
    return sorted(keys)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sinkronisasi data mentah cuaca dengan Cloudflare R2")
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("upload", help="Unggah CSV mentah ke R2")
    up.add_argument("--src", type=Path, default=DEFAULT_LOCAL_PATH)

    down = sub.add_parser("download", help="Unduh CSV dari R2")
    down.add_argument("--dest", type=Path, default=DEFAULT_LOCAL_PATH)
    down.add_argument("--key", default=LATEST_KEY, help="Key di bucket (default: raw/latest.csv)")

    sub.add_parser("list", help="Daftar snapshot di R2")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "upload":
        for key in upload(args.src):
            print(f"uploaded: {key}")
    elif args.command == "download":
        print(f"downloaded: {download(args.dest, args.key)}")
    else:
        for key in list_snapshots():
            print(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
