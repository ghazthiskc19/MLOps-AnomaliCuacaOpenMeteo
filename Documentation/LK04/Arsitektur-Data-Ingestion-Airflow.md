# 📊 Arsitektur & Visualisasi Pipeline Data Ingestion Apache Airflow
> **Proyek**: Sistem Otomatis Deteksi Anomali Data Cuaca Open-Meteo untuk Smart Farming Berbasis MLOps (LK-04)  
> **Lokasi Target**: Kota Malang, Jawa Timur (-7.95, 112.61)  
> **Environment**: Ubuntu Server (2 vCPU, 2 GB RAM, 20 GB Disk + 2 GB Swap)  

---

## 1. Diagram Arsitektur Makro (End-to-End Infrastructure)

Diagram berikut menggambarkan bagaimana sistem operasi Linux di VM lab, daemon Airflow, repositori kode, dan Open-Meteo API saling berinteraksi:

```mermaid
flowchart TB
    subgraph VM ["🖥️ Ubuntu VM Server Lab (2 Core, 2 GB RAM, 20 GB Disk)"]
        subgraph OS ["⚙️ Linux Systemd Daemon (24/7 Background Service)"]
            SRV_SCHED["airflow-scheduler.service<br/>(Daemon Penjadwal Otomatis)"]
            SRV_WEB["airflow-webserver.service<br/>(Daemon Dashboard UI :8080)"]
        end

        subgraph AIRFLOW_CORE ["🌪️ Apache Airflow Core (SequentialExecutor + SQLite)"]
            METASTORE[("airflow.db<br/>(SQLite Metastore)")]
            SCHEDULER["Airflow Scheduler Engine"]
            UI["Airflow Webserver (Gunicorn, 1 worker)"]
            SYMLINK["~/airflow/dags/weather_ingestion_dag.py<br/>(Symlink Pointer)"]
        end

        subgraph REPO ["📦 Repositori Proyek: ~/MLOps-AnomaliCuacaOpenMeteo"]
            DAG_FILE["dags/weather_ingestion_dag.py"]
            VENV["venv/bin/python<br/>(Python 3.12 Virtualenv terisolasi)"]
            SCRIPT["src/data_ingestion.py"]
            DISK_RAW[("data/raw/weather_raw_current.csv<br/>(Rolling Buffer 720 Baris / 30 Hari)")]
        end
    end

    subgraph CLOUD ["☁️ Cloud Eksternal"]
        API["Open-Meteo Weather API<br/>(https://api.open-meteo.com/v1/forecast)"]
        BROWSER["💻 Browser Pengguna di Laptop<br/>(http://IP_VM:8080)"]
    end

    %% Relasi Systemd ke Airflow
    SRV_SCHED -.->|Mengontrol proses| SCHEDULER
    SRV_WEB -.->|Mengontrol proses| UI

    %% Airflow Engine
    SCHEDULER <-->|Baca jadwal & catat run status| METASTORE
    SCHEDULER -->|Pindai DAG tiap 30 detik| SYMLINK
    SYMLINK -->|Menunjuk ke file fisik| DAG_FILE
    UI <-->|Tampilkan status & grafik DAG| METASTORE
    BROWSER <-->|Akses Web UI| UI

    %% Eksekusi Task
    SCHEDULER -->|Trigger tiap jam menit 00| DAG_FILE
    DAG_FILE -->|Spawn BashOperator Subprocess| VENV
    VENV -->|Eksekusi script| SCRIPT
    SCRIPT <-->|HTTP GET past_days=1 atau 30| API
    SCRIPT -->|Simpan atomik| DISK_RAW

    %% Styling Warna Grafis
    style VM fill:#f8f9fa,stroke:#343a40,stroke-width:2px
    style OS fill:#e9ecef,stroke:#495057,stroke-width:1px
    style AIRFLOW_CORE fill:#e8f4f8,stroke:#0288d1,stroke-width:2px
    style REPO fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style CLOUD fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style DISK_RAW fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px
```

---

## 2. Diagram Detail Alur Logika DAG (`weather_ingestion_dag.py`)

Diagram ini memperlihatkan mekanisme internal pada script DAG penjadwal:

