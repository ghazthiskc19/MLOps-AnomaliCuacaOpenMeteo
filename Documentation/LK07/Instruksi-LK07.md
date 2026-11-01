# LK07 Model Registry, Versioning, dan Kesiapan Inferensi

Sumber: instruksi tugas yang diberikan pengguna pada 31 Oktober 2026.
Status: instruksi disimpan sebagai acuan; implementasi LK07 belum dimulai.

- Opened: Wednesday, 28 October 2026, 12:00 AM
- Due: Monday, 2 November 2026, 12:00 AM

Timezone tenggat tidak disebutkan dalam instruksi yang diberikan.

## Deskripsi tugas

Mahasiswa diminta untuk mengelola artefak model yang dihasilkan pada LK-06
ke dalam sebuah Model Registry. Aktivitas ini bertujuan agar mahasiswa
memahami bagaimana sebuah model yang sudah dilatih dikelola siklus hidupnya
(dari tahap eksperimen ke tahap siap produksi) melalui mekanisme versioning.
Mahasiswa akan mempraktikkan transisi stage model untuk memastikan hanya
versi terbaik yang dapat diakses oleh layanan inferensi.

## Metode pengerjaan aktivitas

1. **Registrasi Model:** Gunakan artefak model terbaik dari eksperimen MLflow
   sebelumnya (LK-06) dan daftarkan ke dalam MLflow Model Registry dengan
   nama model yang unik.
2. **Versioning Artefak:** Lakukan pembaruan model (misal: dengan parameter
   sedikit berbeda) dan daftarkan kembali sebagai versi terbaru (v2) untuk
   melihat bagaimana sistem melacak riwayat perubahan.
3. **Transisi Stage:** Simulasikan alur kerja industri dengan mengubah status
   (stage) model dari None ke Staging, kemudian ke Production melalui MLflow
   UI atau API.
4. **Sinkronisasi Metadata dengan DVC:** Gunakan DVC untuk mencatat metadata
   versi model yang dipilih guna menjamin silsilah data (data lineage) tetap
   terhubung dengan versi model tersebut.
5. **Verifikasi Inferensi:** Uji apakah model yang berstatus Production dapat
   dipanggil secara programatik (misal: menggunakan fungsi
   `mlflow.pyfunc.load_model`) sebagai simulasi kesiapan sistem inferensi.

## Bentuk dan format luaran

1. **Laporan Teknis (PDF):** Berisi screenshot daftar versi model di MLflow UI
   dan bukti transisi stage ke Production.
2. **Metadata File:** Salinan file `.dvc` atau YAML yang menyimpan referensi
   ke model yang telah di-publish.
3. **Dokumentasi README:** Penjelasan singkat di repositori mengenai versi
   model mana yang saat ini aktif digunakan untuk inferensi dan alasannya.

## Batas lingkup berdasarkan instruksi

Instruksi ini menjadi acuan utama pengerjaan LK07. Rencana sementara pada
`docs/project-scan-lk07.md` dibuat sebelum soal tersedia. Usulan FastAPI,
Docker, dan containerization pada catatan tersebut bukan persyaratan LK07
dalam instruksi yang diberikan.
