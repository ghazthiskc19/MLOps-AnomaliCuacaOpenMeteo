# 📋 LK-02: Indikator & Kriteria Penilaian

> Dokumen ini berisi kriteria penilaian yang digunakan dosen untuk menilai tugas LK-02 (Pertemuan 2) mata kuliah MLOps.

## Kriteria Penilaian GitHub Repository

| Komponen | Bobot | Indikator |
|---|---|---|
| **Standardisasi Struktur** | **30%** | Kerapian folder sesuai best practices, naming convention konsisten |
| **Setup Codespaces** | **30%** | Environment berjalan tanpa error, dependencies terinstall |
| **Branching Strategy** | **20%** | Commit history informatif, penggunaan branch yang tepat |
| **Dokumentasi README** | **20%** | Instruksi setup dan penggunaan sistem yang jelas |

### Skala Penilaian

| Skala | Keterangan |
|---|---|
| **4** | Sangat Baik |
| **3** | Baik |
| **2** | Cukup |
| **1** | Kurang |

---

## Tugas LK-02: Langkah Utama

### 1. 🔧 Inisiasi Repository
1. Buka GitHub.com → "New repository"
2. Nama: `MLOps-[TopikProyek]` → **MLOps-AnomaliCuacaOpenMeteo**
3. Tambahkan `.gitignore` (Python template)
4. Tambahkan lisensi MIT
5. Clone ke lokal: `git clone https://github.com/username/MLOps-AnomaliCuacaOpenMeteo.git`

### 2. ☁️ Konfigurasi GitHub Codespaces
1. Klik tombol hijau "Code" → "Codespaces" → Create
2. Tunggu setup selesai (2-3 menit)
3. Install dependencies: `pip install pandas scikit-learn jupyter`
4. Verifikasi: `python --version`
5. Ekstensi sudah ada (Python, Jupyter, GitLens)
6. Test: buat file Python sederhana dan jalankan

### 3. 📁 Penyusunan Struktur Direktori
```bash
mkdir -p data/raw data/processed models src configs notebooks tests docs
touch data/.gitkeep models/.gitkeep
```
1. Commit: `git add . && git commit -m "Initial structure"`
2. Push: `git push origin main`

### 4. 🌿 Implementasi Branching Strategy
1. Buat branch: `git checkout -b feat/initial-setup`
2. Tambah file: `echo "print('Hello MLOps')" > src/hello.py`
3. Commit & push: `git add . && git commit -m "..." && git push origin feat/initial-setup`
4. Buat Pull Request di GitHub
5. Merge PR, hapus branch

### 5. 📖 README.md
Dokumentasikan deskripsi, struktur, dan cara menjalankan proyek.

---

## Struktur Direktori Standar

```
project/
├── data/
├── models/
├── src/
├── notebooks/
├── tests/
├── docs/
└── configs/
```

## Inisiasi Repository — Checklist

- [x] GitHub repo dengan proper README
- [x] .gitignore untuk Python/Data
- [x] Initial commit dengan project structure
- [ ] Konfigurasi Codespaces (devcontainer.json)
- [ ] Branching strategy (GitHub Flow)
