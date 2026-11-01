# LK07 Model Registry Versioning dan Kesiapan Inferensi

Model aktif untuk simulasi inferensi adalah **WeatherAnomalyRandomForest versi 1**,
dengan stage **Production** dan URI:

```text
models:/WeatherAnomalyRandomForest/Production
```

V1 dipertahankan karena lebih baik daripada V2 pada 134 observasi holdout LK07
yang sama. Ini merupakan keputusan untuk simulasi akademik, dengan label aturan
dan fault sintetis; belum merupakan persetujuan penggunaan pada sensor lapangan.

## Riwayat versi

| Versi | Jumlah pohon | Dataset training | Stage akhir | Keterangan |
|---|---:|---|---|---|
| V1 | 100 | `dataset-v3.0.0` | Production | Model terbaik LK06; dipertahankan setelah perbandingan LK07 |
| V2 | 150 | `dataset-v4.0.0` | None | Kandidat baru, memakai pembaruan dataset dari pipeline Airflow dan R2 |
| V3 | 150 | `dataset-v4.0.0` | None | Registrasi ulang artefak V2; run ID dan source model URI identik |

V1 berasal dari run `044402f101154e1c8c295161c0542077`.
V2 dan V3 berasal dari run `1e6c8d1bb00940f8a2e5212a11bd68af`.
Parameter V1/V2 lainnya: `max_depth=None`, `min_samples_leaf=1`,
`class_weight=None`, `random_state=42`, dan `n_jobs=-1`.

## Dasar pemilihan Production

Holdout bersama berlangsung pada 27 Oktober 2026 pukul 04.00 sampai
1 November 2026 pukul 17.00 WIB. Kedua model sudah menyelesaikan periode
fitting sebelum awal holdout tersebut. V1 selesai fitting pada 14 Oktober
pukul 08.00 WIB; V2 pada 27 Oktober pukul 03.00 WIB.

| Metrik pada holdout yang sama | V1 | V2 |
|---|---:|---:|
| Accuracy | 0,9851 | 0,9701 |
| Macro F1 dengan label tetap 0/1/2 | 0,6224 | 0,5662 |
| Balanced accuracy | 0,9335 | 0,8085 |
| Recall hardware fault | 0,8750 (7/8) | 0,6250 (5/8) |

Holdout berisi 126 normal, 8 hardware fault, dan **0 extreme weather**.
Macro F1 memasukkan ketiga label; kontribusi kelas tanpa contoh/prediksi adalah
nol. Balanced accuracy hanya merata-ratakan recall kelas yang memiliki support.
Kemampuan mendeteksi extreme weather belum dapat dinilai pada periode ini.

Skor test LK06 sebesar 0,9039 dan skor test LK07 sebesar 0,5662 berasal dari
dataset berbeda dan tidak dipakai sebagai perbandingan langsung. Kandidat V2
dipilih dari tiga konfigurasi 150 pohon melalui CV development; hasil holdout
bersama kemudian digunakan untuk keputusan registry. Karena holdout itu sudah
mempengaruhi keputusan deployment, belum ada test independen setelah keputusan.
Perubahan dataset dan jumlah pohon dilakukan bersamaan sehingga selisih skor
tidak dapat dikaitkan hanya dengan `n_estimators`.

## Transisi stage melalui UI

Pada MLflow 3.17.1, tampilan lama diaktifkan dengan mematikan **New model
registry UI**. Pada halaman Version 1, dropdown stage dipakai untuk mengubah
None menjadi Staging, kemudian Production. Bukti asli tersedia pada
`screenshots/08-v1-staging.png` dan `screenshots/09-v1-production.png`.

Screenshot `11-v1-none-intermediate.png` merekam perubahan sementara kembali
ke None setelah promosi awal. Screenshot ini disimpan sebagai arsip dan tidak
dipakai sebagai bukti kondisi akhir. Daftar versi pada
`07-registry-versions.png` serta verifikasi API terakhir menunjukkan V1
Production, sementara V2 dan V3 None. Stage di sini adalah stage registry,
bukan alias ataupun bukti tersedianya layanan API produksi.

## Lineage dan metadata DVC

Metadata model aktif berada di `production_model.yaml`, dengan pointer yang
disimpan Git pada [production_model.yaml.dvc](production_model.yaml.dvc).
File tersebut menghubungkan identitas registry, run ID, hash artefak model,
parameter, kontrak fitur, dataset training V1, dan dataset evaluasi LK07.

```powershell
# Pulihkan metadata yang dibekukan melalui DVC
dvc pull Documentation/LK07/production_model.yaml.dvc

# Periksa apakah metadata masih cocok dengan pointer
dvc status Documentation/LK07/production_model.yaml.dvc
```

Dataset training V1: `data/simulated/weather_faults_s42.csv`, tag
`dataset-v3.0.0`, MD5 `64d906e7d0086d1814f5e61b359e22fe`.
Dataset training V2/evaluasi bersama: `data/simulated/weather_lk07_faults_s42.csv`,
tag `dataset-v4.0.0`, MD5 `e37325821734e2576273e5715b6a6c88`.

Snapshot baru berasal dari download object R2 hasil ingestion Airflow, kemudian
disaring untuk jam yang sudah lewat dan diberi fault sintetis dengan seed 42.
Pipeline memanfaatkan data model cuaca Open-Meteo, bukan pengukuran sensor fisik.

