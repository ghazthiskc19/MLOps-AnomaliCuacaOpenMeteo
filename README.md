# 🌤️ MLOps-AnomaliCuacaOpenMeteo

**Sistem Otomatis Deteksi Anomali Data Cuaca Open-Meteo untuk Smart Farming Berbasis MLOps**

> Proyek MLOps end-to-end yang mendeteksi anomali data cuaca dari Open-Meteo API menggunakan Multiclass Classification untuk mendukung Smart Farming di area Malang, Jawa Timur.

---

## 📋 Deskripsi

Proyek ini berfokus pada domain **Internet of Things (IoT)** dan **Smart Agriculture** (Pertanian Pintar). Sistem ini menangani manajemen data metrik lingkungan yang dihasilkan oleh infrastruktur Smart Farming otomatis.

### Machine Learning Task

Pendekatan Machine Learning yang diterapkan adalah **Multiclass Classification** untuk deteksi dan diferensiasi anomali data cuaca ke dalam 3 kelas:

| Class | Label | Deskripsi |
|---|---|---|
| **0** | Normal State | Pembacaan sensor dalam rentang operasional wajar |
| **1** | Hardware Fault Anomaly | Indikasi kegagalan perangkat keras (stuck value, spiking, out-of-bounds) |
| **2** | Extreme Environmental Anomaly | Perubahan kondisi lingkungan ekstrem (gelombang panas, kekeringan) |

### Mengapa MLOps?

Data cuaca bersifat dinamis dan mengalami **Data Drift** (pergeseran distribusi saat pergantian musim) dan **Concept Drift** (perubahan definisi "anomali" di musim berbeda). Sistem MLOps dibutuhkan untuk:
- Monitoring model secara real-time
- Continuous Training otomatis saat drift terdeteksi
- Shadow Deployment untuk validasi model baru

---

## 🏗️ Struktur Proyek

```
MLOps-AnomaliCuacaOpenMeteo/
├── dags/                       # Apache Airflow DAGs
│   └── weather_ingestion_dag.py# DAG orkestrasi data ingestion per jam
├── data/
│   ├── raw/                    # Buffer data mentah (weather_raw_current.csv)
│   └── processed/              # Fitur diproses & dilabel (weather_features_v1.0.csv)
├── models/                     # Model artifacts (.pkl, .joblib)
├── src/                        # Source code Python utama
│   ├── __init__.py
│   ├── data_ingestion.py       # Modul ingestion API Open-Meteo & buffer 30 hari
│   ├── ingest_data.py          # Entrypoint / CLI wrapper ingestion
│   ├── data_preprocessing.py   # Pipeline ETL, Quality Gate, Anomaly Labeling, & Feature Eng.
│   └── preprocess.py           # Entrypoint / CLI wrapper preprocessing
├── notebooks/                  # Jupyter notebooks (EDA, PoC, eksperimen)
├── tests/                      # Unit tests komprehensif
│   ├── test_dags.py            # Pengujian DAG Airflow
│   ├── test_data_ingestion.py  # Pengujian pipeline ingestion
│   └── test_data_preprocessing.py # Pengujian Quality Gate, Anomaly Labeler, & Features
├── configs/                    # File konfigurasi
├── Documentation/              # Dokumen akademik (LK01, LK02, LK03, LK04)
│   ├── LK03/                   # Perancangan arsitektur data & DVC
│   └── LK04/                   # Laporan implementasi ingestion & preprocessing
├── .devcontainer/              # GitHub Codespaces configuration
├── requirements.txt            # Python dependencies
├── LICENSE                     # MIT License
└── README.md                   # Dokumentasi proyek
```

---

## 🚀 Cara Menjalankan

### Prerequisites

- Python 3.11+
- Git
- pip (Python package manager)

### Setup Environment (Lokal)

```bash
# 1. Clone repository
git clone https://github.com/<username>/MLOps-AnomaliCuacaOpenMeteo.git
cd MLOps-AnomaliCuacaOpenMeteo

# 2. Buat virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# atau
venv\Scripts\activate     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verifikasi instalasi
python -c "import requests; import pandas; print('Setup berhasil!')"
```

