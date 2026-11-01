# Hasil scan proyek untuk persiapan LK07

Pemeriksaan dilakukan pada 30 Oktober 2026, pada branch
`feat/lk06-mlflow-training`, dengan HEAD `de457c9`. Implementasi yang tersedia
mencakup ingestion, preprocessing, simulasi data, data versioning, training,
evaluasi, dan model registry. Serving API serta Docker image belum tersedia.
Instruksi resmi LK07 belum ditemukan di repository maupun folder `Tugas`.
Rencana serving dan containerization di bawah bersifat sementara sampai soal
LK07 tersedia.

## Komponen yang tersedia

| Komponen | Lokasi | Hasil pemeriksaan |
|---|---|---|
| Ingestion | `src/0_data_ingestion.py` | Pengambilan Open-Meteo, retry, deduplikasi, dan rolling buffer |
| Preprocessing | `src/1_data_preprocessing.py` | Cleaning, pelabelan aturan tiga kelas, dan feature engineering |
| Object storage | `src/2_r2_sync.py` | Implementasi upload, download, dan daftar snapshot R2; koneksi remote tidak diuji dalam scan ini |
| Simulasi | `src/3_simulate_data.py` | Hardware fault dan data drift sintetis |
| Kontrak data | `src/4_training_data.py` | Validasi raw hourly, warm-up, verifikasi DVC, dan helper `latest_features` |
| Evaluasi | `src/5_model_evaluation.py` | Split temporal dan metrik klasifikasi |
| CLI | `src/6_ingest_data.py`, `src/7_preprocess.py` | Wrapper ingestion dan preprocessing |
| Training | `train.py` | Baseline, tiga konfigurasi RF, walk-forward validation, final test, dan registrasi model |
| Orchestration | `dags/weather_ingestion_dag.py` | DAG ingestion dan sinkronisasi R2; scheduler VPS tidak diperiksa |
| Bukti LK06 | `Documentation/LK06/` | Metadata, metrik, prediksi test, screenshot MLflow, dan laporan |

Nama import stabil disediakan oleh `src/__init__.py`. Contohnya,
`from src.training_data import latest_features` memuat file
`src/4_training_data.py`.

## Verifikasi yang dijalankan

- `.venv/Scripts/python.exe -m unittest discover -s tests -q`:
  **99 test lulus** dalam 22,938 detik.
- `verify_dataset` berhasil memverifikasi snapshot
  `data/simulated/weather_faults_s42.csv` terhadap pointer workspace dan tag
  `dataset-v3.0.0`, dengan MD5 `64d906e7d0086d1814f5e61b359e22fe`.
- Model `models:/WeatherAnomalyRandomForest/1` berhasil dimuat melalui
  `mlflow.sklearn.load_model` dari tracking store SQLite lokal.
- `latest_features` berhasil menghasilkan satu baris berisi 37 fitur dari
  49 observasi terakhir snapshot simulasi. Model menghasilkan kelas `0`,
  dengan probabilitas `[0.98, 0.02, 0.0]` untuk kelas `[0, 1, 2]`.
  Ini merupakan smoke test pemuatan dan inferensi, bukan evaluasi baru.
- Docker CLI versi 27.3.1 tersedia. `docker version` gagal menghubungi
  Docker Desktop Linux engine karena named pipe engine tidak tersedia.
  Build dan eksekusi container belum diuji.

Environment lokal memakai Python 3.12.3, pandas 2.2.0, NumPy 1.26.0,
scikit-learn 1.5.0, MLflow 3.17.1, dan skops 0.16.0. Artefak model juga
mencatat Python 3.12.3. Devcontainer saat ini menggunakan image Python 3.11.
Perbedaan ini perlu diperhitungkan ketika memilih runtime container.

## Kontrak inferensi yang harus dipertahankan

Model menerima 37 fitur numeric hasil feature engineering, sesuai nama dan
urutan dalam `Documentation/LK06/results/best_model_metadata.json`.
Kolom `timestamp`, `anomaly_class`, dan `anomaly_reason` bukan input model.

