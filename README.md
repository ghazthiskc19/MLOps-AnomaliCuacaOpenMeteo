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
├── data/
│   ├── raw/                    # Data mentah dari Open-Meteo API
│   └── processed/              # Data yang sudah diproses & dilabel
├── models/                     # Model artifacts (.pkl, .joblib)
├── src/                        # Source code Python utama
│   ├── __init__.py
│   └── data_ingestion.py       # Modul ingestion data dari API
├── notebooks/                  # Jupyter notebooks (EDA, PoC, eksperimen)
├── tests/                      # Unit tests
├── docs/                       # Dokumentasi teknis tambahan
├── configs/                    # File konfigurasi (YAML, JSON)
├── Documentation/              # Dokumen akademik (LK01, LK02, dll)
├── .devcontainer/              # GitHub Codespaces configuration
│   └── devcontainer.json
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies
├── LICENSE                     # MIT License
└── README.md                   # Dokumentasi ini
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

### Menjalankan Data Ingestion

```bash
# Jalankan script data ingestion
python src/data_ingestion.py

# Atau buka notebook di Jupyter
jupyter notebook notebooks/
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

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐    ┌────────────────┐
│  Tahap 1:   │    │    Tahap 2:      │    │    Tahap 3:     │    │   Tahap 4:     │
│  Data       │───▶│  Continuous      │───▶│  Model Serving  │───▶│  Monitoring &  │
│  Ingestion  │    │  Training        │    │  & Deployment   │    │  Feedback Loop │
│  & DVC      │    │  & MLflow        │    │  (FastAPI)      │    │  (Evidently)   │
└─────────────┘    └──────────────────┘    └─────────────────┘    └────────────────┘
     ▲                                                                    │
     └────────────────────── Retraining Trigger ◄─────────────────────────┘
```

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
| [LK01](Documentation/) | Rancangan sistem MLOps lengkap |
| [LK02 - Kriteria Penilaian](Documentation/LK02-Grading-Criteria.md) | Indikator & kriteria penilaian |
| [GitHub Flow Guide](Documentation/GITHUB_FLOW.md) | Panduan branching strategy |

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