### Setup Environment (GitHub Codespaces)

1. Klik tombol hijau **"Code"** → **"Codespaces"** → **"Create codespace on main"**
2. Tunggu setup selesai (2-3 menit, otomatis install dependencies)
3. Verifikasi: `python --version`

### Menjalankan Pipeline Data

#### 1. Data Ingestion (Open-Meteo API)
Mengambil data cuaca per jam untuk Kota Malang dengan mekanisme retry backoff dan rolling buffer 30 hari (720 baris).

```bash
# Menjalankan modul ingestion utama
python src/data_ingestion.py

# Atau melalui entrypoint wrapper
python src/ingest_data.py --past-days 30 --buffer-size 720
```

#### 2. Data Preprocessing & Feature Engineering
Mengeksekusi Quality Gate, pelabelan anomali 3-kelas (Normal, Hardware Fault, Extreme Weather), dan ekstraksi 40 fitur temporal serta agrometeorologi (VPD, Dew Point, rolling statistics).

```bash
# Menjalankan modul preprocessing utama
python src/data_preprocessing.py

# Atau melalui entrypoint wrapper
python src/preprocess.py --input-path data/raw/weather_raw_current.csv --output-path data/processed/weather_features_v1.0.csv
```

#### 3. Menjalankan Unit Tests
Menjalankan seluruh 67 unit tests yang mencakup pengujian DAG Airflow, modul ingestion, dan modul preprocessing.

```bash
# Menjalankan seluruh rangkaian tes unit
python -m unittest discover tests
```

#### 4. Menjalankan Apache Airflow DAG (Opsional / VM Server)
```bash
# Verifikasi integritas DAG
python dags/weather_ingestion_dag.py

# Trigger DAG secara manual via Airflow CLI
airflow dags test weather_data_ingestion
```

---

## 📊 Data Source