```mermaid
flowchart TD
    START(["🕒 Trigger Jadwal Tiap Jam (Cron: '0 * * * *')"]) --> EVAL_ENV

    subgraph RESOLUTION ["1. Dynamic Path Resolution"]
        EVAL_ENV["get_repo_root()<br/>• Cek argumen fungsi<br/>• Cek AIRFLOW_REPO_ROOT<br/>• Default: Path(__file__).resolve().parent.parent"]
        EVAL_ENV --> GET_PY["get_python_interpreter()<br/>• Deteksi OS (Linux vs Windows)<br/>• Cari: .venv/bin/python atau venv/bin/python<br/>• Gunakan .absolute() (Preservasi Symlink Linux)"]
    end

    subgraph DAG_DEF ["2. Konfigurasi Proteksi DAG & Eksekusi"]
        GET_PY --> BUILD_CMD["Susun Perintah Eksekusi:<br/>bash_command = 'venv/bin/python src/data_ingestion.py'<br/>cwd = REPO_ROOT"]
        BUILD_CMD --> PROTECT["Konfigurasi Parameter Proteksi VPS 2 GB RAM:<br/>• catchup = False (Cegah Backfill Storm)<br/>• max_active_runs = 1 (Anti-Tabrakan Task)<br/>• execution_timeout = 5 menit (Cegah Zombie Task)<br/>• retries = 2 (Jeda 2 menit jika koneksi putus)"]
        PROTECT --> BASH_OP["BashOperator: 'fetch_and_save_weather_data'"]
    end

    subgraph EXEC ["3. Eksekusi Mandiri (Process Isolation)"]
        BASH_OP --> SPAWN["Spawn Isolated Subprocess Linux"]
        SPAWN --> RUN_SCRIPT["Jalankan src/data_ingestion.py"]
        RUN_SCRIPT --> FINISH{"Exit Code == 0?"}
        FINISH -->|Ya| SUCCESS["Tandai Task SUCCESS di Airflow<br/>(Memori Subproses langsung dilepas ke OS)"]
        FINISH -->|Tidak| RETRY["Tunggu 2 Menit & Coba Ulang (Maks 2x)"]
    end

    style RESOLUTION fill:#ede7f6,stroke:#512da8,stroke-width:2px
    style DAG_DEF fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style EXEC fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
```

---

## 3. Diagram Detail Fungsi di `src/data_ingestion.py`

Diagram ini memperlihatkan alur logika setiap fungsi pada modul inti penarikan dan pemrosesan data:

```mermaid
flowchart TD
    CLI["CLI / Airflow BashOperator"] --> MAIN["main()"]
    
    MAIN --> INGEST["ingest_weather_data(output_path, latitude, longitude, buffer_size=720)"]
    
    subgraph LOGIC_ADAPTIF ["Penentuan Mode Penarikan Adaptif"]
        INGEST --> CHECK_DISK{"Apakah weather_raw_current.csv<br/>sudah ada dan terisi >= 720 baris?"}
        CHECK_DISK -->|Belum Ada / < 720 baris| INIT_MODE["Mode Inisialisasi Buffer:<br/>past_days = 30 (Tarik 720 jam data)"]
        CHECK_DISK -->|Sudah Penuh >= 720 baris| REGULAR_MODE["Mode Pembaruan Rutin:<br/>past_days = 1 (Hemat kuota & bandwidth)"]
    end

    subgraph FETCH_STAGE ["fetch_weather_data() (Ketahanan Jaringan)"]
        INIT_MODE & REGULAR_MODE --> FETCH["fetch_weather_data()<br/>Endpoint: api.open-meteo.com/v1/forecast"]
        FETCH --> REQ["HTTP GET Request (timeout=10s)"]
        REQ --> STATUS_CHECK{"Status Response?"}
        STATUS_CHECK -->|200 OK| PARSE["Ekstrak 6 Fitur Cuaca + Timestamp<br/>Ubah ke Pandas DataFrame"]
        STATUS_CHECK -->|"4xx Client Error (kecuali 429)"| FAIL_FAST["Fail-Fast: Lempar ValueError seketika<br/>(Tanpa retry sia-sia)"]
        STATUS_CHECK -->|"5xx Server Error / Timeout / 429"| RETRY_LOOP{"Sudah 3x Retry?"}
        RETRY_LOOP -->|Belum| BACKOFF["Jeda Eksponensial (2s, 4s)<br/>Coba lagi..."] --> REQ
        RETRY_LOOP -->|Sudah| ERR["Lempar ConnectionError"]
    end

    subgraph SAVE_STAGE ["save_weather_data() (Pengelolaan Jendela Geser)"]
        PARSE --> SAVE["save_weather_data()"]
        SAVE --> VAL["Validasi Timestamp (Buang nilai NaT / Invalid)"]
        VAL --> CONCAT["Gabungkan (pd.concat) Data Baru dengan Data Lama"]
        CONCAT --> DEDUP["Deduplikasi: drop_duplicates(subset=['timestamp'], keep='last')"]
        DEDUP --> SORT["Urutkan Kronologis: sort_values('timestamp')"]
        SORT --> SLICE["Potong Jendela Geser: tail(720)<br/>(Membuang data hari ke-31 yang usang)"]
        SLICE --> SCHEMA["Pastikan Struktur 7 Kolom RAW_COLUMNS Utuh"]
    end

    subgraph ATOMIC_STAGE ["_atomic_to_csv() (Penulisan Anti-Korup)"]
        SCHEMA --> ATOMIC["_atomic_to_csv()"]
        ATOMIC --> TMP_WRITE["Tulis ke file temporer:<br/>weather_raw_current.csv.<PID>_<TIMESTAMP>.tmp"]
        TMP_WRITE --> OS_REPLACE["Operasi Kernel: os.replace(tmp_file, target_path)<br/>(Pertukaran Berkas Seketika / Atomik)"]
        OS_REPLACE --> DISK_FINAL[("data/raw/weather_raw_current.csv")]
    end

    style LOGIC_ADAPTIF fill:#fff8e1,stroke:#f57f17,stroke-width:2px
    style FETCH_STAGE fill:#e0f2f1,stroke:#00796b,stroke-width:2px
    style SAVE_STAGE fill:#ede7f6,stroke:#512da8,stroke-width:2px
    style ATOMIC_STAGE fill:#fce4ec,stroke:#c2185b,stroke-width:2px
    style DISK_FINAL fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
```

