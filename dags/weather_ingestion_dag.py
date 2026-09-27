"""
dags/weather_ingestion_dag.py - Apache Airflow DAG untuk orkestrasi data ingestion Open-Meteo per jam.

Fungsi utama:
1. Menjadwalkan penarikan data cuaca historis dan nowcast dari Open-Meteo API setiap jam ("0 * * * *").
2. Menyediakan resolusi path dinamis untuk REPO_ROOT dan Python virtual environment
   (mendukung Windows .venv/Scripts/python.exe & venv/Scripts/python.exe,
    serta Linux .venv/bin/python & venv/bin/python, dengan fallback ke sys.executable).
3. Mengeksekusi modul src/data_ingestion.py menggunakan BashOperator dengan direktori kerja (cwd)
   ditetapkan ke REPO_ROOT.
4. Memiliki mekanisme graceful fallback jika pustaka apache-airflow atau pendulum belum terpasang
   pada lingkungan runtime pengujian lokal.
"""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from typing import List, Optional, Union

# ---------------------------------------------------------------------------
# Dynamic Path Resolution
# ---------------------------------------------------------------------------
def get_repo_root(repo_root: Optional[Union[str, Path]] = None) -> Path:
    """
    Meresolusikan root direktori repositori secara dinamis.

    Urutan prioritas:
    1. Parameter repo_root jika diberikan (dikonversi ke Path absolut teresolusi).
    2. Environment variable AIRFLOW_REPO_ROOT jika diset.
    3. Direktori induk dari direktori dags/ (Path(__file__).resolve().parent.parent).

    Parameters
    ----------
    repo_root : Optional[Union[str, Path]]
        Path kandidat root repositori (berupa str atau Path).

    Returns
    -------
    Path
        Path absolut yang teresolusi ke root repositori.
    """
    if repo_root is not None:
        return Path(repo_root).resolve()
    env_root = os.environ.get("AIRFLOW_REPO_ROOT")
    if env_root and env_root.strip():
        return Path(env_root.strip()).resolve()
    return Path(__file__).resolve().parent.parent


REPO_ROOT = get_repo_root()


def get_python_interpreter(repo_root: Optional[Union[str, Path]] = None) -> str:
    """
    Menemukan executable Python virtual environment jika tersedia.

    Urutan prioritas pencarian:
    1. Windows: .venv/Scripts/python.exe
    2. Windows: venv/Scripts/python.exe
    3. Linux/macOS: .venv/bin/python
    4. Linux/macOS: venv/bin/python
    5. Linux/macOS: .venv/bin/python3
    6. Linux/macOS: venv/bin/python3
    7. Fallback: sys.executable saat ini

    Parameters
    ----------
    repo_root : Optional[Union[str, Path]]
        Root repositori proyek. Jika None, menggunakan konstanta REPO_ROOT.

    Returns
    -------
    str
        Path absolut ke executable Python (tanpa mendereference symlink venv).
    """
    root = get_repo_root(repo_root) if repo_root is not None else REPO_ROOT
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
        root / "venv" / "bin" / "python",
        root / ".venv" / "bin" / "python3",
        root / "venv" / "bin" / "python3",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            # Menggunakan absolute() alih-alih resolve() untuk menjaga integritas symlink virtualenv
            # pada sistem Linux/macOS sehingga sys.prefix dan pyvenv.cfg tetap terbaca dengan benar.
            return str(candidate.absolute())
    return sys.executable


# ---------------------------------------------------------------------------
# Pendulum Compatibility Handling
# ---------------------------------------------------------------------------
try:
    import pendulum
except ImportError:
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        ZoneInfo = None

    class _PendulumFallback:
        """Fallback emulator untuk pendulum.datetime ketika pendulum belum terpasang."""

        @staticmethod
        def datetime(
            year: int,
            month: int,
            day: int,
            hour: int = 0,
            minute: int = 0,
            second: int = 0,
            tz: Union[str, timezone, None] = "UTC",
        ) -> datetime:
            tzinfo = None
            if ZoneInfo and isinstance(tz, str):
                try:
                    tzinfo = ZoneInfo(tz)
                except Exception:
                    tzinfo = None

            # Fallback untuk timezone jika ZoneInfo tidak tersedia atau gagal (misal Windows tanpa tzdata)
            if tzinfo is None:
                if isinstance(tz, str):
                    tz_clean = tz.strip().upper()
                    if "JAKARTA" in tz_clean or "WIB" in tz_clean or tz_clean in ("+07:00", "+0700", "+07"):
                        tzinfo = timezone(timedelta(hours=7))
                    elif "UTC" in tz_clean or "GMT" in tz_clean or tz_clean in ("Z", "+00:00", "+00"):
                        tzinfo = timezone.utc
                    else:
                        tzinfo = timezone.utc
                elif isinstance(tz, timezone):
                    tzinfo = tz
                else:
                    tzinfo = timezone.utc

            return datetime(year, month, day, hour, minute, second, tzinfo=tzinfo)

    pendulum = _PendulumFallback()


