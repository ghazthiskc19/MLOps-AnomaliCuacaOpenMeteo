"""Build LK07 PDF from verified registry evidence and original screenshots."""

from html import escape
import json
from pathlib import Path
import textwrap

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)
import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Documentation/LK07"
PDF = OUT / "LK07-Muhammad Ghazy Humaidi-245150200111071.pdf"


def build():
    for name, filename in [("TNR", "times.ttf"), ("TNR-Bold", "timesbd.ttf"), ("TNR-Italic", "timesi.ttf")]:
        pdfmetrics.registerFont(TTFont(name, str(Path("C:/Windows/Fonts") / filename)))
    pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic", boldItalic="TNR-Bold")
    body = ParagraphStyle("Body", fontName="TNR", fontSize=11.5, leading=15.5, alignment=TA_JUSTIFY, spaceAfter=9)
    heading = ParagraphStyle("Heading", parent=body, fontName="TNR-Bold", fontSize=15, leading=19, alignment=TA_LEFT, spaceAfter=15)
    sub = ParagraphStyle("Sub", parent=body, fontName="TNR-Bold", fontSize=12, leading=16, alignment=TA_LEFT, spaceBefore=7)
    small = ParagraphStyle("Small", parent=body, fontSize=9.5, leading=12.5, alignment=TA_LEFT, spaceAfter=6)
    cell = ParagraphStyle("Cell", parent=small, fontSize=10, leading=13, spaceAfter=0)
    center = ParagraphStyle("Center", parent=body, alignment=TA_CENTER)
    title = ParagraphStyle("Title", parent=center, fontName="TNR-Bold", fontSize=19, leading=25, spaceAfter=18)
    code = ParagraphStyle("Code", fontName="Courier", fontSize=8.1, leading=11, alignment=TA_LEFT, spaceAfter=8)
    evidence = json.loads((OUT / "results/registry_verification.json").read_text(encoding="utf-8"))
    meta = yaml.safe_load((OUT / "production_model.yaml").read_text(encoding="utf-8"))
    pointer = yaml.safe_load((OUT / "production_model.yaml.dvc").read_text(encoding="utf-8"))["outs"][0]
    old = json.loads((ROOT / "Documentation/LK06/results/best_model_metadata.json").read_text(encoding="utf-8"))
    new = json.loads((OUT / "results/best_model_metadata.json").read_text(encoding="utf-8"))
    summary = json.loads((OUT / "results/summary.json").read_text(encoding="utf-8"))
    story = []

    def p(text, style=body):
        story.append(Paragraph(text, style))

    def h(text):
        p(text, heading)

    def page(template="portrait"):
        story.extend([NextPageTemplate(template), PageBreak()])

    def table(rows, widths=None):
        values = [[Paragraph(escape(str(v)).replace("\n", "<br/>"), cell) for v in row] for row in rows]
        t = Table(values, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf0f2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, 0), .7, colors.HexColor("#777777")),
            ("LINEBELOW", (0, 1), (-1, -1), .25, colors.HexColor("#d3d3d3")),
        ]))
        story.extend([t, Spacer(1, 12)])

    def image(path, width, height):
        with PILImage.open(path) as im:
            w, hgt = im.size
        scale = min(width / w, height / hgt)
        story.append(Image(str(path), width=w * scale, height=hgt * scale, hAlign="CENTER"))

    def codeblock(text):
        lines = []
        for line in text.splitlines():
            lines.extend(textwrap.wrap(line, width=88, subsequent_indent="  ", break_long_words=True, break_on_hyphens=False) or [""])
        p("<br/>".join(escape(v).replace(" ", "&#160;") for v in lines), code)

    def footer(canvas, doc):
        canvas.saveState()
        w, _ = canvas._pagesize
        canvas.setFont("TNR", 9)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(48, 28, "LK07 | Muhammad Ghazy Humaidi | 245150200111071")
        canvas.drawRightString(w - 48, 28, str(doc.page))
        canvas.restoreState()

    portrait_frame = Frame(50, 48, A4[0] - 100, A4[1] - 96, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    wide = landscape(A4)
    landscape_frame = Frame(42, 45, wide[0] - 84, wide[1] - 88, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    document = BaseDocTemplate(str(PDF), pagesize=A4, title="LK07 Model Registry Versioning dan Kesiapan Inferensi",
                               author="Muhammad Ghazy Humaidi")
    document.addPageTemplates([
        PageTemplate(id="cover", frames=[portrait_frame], pagesize=A4),
        PageTemplate(id="portrait", frames=[portrait_frame], pagesize=A4, onPage=footer),
        PageTemplate(id="landscape", frames=[landscape_frame], pagesize=wide, onPage=footer),
    ])

    story.append(Spacer(1, 20))
    image(ROOT / "Documentation/assets/logo-filkom.png", 230, 100)
    story.append(Spacer(1, 26))
    p("LEMBAR KERJA 07", title)
    p("Model Registry Versioning<br/>dan Kesiapan Inferensi", title)
    p("Deteksi Anomali Cuaca Open-Meteo", center)
    story.append(Spacer(1, 26))
    image(ROOT / "Documentation/assets/logo-ub.png", 120, 135)
    story.append(Spacer(1, 25))
    p("Disusun oleh", center)
    p("<b>Muhammad Ghazy Humaidi</b><br/>245150200111071", center)
    story.append(Spacer(1, 16))
    p("Mata Kuliah MLOps<br/>Dosen Rizal Setya Perdana, S.Kom., M.Kom., Ph.D.", center)
    story.append(Spacer(1, 14))
    p("PROGRAM STUDI TEKNIK INFORMATIKA<br/>FAKULTAS ILMU KOMPUTER<br/>UNIVERSITAS BRAWIJAYA<br/>2026", center)

    page()
    h("1 Tujuan dan Hasil Pengelolaan Model")
    p("LK07 mengelola artefak Random Forest dari LK06 melalui registrasi, versioning, transisi stage, pencatatan lineage dengan DVC, dan verifikasi inferensi. Hasil akhirnya adalah <b>WeatherAnomalyRandomForest versi 1 pada stage Production</b>. V1 dipertahankan setelah dibandingkan dengan V2 pada periode evaluasi LK07 yang sama.")
    p("Model Registry menggunakan backend SQLite lokal mlflow.db dan artefak pada mlruns/. Registrasi memakai nama model yang sama agar versi-versinya tetap berada dalam satu riwayat. Penggunaan stage Production pada laporan ini merupakan simulasi lifecycle akademik, belum menunjukkan validasi sensor lapangan atau tersedianya layanan serving.")
    table([["Versi", "Pohon", "Dataset training", "Stage akhir", "Keterangan"],
           ["V1", 100, "dataset-v3.0.0", "Production", "Pemenang LK06; model aktif"],
           ["V2", 150, "dataset-v4.0.0", "None", "Kandidat dari dataset baru"],
           ["V3", 150, "dataset-v4.0.0", "None", "Registrasi ulang artefak V2"]], [42, 50, 108, 75, 220])
    p("V3 memiliki source model URI dan run ID yang sama dengan V2. Karena itu V3 dicatat sebagai registrasi ulang, bukan sebagai hasil training atau peningkatan model tambahan. Riwayat ini tetap dipertahankan untuk menjelaskan keadaan registry yang terlihat pada screenshot.")
    p("Identitas run", sub)
    table([["Versi", "Run ID dan source model URI"],
           ["V1", old["run_id"] + "\n" + old["model_uri"]],
           ["V2 / V3", new["run_id"] + "\n" + new["model_uri"]]], [65, 430])
    p("Pemilihan kandidat pada masing-masing eksperimen menggunakan mean CV macro F1 pada development. Keputusan mempertahankan versi Production menggunakan perbandingan kedua model pada holdout LK07 yang sama. Artefak tidak dilatih ulang untuk menghasilkan pembuktian ini.")

    page()
    h("2 Pembaruan Data dan Dasar Pemilihan Versi")
    p("Dataset baru diambil dari object R2 yang diunggah oleh pipeline Airflow. Data disimpan sebagai snapshot terpisah, disaring untuk jam yang sudah lewat, lalu diberi hardware fault sintetis dengan seed 42 dan fault rate 0,05. Label kelas tetap berasal dari aturan preprocessing proyek. Kedua dataset dibekukan melalui pointer DVC dan tag Git masing-masing.")
    table([["Konfigurasi", "V1", "V2"], ["n_estimators", "100", "150"],
           ["max_depth / min_samples_leaf", "None / 1", "None / 1"],
           ["class_weight / random_state", "None / 42", "None / 42"],
           ["Development / final test", "537 / 135", "532 / 134"],
           ["Mean CV macro F1", f"{old['cv_value']:.4f}", f"{new['cv_value']:.4f}"]], [225, 135, 135])
    p("Skor CV di atas berasal dari snapshot dan periode berbeda sehingga tidak dipakai sebagai bukti langsung keunggulan V1 atas V2. Di LK07, tiga konfigurasi RF 150 pohon dibandingkan pada development baru; rf_baseline terpilih dengan mean CV macro F1 0,6380.")
    p("Perbandingan pada holdout yang sama", sub)
    table([["Metrik", "V1", "V2"],
           ["Accuracy", "0,9851", "0,9701"], ["Macro F1 tetap 3 kelas", "0,6224", "0,5662"],
           ["Balanced accuracy", "0,9335", "0,8085"], ["Recall hardware fault", "7/8 = 0,8750", "5/8 = 0,6250"]], [225, 135, 135])
    p("Holdout bersama berisi 134 observasi pada 27 Oktober 2026 pukul 04.00 sampai 1 November 2026 pukul 17.00 WIB. Seluruh timestamp berada setelah batas fitting kedua model. V1 melewatkan satu dari delapan fault, sedangkan V2 melewatkan tiga; keduanya salah memberi kelas fault pada satu observasi normal.")
    p("Distribusi holdout adalah 126 normal, 8 hardware fault, dan <b>nol extreme weather</b>. Macro F1 tetap memasukkan label 0/1/2 dengan kontribusi nol bagi kelas yang tidak memiliki contoh maupun prediksi. Balanced accuracy merata-ratakan recall kelas yang memiliki support. Keputusan ini belum menguji kemampuan extreme weather; perubahan data dan jumlah pohon juga tidak dapat dipisahkan pengaruhnya.")

    page()
    h("3 Metadata Production dan Lineage DVC")
    p("Snapshot production_model.yaml mencatat versi aktif, URI inferensi, run ID, parameter, kontrak 37 fitur, hash artefak, dataset training V1, dan dataset evaluasi LK07. DVC melacak bytes metadata tersebut melalui production_model.yaml.dvc. Metadata telah diunggah ke remote r2 dan pemeriksaan cloud menyatakan cache serta remote sinkron.")
    table([["Atribut", "Nilai"],
           ["Model / stage", "WeatherAnomalyRandomForest / V1 / Production"],
           ["URI inferensi", "models:/WeatherAnomalyRandomForest/Production"],
           ["Dataset training V1", "dataset-v3.0.0\nMD5 64d906e7d0086d1814f5e61b359e22fe"],
           ["Dataset evaluasi LK07", "dataset-v4.0.0\nMD5 e37325821734e2576273e5715b6a6c88"],
           ["MD5 metadata DVC", pointer["md5"]], ["Ukuran metadata", str(pointer["size"]) + " bytes"]], [145, 350])
    p("Pointer metadata yang dikumpulkan", sub)
    codeblock((OUT / "production_model.yaml.dvc").read_text(encoding="utf-8"))
    p("Pemeriksaan DVC", sub)
    codeblock((OUT / "results/dvc_metadata_verification.txt").read_text(encoding="utf-8"))
    p("V1 tetap memiliki lineage training dataset v3 walaupun pengujian pembanding memakai dataset v4. Metadata membedakan kedua peran tersebut agar model tidak keliru diatribusikan sebagai hasil training pada data terbaru.")
    p("Metadata DVC menyimpan referensi dan identitas artefak, bukan salinan penuh registry atau model. Pemuatan model pada mesin lain memerlukan tracking store dan artefak yang cocok. Nomor versi 1/2/3 berlaku pada registry lokal ini.")

    page()
    h("4 Verifikasi Inferensi dan Batas Penggunaan")
    p("Inferensi diuji dengan mlflow.pyfunc.load_model menggunakan URI stage Production. Script memeriksa bahwa tepat satu versi berada pada stage tersebut, lalu mencocokkan prediksinya dengan pemanggilan V1 secara eksplisit pada seluruh holdout bersama. Prediksi V2 juga dibandingkan dengan file prediksi yang disimpan saat training dan hasilnya identik.")
    codeblock((OUT / "results/registry_verification.txt").read_text(encoding="utf-8"))
    p("Kontrak input", sub)
    p("Model menerima 37 fitur numeric float64. Helper src.training_data.latest_features membentuk satu baris fitur dari sedikitnya 49 observasi hourly: 48 jam konteks dan observasi terkini. Timestamp harus berurutan, unik, dan berinterval satu jam. Timestamp tanpa timezone bermakna Asia/Jakarta. Data nonnumeric, missing, nonfinite, gap, dan duplikasi ditolak oleh kontrak data.")
    p("Reproduksi pemeriksaan", sub)
    codeblock("dvc pull Documentation/LK07/production_model.yaml.dvc\npython scripts/verify_lk07_registry.py")
    p("Script verifikasi tidak meregistrasikan model dan tidak mengubah stage. Eksekusinya memperbarui snapshot metadata serta bukti lokal. Jika pembaruan itu sengaja dibekukan, pointer DVC perlu diperbarui dan didorong kembali ke remote. Perintah training dan petunjuk UI tersedia pada README LK07.")
    p("Batas interpretasi", sub)
    p("Hasil berbasis pseudo-label dan fault sintetis belum menunjukkan akurasi sensor lapangan. Holdout tidak memiliki kelas extreme weather. Holdout bersama sudah digunakan dalam keputusan deployment sehingga belum menjadi test independen setelah seleksi. Status Production hanya menandai versi yang dipilih untuk simulasi inferensi; layanan FastAPI, Docker, dan validasi aktuator tidak menjadi bagian implementasi LK07 ini.")

    def evidence_page(title_text, filename, caption, note):
        page("landscape")
        h(title_text)
        image(OUT / "screenshots" / filename, wide[0] - 90, 386)
        story.append(Spacer(1, 10))
        p(caption, small)
        p(note + " Berkas asli: screenshots/" + filename + ".", small)

    evidence_page("5 Bukti Daftar Versi Model Registry", "07-registry-versions.png",
        "Gambar 1. Registered model WeatherAnomalyRandomForest memiliki V1, V2, dan V3. V1 berstatus Production; V2 serta V3 berstatus None.",
        "V3 merujuk artefak yang sama dengan V2 dan dicatat sebagai registrasi ulang")
    evidence_page("6 Bukti Parameter Model V1", "03-v1-parameters.png",
        "Gambar 2. Run rf_baseline LK06 mencatat n_estimators=100, max_depth=None, min_samples_leaf=1, class_weight=None, dan random_state=42. Tautan registered model menunjukkan v1.",
        "Parameter model dicatat pada child run kandidat, sedangkan parent run memuat pengaturan split dan jumlah fitur")
    evidence_page("7 Bukti Pembaruan Parameter Model V2", "06-v2-parameters.png",
        "Gambar 3. Run rf_baseline pada eksperimen LK07 mencatat n_estimators=150. Parameter max_depth, min_samples_leaf, class_weight, dan random_state pada kandidat terpilih tetap sama dengan V1.",
        "Perubahan parameter disertai pembaruan dataset ke dataset-v4.0.0")
    evidence_page("8 Bukti Transisi V1 ke Staging", "08-v1-staging.png",
        "Gambar 4. Halaman Version 1 menunjukkan stage Staging. Transisi dilakukan melalui dropdown stage pada tampilan registry lama, setelah toggle New model registry UI dimatikan.",
        "Stage masih didukung MLflow 3.17.1 meskipun ditandai deprecated; aliases tidak digunakan sebagai pengganti stage dalam bukti ini")
    evidence_page("9 Bukti Transisi V1 ke Production", "09-v1-production.png",
        "Gambar 5. Versi yang sama kemudian berada pada stage Production. Tag dataset-v3.0.0 mempertahankan identitas dataset training V1.",
        "Screenshot status None setelah promosi awal tetap disimpan sebagai arsip perubahan sementara; kondisi akhir dikonfirmasi oleh Gambar 1 dan verifikasi API")
    evidence_page("10 Bukti Pemanggilan Model Production", "10-production-inference.png",
        "Gambar 6. mlflow.pyfunc.load_model memuat models:/WeatherAnomalyRandomForest/Production. Terminal menampilkan versi 1, input shape (1, 37), prediksi [0], dan keberhasilan verifikasi.",
        "Ini merupakan smoke test kesiapan inferensi. Hasil pengujian tambahan seluruh holdout tersimpan pada results/registry_verification.json")

    page()
    h("11 Kelengkapan Luaran dan Referensi")
    table([["Persyaratan LK07", "Bukti yang disediakan"],
           ["Registrasi model terbaik LK06", "V1 terhubung ke run LK06; registry dan metadata aktif"],
           ["Pembaruan dan versioning", "V2 150 pohon, dataset v4; screenshot parameter dan daftar versi"],
           ["None ke Staging ke Production", "Screenshot V1 Staging dan Production; daftar stage akhir"],
           ["Sinkronisasi metadata DVC", "production_model.yaml, pointer .dvc, verifikasi lokal/cloud"],
           ["Inferensi Production", "Screenshot pemanggilan /Production dan hasil script verifikasi"],
           ["README repositori", "README utama dan Documentation/LK07/README.md"]], [185, 310])
    p("Paket bukti menyertakan screenshot asli, manifest perubahan nama beserta SHA256, metadata model aktif, pointer DVC, hasil prediksi holdout bersama, dan script reproduksi. Isi screenshot tidak diedit saat penggantian nama. Screenshot metrik historis dan detail run tambahan tersedia dalam folder screenshots/ pada resolusi penuh.")
    p("Kesimpulan", sub)
    p("LK07 menghasilkan riwayat versi yang dapat ditelusuri dan satu versi Production yang dapat dimuat untuk inferensi. V1 dipertahankan karena mendeteksi 7 dari 8 hardware fault pada holdout bersama, dibandingkan 5 dari 8 oleh V2. Keputusan berlaku untuk simulasi dan periode evaluasi yang tersedia. Penambahan jumlah pohon serta pembaruan dataset belum menghasilkan kandidat yang lebih baik pada pengujian tersebut.")
    p("Referensi", sub)
    for label, url in [
        ("MLflow Model Registry concepts", "https://www.mlflow.org/docs/latest/ml/model-registry/"),
        ("MLflow Model Registry workflows dan migrasi stage", "https://www.mlflow.org/docs/latest/ml/model-registry/workflow/"),
        ("DVC add", "https://dvc.org/doc/command-reference/add"),
        ("DVC push", "https://dvc.org/doc/command-reference/push"),
    ]:
        p(f'{escape(label)}. <link href="{url}" color="#234d74">{escape(url)}</link>', small)
    p("Sumber hasil: metadata eksperimen LK06/LK07, registry SQLite lokal, snapshot DVC, screenshot MLflow UI, dan verifikasi programatik pada " + escape(evidence["verified_at_utc"]) + ". Dokumentasi resmi diakses 1 November 2026.", small)
    document.build(story)
    print(PDF)


if __name__ == "__main__":
    build()