---

## 4. Diagram Kronologis Siklus Eksekusi per Jam (Sequence Diagram)

Diagram berikut memperlihatkan lini masa interaksi komponen mulai dari detik ke-0 hingga selesai:

```mermaid
sequenceDiagram
    autonumber
    actor Cron as ⏰ Pemicu Waktu Linux (Setiap Jam Menit 00)
    participant Sched as 🕒 Airflow Scheduler
    participant DB as 🗄️ SQLite Metastore
    participant Worker as ⚡ BashOperator (Subprocess)
    participant Python as 🐍 src/data_ingestion.py
    participant API as ☁️ Open-Meteo API
    participant Disk as 📁 data/raw/weather_raw_current.csv

    Cron->>Sched: Jam 14:00:00 WIB tiba
    Sched->>DB: Cek status DAG 'weather_data_ingestion' (Unpaused / Active)
    Sched->>DB: Buat record DagRun baru (State: RUNNING)
    Sched->>Worker: Jalankan Task: "venv/bin/python src/data_ingestion.py"
    
    activate Worker
    Worker->>Python: Memuat modul Python & pandas (~80 MB RAM)
    Python->>Disk: Cek baris file eksisting (terdeteksi 720 baris)
    Python->>API: HTTP GET (past_days=1, forecast_days=1)
    API-->>Python: Respons JSON (24 data jam, ~5 KB)
    Python->>Python: Deduplikasi timestamp & pertahankan tepat 720 baris
    Python->>Disk: Tulis file .tmp -> rename ke weather_raw_current.csv
    Python-->>Worker: Exit Code 0 (Proses selesai dalam ~2.5 detik)
    deactivate Worker

    Worker-->>Sched: Task Finished (Exit Code 0)
    Note over Worker,Sched: Seluruh memori subproses dilepas kembali ke OS VPS
    Sched->>DB: Update TaskInstance & DagRun (State: SUCCESS)
    Sched->>Sched: Hibernasi sampai pergantian jam berikutnya (15:00:00 WIB)
```

---

## 5. Matriks Peran & Fungsi Komponen

| Komponen / Fungsi | Lokasi Berkas | Peran Utama dalam Sistem |
|---|---|---|
| **`get_repo_root()`** | `dags/weather_ingestion_dag.py` | Menentukan lokasi root proyek secara independen, mencegah salah direktori saat dipanggil Airflow daemon. |
| **`get_python_interpreter()`** | `dags/weather_ingestion_dag.py` | Mendeteksi Python di `venv/bin/python` dengan preservasi symlink Linux agar paket `pandas` dan `requests` terbaca. |
| **`weather_data_ingestion` (DAG)** | `dags/weather_ingestion_dag.py` | Menjadwalkan penarikan data tiap jam (`0 * * * *`) dengan proteksi `catchup=False` dan `max_active_runs=1`. |
| **`fetch_weather_data()`** | `src/data_ingestion.py` | Mengambil payload cuaca dari Open-Meteo dengan proteksi retry eksponensial (3x) dan fail-fast 4xx. |
| **`save_weather_data()`** | `src/data_ingestion.py` | Mengelola rolling window 30 hari (720 baris), deduplikasi timestamp, dan penjagaan skema 7 kolom LK03. |
| **`_atomic_to_csv()`** | `src/data_ingestion.py` | Menulis file via buffer temporer (`.tmp`) dan atomic rename (`os.replace`) agar data tidak pernah korup. |
| **`ingest_weather_data()`** | `src/data_ingestion.py` | Fungsi fasad yang mengorkestrasi penarikan adaptif (30 hari pada inisiasi awal, 1 hari pada pembaruan rutin). |
| **`airflow-scheduler.service`** | `/etc/systemd/system/` | Service systemd Linux yang menjaga scheduler Airflow tetap menyala 24/7 dan auto-restart saat reboot. |
| **`airflow-webserver.service`** | `/etc/systemd/system/` | Service systemd Linux yang melayani Web UI dashboard Airflow di port 8080. |
