"""
tests/test_dags.py - Unit tests untuk dags/weather_ingestion_dag.py.

Menguji:
1. Resolusi path dinamis untuk REPO_ROOT dan Python virtual environment:
   - Windows (.venv/Scripts/python.exe dan venv/Scripts/python.exe)
   - Linux/macOS (.venv/bin/python dan venv/bin/python)
   - Fallback ke sys.executable jika kandidat tidak ditemukan.
2. Struktur metadata DAG:
   - dag_id == "weather_data_ingestion"
   - schedule == "0 * * * *"
   - catchup == False
   - max_active_runs == 1
   - start_date pada 2026-09-01 dengan timezone Asia/Jakarta (+07:00).
   - default_args (retries=2, retry_delay=2 menit, execution_timeout=5 menit).
3. Struktur Task fetch_and_save_weather_data:
   - task_id == "fetch_and_save_weather_data"
   - cwd menunjuk ke REPO_ROOT
   - execution_timeout == 5 menit
   - retries == 2, retry_delay == 2 menit
   - bash_command memanggil src/data_ingestion.py dengan python executable yang valid.
4. Kompatibilitas saat pustaka apache-airflow dan pendulum dimock seolah terpasang di runtime.
"""

from datetime import datetime, timedelta
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Pastikan REPO_ROOT ada di sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import dags.weather_ingestion_dag as dag_module
from dags.weather_ingestion_dag import (
    DEFAULT_DAG_ARGS,
    REPO_ROOT as DAG_REPO_ROOT,
    _BashOperatorFallback,
    _DAGFallback,
    _PendulumFallback,
    create_weather_ingestion_dag,
    get_python_interpreter,
    get_repo_root,
)


