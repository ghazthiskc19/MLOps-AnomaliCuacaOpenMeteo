"""
tests/test_r2_sync.py - Pengujian src/r2_sync.py dengan klien S3 palsu (tanpa jaringan).
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import r2_sync  # noqa: E402


class FakeS3:
    def __init__(self):
        self.uploaded = []
        self.downloaded = []

    def upload_file(self, filename, bucket, key):
        self.uploaded.append((filename, bucket, key))

    def download_file(self, bucket, key, filename):
        self.downloaded.append((bucket, key, filename))
        Path(filename).write_text("data", encoding="utf-8")


class TestR2Sync(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"R2_BUCKET": "bucket-test"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_build_snapshot_key_uses_utc_timestamp(self):
        key = r2_sync.build_snapshot_key(datetime(2026, 10, 13, 2, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(key, "raw/weather_raw_20261013T020000Z.csv")

    def test_upload_writes_snapshot_and_latest(self):
        s3 = FakeS3()
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "raw.csv"
            src.write_text("a,b\n1,2\n", encoding="utf-8")
            keys = r2_sync.upload(src, client=s3)
        self.assertEqual(len(keys), 2)
        self.assertTrue(keys[0].startswith("raw/weather_raw_"))
        self.assertEqual(keys[1], "raw/latest.csv")
        self.assertEqual([u[1] for u in s3.uploaded], ["bucket-test", "bucket-test"])

    def test_upload_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            r2_sync.upload(Path("tidak_ada.csv"), client=FakeS3())

    def test_download_creates_parent_dir(self):
        s3 = FakeS3()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "nested" / "out.csv"
            result = r2_sync.download(dest, client=s3)
            self.assertTrue(result.is_file())
        self.assertEqual(s3.downloaded[0][:2], ("bucket-test", "raw/latest.csv"))

    def test_get_client_reports_missing_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            r2_sync, "load_env_file"
        ):
            with self.assertRaises(RuntimeError) as ctx:
                r2_sync.get_client()
        self.assertIn("R2_ENDPOINT_URL", str(ctx.exception))

    def test_load_env_file_does_not_override_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text('# komentar\nR2_X_NEW="baru"\nR2_X_OLD=ditimpa\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"R2_X_OLD": "asli"}):
                r2_sync.load_env_file(env)
                self.assertEqual(os.environ["R2_X_NEW"], "baru")
                self.assertEqual(os.environ["R2_X_OLD"], "asli")
            os.environ.pop("R2_X_NEW", None)


if __name__ == "__main__":
    unittest.main()