# ---------------------------------------------------------------------------
# Airflow Compatibility Handling
# ---------------------------------------------------------------------------
_CURRENT_DAG_CONTEXT: Optional["_DAGFallback"] = None
_DAG_CONTEXT_STACK: List["_DAGFallback"] = []


def _get_active_dag_context() -> Optional["_DAGFallback"]:
    if _DAG_CONTEXT_STACK:
        return _DAG_CONTEXT_STACK[-1]
    return _CURRENT_DAG_CONTEXT


class _DAGFallback:
    """Fallback emulator untuk airflow.DAG ketika apache-airflow belum terpasang."""

    def __init__(
        self,
        dag_id: str,
        schedule: Optional[str] = None,
        schedule_interval: Optional[str] = None,
        start_date: Optional[datetime] = None,
        catchup: bool = False,
        max_active_runs: int = 1,
        default_args: Optional[dict] = None,
        description: Optional[str] = None,
        tags: Optional[list] = None,
        **kwargs,
    ):
        self.dag_id = dag_id
        resolved_schedule = schedule if schedule is not None else schedule_interval
        self.schedule = resolved_schedule
        self.schedule_interval = resolved_schedule
        self.start_date = start_date
        self.catchup = catchup
        self.max_active_runs = max_active_runs
        self.default_args = default_args.copy() if default_args else {}
        self.description = description
        self.tags = tags or []
        self.extra_kwargs = kwargs
        self.tasks: list = []
        self.task_dict: dict = {}

    @property
    def task_ids(self) -> List[str]:
        return list(self.task_dict.keys())

    def has_task(self, task_id: str) -> bool:
        return task_id in self.task_dict

    def __enter__(self):
        global _CURRENT_DAG_CONTEXT
        _DAG_CONTEXT_STACK.append(self)
        _CURRENT_DAG_CONTEXT = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _CURRENT_DAG_CONTEXT
        if self in _DAG_CONTEXT_STACK:
            _DAG_CONTEXT_STACK.remove(self)
        _CURRENT_DAG_CONTEXT = _DAG_CONTEXT_STACK[-1] if _DAG_CONTEXT_STACK else None

    def add_task(self, task):
        if task not in self.tasks:
            self.tasks.append(task)
            self.task_dict[task.task_id] = task

    def get_task(self, task_id: str):
        if task_id in self.task_dict:
            return self.task_dict[task_id]
        raise KeyError(f"Task '{task_id}' tidak ditemukan dalam DAG '{self.dag_id}'")


class _BashOperatorFallback:
    """Fallback emulator untuk airflow.operators.bash.BashOperator ketika apache-airflow belum terpasang."""

    def __init__(
        self,
        task_id: str,
        bash_command: str,
        cwd: Optional[str] = None,
        execution_timeout: Optional[timedelta] = None,
        retries: Optional[int] = None,
        retry_delay: Optional[timedelta] = None,
        dag: Optional[_DAGFallback] = None,
        **kwargs,
    ):
        self.task_id = task_id
        self.bash_command = bash_command
        self.cwd = cwd
        self.extra_kwargs = kwargs

        effective_dag = dag if dag is not None else _get_active_dag_context()
        self.dag = effective_dag

        if execution_timeout is not None:
            self.execution_timeout = execution_timeout
        elif effective_dag and "execution_timeout" in effective_dag.default_args:
            self.execution_timeout = effective_dag.default_args["execution_timeout"]
        else:
            self.execution_timeout = None

        if retries is not None:
            self.retries = retries
        elif effective_dag and "retries" in effective_dag.default_args:
            self.retries = effective_dag.default_args["retries"]
        else:
            self.retries = 0

        if retry_delay is not None:
            self.retry_delay = retry_delay
        elif effective_dag and "retry_delay" in effective_dag.default_args:
            self.retry_delay = effective_dag.default_args["retry_delay"]
        else:
            self.retry_delay = None

        self.owner = kwargs.get(
            "owner",
            effective_dag.default_args.get("owner", "airflow")
            if effective_dag
            else "airflow",
        )
        self.depends_on_past = kwargs.get(
            "depends_on_past",
            effective_dag.default_args.get("depends_on_past", False)
            if effective_dag
            else False,
        )

        if effective_dag and hasattr(effective_dag, "add_task"):
            effective_dag.add_task(self)

    def execute(self, context: Optional[dict] = None) -> int:
        """
        Mengeksekusi bash_command menggunakan subprocess untuk pengujian lokal
        atau verifikasi pipeline tanpa Airflow scheduler aktif.
        """
        import subprocess

        result = subprocess.run(
            self.bash_command,
            shell=True,
            cwd=self.cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Bash command failed with exit code {result.returncode}:\n"
                f"STDOUT: {result.stdout}\n"
                f"STDERR: {result.stderr}"
            )
        return result.returncode