Jika API menerima data raw, input perlu menyediakan minimal 49 observasi:
48 jam histori dan satu observasi yang akan diprediksi. Alternatifnya,
layanan perlu mengelola histori tersebut secara eksplisit. Tujuh kolom raw
yang diperlukan adalah:

```text
timestamp
temperature_2m_C
humidity_percent
precipitation_mm
soil_moisture
radiation_wm2
wind_speed_kmh
```

Gunakan `src.training_data.latest_features` untuk membentuk fitur.
Timestamp harus berurutan, unik, dan berinterval satu jam. Timestamp tanpa
timezone diartikan sebagai Asia/Jakarta. Nilai sensor harus numeric dan
finite. Histori tidak boleh diisi dengan observasi buatan agar satu baris
input terlihat memenuhi persyaratan.

Pemetaan kelas model adalah `0 = normal`, `1 = hardware fault`, dan
`2 = extreme weather`. Jangan menolak seluruh nilai sensor yang keluar dari
rentang fisik dengan validator API, karena sebagian nilai tersebut memang
merupakan input hardware fault yang ingin diklasifikasikan. Validasi format,
nilai finite, dan kebijakan feature engineering tetap diperlukan.

## Kendala untuk deployment

1. **Artefak belum portabel.** `models/` hanya berisi `.gitkeep`.
   Model tersimpan di `mlruns/`, yang diabaikan Git bersama `mlflow.db`.
   Tracking store dan `MLmodel` lokal memuat path absolut Windows. Menyalin
   SQLite saja ke container tidak memindahkan isi model dan lokasi artefaknya.
2. **Serving belum diimplementasikan.** Tidak ada aplikasi FastAPI,
   `Dockerfile`, atau `.dockerignore` di repository. Bagian deployment,
   shadow inference, monitoring, dan retraining pada README masih rancangan.
3. **Dependency serving belum dinyatakan secara khusus.** FastAPI dan
   Uvicorn tersedia di environment lokal, tetapi tidak tercantum langsung
   pada `requirements.txt`. Artefak menggunakan serialisasi skops dan
   mencatat dependency tersendiri dalam direktori model. Environment
   container perlu diuji dari instalasi bersih.
4. **Klaim evaluasi harus tetap terbatas.** Metadata LK06 mencatat test
   macro F1 0,9039, tetapi recall hardware fault hanya 8/13 atau 61,54%.
   Label berasal dari aturan dan fault sintetis pada satu lokasi/snapshot.
   Hasil ini belum menunjukkan akurasi pada sensor lapangan.

## Urutan pengerjaan setelah soal tersedia

1. Petakan setiap butir rubrik LK07 ke kode, perintah demonstrasi, dan bukti
   yang harus dikumpulkan. Pastikan apakah tugas meminta training dalam
   container, inference, REST API, publikasi image, atau kombinasi tertentu.
2. Jika tugas mencakup model serving, siapkan ekspor model terpilih beserta
   metadata kontrak dan identitas artefaknya. Pastikan model dapat dimuat
   dari direktori lokal tanpa bergantung pada path registry Windows.
3. Jika tugas meminta API, implementasikan pemuatan model saat startup,
   health check, serta prediksi yang memakai kontrak histori LK06.
   Sediakan payload contoh dari snapshot yang sudah ada.
4. Jika tugas meminta container, siapkan Dockerfile dan `.dockerignore`
   dengan dependency yang diperlukan. Kecualikan `.env`, Git, cache DVC,
   virtual environment, dan tracking store lokal dari build context.
5. Uji kesamaan prediksi Python, API, dan container untuk input yang sama.
   Uji juga penolakan input dengan histori kurang, timestamp bermasalah,
   serta sensor nonfinite. Catat latency hasil pengukuran aktual jika diminta.
6. Susun laporan dan screenshot berdasarkan perintah yang benar-benar
   berhasil dijalankan, dengan pemetaan langsung ke rubrik.

## Kondisi workspace

Notebook `notebooks/Proof_Of_Concept_Muhammad_Ghazy_Humaidi.ipynb` sudah
memiliki perubahan sebelum scan dimulai. Notebook tersebut tidak diedit
dalam pekerjaan ini. Scan tidak menjalankan ingestion, regenerasi dataset,
training ulang proyek, atau publikasi image.
