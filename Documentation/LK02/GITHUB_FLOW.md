# 🔀 GitHub Flow — Branching Strategy Guide

> Panduan langkah demi langkah untuk menerapkan **GitHub Flow** branching strategy pada proyek MLOps ini. Semua command siap copy-paste.

---

## Apa itu GitHub Flow?

GitHub Flow adalah branching strategy yang sederhana dan efektif. Prinsip utamanya: **branch `main` selalu dalam keadaan deployable**. Semua perubahan dilakukan di feature branch, lalu di-merge melalui Pull Request setelah review.

---

## 6 Langkah GitHub Flow

### Langkah 1: 📌 Buat Branch dari `main`

Buat branch baru dengan nama yang deskriptif sesuai tujuan perubahan.

```bash
# Pastikan di branch main dan up-to-date
git checkout main
git pull origin main

# Buat branch baru
git checkout -b feature/add-model-training
```

**Konvensi Penamaan Branch:**
| Prefix | Kegunaan | Contoh |
|---|---|---|
| `feat/` atau `feature/` | Fitur baru | `feat/initial-setup`, `feature/add-model-training` |
| `fix/` | Bug fix | `fix/api-timeout-error` |
| `docs/` | Update dokumentasi | `docs/update-readme` |
| `chore/` | Maintenance | `chore/update-dependencies` |
| `refactor/` | Refactoring code | `refactor/data-pipeline` |

---

### Langkah 2: ✏️ Buat Perubahan dan Commit

Kerjakan perubahan, lakukan commit secara berkala dengan pesan yang jelas menggunakan **Conventional Commits**.

```bash
# Tambahkan file yang diubah
git add src/model_training.py

# Commit dengan pesan deskriptif
git commit -m "feat: add random forest model training"

# Push branch ke remote
git push origin feature/add-model-training
```

**Format Commit Message (Conventional Commits):**
```
<type>: <deskripsi singkat>

Contoh:
feat: add weather data ingestion from Open-Meteo API
fix: handle API timeout with retry mechanism
docs: update README with setup instructions
chore: update requirements.txt dependencies
refactor: modularize data preprocessing pipeline
```

---

### Langkah 3: 📝 Buat Pull Request (PR)

Ajukan PR untuk review dan diskusi perubahan sebelum merge ke `main`.

**Cara Buat PR:**
1. Buka repository di GitHub.com
2. Klik tab **"Pull requests"** → **"New pull request"**
3. Pilih **base:** `main` ← **compare:** `feature/add-model-training`
4. Isi deskripsi PR dengan template berikut:

**Template PR yang Baik:**
```markdown
## Deskripsi
Menambahkan notebook data ingestion cuaca dari Open-Meteo API untuk area Malang.

## Perubahan
- Implementasi fungsi fetch_weather_data()
- Menambahkan EDA (Exploratory Data Analysis)
- Rule-based anomaly detection (3 class)
- Save data ke data/raw/

## Testing
✅ Notebook berhasil dijalankan di Google Colab
✅ Data berhasil di-fetch dari Open-Meteo API
✅ Anomaly detection menghasilkan 3 class output

## Screenshots (jika ada)
(Tambahkan screenshot output jika relevan)
```

---

### Langkah 4: 💬 Review dan Diskusi

Tim (atau dosen/asisten) melakukan code review, memberikan feedback, dan mendiskusikan perubahan.

**Yang dilakukan reviewer:**
- Cek kualitas kode
- Cek apakah perubahan sesuai dengan deskripsi PR
- Berikan komentar/saran perbaikan
- Approve jika sudah sesuai

**Yang dilakukan author (kamu):**
- Respond komentar reviewer
- Lakukan perbaikan jika diminta
- Push commit tambahan ke branch yang sama:

```bash
# Perbaiki berdasarkan feedback
git add .
git commit -m "fix: address review feedback on data validation"
git push origin feature/add-model-training
```

---

### Langkah 5: 🚀 Deploy / Testing

Jalankan testing otomatis dan verifikasi perubahan berjalan dengan benar sebelum merge.

**Checklist sebelum merge:**
- [ ] Kode berjalan tanpa error
- [ ] Tidak ada konflik dengan `main`
- [ ] Semua test passed (jika ada CI/CD)
- [ ] Dokumentasi sudah di-update

```bash
# Pastikan tidak ada konflik
git checkout main
git pull origin main
git checkout feature/add-model-training
git merge main
# Resolve konflik jika ada
```

---

### Langkah 6: ✅ Merge PR dan Hapus Branch

Setelah PR di-approve dan semua check passed, merge PR ke `main` dan hapus branch yang sudah tidak dibutuhkan.

**Di GitHub:**
1. Klik tombol **"Merge pull request"** di halaman PR
2. Pilih **"Create a merge commit"** (recommended)
3. Klik **"Confirm merge"**
4. Klik **"Delete branch"** untuk menghapus branch di remote

**Di Terminal (lokal):**
```bash
# Pindah ke main dan pull perubahan terbaru
git checkout main
git pull origin main

# Hapus branch lokal yang sudah di-merge
git branch -d feature/add-model-training

# Hapus branch remote (jika belum dihapus via GitHub)
git push origin --delete feature/add-model-training
```

---

## 📋 Quick Reference (Cheat Sheet)

```bash
# === ALUR LENGKAP GITHUB FLOW ===

# 1. Buat branch baru
git checkout main
git pull origin main
git checkout -b feat/nama-fitur

# 2. Kerja, commit, push
git add .
git commit -m "feat: deskripsi perubahan"
git push origin feat/nama-fitur

# 3. Buat PR di GitHub.com
# 4. Review & diskusi
# 5. Testing & verifikasi

# 6. Setelah merge di GitHub:
git checkout main
git pull origin main
git branch -d feat/nama-fitur
```

---

## 🔗 Referensi
- [GitHub Flow Documentation](https://docs.github.com/en/get-started/using-github/github-flow)
- [Conventional Commits](https://www.conventionalcommits.org/)
