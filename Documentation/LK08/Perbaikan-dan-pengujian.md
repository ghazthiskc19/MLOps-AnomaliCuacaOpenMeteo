# Perbaikan dan pengujian model LK08

Tanggal: 4 November 2026. Perbaikan ini mengikuti
[audit awal](Audit-model-sebelum-otomatisasi.md). Kode dan pengujian lokal telah
dijalankan. Kandidat baru belum memenuhi syarat promosi karena test temporal
v4 tidak memiliki kelas extreme weather. Tidak ada klaim validasi lapangan.

## Hasil pengujian

| Pemeriksaan | Hasil |
|---|---|
| Seluruh pytest | **133 passed**, 0 failed, 0 skipped, 115,29 detik |
| Training tiga kandidat pada DVC v4 | Selesai, exit code 0; run MLflow FINISHED |
| Pemilihan melalui development CV | RF 100 pohon; mean macro F1 gabungan 0,968929 |
| Test temporal v4 | 134/134 sesuai rule label; 8/8 fault dan 126/126 normal benar |
| Test skenario terpisah | 184/184 sesuai rule label, 23 jenis skenario |
| Paket model dipindahkan dan dimuat proses Python baru | Lulus; kode dimuat dari paket ekspor, bukan direktori proyek |
| Registrasi kandidat lolos pada store test sementara | Staging terverifikasi, retry tidak membuat versi duplikat |
| Registrasi kandidat gagal/coverage kurang | Ditolak sebelum pembuatan versi |
| Bukti prediksi berubah / run training gagal | Ditolak |
| Registry proyek LK07 | Byte SQLite tidak berubah; V1 tetap Production |
| `pip check` | Tidak ada dependency rusak |
| Resolusi requirements tanpa memakai installed packages | Dry-run berhasil; ini bukan pengujian runtime pada environment bersih |
| Empat snapshot DVC yang dibutuhkan CI | Cache dan remote R2 sinkron dari mesin lokal |
| YAML workflow | Parsing dan urutan tahap diperiksa; belum dieksekusi di GitHub |

Bukti yang dapat dibaca mesin berada pada [verification.json](verification.json).
Hasil kandidat terdapat pada [summary.json](runs/fix-v2-complete/summary.json),
[validation.json](runs/fix-v2-complete/validation.json),
[prediksi temporal](runs/fix-v2-complete/temporal_predictions.csv), dan
[prediksi skenario](runs/fix-v2-complete/scenario_predictions.csv).
Run ID aktual: `4ca0b98fef004bbfae7c9f4ca61b08c3`.

Paket `runs/fix-v2-complete/model/` dan manifest skenario lengkap disimpan lokal
serta sebagai artefak MLflow, dan diabaikan Git. Workflow mengunggah paket itu
sebagai Actions artifact apabila nanti dijalankan. Manifest berisi 1.840 event
development/CV/test beserta perubahan setiap sel. Event sintetis dapat berbagi
konteks sumber; jumlah tersebut tidak berarti 1.840 kejadian lapangan independen.

## Perubahan perilaku model

Model baru menggunakan kontrak **weather-guarded-v2** dan nama registry
**WeatherAnomalyGuardedRF**. Kontrak lama 37 fitur tetap tersedia untuk artefak
historis. Kontrak baru memiliki 41 fitur, termasuk std suhu 12 jam, humidity
stuck 24 jam, wind zero 48 jam, dan indikator soil waterlogging.

Keputusan hardware fault yang memenuhi aturan dijalankan melalui deterministic
safety guard. Guard dan labeler memakai implementasi pemeriksaan fault yang sama.
Nilai negatif, OOB, night radiation, discordance, spike, dan stuck yang memenuhi
syarat tidak dapat dibatalkan oleh prediksi RF. Ini penguatan kepatuhan aturan,
bukan keberhasilan RF mempelajari seluruh fault tersebut.

RF hanya mempelajari **normal versus extreme weather** dari enam pembacaan sensor
saat ini. Fitur kalender dan rolling tidak dipakai sebagai shortcut untuk target
lingkungan yang aturannya instantaneous. Fitur histori tetap diperlukan guard.
Temperatur hanya dibatasi pada input rumus dew point/VPD agar rumus tidak singular;
raw sensor dan fitur raw tetap mempertahankan nilainya. Guard memeriksa OOB sebelum
raw inference menjalankan rumus tersebut.

Hasil pada holdout yang sama:

| Ukuran | V1 lama | Kandidat baru |
|---|---:|---:|
| Normal benar | 125/126 | 126/126 |
| Fault benar | 7/8 | 8/8 |
| False alarm pada normal | 1/126 | 0/126 |
| Extreme weather yang tersedia | 0 | 0 |
| Macro F1 tiga kelas | 0,622354 | 0,666667 |

Kelas 2 tetap bernilai nol dalam agregasi fixed-label karena tidak tersedia.
Skor tiga kelas tidak diubah menjadi averaging dua kelas agar terlihat lolos.
Pada test skenario, 112 keputusan berasal dari guard dan 72 dari RF (8 normal,
64 extreme). Seluruhnya sesuai pseudo-label pada seed dan skenario tersebut.
Angka 1,0 ini tidak menunjukkan generalisasi ke kerusakan sensor nyata atau
kondisi ekstrem di luar rancangan simulasi.

## Kontrak input

Raw entrypoint baru: `src.weather_model.predict_latest(model, raw_history)`.

- Sensor saat ini missing, nonnumeric, NaN, atau infinity menghasilkan keputusan
  kelas 1 dengan `decision_source=input_quality`.
- Missing/nonfinite pada 49 jam konteks menghasilkan `prediction=null` dan
  `status=insufficient_history`. Nilai tidak diimputasi diam-diam.
- Gap, timestamp duplikat/terbalik, skema salah, atau histori kurang dari 49 baris
  ditolak sebagai kesalahan kontrak.
- Timestamp UTC ekuivalen dan WIB menghasilkan keputusan yang sama.
- Keputusan deterministik tidak diberi confidence RF 1,0. `rf_confidence` hanya
  disediakan untuk jalur RF dan ditandai belum dikalibrasi.

URI model MLflow menerima engineered features sesuai signature. Pengguna yang
memasukkan raw history harus melalui helper di atas; belum ada layanan API di repo.

## Skenario dan pencegahan leakage

Generator baru mencakup 23 jenis: normal, OOB suhu/humidity/soil, tiga jenis nilai
negatif, spike, night radiation, tiga jenis stuck, discordance, soil surge,
soil unresponsive, panas, dingin, dry air, hujan ekstrem, drought, waterlogging,
solar extreme, dan high wind. Nilai injeksi bervariasi dan diatur oleh seed.

Pembuatan skenario memakai salinan konteks sumber 49 jam. Manifest mencatat event
ID, partition, seed, rentang sumber, hash sumber, nilai asli/injeksi, serta label
dan alasan aktual. Skenario yang bertentangan dengan label yang direncanakan
menghasilkan error, tanpa fallback tersembunyi ke jenis fault lain.

Partition dipotong sebelum injeksi. Skenario training fold hanya bersumber dari
rentang training fold; validation dari validation; test dari blok test. Tidak
ada konteks skenario yang melewati batas partition. Seed development, validation,
dan test berbeda. Konfigurasi dipilih dari CV development lalu dibekukan sebelum
final test diprediksi. Skenario test dilaporkan terpisah dari test temporal asli.

Natural holdout tersebut sudah pernah diperiksa dalam audit awal. Karena audit
memengaruhi rancangan perbaikan, hasil sesudah perbaikan adalah regression check
pada data yang dikenal, bukan independent post-development test. Evaluasi akhir
yang lebih kuat masih memerlukan snapshot baru yang belum digunakan merancang
perbaikan, serta label lapangan untuk klaim diagnosis sensor nyata.

## Quality gate dan registry

Kebijakan tersimpan di [configs/lk08.yaml](../../configs/lk08.yaml):

- Macro F1 harus **lebih besar dari 0,85**.
- Setiap kelas harus memiliki minimal 5 observasi evaluasi.
- Recall hardware fault minimal 0,85; false alarm normal maksimal 0,05.
- Tiap jenis skenario membutuhkan support minimal 5 dan agreement minimal 0,80.
- Test temporal dan test skenario harus sama-sama memenuhi kebijakan.

F1 > 0,85 berasal dari LK01. Persyaratan support, recall, false alarm, dan skenario
merupakan pengaman tambahan LK08 yang dinyatakan eksplisit, bukan kutipan threshold
yang sebelumnya ditetapkan di LK01. Minimum lima contoh masih merupakan batas
operasional akademik, bukan jaminan ketelitian statistik atau kesiapan produksi.

Evaluator membedakan `insufficient_coverage`, `failed_performance`, dan `passed`.
Pada kandidat aktual, evaluasi dan registrasi masing-masing menghasilkan exit code
**1 yang diharapkan**, dengan status `insufficient_coverage` untuk kelas 2.
Tidak ada versi kandidat aktual yang diregistrasikan. Penolakan ini tidak diubah
menjadi run sukses hanya agar bukti tampak hijau.