class TestWeatherIngestionDAG(unittest.TestCase):
    """Pengujian untuk validasi DAG weather_data_ingestion."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # -----------------------------------------------------------------------
    # 1. Path & Python Resolution Tests
    # -----------------------------------------------------------------------
    def test_repo_root_validity(self):
        """Verifikasi bahwa REPO_ROOT teresolusi ke direktori proyek yang valid."""
        self.assertTrue(DAG_REPO_ROOT.is_dir(), "DAG REPO_ROOT harus merupakan direktori")
        self.assertTrue(
            (DAG_REPO_ROOT / "src" / "data_ingestion.py").is_file(),
            "File src/data_ingestion.py harus ada di dalam REPO_ROOT",
        )
        self.assertTrue(
            (DAG_REPO_ROOT / "dags" / "weather_ingestion_dag.py").is_file(),
            "File dags/weather_ingestion_dag.py harus ada di dalam REPO_ROOT",
        )

    def test_get_repo_root_with_explicit_arg(self):
        """Uji resolusi repo_root saat argumen eksplisit diberikan (Path dan str)."""
        res_path = get_repo_root(self.temp_path)
        self.assertEqual(res_path, self.temp_path.resolve())

        # Uji penerimaan string path
        res_str = get_repo_root(str(self.temp_path))
        self.assertEqual(res_str, self.temp_path.resolve())

    def test_get_repo_root_with_airflow_repo_root_env(self):
        """Uji resolusi repo_root menggunakan environment variable AIRFLOW_REPO_ROOT."""
        with patch.dict(os.environ, {"AIRFLOW_REPO_ROOT": str(self.temp_path)}):
            res = get_repo_root()
            self.assertEqual(res, self.temp_path.resolve())

    def test_create_weather_ingestion_dag_with_string_path(self):
        """Uji pembuatan DAG dengan path bertipe str tidak menimbulkan TypeError."""
        test_dag = create_weather_ingestion_dag(str(self.temp_path))
        self.assertEqual(test_dag.dag_id, "weather_data_ingestion")
        task = test_dag.get_task("fetch_and_save_weather_data")
        self.assertEqual(task.cwd, str(self.temp_path.resolve()))

    def test_get_python_interpreter_with_string_path(self):
        """Uji get_python_interpreter dengan input string path tidak menimbulkan TypeError."""
        py_bin = self.temp_path / ".venv" / "bin" / "python"
        py_bin.parent.mkdir(parents=True, exist_ok=True)
        py_bin.write_text("# dummy")

        result = get_python_interpreter(str(self.temp_path))
        self.assertEqual(result, str(py_bin.absolute()))

    def test_get_python_interpreter_windows_dot_venv(self):
        """Uji resolusi interpreter untuk Windows .venv/Scripts/python.exe."""
        py_exe = self.temp_path / ".venv" / "Scripts" / "python.exe"
        py_exe.parent.mkdir(parents=True, exist_ok=True)
        py_exe.write_text("# dummy")

        result = get_python_interpreter(self.temp_path)
        self.assertEqual(result, str(py_exe.absolute()))

    def test_get_python_interpreter_windows_venv(self):
        """Uji resolusi interpreter untuk Windows venv/Scripts/python.exe."""
        py_exe = self.temp_path / "venv" / "Scripts" / "python.exe"
        py_exe.parent.mkdir(parents=True, exist_ok=True)
        py_exe.write_text("# dummy")

        result = get_python_interpreter(self.temp_path)
        self.assertEqual(result, str(py_exe.absolute()))

    def test_get_python_interpreter_linux_dot_venv(self):
        """Uji resolusi interpreter untuk Linux .venv/bin/python."""
        py_bin = self.temp_path / ".venv" / "bin" / "python"
        py_bin.parent.mkdir(parents=True, exist_ok=True)
        py_bin.write_text("# dummy")

        result = get_python_interpreter(self.temp_path)
        self.assertEqual(result, str(py_bin.absolute()))

    def test_get_python_interpreter_linux_venv(self):
        """Uji resolusi interpreter untuk Linux venv/bin/python."""
        py_bin = self.temp_path / "venv" / "bin" / "python"
        py_bin.parent.mkdir(parents=True, exist_ok=True)
        py_bin.write_text("# dummy")

        result = get_python_interpreter(self.temp_path)
        self.assertEqual(result, str(py_bin.absolute()))

    def test_get_python_interpreter_linux_python3_candidates(self):
        """Uji resolusi interpreter untuk kandidat python3 di Linux (.venv/bin/python3)."""
        py_bin3 = self.temp_path / ".venv" / "bin" / "python3"
        py_bin3.parent.mkdir(parents=True, exist_ok=True)
        py_bin3.write_text("# dummy")

        result = get_python_interpreter(self.temp_path)
        self.assertEqual(result, str(py_bin3.absolute()))

    def test_get_python_interpreter_priority_dot_venv_over_venv_windows(self):
        """Verifikasi prioritas .venv diutamakan dibanding venv pada Windows."""
        dot_venv_py = self.temp_path / ".venv" / "Scripts" / "python.exe"
        dot_venv_py.parent.mkdir(parents=True, exist_ok=True)
        dot_venv_py.write_text("# dummy 1")

        venv_py = self.temp_path / "venv" / "Scripts" / "python.exe"
        venv_py.parent.mkdir(parents=True, exist_ok=True)
        venv_py.write_text("# dummy 2")

        result = get_python_interpreter(self.temp_path)
        self.assertEqual(result, str(dot_venv_py.absolute()))

    def test_get_python_interpreter_priority_dot_venv_over_venv_linux(self):
        """Verifikasi prioritas .venv diutamakan dibanding venv pada Linux."""
        dot_venv_py = self.temp_path / ".venv" / "bin" / "python"
        dot_venv_py.parent.mkdir(parents=True, exist_ok=True)
        dot_venv_py.write_text("# dummy 1")

        venv_py = self.temp_path / "venv" / "bin" / "python"
        venv_py.parent.mkdir(parents=True, exist_ok=True)
        venv_py.write_text("# dummy 2")

        result = get_python_interpreter(self.temp_path)
        self.assertEqual(result, str(dot_venv_py.absolute()))

    def test_get_python_interpreter_fallback_sys_executable(self):
        """Uji fallback ke sys.executable jika tidak ada venv di direktori target."""
        empty_dir = self.temp_path / "empty_repo"
        empty_dir.mkdir(parents=True, exist_ok=True)

        result = get_python_interpreter(empty_dir)
        self.assertEqual(result, sys.executable)

    # -----------------------------------------------------------------------
    # 2. DAG Metadata Verification
    # -----------------------------------------------------------------------
    def test_dag_instance_metadata(self):
        """Verifikasi bahwa parameter DAG weather_data_ingestion terkonfigurasi sesuai spesifikasi."""
        test_dag = create_weather_ingestion_dag(DAG_REPO_ROOT)

        # ID dan schedule
        self.assertEqual(test_dag.dag_id, "weather_data_ingestion")
        self.assertEqual(test_dag.schedule, "0 * * * *")
        self.assertEqual(test_dag.schedule_interval, "0 * * * *")

        # Concurrency & catchup
        self.assertFalse(test_dag.catchup)
        self.assertEqual(test_dag.max_active_runs, 1)

        # Start Date
        start_date = test_dag.start_date
        self.assertIsNotNone(start_date)
        self.assertEqual(start_date.year, 2026)
        self.assertEqual(start_date.month, 9)
        self.assertEqual(start_date.day, 1)
        self.assertEqual(start_date.hour, 0)
        self.assertEqual(start_date.minute, 0)

        # Timezone Asia/Jakarta (UTC+7 -> offset 25200 detik)
        if start_date.tzinfo is not None:
            offset = start_date.utcoffset()
            if offset is not None:
                self.assertEqual(offset.total_seconds(), 7 * 3600)

        # Default args
        self.assertIn("retries", test_dag.default_args)
        self.assertEqual(test_dag.default_args["retries"], 2)
        self.assertEqual(
            test_dag.default_args["retry_delay"], timedelta(minutes=2)
        )
        self.assertEqual(
            test_dag.default_args["execution_timeout"], timedelta(minutes=5)
        )

    # -----------------------------------------------------------------------
    # 3. Task Structure & Bash Command Verification
    # -----------------------------------------------------------------------
    def test_task_attributes(self):
        """Verifikasi konfigurasi task fetch_and_save_weather_data."""
        test_dag = create_weather_ingestion_dag(DAG_REPO_ROOT)
        task = test_dag.get_task("fetch_and_save_weather_data")

        self.assertIsNotNone(task, "Task fetch_and_save_weather_data harus terdaftar di DAG")
        self.assertEqual(task.task_id, "fetch_and_save_weather_data")
        self.assertEqual(task.cwd, str(DAG_REPO_ROOT))
        self.assertEqual(task.execution_timeout, timedelta(minutes=5))
        self.assertEqual(task.retries, 2)
        self.assertEqual(task.retry_delay, timedelta(minutes=2))

    def test_task_bash_command_format(self):
        """Verifikasi format bash_command mengeksekusi src/data_ingestion.py."""
        test_dag = create_weather_ingestion_dag(DAG_REPO_ROOT)
        task = test_dag.get_task("fetch_and_save_weather_data")

        cmd = task.bash_command
        self.assertIsInstance(cmd, str)
        self.assertIn("src/data_ingestion.py", cmd)

        # Memastikan executable Python di dalam command sesuai dengan get_python_interpreter
        expected_py = get_python_interpreter(DAG_REPO_ROOT)
        self.assertIn(expected_py, cmd)
        # Memastikan path python dibungkus dengan tanda kutip untuk keamanan path dengan spasi
        self.assertTrue(cmd.startswith(f'"{expected_py}"'))

    def test_module_level_dag_object(self):
        """Verifikasi bahwa instance dag level modul siap discan oleh Airflow scheduler."""
        self.assertIsNotNone(dag_module.dag)
        self.assertEqual(dag_module.dag.dag_id, "weather_data_ingestion")
        self.assertIsNotNone(dag_module.fetch_and_save_weather_data)
        self.assertEqual(
            dag_module.fetch_and_save_weather_data.task_id,
            "fetch_and_save_weather_data",
        )

    # -----------------------------------------------------------------------
    # 4. Fallback Classes Behavior Verification
    # -----------------------------------------------------------------------
    def test_pendulum_fallback_behavior(self):
        """Uji fungsionalitas _PendulumFallback saat pendulum tidak terpasang."""
        dt = _PendulumFallback.datetime(2026, 9, 1, 10, 30, tz="Asia/Jakarta")
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 9)
        self.assertEqual(dt.day, 1)
        self.assertEqual(dt.hour, 10)
        self.assertEqual(dt.minute, 30)
        self.assertIsNotNone(dt.tzinfo, "Fallback datetime harus timezone-aware")
        self.assertEqual(
            dt.utcoffset(),
            timedelta(hours=7),
            "Asia/Jakarta harus memiliki offset UTC+7",
        )

    def test_pendulum_fallback_without_zoneinfo(self):
        """Uji _PendulumFallback tetap mengembalikan timezone valid meski ZoneInfo tidak tersedia."""
        with patch.object(dag_module, "ZoneInfo", None):
            dt = _PendulumFallback.datetime(2026, 9, 1, 0, 0, tz="Asia/Jakarta")
            self.assertIsNotNone(dt.tzinfo)
            self.assertEqual(dt.utcoffset(), timedelta(hours=7))

            dt_utc = _PendulumFallback.datetime(2026, 9, 1, 0, 0, tz="UTC")
            self.assertIsNotNone(dt_utc.tzinfo)
            self.assertEqual(dt_utc.utcoffset(), timedelta(0))

    def test_dag_fallback_context_manager(self):
        """Uji context manager `with _DAGFallback(...) as dag:` dan add_task."""
        with _DAGFallback(
            dag_id="test_dag_cm",
            schedule="0 * * * *",
            default_args={"retries": 1, "retry_delay": timedelta(minutes=1)},
        ) as cm_dag:
            op = _BashOperatorFallback(
                task_id="test_task",
                bash_command="echo 'test'",
            )

        self.assertIn("test_task", cm_dag.task_dict)
        self.assertEqual(cm_dag.get_task("test_task"), op)
        self.assertEqual(op.retries, 1)
        self.assertEqual(op.retry_delay, timedelta(minutes=1))

    def test_dag_fallback_has_task_and_task_ids(self):
        """Uji properti task_ids, has_task, dan penanganan task yang tidak ditemukan."""
        with _DAGFallback(dag_id="test_dag_ids") as d:
            _BashOperatorFallback(task_id="task_1", bash_command="echo 1")
            _BashOperatorFallback(task_id="task_2", bash_command="echo 2")

        self.assertEqual(d.task_ids, ["task_1", "task_2"])
        self.assertTrue(d.has_task("task_1"))
        self.assertTrue(d.has_task("task_2"))
        self.assertFalse(d.has_task("task_nonexistent"))

        with self.assertRaises(KeyError):
            d.get_task("task_nonexistent")

    def test_dag_fallback_nested_context_managers(self):
        """Uji bahwa context manager bertingkat (nested) mengembalikan context terluar dengan benar."""
        with _DAGFallback(dag_id="outer_dag") as outer:
            t1 = _BashOperatorFallback(task_id="t1", bash_command="echo 1")
            self.assertEqual(t1.dag, outer)

            with _DAGFallback(dag_id="inner_dag") as inner:
                t2 = _BashOperatorFallback(task_id="t2", bash_command="echo 2")
                self.assertEqual(t2.dag, inner)

            # Setelah inner exit, context harus kembali ke outer
            t3 = _BashOperatorFallback(task_id="t3", bash_command="echo 3")
            self.assertEqual(t3.dag, outer)

    def test_bash_operator_fallback_execute_success(self):
        """Uji eksekusi langsung operator fallback via .execute() menghasilkan kode sukses 0."""
        op = _BashOperatorFallback(
            task_id="test_exec",
            bash_command=f'"{sys.executable}" -c "print(\'hello_fallback\')"',
            cwd=str(DAG_REPO_ROOT),
        )
        returncode = op.execute()
        self.assertEqual(returncode, 0)

    def test_bash_operator_fallback_execute_failure(self):
        """Uji eksekusi operator fallback yang gagal melempar RuntimeError."""
        op = _BashOperatorFallback(
            task_id="test_exec_fail",
            bash_command=f'"{sys.executable}" -c "import sys; sys.exit(1)"',
            cwd=str(DAG_REPO_ROOT),
        )
        with self.assertRaises(RuntimeError):
            op.execute()

    # -----------------------------------------------------------------------
    # 5. Simulated Airflow Environment (Mocking airflow & pendulum)
    # -----------------------------------------------------------------------
    def test_creation_with_mocked_airflow_classes(self):
        """
        Mensimulasikan lingkungan di mana pustaka apache-airflow dan pendulum
        terpasang penuh, memastikan argumen yang dipassing ke DAG dan BashOperator
        sama persis.
        """
        mock_dag_cls = MagicMock()
        mock_operator_cls = MagicMock()
        mock_pendulum = MagicMock()
        mock_pendulum_dt = MagicMock()
        mock_pendulum.datetime.return_value = mock_pendulum_dt

        # Mock context manager behavior pada mock DAG
        mock_dag_instance = MagicMock()
        mock_dag_cls.return_value.__enter__.return_value = mock_dag_instance

        with patch.object(dag_module, "DAG", mock_dag_cls), \
             patch.object(dag_module, "BashOperator", mock_operator_cls), \
             patch.object(dag_module, "pendulum", mock_pendulum):

            dag_res = create_weather_ingestion_dag(DAG_REPO_ROOT)

            # Verifikasi pemanggilan pendulum.datetime
            mock_pendulum.datetime.assert_called_once_with(
                2026, 9, 1, tz="Asia/Jakarta"
            )

            # Verifikasi instansiasi DAG
            mock_dag_cls.assert_called_once_with(
                dag_id="weather_data_ingestion",
                default_args=DEFAULT_DAG_ARGS,
                description="DAG orkestrasi penarikan dan pembaruan data cuaca Open-Meteo per jam",
                schedule="0 * * * *",
                start_date=mock_pendulum_dt,
                catchup=False,
                max_active_runs=1,
                tags=["mlops", "data_ingestion", "weather", "open-meteo"],
            )

            # Verifikasi instansiasi BashOperator
            expected_py = get_python_interpreter(DAG_REPO_ROOT)
            mock_operator_cls.assert_called_once_with(
                task_id="fetch_and_save_weather_data",
                bash_command=f'"{expected_py}" src/data_ingestion.py',
                cwd=str(DAG_REPO_ROOT),
                execution_timeout=timedelta(minutes=5),
                retries=2,
                retry_delay=timedelta(minutes=2),
                dag=mock_dag_instance,
            )

    # -----------------------------------------------------------------------
    # 6. Direct CLI Script Invocation
    # -----------------------------------------------------------------------
    def test_direct_script_cli_execution(self):
        """Verifikasi bahwa dags/weather_ingestion_dag.py dapat dieksekusi langsung via CLI."""
        dag_script = DAG_REPO_ROOT / "dags" / "weather_ingestion_dag.py"
        result = subprocess.run(
            [sys.executable, str(dag_script)],
            capture_output=True,
            text=True,
            cwd=str(DAG_REPO_ROOT),
        )
        self.assertEqual(
            result.returncode, 0, f"Script CLI harus exit 0. Stderr: {result.stderr}"
        )
        self.assertIn("weather_data_ingestion", result.stdout)
        self.assertIn("fetch_and_save_weather_data", result.stdout)
        self.assertIn("0 * * * *", result.stdout)


if __name__ == "__main__":
    unittest.main()
