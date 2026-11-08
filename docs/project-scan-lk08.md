# Hasil scan proyek untuk LK08

Pemeriksaan dilakukan pada 4 November 2026 pada branch
`feat/lk06-mlflow-training`, HEAD `bef00d4`. Working tree bersih sebelum
pemeriksaan. Ruang lingkup tahap ini adalah inventarisasi kode, pemeriksaan
baseline lokal, dan pemetaan kebutuhan LK08. Implementasi workflow belum dibuat.

## Hasil verifikasi

- `rtk test .venv/Scripts/python.exe -m unittest discover -s tests -q`:
  99 test lulus dalam 54,355 detik. Terdapat tujuh file test.
- `.venv/Scripts/python.exe -m pip check`: tidak ada dependency yang rusak.
- Python lokal 3.12.3; MLflow 3.17.1; DVC 3.67.1;
  scikit-learn 1.5.0; skops 0.16.0; PyYAML 6.0.3.
- `pytest` belum tersedia di virtual environment dan belum tercantum pada
  `requirements.txt`. Test yang ada menggunakan `unittest`; kompatibilitas
  eksekusi melalui pytest perlu diverifikasi setelah dependency ditambahkan.
- Verifikasi isi dataset, pointer DVC workspace, dan pointer pada Git tag berhasil:

| Snapshot | Tag | MD5 |
|---|---|---|
| `data/simulated/weather_faults_s42.csv` | `dataset-v3.0.0` | `64d906e7d0086d1814f5e61b359e22fe` |
| `data/simulated/weather_lk07_faults_s42.csv` | `dataset-v4.0.0` | `e37325821734e2576273e5715b6a6c88` |

Verifikasi tersebut memakai `src.training_data.verify_dataset`, tanpa mengunduh
ulang data. Ketersediaan objek pada remote R2 belum diuji. Keberadaan nama kunci
kredensial lokal diperiksa tanpa menampilkan nilainya.

## Pemetaan kebutuhan LK08

| Kebutuhan | Kondisi saat scan | Pekerjaan yang diperlukan |
|---|---|---|
| Push branch utama atau pull request memicu pipeline | Tidak ada workflow GitHub Actions yang dilacak Git | Buat `.github/workflows/mlops-automation.yaml` |
| Automated testing memakai pytest | 99 test unittest lulus | Tambahkan pytest dan verifikasi seluruh test dari runner bersih |
| Training melalui `train.py` dengan DVC | Training, fitur, split temporal, dan verifikasi hash sudah tersedia | Konfigurasikan DVC pull, checkout tags, dependency, input, dan tag dataset |
| Evaluasi terhadap threshold LK01 | Metrik tersedia; belum ada quality gate | Tambahkan evaluasi yang menghentikan pipeline jika hasil tidak memenuhi syarat |
| Registrasi otomatis ke Staging setelah lolos | Training langsung meregistrasikan kandidat; belum menjalankan gate LK08 | Pisahkan keputusan registrasi dari training dan transisikan model tervalidasi ke Staging |
| Simulasi perubahan kode | Override `--n-estimators` tersedia | Commit perubahan kecil yang dapat ditelusuri, lalu simpan URL run aktual |
| Refleksi PDF | Belum ada artefak LK08 | Susun refleksi berdasarkan implementasi dan bukti eksekusi aktual |

## Threshold dan kondisi evaluasi

[Laporan LK01](../Documentation/LK01/LK01-Muhammad%20Ghazy%20Humaidi-245150200111071.pdf),
bagian 5.1 pada halaman 7, menetapkan **F1-Score > 85%**. Bagian 4.2
menetapkan F1 di bawah 0,80 sebagai pemicu retraining. Kedua angka tersebut
memiliki fungsi berbeda. LK01 tidak menyebut averaging F1 secara eksplisit;
pemakaian macro F1 untuk LK08 perlu dinyatakan sebagai keputusan implementasi.

Hasil tersimpan LK06 memiliki test macro F1 0,903905, dengan support ketiga
kelas. Hasil tersimpan LK07 memiliki test macro F1 0,566179, accuracy 0,970149,
dan support kelas extreme weather sebesar nol. Dengan kebijakan macro F1
fixed labels `[0, 1, 2]` pada kode saat ini, kelas tanpa support memberikan
kontribusi F1 nol. Nilai tersebut tidak boleh diubah menjadi averaging kelas
yang hadir hanya untuk meloloskan gate.

