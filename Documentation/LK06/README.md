# LK06: Random Forest dan MLflow

Implementasi yang disetujui pada 19 Oktober 2026. Audit dan notebook EDA
mendokumentasikan keadaan sebelum training; hasil implementasi ada di
`results/summary.json` dan `results/best_model_metadata.json`.

## Nomor file source

| File fisik | Peran |
|---|---|
| `src/0_data_ingestion.py` | Modul pengambilan data Open-Meteo |
| `src/1_data_preprocessing.py` | Cleaning, pseudo-label dan feature engineering |
| `src/2_r2_sync.py` | Upload/download snapshot ke Cloudflare R2 |
| `src/3_simulate_data.py` | Injeksi fault dan simulasi drift |
| `src/4_training_data.py` | Validasi dataset/waktu dan kontrak histori training |
| `src/5_model_evaluation.py` | Split temporal dan metrik klasifikasi |
| `src/6_ingest_data.py` | Wrapper CLI untuk modul ingestion nomor 0 |
| `src/7_preprocess.py` | Wrapper CLI untuk modul preprocessing nomor 1 |

`__init__.py` tetap memakai nama khusus Python. File bernomor dipetakan secara
lazy ke nama modul yang valid, sehingga `from src.training_data import
latest_features` dan import lama tetap bekerja. Import ingestion tidak ikut
memuat sklearn/MLflow. CLI dan DAG memakai nama file fisik bernomor.

Nomor adalah urutan membaca komponen, bukan perintah menjalankan semuanya.
Alur training memakai input hasil ingestion/sinkronisasi, opsional simulasi,
kemudian preprocessing/validasi, training di `train.py`, dan evaluasi. Dua
wrapper memanggil modul yang sama, bukan proses tambahan setelah evaluasi.

Rename tidak menjalankan training ulang atau mengganti registry versi 1.
Hash/nama source pada metadata dan laporan lama tetap bukti saat eksperimen
tersebut dibuat. Eksekusi training berikutnya mencatat path bernomor terbaru.

## Menjalankan

Jalankan dari root repository pada environment Python proyek:

```bash
pip install -r requirements.txt
dvc pull
python -m unittest discover tests
python train.py
python -m mlflow ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5000 --workers 1
```

Buka `http://127.0.0.1:5000`, pilih **Model training**, lalu eksperimen
`LK06-Weather-RandomForest`. Satu session berisi baseline normal dan tiga
candidate RF. Pilih ketiga run RF untuk Compare; metrik pemilihan adalah
`cv_val_f1_macro_mean`, bukan test. Detail registry ada di Models, nama
`WeatherAnomalyRandomForest`. Filter berdasarkan session run untuk membedakan
eksekusi berulang. Run gagal tetap disimpan sebagai audit, bukan dihapus.

`python train.py --help` menampilkan opsi sumber/tag, lokasi tracking,
output, nama eksperimen/model dan seed. Perintah default membaca snapshot
v3; tidak melakukan ingestion, simulator, checkout, commit atau push.
Kalau workspace sudah memakai dataset baru, jangan diam-diam memakai tag v3:
gunakan pointer/tag yang benar atau pulihkan snapshot pada workspace terpisah.

Default SQLite `mlflow.db` dan artefak `mlruns/` diabaikan Git. Keduanya
**lokal pada mesin ini**; commit kode saja tidak memindahkan dashboard/model
ke Codespaces. Jalankan training di Codespaces atau pindahkan tracking store
beserta artefaknya secara konsisten. File JSON/CSV/PNG/PDF laporan portable.
Eksekusi ulang membuat session dan versi registry baru, bukan mengganti versi 1.

## Kontrak evaluasi final

- Sumber: `data/simulated/weather_faults_s42.csv`, tag `dataset-v3.0.0`;
  MD5 diverifikasi terhadap pointer workspace dan pointer pada tag.
- Naive timestamp berarti WIB; timestamp aware dinormalisasi ke WIB.
  Skema raw harus tepat tujuh kolom, finite, unik, terurut dan hourly.
  Gap, duplikasi, missing/inf atau fitur turunan nonfinite menghentikan proses.
- Pipeline LK04 dipakai ulang tanpa mengubah dataset atau rumusnya. Setelah
  engineering ada 37 input numerik; target, alasan dan timestamp dikeluarkan.
- 48 jam awal disimpan sebagai konteks, tidak di-fit atau di-score. Tersisa
  672 observasi; 537 development dan 135 test terakhir. Konteks asli sebelum
  setiap validation/test dipertahankan untuk fitur kausal.
- Tiga fold expanding pada development, validation masing-masing 134 jam.
  Semua train mempunyai tiga kelas. Dukungan kelas validation dicatat,
  termasuk fold dengan hanya tiga contoh ekstrem.