Metadata DVC merupakan referensi lineage. File ini tidak mencadangkan seluruh
tracking store SQLite dan model di `mlruns/`; pemuatan model memerlukan store
beserta artefak yang cocok. Nomor versi registry berlaku pada store ini, bukan
nomor yang dijamin sama ketika training diulang di mesin lain.

## Verifikasi inferensi

Jalankan dari root repository dalam environment proyek yang berisi MLflow
dan artefak LK06/LK07:

```powershell
python scripts/verify_lk07_registry.py
```

Script tidak melatih, meregistrasikan, atau mengubah stage model. Script
memeriksa satu Production pada V1, memverifikasi hash DVC dataset, membandingkan
kedua model pada holdout yang sama, lalu memuat URI `/Production` menggunakan
`mlflow.pyfunc.load_model`. Prediksi Production diverifikasi identik dengan
V1 langsung pada seluruh 134 baris holdout. Prediksi V2 juga diverifikasi sama
dengan prediksi yang disimpan saat training.

Contoh observasi terakhir menghasilkan kelas `[0]` dengan input `(1, 37)`.
Input disiapkan oleh `src.training_data.latest_features` dari 49 observasi
hourly berurutan. Model menerima 37 fitur float64, bukan satu baris raw.
Timestamp tanpa timezone diartikan sebagai Asia/Jakarta. Gap, duplikasi,
nilai nonnumeric dan nonfinite ditolak oleh kontrak data.

Eksekusi script memperbarui `production_model.yaml` dan bukti verifikasi.
Jika snapshot itu sengaja diperbarui, jalankan kembali `dvc add` serta
`dvc push` pada pointer metadata dan simpan perubahan pointer di Git.

## Reproduksi training kandidat

Perintah yang digunakan untuk V2:

```powershell
python train.py --input-path data/simulated/weather_lk07_faults_s42.csv --dataset-tag dataset-v4.0.0 --n-estimators 150 --experiment-name LK07-Weather-RandomForest --model-name WeatherAnomalyRandomForest --output-dir Documentation/LK07/results
```

Menjalankan training lagi membuat versi registry baru. Untuk memeriksa hasil
yang sudah ada, gunakan script verifikasi. UI dapat dijalankan dengan:

```powershell
python -m mlflow ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5000 --workers 1
```

## Berkas pengumpulan dan bukti

- [Laporan PDF](LK07-Muhammad%20Ghazy%20Humaidi-245150200111071.pdf).
- `production_model.yaml` dan pointer `.dvc` untuk metadata aktif.
- `results/registry_verification.json` dan `.txt`: snapshot registry, pemeriksaan
  inferensi, serta hasil perbandingan yang benar-benar dijalankan.
- `results/version_comparison.csv` dan `common_holdout_predictions.csv`:
  metrik dan prediksi kedua versi pada timestamp yang sama.
- `results/best_model_metadata.json`: metadata kandidat V2 hasil training;
  identitas model Production tetap merujuk `production_model.yaml`.
- [Manifest screenshot](screenshot-manifest.json): nama asli, nama baru, dan
  SHA256 untuk membuktikan isi screenshot tidak diubah.

| Bukti | Isi |
|---|---|
| `01-v1-run-metrics.png` | Metrik historis test LK06 |
| `02-v1-source-run.png` | Hubungan run kandidat dengan V1 |
| `03-v1-parameters.png` | Parameter 100 pohon |
| `04-v2-run-metrics.png` | Metrik test LK07 dan identitas dataset |
| `05-v2-registry-detail.png` | Detail registrasi V2 |
| `06-v2-parameters.png` | Parameter 150 pohon |
| `07-registry-versions.png` | Daftar V1/V2/V3 dan stage akhir |
| `08-v1-staging.png` | V1 pada Staging |
| `09-v1-production.png` | V1 pada Production |
| `10-production-inference.png` | Pemanggilan `/Production` dan hasil prediksi |
| `11-v1-none-intermediate.png` | Arsip status sementara setelah promosi awal |

Seluruh screenshot berada di `screenshots/`. PDF menampilkan bukti terpilih;
gambar asli tetap tersedia pada resolusi penuh.

Untuk membangun ulang PDF dari bukti yang tersedia:

```powershell
pip install -r requirements-report.txt
python scripts/generate_lk07_report.py
```

Generator PDF memakai ReportLab dan font Times New Roman pada Windows.
Render PNG untuk pemeriksaan layout berada di `.pdf-review/` dan diabaikan Git.
Pemeriksaan akhir: 99 unit/integration test lulus; hasil inferensi Production,
kesamaan prediksi, identitas dataset, dan sinkronisasi metadata DVC diverifikasi.
Paket pengumpulan ZIP tersedia di `dist/LK07-Muhammad Ghazy Humaidi-245150200111071.zip`
dari root repo; isinya mencakup PDF, README, metadata YAML/pointer, hasil, screenshot,
dan script reproduksi. SQLite serta artefak model lokal tidak dimasukkan.

## Referensi

- [MLflow Model Registry workflows](https://www.mlflow.org/docs/latest/ml/model-registry/workflow/).
- [MLflow Model Registry concepts](https://www.mlflow.org/docs/latest/ml/model-registry/).
- [DVC add](https://dvc.org/doc/command-reference/add).
- [DVC push](https://dvc.org/doc/command-reference/push).
