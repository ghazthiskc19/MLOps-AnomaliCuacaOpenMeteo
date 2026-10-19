# Catatan dan kontrak sebelum implementasi train.py

Catatan diskusi 19 Oktober 2026. Pengguna kemudian menyetujui implementasi;
hasil penerapannya dijelaskan di [README LK06](README.md).
Random Forest sudah dipilih. Rekomendasi evaluasi terbaru adalah menyisihkan
20% waktu terakhir sebagai test, lalu walk-forward pada 80% pengembangan.
Ini memperinci alternatif pada laporan audit; 60/20/20 tetap opsi sederhana.
Tidak ada training model atau perubahan sumber DVC saat memeriksa kasus ini.

## Temuan yang direproduksi langsung pada pipeline

| Kasus | Hasil pemeriksaan di memori | Implikasi |
|---|---|---|
| Satu timestamp hilang sebelum baris ke-24 | `diff(24)` membandingkan observasi yang berjarak 25 jam | Nama fitur berbasis jam hanya benar jika data tepat satu baris per jam. |
| Suhu raw diganti menjadi -237.3 C pada satu baris | Raw tetap finite, label menjadi kelas 1, tetapi `dew_point_C` menjadi nonfinite | Validasi angka harus dilakukan sesudah feature engineering juga. |
| Baris indeks 50 diproses sendirian vs dengan 50 baris sebelumnya | `temp_diff_1h`: 0 vs 0.2; `temp_diff_24h`: 0 vs 1.1; rolling mean 24 jam: 19.8 vs 23.5667 | Model berbasis fitur temporal memerlukan konteks riwayat atau fitur yang dihitung upstream dengan kontrak sama. |
| Timestamp WIB dikonversi ke UTC sebelum pipeline | Fitur `hour` menjadi 17 untuk observasi pukul 00 WIB | Labeler mengonversi ke WIB, tetapi kalender feature engineer mengikuti timezone input. Normalisasi harus konsisten. |

Keempat pemeriksaan dilakukan tanpa menulis ulang CSV sumber. Dataset v3
sendiri kontinu per jam dan tidak memiliki NaN/inf pada 37 kandidat fitur;
kasus di atas menunjukkan perilaku pada input yang berbeda.

## Kontrak wajib yang direkomendasikan

1. **Identitas data.** Training tidak memanggil ingestion atau simulator secara
   otomatis. Gunakan sumber DVC eksplisit; periksa hash dan tag, bangun fitur
   ulang, lalu log hash raw/simulated, kode preprocessing, seed, dan versi
   dependency. Jangan mempercayai cache processed lama atau nama filenya.

2. **Sumbu waktu.** Normalisasi ke Asia/Jakarta sebelum label dan fitur.
   Periksa timestamp valid, unik, terurut, dan interval satu jam. Untuk LK06,
   gap atau konflik duplikasi sebaiknya menghentikan training dengan pesan
   jelas, bukan diteruskan diam-diam atau diisi dari masa depan. Perluasan ke
   data tidak teratur membutuhkan keputusan terpisah tentang gap dan window.

3. **Riwayat dan warm-up.** Fitur diff 24 jam dan aturan stuck hingga 48 jam
   membutuhkan konteks. `fillna(0)` pada awal seri bukan bukti tidak ada
   perubahan. Kebijakan warm-up harus sama saat training dan inference serta
   jumlah baris yang dinilai harus dicatat. Jika warm-up dikeluarkan dari
   fitting/scoring, hitung ulang batas split dan dukungan kelas. Jangan
   mengulang warm-up seolah-olah histori kosong pada setiap batas fold;
   konteks masa lalu yang benar-benar tersedia boleh dipakai.

4. **Validitas nilai.** Jangan `dropna()` atau clipping semua sensor secara
   global: nilai hilang dan out-of-range bisa menjadi sinyal fault. Bedakan
   missing pada sensor dari NaN/inf yang muncul karena rumus turunan. Untuk
   snapshot LK06 saat ini, pemeriksaan finite sesudah feature engineering
   harus lolos; perubahan karakteristik input harus menghasilkan diagnosis
   eksplisit sebelum model dilatih. Dukungan missing pada produksi perlu
   kebijakan tersendiri, bukan ditutupi dengan angka nol.

5. **Label dan cakupan.** Target adalah pseudo-label aturan, kelas 1 mempunyai
   prioritas atas kelas 2, dan satu baris hanya menyimpan satu kelas/alasan.
   Fault dan kondisi ekstrem yang bersamaan dapat berakhir sebagai kelas 1.
   Jumlah label tidak sama dengan jumlah injeksi. Target stuck adalah deteksi
   setelah histori cukup, bukan otomatis sejak jam pertama injeksi. Jangan
   menyatakan evaluasi per kelas mencakup seluruh subtipe atau sensor nyata.