Registrasi melakukan evaluasi ulang, memverifikasi hash bukti/model/kode, mencocokkan
prediksi artefak, serta mengharuskan training run berstatus FINISHED. Model di
tracking store dicocokkan dengan paket yang tervalidasi sebelum registrasi.
Sesudah transisi, stage dan prediksi model registry diperiksa kembali. Pengulangan
registrasi untuk run yang sama menggunakan versi yang ada. Fungsi ini tidak
mempromosikan model ke Production.

Legacy training juga tidak lagi meregistrasikan pemenang secara otomatis.
Registrasi harus diminta dan melewati gate. Stage Staging dipertahankan karena
diminta rubrik; API stage merupakan mekanisme legacy MLflow, sebagaimana dijelaskan
dalam [dokumentasi registry MLflow](https://mlflow.org/docs/latest/ml/model-registry/workflow/).

## Cache dan environment

Ketiga cache preview dibangun ulang dari sumber DVC yang benar. File clean v3
berisi 0 hardware fault, file faults v3 berisi 61 hardware fault, sedangkan cache
current dari raw v4 berisi 0 hardware fault. Rentang dan hash setiap sumber/output
tercatat di [cache-refresh.json](cache-refresh.json).

Preprocessing menulis sidecar metadata sumber dan hash output. Secondary cache
tidak lagi ditimpa secara default. Ini mencegah proses simulated yang tidak
meminta secondary output mengubah file bernama current tanpa penjelasan sumber.

Dependency skops, PyYAML, dan pytest dinyatakan langsung. Devcontainer memakai
Python 3.12; workflow memakai 3.12.3. `pip check` dan dependency resolution dry-run
lulus. Runtime Linux dan instalasi bersih penuh belum diuji dalam pekerjaan lokal
ini. Salinan sumber dan hashes disertakan karena training berjalan pada working
tree yang belum di-commit.

## Otomatisasi dan batas penyelesaian LK08

[Workflow](../../.github/workflows/mlops-automation.yaml) memuat trigger push/PR
ke main, checkout histori/tags, pemulihan DVC, pytest, training, evaluation, Staging,
dan penyimpanan artefak walaupun gate gagal. DVC pull berada sebelum testing karena
sebagian test historis memverifikasi snapshot v3. Workflow menggunakan store
MLflow per-run; paket kandidat portabel dan store tersebut diunggah sebagai bukti,
bukan mengklaim registry terpusat persisten yang melanjutkan nomor versi antar-run.

Remote R2 sinkron untuk empat snapshot yang dibutuhkan. GitHub masih memerlukan
Repository Secrets `R2_ACCESS_KEY_ID` dan `R2_SECRET_ACCESS_KEY`; status Secrets
belum diperiksa atau diubah. Fork PR tidak menerima secrets privat. Tidak ada
commit, push, eksekusi Actions remote, perubahan threshold untuk meloloskan model,
atau perubahan Production dalam pekerjaan ini. Bukti run Actions sukses dan
promosi kandidat aktual masih memerlukan data evaluasi memadai serta konfigurasi
remote yang siap. Perbaikan software lokal sudah diuji; kesiapan produksi belum
dapat dinyatakan.

## Menjalankan ulang

```powershell
.venv/Scripts/python.exe -m pytest tests -q --junitxml=artifacts/lk08-tests.xml
.venv/Scripts/python.exe train.py --output-dir artifacts/lk08-new-run
.venv/Scripts/python.exe scripts/evaluate_candidate.py --candidate-dir artifacts/lk08-new-run
# Hanya setelah gate lolos:
.venv/Scripts/python.exe scripts/register_candidate.py --candidate-dir artifacts/lk08-new-run
```

Gunakan direktori output baru untuk setiap training. Untuk memverifikasi kandidat
yang sudah dibuat dan memastikan penolakan coverage serta Production tetap sama:

```powershell
.venv/Scripts/python.exe scripts/verify_lk08_fixes.py --candidate-dir Documentation/LK08/runs/fix-v2-complete
```

Hasil pengujian 133 test mencakup fixture in-sample sementara untuk menguji jalur
registrasi lolos. Fixture tersebut bukan bukti performa kandidat aktual. Snapshot
audit awal dipertahankan; pengulangan script audit kini menulis ke
`artifacts/lk08-audit/` agar bukti sebelum perbaikan tidak tertimpa.