try:
    from airflow import DAG
    from airflow.operators.bash import BashOperator

    AIRFLOW_INSTALLED = True
except ImportError:
    DAG = _DAGFallback  # type: ignore
    BashOperator = _BashOperatorFallback  # type: ignore
    AIRFLOW_INSTALLED = False


# ---------------------------------------------------------------------------
# DAG Definition Factory & Instance
# ---------------------------------------------------------------------------
DEFAULT_DAG_ARGS = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=5),
}


def create_weather_ingestion_dag(repo_root: Optional[Union[str, Path]] = None):
    """
    Membuat dan mengonfigurasi instance DAG untuk weather data ingestion.

    Parameters
    ----------
    repo_root : Optional[Union[str, Path]]
        Root direktori repositori. Jika None, menggunakan resolusi dinamis get_repo_root().

    Returns
    -------
    DAG
        Instance DAG Apache Airflow yang siap dieksekusi.
    """
    root = get_repo_root(repo_root) if repo_root is not None else REPO_ROOT
    python_executable = get_python_interpreter(root)

    # Command BashOperator: mengeksekusi src/data_ingestion.py relatif terhadap cwd REPO_ROOT
    bash_command = f'"{python_executable}" src/data_ingestion.py'

    with DAG(
        dag_id="weather_data_ingestion",
        default_args=DEFAULT_DAG_ARGS,
        description="DAG orkestrasi penarikan dan pembaruan data cuaca Open-Meteo per jam",
        schedule="0 * * * *",
        start_date=pendulum.datetime(2026, 9, 1, tz="Asia/Jakarta"),
        catchup=False,
        max_active_runs=1,
        tags=["mlops", "data_ingestion", "weather", "open-meteo"],
    ) as dag_instance:
        BashOperator(
            task_id="fetch_and_save_weather_data",
            bash_command=bash_command,
            cwd=str(root),
            execution_timeout=timedelta(minutes=5),
            retries=2,
            retry_delay=timedelta(minutes=2),
            dag=dag_instance,
        )

    return dag_instance


# Top-level DAG instance untuk deteksi otomatis oleh Airflow scheduler
dag = create_weather_ingestion_dag(REPO_ROOT)
fetch_and_save_weather_data = dag.get_task("fetch_and_save_weather_data")


if __name__ == "__main__":
    print("=" * 60)
    print("Apache Airflow DAG Definition: weather_data_ingestion")
    print("=" * 60)
    print(f"DAG ID          : {dag.dag_id}")
    print(f"Schedule        : {dag.schedule}")
    print(f"Start Date      : {dag.start_date}")
    print(f"Catchup         : {dag.catchup}")
    print(f"Max Active Runs : {dag.max_active_runs}")
    print(f"Airflow Installed: {AIRFLOW_INSTALLED}")
    print(f"Tasks ({len(dag.tasks)}):")
    for t in dag.tasks:
        print(f"  - Task ID   : {t.task_id}")
        print(f"    Command   : {getattr(t, 'bash_command', None)}")
        print(f"    CWD       : {getattr(t, 'cwd', None)}")
        print(f"    Timeout   : {getattr(t, 'execution_timeout', None)}")
        print(f"    Retries   : {getattr(t, 'retries', None)}")
        print(f"    RetryDelay: {getattr(t, 'retry_delay', None)}")
    print("=" * 60)
