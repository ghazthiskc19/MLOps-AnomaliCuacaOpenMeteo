"""Generate LK06 DOCX/PDF using the exact LK04/LK05 typography and template.

Install requirements-report.txt; run from the repository root after train.py.
Screenshots are evidence from MLflow UI, never synthesized by this generator.
"""

import json
from pathlib import Path
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_lk04_report import (
    add_custom_table, add_figure, add_heading_1, add_p, format_run,
)
from generate_lk05_report import _add_field, add_logo, h1

ROOT = Path(__file__).resolve().parent.parent
LK06 = ROOT / "Documentation/LK06"
RESULTS = LK06 / "results"
PDF = LK06 / "LK06-Muhammad Ghazy Humaidi-245150200111071.pdf"
DOCX = PDF.with_suffix(".docx")
TEMPLATE = ROOT / "Documentation/LK05/LK05-Muhammad Ghazy Humaidi-245150200111071.docx"


def build_report():
    summary = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
    report = json.loads((RESULTS / "test_classification_report.json").read_text(encoding="utf-8"))
    screenshots = [LK06 / "screenshots" / name for name in ["01-run-list.png", "02-run-comparison.png", "03-model-registry.png"]]
    for image in screenshots:
        if not image.is_file():
            raise FileNotFoundError(f"Capture the actual MLflow UI first: {image}")
    # Retain LK05's cover decoration, section geometry, headers and footers.
    document = docx.Document(str(TEMPLATE))
    body = document._body._element
    for element in list(body):
        if not element.tag.endswith("sectPr"):
            body.remove(element)
    for section in document.sections:
        section.top_margin = section.bottom_margin = Pt(65)
        section.left_margin = section.right_margin = Pt(72)
        section.page_width, section.page_height = Inches(8.27), Inches(11.69)
    content_width = document.sections[0].page_width.pt - 144
    for name in ["Normal", "TOC 1", "TOC 2"]:
        if name in document.styles:
            document.styles[name].font.name = "Times New Roman"
    document.styles["Normal"].font.size = Pt(12)

    def paragraph(text, style="BodyText"):
        center = style == "CenterText"
        p = add_p(document, "", align=WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.JUSTIFY)
        bold = False
        for token in re.split(r"(<b>|</b>|<br\s*/?>)", text):
            if token == "<b>":
                bold = True
            elif token == "</b>":
                bold = False
            elif token.startswith("<br"):
                p.add_run().add_break()
            elif token:
                format_run(p.add_run(token), size_pt=12, bold=bold)

    def heading(text):
        number, title = text.split(". ", 1)
        h1(document, f"BAB {number}: {title.upper()}")

    def table(rows, widths):
        block = add_custom_table(
            document, rows[0], rows[1:],
            col_widths=[w / sum(widths) * content_width / 72 for w in widths],
        )
        block.autofit = False

    def figure(path, max_height=340, caption=""):
        add_figure(document, path, caption, max_width_in=content_width / 72,
                   max_height_in=max_height / 72)

    rows = [summary["baseline"]] + summary["candidates"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.4))
    labels = ["Normal only", "RF", "RF balanced", "RF balanced d10"]
    axes[0].bar(range(4), [r["cv_val_f1_macro_mean"] for r in rows],
                yerr=[r["cv_val_f1_macro_std"] for r in rows], capsize=4,
                color=["#9aa7b1", "#367e72", "#cf9153", "#7495b7"])
    axes[0].set_xticks(range(4), labels, rotation=15, fontsize=8)
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Fixed-3-class macro F1")
    axes[0].set_title("Mean CV score +/- fold std")
    for row, label in zip(summary["candidates"], labels[1:]):
        axes[1].plot([1, 2, 3], row["fold_val_f1_macro"], marker="o", label=label)
    axes[1].set_xticks([1, 2, 3])
    axes[1].set_ylim(0, 1)
    axes[1].set_xlabel("Chronological fold")
    axes[1].set_title("Validation performance by period")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    comparison_plot = RESULTS / "cv_comparison.png"
    fig.savefig(comparison_plot, dpi=150)
    plt.close(fig)

    center = WD_ALIGN_PARAGRAPH.CENTER
    add_logo(document, ROOT / "Documentation/assets/logo-filkom.png", width_in=2.9, space_after=14)
    add_p(document, "LEMBAR KERJA-06 (LK-06)", align=center, size_pt=20, bold=True, space_after=10)
    add_p(document, "Manajemen Eksperimen dan Pelacakan Metrik Pemodelan dengan MLflow", align=center, size_pt=17, bold=True, space_after=8)
    add_p(document, "Sistem Otomatis Deteksi Anomali Data Cuaca Open-Meteo untuk Smart Farming Berbasis MLOps", align=center, size_pt=13.5, bold=True, space_after=12)
    add_p(document, "MLOPS TIF-B 2026", align=center, size_pt=15, bold=True, space_after=26)
    add_p(document, "Nama Mahasiswa:", align=center, bold=True, space_after=2)
    add_p(document, "Muhammad Ghazy Humaidi (245150200111071)", align=center, space_after=14)
    add_p(document, "Dosen Pengampu:", align=center, bold=True, space_after=2)
    add_p(document, "Rizal Setya Perdana, S.Kom., M.Kom., Ph.D.", align=center, space_after=16)
    add_logo(document, ROOT / "Documentation/assets/logo-ub.png", width_in=2.0, space_after=14)
    for label in ["Program Studi Teknik Informatika", "Jurusan Teknik Informatika"]:
        add_p(document, label, align=center, bold=True, space_after=2)
    add_p(document, "Fakultas Ilmu Komputer, Universitas Brawijaya", align=center, bold=True, space_after=10)
    add_p(document, "2026", align=center, bold=True, space_after=0)
    document.add_page_break()

    add_heading_1(document, "RINGKASAN DAN DAFTAR ISI")
    table([
        ["Informasi Akademik", "Detail Implementasi Mahasiswa"],
        ["Nama Mahasiswa / NIM", "Muhammad Ghazy Humaidi / 245150200111071"],
        ["Mata Kuliah / Dosen", "MLOps - TIF-B 2026 / Rizal Setya Perdana, S.Kom., M.Kom., Ph.D."],
        ["Institusi", "Teknik Informatika, FILKOM, Universitas Brawijaya"],
        ["Cakupan LK-06", "EDA, tuning Random Forest, tracking MLflow, Model Registry, dan metadata model"],
        ["Hasil Utama", "RF baseline terpilih; mean CV macro F1 0.8122; test macro F1 0.9039; kandidat registry versi 1"],
    ], [170, 341])
    add_p(document, "DAFTAR ISI", bold=True, size_pt=12.5, space_before=6, space_after=4)
    toc = add_p(document, "", align=WD_ALIGN_PARAGRAPH.LEFT, space_after=0)
    _add_field(toc, 'TOC \\o "1-2" \\h \\z \\u', "Daftar isi diperbarui oleh Microsoft Word.", size_pt=11)
    document.add_page_break()

    heading("1. Data dan protokol eksperimen")
    paragraph("Tujuan LK06 adalah melatih Random Forest, membandingkan variasi hyperparameter melalui MLflow, serta menyimpan kandidat terbaik untuk tahap deployment berikutnya. Target 0/1/2 berasal dari AnomalyLabeler; evaluasi mengukur kecocokan terhadap pseudo-label, bukan validasi kerusakan sensor lapangan.")
    dataset = summary["provenance"]["dataset"]
    table([
        ["Atribut", "Nilai"], ["Dataset", dataset["path"]],
        ["Tag / MD5", f"{dataset['dataset_tag']} / {dataset['md5']}"],
        ["Snapshot raw", "720 jam, 20 September-19 Oktober 2026 (WIB)"],
        ["Kelas raw simulasi", "Normal 590; hardware fault 61; ekstrem 69"],
        ["Warm-up", "48 jam pertama sebagai konteks; tidak di-fit atau di-score"],
        ["Development / test", "537 / 135 observasi eligible; 37 input numerik"],
        ["Holdout", "20% waktu terakhir; tidak dipakai memilih parameter"],
        ["Seed model / simulator", "42 / 42"],
    ], [135, 376])
    fold_rows = [["Fold", "Train: N / kelas 0,1,2", "Validation: N / kelas 0,1,2"]]
    for fold in summary["split"]["folds"]:
        values = [fold["fold"]]
        for scope in ["train", "validation"]:
            part = fold[scope]
            values.append(f"{part['rows']} / " + ", ".join(str(part["class_counts"][str(c)]) for c in [0, 1, 2]))
        fold_rows.append(values)
    table(fold_rows, [45, 233, 233])
    paragraph("Timestamp dinormalisasi ke WIB, harus unik, terurut dan berjarak satu jam. Gap, NaN/inf raw, skema salah, serta fitur turunan nonfinite ditolak eksplisit. Riwayat tetap tersedia di batas fold; tidak ada shuffle, SMOTE atau balancing holdout. Class weight hanya dihitung dari train fold.")
    paragraph("Pemeriksaan mencakup gap waktu, timezone, konteks inferensi vs batch, kausalitas prefix, warm-up, singularitas dew point, dukungan kelas dan serialisasi model. Seluruh 97 unit/integration tests lulus pada environment lokal.")
    document.add_page_break()

    heading("2. Perbandingan model dan pemilihan")
    table([["Run", "Weight", "Depth", "Mean CV F1", "Std"]] + [
        [r["name"], r["parameters"].get("class_weight"), r["parameters"].get("max_depth"), f"{r['cv_val_f1_macro_mean']:.4f}", f"{r['cv_val_f1_macro_std']:.4f}"] for r in rows
    ], [155, 80, 60, 108, 108])
    figure(comparison_plot, max_height=205)
    paragraph("Ketiga RF memakai 100 pohon, min_samples_leaf=1, seed dan fold identik. R1 ke R2 menguji class weighting; R2 ke R3 menguji max_depth=10. Dua konfigurasi balanced menghasilkan skor identik dan tetap dilaporkan. Grafik ini dihitung dari JSON run; bukti UI asli ada pada halaman berikutnya.")
    paragraph("Pemilihan ditetapkan sebelum test: mean validation macro F1 tertinggi, lalu std lebih rendah dan urutan konfigurasi. RF baseline menang (0.8122), di atas baseline normal (0.3126). Class weighting menurunkan skor pada snapshot ini; tidak ada klaim bahwa balanced selalu lebih buruk pada dataset lain.")
    paragraph("Skor RF pada train fold adalah 1.0; gap terhadap validation perlu diperhatikan. Std menggambarkan variasi antar periode, bukan confidence interval dari observasi independen. Fold dengan sedikit kejadian ekstrem membuat skor sensitif terhadap beberapa kesalahan.")
    document.add_page_break()

    heading("3. Evaluasi test dan batas kesimpulan")
    metrics = summary["test_metrics"]
    paragraph(f"Setelah konfigurasi dibekukan, model yang di-fit pada seluruh development diuji pada 135 jam terakhir: accuracy <b>{metrics['accuracy']:.4f}</b>, macro F1 <b>{metrics['f1_macro']:.4f}</b>, balanced accuracy <b>{metrics['balanced_accuracy']:.4f}</b>.")
    table([["Kelas", "Precision", "Recall", "F1", "Support"]] + [
        [label, f"{values['precision']:.4f}", f"{values['recall']:.4f}", f"{values['f1']:.4f}", values['support']]
        for label, values in report["classes"].items()
    ], [75, 109, 109, 109, 109])
    figure(RESULTS / "test_confusion_matrix.png", max_height=260)
    paragraph("Hardware fault yang terdeteksi hanya 8 dari 13: <b>lima fault terlewat</b>. Recall 0.6154 membatasi kelayakan operasional meskipun accuracy total tinggi. Hasil test tidak dipakai untuk mengganti hyperparameter atau label yang dilaporkan.")
    paragraph("Kelas ekstrem didominasi udara kering; beberapa subtipe fault tidak ada di holdout. Data hanya satu lokasi, 30 hari dan satu seed. EDA sudah melihat distribusi kelas test; ini bukan blind test sepenuhnya. Endpoint forecast dapat memuat prakiraan/revisi. Labeler berambang tetap tidak otomatis beradaptasi musim melalui retraining.")
    document.add_page_break()

    for title, screenshot, caption in [
        ("4. Bukti MLflow: daftar run", screenshots[0], "Daftar run session final menampilkan baseline dan tiga variasi RF. Kolom mean/std CV dan hyperparameter berasal dari tracking store SQLite yang sama dengan training."),
        ("5. Bukti MLflow: perbandingan metrik", screenshots[1], "Tampilan Compare MLflow untuk tiga candidate RF. Pemilihan menggunakan validation/CV; test hanya tersedia untuk pemenang dan tidak menjadi metrik ranking antar kandidat."),
        ("6. Bukti MLflow: Model Registry", screenshots[2], f"Kandidat terpilih terdaftar pada {summary['registry_uri']}. Status kandidat pseudo-label tidak berarti sudah tervalidasi untuk pengendalian aktuator."),
    ]:
        heading(title)
        figure(screenshot, max_height=400, caption=caption)
        paragraph("Screenshot asli tersedia terpisah di Documentation/LK06/screenshots/ untuk pemeriksaan dengan resolusi penuh.")
        document.add_page_break()

    heading("7. Metadata model dan reproduksi")
    best = summary["best"]
    table([
        ["Atribut", "Nilai"], ["Registry URI", summary["registry_uri"]],
        ["Selected run ID", best["run_id"]], ["Session run ID", summary["session_run_id"]],
        ["Parameter", json.dumps({**best["parameters"], "random_state": 42})],
        ["Fit scope", "Seluruh 537 development; final test tidak ikut fitting"],
        ["Input model", "37 fitur float64; target, alasan, timestamp raw tidak menjadi input"],
        ["Input histori", "Minimal 49 observasi hourly; helper src.training_data.latest_features"],
        ["Reload checks", json.dumps(summary["reload_checks"])],
        ["Environment", "; ".join(f"{p} {v}" for p, v in summary["provenance"]["versions"].items())],
    ], [125, 386])
    paragraph("Reproduksi: install requirements.txt, dvc pull pada pointer v3, jalankan python train.py. Buka UI dengan python -m mlflow ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5000 --workers 1. Di Codespaces jalankan training kembali atau pindahkan tracking store beserta artefaknya secara konsisten; database dan model lokal tidak masuk Git.")
    paragraph("Metadata portable: results/best_model_metadata.json dan results/summary.json. Versi kode saat eksekusi belum di-commit; source SHA256 dan salinan kode direkam di MLflow. Eksekusi ulang membuat session/versi registry baru. Model final sudah dimuat ulang melalui sklearn, pyfunc dan registry dengan prediksi identik; fitur dari 49 raw rows terakhir juga cocok dengan batch.")
    paragraph("Satu eksekusi awal gagal pada format skops dan tetap tersimpan sebagai audit. Export kemudian memakai daftar tipe internal pohon yang spesifik untuk model yang baru dilatih sendiri; regression test round-trip lulus. Run gagal tidak dipakai memilih model.")
    paragraph("Referensi: dokumentasi resmi scikit-learn RandomForestClassifier/TimeSeriesSplit/F1 dan MLflow tracking, sklearn flavor, serta model signatures. Daftar tautan lengkap ada dalam notebook EDA dan dokumentasi LK06.")

    document.core_properties.title = "LK06 - Eksperimen Random Forest dan MLflow"
    document.core_properties.author = "Muhammad Ghazy Humaidi"
    document.save(str(DOCX))
    export_pdf()
    print(DOCX)
    print(PDF)


def export_pdf():
    """Use a separate hidden Word instance, as previous LK report generators."""
    import win32com.client

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = None
    try:
        doc = word.Documents.Open(str(DOCX.resolve()))
        doc.Repaginate()
        if doc.TablesOfContents.Count:
            doc.TablesOfContents(1).Update()
            doc.Repaginate()
            doc.TablesOfContents(1).Update()
        doc.Fields.Update()
        doc.Save()
        doc.ExportAsFixedFormat(str(PDF.resolve()), 17)
    finally:
        if doc is not None:
            doc.Close(False)
        word.Quit()


if __name__ == "__main__":
    build_report()