6. **Split dan kebocoran.** Simpan timestamp/indeks batas fold. Semua kandidat
   memakai fold identik. Tidak melakukan shuffle lintas waktu, stratifikasi
   baris acak, balancing validation/test, atau penggabungan raw dan simulated
   yang menaruh konteks waktu sama di bagian berbeda. Konteks observasi saat
   ini sah untuk klasifikasi jam saat ini; forecasting memerlukan penyusunan
   target dan pemisahan yang berbeda. Gap antar partisi harus didasarkan pada
   horizon/kejadian yang hendak diuji, bukan otomatis karena ada rolling.

7. **Dukungan kelas dan metrik.** Periksa tiap fold; train yang tidak memiliki
   salah satu kelas tidak layak menjadi bukti evaluasi lengkap tiga kelas.
   Jangan mengubah split untuk mengejar skor. Tetapkan urutan label [0,1,2],
   perlakuan zero division, support, dan confusion matrix secara eksplisit.
   Kelas tanpa contoh evaluasi tidak dapat dinilai; angka nol yang dipakai
   untuk agregasi bukan bukti model gagal pada contoh kelas yang tidak ada.
   Salah satu fold usulan hanya mempunyai satu kelas ekstrem: laporkan skor
   tiap fold, rata-rata/sebaran, serta dukungan kelas. Jangan menyebut skor
   dari beberapa fold sebagai pengukuran independen sepenuhnya.

8. **Pemilihan model.** Baseline normal, RF tanpa bobot, RF balanced, dan
   variasi depth harus memakai data/fold sama. Bobot dihitung dari train fold.
   Skor sama antar konfigurasi adalah hasil sah; tetapkan tie-break sebelum
   melihat test. Macro F1 adalah kriteria usulan, dengan precision/recall per
   kelas untuk menilai false alarm dan kegagalan mendeteksi anomali. Jangan
   memakai hasil test untuk memilih seed, ambang label, fitur, atau konfigurasi.

9. **Refit final.** Model fold bukan otomatis artefak deployment. Setelah
   hyperparameter dipilih, refit pada seluruh data pengembangan yang memenuhi
   kebijakan warm-up, evaluasi pada test sekali, dan log fit scope model itu.
   Jangan refit memakai test lalu melekatkan skor test sebelumnya pada model
   yang sudah ikut mempelajarinya.

10. **Kontrak artefak dan kegagalan.** Simpan nama/urutan/tipe fitur, mapping
    label, signature/input example, kode dan kebijakan konteks riwayat, serta
    dependency. Muat ulang artefak MLflow dan bandingkan prediksinya terhadap
    model dalam memori pada fitur yang sama. Pendaftaran registry harus dapat
    dilacak ke run dan artefak yang tepat. Logging/registry gagal tidak boleh
    dilaporkan sebagai sukses; ulangi hanya tahap yang sesuai agar tidak
    menghasilkan kandidat atau versi duplikat tanpa penjelasan. Jangan
    menganggap pendaftaran kandidat berarti layak dipakai pada aktuator nyata.

## Batas interpretasi yang tetap berlaku

- EDA sudah memeriksa distribusi label blok test usulan; bukan blind test
  sepenuhnya, walaupun belum dipakai untuk memilih berdasarkan skor model.
- Snapshot berasal dari endpoint forecast dan dapat berisi revisi/prakiraan;
  belum merekonstruksi informasi yang tersedia pada setiap waktu historis.
- Evaluasi pada satu seed dan satu lokasi belum membuktikan generalisasi
  lintas perangkat, musim, atau keluarga fault. Snapshot/seed baru dapat
  memperluas uji sintetis, tetapi tidak menghilangkan keterbatasan pseudo-label.
- Labeler memakai ambang tetap. Retraining dengan labeler tetap tidak otomatis
  membuat definisi anomali beradaptasi terhadap musim.
- Model dapat memberi probabilitas tinggi pada kombinasi di luar pengalaman
  training. Probabilitas RF bukan jaminan kebenaran atau kepastian fisik.

## Verifikasi yang perlu ada saat implementasi

Prioritas sebelum fitting: input/hash/skema, kontrak waktu, fitur finite,
kebijakan konteks, dukungan kelas, dan batas fold yang tetap. Saat eksperimen:
baseline serta evaluasi per kelas/fold dan test yang tidak dipakai tuning.
Sesudahnya: refit scope, pemuatan ulang artefak, registry yang dapat diaudit,
dan metadata sesuai model yang benar-benar disimpan.

Referensi primer:
[RandomForestClassifier 1.5](https://scikit-learn.org/1.5/modules/generated/sklearn.ensemble.RandomForestClassifier.html),
[persistensi model](https://scikit-learn.org/1.5/model_persistence.html),
[MLflow signatures](https://mlflow.org/docs/latest/ml/model/signatures/).