- Semua konfigurasi memakai fold, fitur dan seed model 42 yang sama.
  Tidak ada SMOTE, stratified random split, resampling holdout, atau clipping
  sinyal fault. Balanced weights dihitung dari train fold saja.
- Pilih mean macro F1 tertinggi, lalu std terendah dan urutan konfigurasi
  sebagai tie-break deterministik. Laporkan skor tiap fold dan pooled OOF
  terpisah; keduanya bukan angka yang sama.
- Artefak tiap kandidat di-fit pada seluruh development. Pemenang yang sudah
  di-fit ini dipakai untuk final test; tidak ada tuning/refit memakai test.
- Signature/input example, feature contract, source code/hash, dependency,
  pointer DVC, split, class weights dan artefak evaluasi disimpan di MLflow.
  Pemuatan ulang sklearn, pyfunc dan registry harus memberi prediksi identik.

## Hasil eksekusi

| Konfigurasi | Mean CV macro F1 | Std antar fold |
|---|---:|---:|
| Selalu normal | 0.3126 | 0.0017 |
| RF tanpa class weighting | **0.8122** | 0.0567 |
| RF balanced | 0.7490 | 0.0632 |
| RF balanced, max_depth=10 | 0.7490 | 0.0632 |

RF terpilih: 100 pohon, `max_depth=None`, `min_samples_leaf=1`,
`class_weight=None`, `random_state=42`. Class weighting tidak meningkatkan
hasil pada protokol/snapshot ini; hasil identik dua konfigurasi balanced
tetap dilaporkan. Skor train fold RF 1.0, sehingga gap generalisasi juga ada.

Final test: accuracy 0.9630, macro F1 0.9039, balanced accuracy 0.8718.
Recall hardware fault hanya **8/13 = 0.6154**: lima fault terlewat. Angka
accuracy atau macro F1 tinggi tidak meniadakan kelemahan ini. Temuan test
tidak digunakan untuk mengganti parameter eksperimen yang dilaporkan.

Model terdaftar sebagai kandidat akademik, bukan model yang tervalidasi di
lapangan. Label berasal dari aturan, fault sintetis, satu lokasi/snapshot,
dan sebagian subtipe tidak ada di holdout. Labeler tetap tidak otomatis
beradaptasi musim. EDA sudah memeriksa support test sehingga bukan blind
test sepenuhnya. Endpoint forecast dapat memuat revisi/prakiraan.

## Inferensi dengan histori

Registry menerima **37 fitur hasil engineering**, bukan satu baris raw JSON.
Gunakan helper yang sama dengan training untuk menyiapkan observasi terbaru:

```python
import json
from pathlib import Path
import mlflow
import mlflow.sklearn
import pandas as pd
from src.training_data import latest_features

metadata = json.loads(Path("Documentation/LK06/results/best_model_metadata.json").read_text())
mlflow.set_tracking_uri("sqlite:///mlflow.db")
model = mlflow.sklearn.load_model(metadata["registry_uri"])
history = pd.read_csv("data/simulated/weather_faults_s42.csv").iloc[-49:]
features = latest_features(history, metadata["feature_contract"]["feature_names"])
prediction = model.predict(features)
```

Sediakan minimal 49 observasi hourly nyata (48 jam sebelumnya + observasi
saat ini). Helper menolak satu baris tanpa riwayat. Jangan mengisi histori
palsu atau menerapkan kebijakan missing yang berbeda saat serving.

## Bukti dan laporan

- `results/summary.json`: session, run ID, seluruh skor, split, provenance,
  reload checks dan registry URI yang benar-benar dihasilkan.
- `results/best_model_metadata.json`: parameter terpilih, fit scope dan
  kontrak input untuk tahap deployment berikutnya.
- `results/test_*`: prediksi per timestamp, metrik, report dan confusion matrix.
- `screenshots/`: tampilan MLflow UI asli, bukan grafik yang menyerupai UI.
- Laporan PDF dibuat dengan `python scripts/generate_lk06_report.py` setelah
  screenshot tersedia; install `requirements-report.txt` untuk generator.
  Generator mengikuti template dan helper LK04/LK05: Times New Roman 12 pt,
  spasi isi 1.15, judul bab 13.5 pt bold, tabel 9.5/10 pt, serta cover/logo
  dan margin yang sama. DOCX ikut disimpan; ekspor PDF memakai Microsoft Word
  melalui COM pada Windows, seperti generator laporan sebelumnya.

Satu run awal gagal pada serialisasi skops karena tipe internal pohon perlu
dicantumkan eksplisit. Export sekarang memakai skops dengan daftar sempit
`sklearn.tree._tree.Tree` untuk model yang baru dilatih oleh proses sendiri;
regression test memverifikasi round-trip. Run gagal tidak digunakan dalam
perbandingan model final.