Snapshot terbaru yang ditemukan adalah v4 dari LK07. Default `train.py` masih
mengarah ke v3. Menjalankan default tersebut tanpa penjelasan tidak membuktikan
training menggunakan snapshot terbaru. Kebutuhan bukti run sukses harus
diselesaikan melalui kebijakan evaluasi dan data yang dapat dipertanggungjawabkan;
threshold tidak boleh diturunkan berdasarkan hasil holdout yang sudah dilihat.
Hasil scan ini belum mencakup training ulang atau pengukuran performa baru.

## Ketergantungan pada environment lokal

1. DVC menggunakan remote R2 berbasis S3. Runner memerlukan kredensial dari
   GitHub Secrets dan objek dataset yang sudah tersedia di remote. Koneksi SSH
   cadangan menuju alamat privat VPS bukan jalur yang dapat diasumsikan tersedia
   dari GitHub-hosted runner. Test verifikasi dataset saat ini juga memerlukan
   snapshot v3 dan Git tag terkait, sehingga DVC pull perlu dilakukan sebelum
   keseluruhan test suite dapat berjalan.
2. `train.py` memverifikasi pointer terhadap Git tag. Checkout perlu mengambil
   tags dan histori yang diperlukan; clone dangkal default perlu disesuaikan.
3. `mlflow.db` dan `mlruns/` diabaikan Git. Training default membuat backend
   SQLite dan artefak lokal dengan path absolut. Registry yang dibuat pada
   runner sementara memerlukan strategi penyimpanan metadata serta artefak.
   Menyimpan SQLite saja tidak menjamin model dapat dipulihkan di mesin lain.
   Pilihan backend persisten atau paket bukti registry per run perlu dinyatakan
   sebelum workflow dianggap selesai.
4. `requirements.txt` belum menyatakan `skops` secara langsung, sedangkan
   ekspor model menggunakan format tersebut. PyYAML juga diimpor langsung tetapi
   saat ini diperoleh secara transitif. Environment lokal yang sehat belum
   membuktikan instalasi bersih pada runner sehat.
5. Devcontainer memakai Python 3.11, sedangkan environment dan artefak lokal
   menggunakan Python 3.12.3. Runtime CI harus dipilih dan diuji secara eksplisit.
6. GitHub CLI `gh` tidak ditemukan melalui PATH saat scan. Git remote menunjuk
   `https://github.com/ghazthiskc19/MLOps-AnomaliCuacaOpenMeteo.git`.
   Status Secrets, default branch remote, dan akses Actions belum diperiksa.

## Urutan implementasi

1. Tetapkan konfigurasi input snapshot terbaru, averaging metrik, dan batas
   F1 > 0,85. Dokumentasikan penanganan kelas tanpa support. Siapkan data evaluasi
   yang memadai tanpa menyesuaikan threshold berdasarkan hasil test.
2. Tambahkan dependency CI yang diperlukan dan buktikan instalasi bersih.
   Jalankan pytest dengan snapshot dan tags yang dibutuhkan test.
3. Tambahkan jalur training tanpa registrasi otomatis. Simpan kandidat, metrik,
   serta identitas commit dan data untuk tahap evaluasi.
4. Tambahkan quality gate dengan perilaku gagal untuk metrik hilang, nonfinite,
   atau di bawah batas. Uji bahwa kandidat gagal tidak menghasilkan registrasi
   Staging. Model lolos baru didaftarkan dan statusnya diperiksa kembali.
5. Susun workflow berurutan: persiapan data, testing, training, evaluasi,
   registrasi Staging. Simpan log, metrik, dan bukti registry sesuai strategi
   persistensi yang dipilih. Atur penanganan secrets pada pull request secara
   eksplisit.
6. Jalankan simulasi perubahan kode melalui commit dan push/PR. Catat commit,
   URL Actions, hash dataset, metrik, serta versi dan stage model aktual.
7. Buat refleksi PDF mengenai silent failures berdasarkan bukti tersebut.

Scan ini tidak menjalankan ingestion, mengganti dataset, melatih ulang model,
mengubah registry proyek, membuat commit, atau melakukan push. Test round-trip
MLflow menggunakan backend in-memory dan direktori artefak sementara.