Proyek ini menggunakan **[Open-Meteo API](https://open-meteo.com/)** sebagai sumber data tunggal.

| Parameter | Detail |
|---|---|
| **API Endpoint** | `https://api.open-meteo.com/v1/forecast` |
| **Lokasi** | Malang, Jawa Timur (-7.95, 112.61) |
| **Modalitas Data** | Tabular Time-Series |
| **Frekuensi Update** | Setiap 1 jam (micro-batch) |
| **Variabel** | temperature_2m, relative_humidity_2m, precipitation, soil_moisture_0_to_7cm |
| **Biaya** | Gratis (Open-Access, tanpa API key) |

---

## 🔧 Tech Stack

| Komponen | Teknologi | Fungsi |
|---|---|---|
| Language & Data Processing | Python & Pandas | Bahasa utama dan manipulasi data |
| Orchestration & Workflow | Apache Airflow | Scheduler dan workflow automation |
| Data Versioning | DVC | Version control untuk dataset |
| Experiment Tracking | MLflow | Tracking eksperimen dan model registry |
| Model Serving | FastAPI | REST API untuk inference |
| Containerization | Docker | Packaging aplikasi |
| Monitoring & Drift Detection | Evidently AI | Deteksi data drift dan concept drift |
| Visual Dashboard | Grafana | Visualisasi metrik dan monitoring |

---

## 📈 Pipeline MLOps

![Pipeline MLOps yang digunakan dalam project ini](Documentation/LK01/MLOps%20LK01-Page-1.jpg)

### 6.1 Diagram Alur End-to-End (Data → Training → Deployment → Monitoring)

#### **Tahap 1: Data Ingestion & Data Versioning (Setiap 1 Jam)**
- **Cara Kerja**: Apache Airflow mengeksekusi DAG harian/jam-jaman. Airflow mengirim HTTP GET Request ke Open-Meteo API.
- **Proses**:
  1. Data JSON dari API ditarik, diekstrak variabelnya (`temperature_2m`, `precipitation`, `soil_moisture`), dan diubah menjadi DataFrame Pandas.
  2. Data divalidasi (memastikan tidak ada kolom hilang). Data baru lalu digabungkan (*appended*) ke file `dataset_current.csv`.
  3. DVC (*Data Version Control*) mencatat hash MD5 dari file data terbaru. Ini memastikan kita bisa kembali (*rollback*) ke versi data jam tertentu jika ada masalah.

#### **Tahap 2: Continuous Training & Model Registry (Saat Trigger Aktif)**
- **Cara Kerja**: Jika Airflow menerima sinyal *Retraining Trigger* (jadwal 2 mingguan atau alarm dari Evidently AI), Airflow akan menjalankan *Retraining DAG*.
- **Proses**:
  1. Airflow memanggil script Python untuk *preprocessing*, *feature scaling*, dan melatih model (antara XGBoost / Random Forest) dengan data 30 hari terakhir.
  2. MLflow Tracking mencatat semua parameter (*hyperparameter*), metrik evaluasi (F1-Score, Confusion Matrix), dan menyimpan file artefak model (`model.pkl`).
  3. Model yang baru dilatih didaftarkan ke MLflow Model Registry dengan status **Staging** (Model Challenger).

#### **Tahap 3: Model Serving & Deployment (Real-Time Inference)**
- **Cara Kerja**: Model dipaketkan ke dalam FastAPI yang berjalan di dalam Docker Container.
- **Proses**:
  1. FastAPI membuka endpoint REST API (misal: `POST /predict`).
  2. Saat ada data baru dari Open-Meteo API, sistem memanggil endpoint tersebut.
  3. FastAPI memuat model dari MLflow, melakukan inferensi cepat (< 100 ms), dan mengembalikan respons JSON: `{"prediction": "Class 0", "confidence": 0.94}`.
  4. Dalam strategi **Shadow Deployment**, FastAPI mengeksekusi prediksi dari model Champion (Lama) dan model Challenger (Baru) secara beriringan untuk membandingkan akurasi di latar belakang.

#### **Tahap 4: Monitoring, Observability & Feedback Loop**
- **Cara Kerja**: Sistem tidak dilepas begitu saja, melainkan terus diawasi secara *real-time*.
- **Proses**:
  1. Setiap input data dari Open-Meteo API beserta hasil prediksi dari FastAPI dicatat ke dalam *Log Database*.
  2. Setiap hari, Evidently AI membandingkan data 24 jam terakhir dengan data *reference* saat training.
  3. Evidently menghitung statistik Data Drift dan Concept Drift.
  4. **Feedback Loop**: Jika Evidently menemukan drift score > 0.1, Evidently mengirimkan panggilan *Webhook / API Call* ke Apache Airflow untuk mengaktifkan kembali **Tahap 2 (Continuous Training)** secara otomatis.

---

## 🗂️ Data Versioning (DVC)

Dataset mentah (`data/raw/weather_raw_current.csv`) dilacak dengan **DVC**. Git hanya menyimpan file penunjuk kecil `weather_raw_current.csv.dvc` (berisi hash MD5 dan ukuran), sedangkan isi CSV disimpan di cache DVC dan di *remote storage* (folder `~/dvc-store` pada VPS lewat SSH, hanya dapat diakses dari jaringan UB).

### Mengapa versioning data krusial untuk reproduksibilitas model

Buffer data cuaca bersifat bergulir (30 hari / 720 baris): setiap jam data lama bergeser keluar dan data baru masuk, sehingga file yang sama berubah isinya dari waktu ke waktu. Tanpa versioning, model yang dilatih hari ini tidak dapat dilatih ulang persis dengan data yang sama minggu depan, dan hasil eksperimen tidak dapat dibandingkan secara adil. Dengan DVC, setiap model dapat dikaitkan ke satu tag data (misal `dataset-v1.0.0`) sehingga kombinasi **kode (commit Git) + data (hash DVC)** dapat dipulihkan kapan saja.

### Versi data yang tercatat

| Tag | Isi | Baris | Rentang waktu | MD5 (`.dvc`) |
|---|---|---|---|---|
| `dataset-v1.0.0` | Baseline dari LK-04 | 720 | 2026-08-29 s.d. 2026-09-27 | `e42dc025…` |
| `dataset-v2.0.0` | Setelah ingestion ulang (`--buffer-size 1000`) | 936 | 2026-08-29 s.d. 2026-10-06 | `8e441262…` |

### Alur menambah versi data baru

```bash
# 1. Ambil data tambahan (buffer diperbesar agar baris benar-benar bertambah)
python src/ingest_data.py --buffer-size 1000

# 2. Catat versi baru: hash di file .dvc berubah
dvc add data/raw/weather_raw_current.csv
git add data/raw/weather_raw_current.csv.dvc
git commit -m "data: update raw weather dataset v2"
git tag dataset-v2.0.0

# 3. Kirim isi data ke remote DULU, baru kirim pointer ke Git
dvc push --all-tags
git push origin <branch> --tags
```

### Audit dan perbandingan versi

```bash
dvc status                                        # workspace sinkron dengan .dvc?
dvc diff --show-hash dataset-v1.0.0 dataset-v2.0.0  # Modified: e42dc025..8e441262
git diff dataset-v1.0.0 dataset-v2.0.0 -- data/raw/weather_raw_current.csv.dvc
```

### Kembali ke versi tertentu / memulihkan data

```bash
git checkout dataset-v1.0.0 && dvc checkout   # CSV kembali ke 720 baris
git checkout <branch>       && dvc checkout   # CSV kembali ke versi terbaru
# Pada clone baru (jaringan UB): git pull && dvc pull
```

> **Catatan:** `dvc add` dijalankan manual pada momen penting (baseline, sebelum training), bukan setiap jam. Pengambilan data per jam tetap ditangani Airflow di VPS.

---

## 🎯 Kriteria Sukses

### Metrik Teknis
- **F1-Score** > 85%
- **Latency Inference** < 500 ms
- **API Availability** > 99.9%

### Metrik Bisnis
- Pengurangan pengecekan manual **40%**
- Pencegahan kegagalan aktuator
- Downtime kalibrasi mendekati **nol**

---

## 📖 Dokumentasi Akademik

| Dokumen | Deskripsi |
|---|---|
| [LK01](Documentation/LK01/LK01-Muhammad%20Ghazy%20Humaidi-245150200111071.pdf) | Rancangan sistem MLOps lengkap |
| [LK02 - Kriteria Penilaian](Documentation/LK02/LK02-Grading-Criteria.md) | Indikator & kriteria penilaian |
| [LK03 - Perancangan Arsitektur Data](Documentation/LK03/LK03-Perancangan-Arsitektur-Data.md) | Desain pipeline ETL, skema data awal & DVC |
| [LK04 - Ingestion & Preprocessing](Documentation/LK04/LK04-Muhammad%20Ghazy%20Humaidi-245150200111071.pdf) | Implementasi Airflow ingestion, Quality Gate, Anomaly Labeling, & Feature Engineering |
| [LK05 - Data Versioning DVC](Documentation/LK05/LK05-Muhammad%20Ghazy%20Humaidi-245150200111071.pdf) | Pelacakan dataset dengan DVC, simulasi data baru, & audit diff antar versi |
| [GitHub Flow Guide](Documentation/LK02/GITHUB_FLOW.md) | Panduan branching strategy |

---

## 🤝 Informasi Proyek

| | |
|---|---|
| **Nama** | Muhammad Ghazy Humaidi |
| **NIM** | 245150200111071 |
| **Mata Kuliah** | MLOps - TIF-B 2026 |
| **Dosen** | Rizal Setya Perdana, S.Kom., M.Kom., Ph.D. |
| **Program Studi** | Teknik Informatika |
| **Universitas** | Universitas Brawijaya |

---

## 📄 Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE).
