"""Build the LK08 reflection PDF from collected GitHub Actions evidence."""

from html import escape
import json
from pathlib import Path
import re

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)
import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Documentation/LK08"
PDF = OUT / "LK08-Muhammad Ghazy Humaidi-245150200111071.pdf"
SHOTS = OUT / "screenshots"


def fmt_s(v):
    return "-" if v is None else (f"{v} dtk" if v < 60 else f"{v // 60} mnt {v % 60} dtk")


def build():
    for name, filename in [("TNR", "times.ttf"), ("TNR-Bold", "timesbd.ttf"), ("TNR-Italic", "timesi.ttf")]:
        pdfmetrics.registerFont(TTFont(name, str(Path("C:/Windows/Fonts") / filename)))
    pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic", boldItalic="TNR-Bold")
    body = ParagraphStyle("Body", fontName="TNR", fontSize=11.5, leading=15.5, alignment=TA_JUSTIFY, spaceAfter=9)
    heading = ParagraphStyle("Heading", parent=body, fontName="TNR-Bold", fontSize=15, leading=19, alignment=TA_LEFT, spaceAfter=13)
    sub = ParagraphStyle("Sub", parent=body, fontName="TNR-Bold", fontSize=12, leading=16, alignment=TA_LEFT, spaceBefore=6)
    small = ParagraphStyle("Small", parent=body, fontSize=9.5, leading=12.5, alignment=TA_LEFT, spaceAfter=6)
    cell = ParagraphStyle("Cell", parent=small, fontSize=9.8, leading=12.6, spaceAfter=0)
    center = ParagraphStyle("Center", parent=body, alignment=TA_CENTER)
    title = ParagraphStyle("Title", parent=center, fontName="TNR-Bold", fontSize=19, leading=25, spaceAfter=18)
    caption = ParagraphStyle("Caption", parent=small, alignment=TA_CENTER, fontName="TNR-Italic")
    code = ParagraphStyle("Code", fontName="Courier", fontSize=7.6, leading=9.6, alignment=TA_LEFT, spaceAfter=8)

    evidence = json.loads((OUT / "actions/evidence.json").read_text(encoding="utf-8"))
    config = yaml.safe_load((ROOT / "configs/lk08.yaml").read_text(encoding="utf-8"))
    workflow = (ROOT / ".github/workflows/mlops-automation.yaml").read_text(encoding="utf-8")
    runs = [evidence[k] for k in ("initial", "simulation") if k in evidence]
    sim = evidence.get("simulation")
    notes = {}
    if sim:
        for a in sim["jobs"][0].get("annotations", []):
            notes[a.get("title") or a["level"]] = a["message"]
    gate_note = next((v for k, v in notes.items() if k.startswith("Quality gate")), None)
    registry_note = notes.get("MLflow Registry")
    story = []

    def p(text, style=body):
        story.append(Paragraph(text, style))

    def h(text):
        p(text, heading)

    def page():
        story.extend([NextPageTemplate("portrait"), PageBreak()])

    def table(rows, widths=None):
        values = [[Paragraph(escape(str(v)).replace("\n", "<br/>"), cell) for v in row] for row in rows]
        t = Table(values, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf0f2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, 0), .7, colors.HexColor("#777777")),
            ("LINEBELOW", (0, 1), (-1, -1), .25, colors.HexColor("#d3d3d3")),
        ]))
        story.extend([t, Spacer(1, 10)])

    def image(path, width, height):
        with PILImage.open(path) as im:
            w, hgt = im.size
        scale = min(width / w, height / hgt)
        story.append(Image(str(path), width=w * scale, height=hgt * scale, hAlign="CENTER"))

    def link(url):
        return f'<link href="{url}" color="#234d74">{escape(url)}</link>'

    def footer(canvas, doc):
        canvas.saveState()
        w, _ = canvas._pagesize
        canvas.setFont("TNR", 9)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(48, 28, "LK08 | Muhammad Ghazy Humaidi | 245150200111071")
        canvas.drawRightString(w - 48, 28, str(doc.page))
        canvas.restoreState()

    frame = Frame(50, 48, A4[0] - 100, A4[1] - 96, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    document = BaseDocTemplate(str(PDF), pagesize=A4, title="LK08 Code as a Trigger",
                               author="Muhammad Ghazy Humaidi")
    document.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], pagesize=A4),
        PageTemplate(id="portrait", frames=[frame], pagesize=A4, onPage=footer),
    ])

    # Cover
    story.append(Spacer(1, 20))
    image(ROOT / "Documentation/assets/logo-filkom.png", 230, 100)
    story.append(Spacer(1, 26))
    p("LEMBAR KERJA 08", title)
    p("Code as a Trigger:<br/>Otomatisasi Test, Retraining, Evaluasi,<br/>dan Registrasi Model", title)
    p("Deteksi Anomali Cuaca Open-Meteo", center)
    story.append(Spacer(1, 22))
    image(ROOT / "Documentation/assets/logo-ub.png", 120, 135)
    story.append(Spacer(1, 22))
    p("Disusun oleh", center)
    p("<b>Muhammad Ghazy Humaidi</b><br/>245150200111071", center)
    story.append(Spacer(1, 14))
    p("Mata Kuliah MLOps<br/>Dosen Rizal Setya Perdana, S.Kom., M.Kom., Ph.D.", center)
    story.append(Spacer(1, 12))
    p("PROGRAM STUDI TEKNIK INFORMATIKA<br/>FAKULTAS ILMU KOMPUTER<br/>UNIVERSITAS BRAWIJAYA<br/>2026", center)

    # 1
    page()
    h("1 Ringkasan Luaran")
    p("LK08 membangun alur kerja GitHub Actions yang berjalan setiap kali kode masuk ke branch <b>main</b> atau ada pull request ke main. "
      "Satu perubahan kode memicu rangkaian tahap secara berurutan: pemulihan data dari DVC, pengujian pytest, training ulang melalui "
      "<b>train.py</b>, evaluasi terhadap ambang performa LK01, lalu registrasi otomatis ke MLflow Model Registry dengan stage <b>Staging</b>. "
      "Jika satu tahap gagal, tahap sesudahnya tidak dijalankan.")
    rows = [["Luaran", "Lokasi / bukti"],
            ["File konfigurasi", ".github/workflows/mlops-automation.yaml (lampiran A)"],
            ["Kebijakan gate", "configs/lk08.yaml; logika di src/automation.py dan src/validation.py"],
            ["Repositori", "https://github.com/ghazthiskc19/MLOps-AnomaliCuacaOpenMeteo"]]
    for r in runs:
        rows.append([f"Log eksekusi ({'commit awal' if r['label'] == 'initial' else 'simulasi perubahan'})", r["url"]])
    table(rows, [150, 345])
    p("Kedua run di atas dipicu oleh event <b>push</b> ke main tanpa langkah manual di antara tahap. "
      "Log baris per baris di GitHub hanya dapat dibuka setelah login. Karena itu ringkasan hasil gate dan versi registry juga dicetak "
      "sebagai <i>annotation</i> yang tampil di halaman run untuk siapa pun.")

    # 2
    h("2 Rancangan Pipeline")
    table([["Tahap", "Step workflow", "Fungsi"],
           ["Pemicu", "on: push / pull_request ke main", "Setiap perubahan kode langsung menjalankan pipeline; concurrency membatalkan run lama pada ref yang sama"],
           ["Persiapan", "checkout (fetch-depth 0), setup-python 3.12.3, pip install + pip check", "Lingkungan bersih di runner Ubuntu; histori dan tag Git ikut diambil untuk verifikasi pointer DVC"],
           ["Data", "dvc pull -r r2", "Mengambil snapshot dataset-v3.0.0 dan dataset-v4.0.0 dari Cloudflare R2 memakai GitHub Secrets"],
           ["Tahap 1", "python -m pytest tests", "Menguji preprocessing, fitur, skenario, validasi, dan registrasi"],
           ["Tahap 2", "python train.py --config configs/lk08.yaml", "Training ulang Random Forest pada data DVC v4; hanya menghasilkan kandidat"],
           ["Tahap 3", "scripts/evaluate_candidate.py", "Menghitung ulang prediksi dan metrik, keluar dengan exit code 1 bila gate gagal"],
           ["Tahap 4", "scripts/register_candidate.py", "Evaluasi ulang, registrasi ke MLflow, transisi ke Staging, lalu verifikasi stage"],
           ["Arsip", "upload-artifact (if: always())", "Paket model, metrik, dan store MLflow disimpan 30 hari, termasuk saat gate menolak"]],
          [62, 165, 268])

    # 3
    h("3 Kriteria Kelulusan Otomatis")
    v = config["validation"]
    p("Laporan LK01 (bagian 5.1) menetapkan target <b>F1-Score lebih dari 85%</b>. Nilai ini dipakai sebagai syarat utama dan dibandingkan "
      "secara ketat (lebih besar, bukan sama dengan). Syarat lain ditambahkan pada LK08 agar model tidak lolos hanya karena satu angka rata-rata terlihat bagus.")
    table([["Syarat", "Nilai", "Alasan"],
           ["Macro F1 tiga kelas", f"> {v['threshold']}", "Ambang LK01; macro agar kelas minoritas tidak tertutup kelas normal"],
           ["Support minimum per kelas", f">= {v['min_support']} data", "Kelas tanpa data uji dianggap belum terbukti, bukan dianggap lolos"],
           ["Recall hardware fault", f">= {v['min_fault_recall']}", "Fault sensor yang lolos tidak terdeteksi adalah kegagalan paling mahal"],
           ["False alarm pada data normal", f"<= {v['max_false_alarm_rate']}", "Alarm palsu yang sering membuat operator mengabaikan sistem"],
           ["Agreement per jenis skenario", f">= {v['scenario_min_agreement']} (23 jenis)", "Setiap jenis gangguan diuji terpisah, bukan hanya total"]],
          [135, 95, 265])
    p("Data uji terdiri dari dua bagian: holdout temporal dari data asli v4 (134 baris, 27 Oktober sampai 1 November 2026) dan uji skenario "
      "terpisah (184 event, seed dan partisi berbeda dari training). Holdout temporal tidak memiliki satu pun kejadian extreme weather (kelas 2). "
      "Jika dinilai sendiri, macro F1 tiga kelas pasti tertahan di 0,667 berapa pun kualitas modelnya, karena F1 kelas 2 dihitung nol.")
    p("Karena itu coverage dan macro F1 dinilai pada <b>gabungan</b> kedua bagian, sedangkan holdout temporal tetap wajib memenuhi recall fault "
      "dan batas false alarm secara mandiri. Perlu dicatat dengan jujur: aturan gabungan ini ditetapkan setelah pemeriksaan lokal menunjukkan "
      "gate ketat selalu gagal. Ambang 0,85 tidak diturunkan, tetapi sumber bukti kelas 2 berasal dari data simulasi, bukan pengamatan lapangan.")
    if gate_note:
        p("Hasil gate pada run simulasi (annotation GitHub):", sub)
        p(escape(gate_note), small)
    if registry_note:
        p("Hasil registrasi:", sub)
        p(escape(registry_note), small)

    # 4
    page()
    h("4 Bukti Eksekusi Otomatis")
    for idx, r in enumerate(runs, 1):
        kind = "Commit awal pipeline" if r["label"] == "initial" else "Simulasi perubahan kode"
        p(f"Run {idx}: {kind}", sub)
        job = r["jobs"][0]
        p(f"Commit <b>{r['head_sha'][:7]}</b> \"{escape(r['commit_message'])}\" | event {r['event']} ke {r['branch']} | "
          f"hasil <b>{r['conclusion']}</b> | durasi job {fmt_s(job['duration_s'])}<br/>{link(r['url'])}", small)
        table([["#", "Step", "Hasil", "Durasi"]] + [[s["number"], s["name"], s["conclusion"], fmt_s(s["duration_s"])]
                                                     for s in job["steps"] if not s["name"].startswith(("Post ", "Set up", "Complete"))],
              [25, 300, 75, 95])
        shot = SHOTS / f"{r['label']}.png"
        if shot.exists():
            image(shot, 495, 300)
            p(f"Gambar {idx}. Ringkasan run #{r['run_number']} ({kind.lower()}) di GitHub Actions: dipicu push, status Success.", caption)

    # 5
    page()
    h("5 Simulasi Perubahan Kode")
    if sim:
        p(f"Perubahan yang disimulasikan adalah hyperparameter: <b>n_estimators</b> pada ketiga konfigurasi kandidat Random Forest "
          f"(src/automation.py) dinaikkan dari 100 menjadi 150. Commit {sim['head_sha'][:7]} di-push ke main. Tidak ada perintah yang dijalankan "
          f"secara manual sesudahnya. GitHub Actions membuat run #{sim['run_number']} dan menjalankan test, training ulang, evaluasi, serta registrasi "
          f"secara berantai dengan hasil <b>{sim['conclusion']}</b>.")
        p("File yang berubah pada commit tersebut: " + escape(", ".join(sim["files_changed"])) + ". Commit yang sama juga menambahkan baris "
          "annotation pada dua script CLI agar metrik gate dan versi registry terbaca tanpa login. Logika evaluasi tidak berubah.")
    p("Store MLflow pada pipeline ini dibuat baru di setiap run (SQLite di runner), lalu diunggah sebagai artifact. Nomor versi registry karena itu "
      "dimulai dari 1 pada setiap run dan tidak menunjukkan urutan antar-run. Registry terpusat yang persisten, misalnya server MLflow di VPS, "
      "belum dapat dijangkau dari runner GitHub karena VPS hanya terbuka dari jaringan UB.")

    # 6
    h("6 Refleksi: Pemicu Otomatis dan Silent Failures")
    p("Silent failure adalah kegagalan yang tidak memunculkan error. Pipeline tetap selesai, model tetap menghasilkan prediksi, dan dasbor tetap "
      "hijau, padahal keputusan yang dihasilkan sudah salah. Kegagalan seperti ini berbahaya justru karena tidak ada yang memeriksanya. "
      "Proyek ini sendiri memberi beberapa contoh nyata.")
    p("<b>Metrik yang menipu.</b> Pada LK07, model mencapai accuracy 0,97 pada holdout v4. Angka itu tampak sangat baik, tetapi macro F1-nya hanya 0,57 "
      "karena data uji tidak memuat extreme weather sama sekali. Kalau keputusan promosi diambil manual dengan melihat accuracy, model akan naik "
      "ke tahap berikutnya tanpa pernah diuji pada kelas tersebut. Gate otomatis memaksa pemeriksaan yang sama setiap kali: kelas tanpa data dianggap "
      "belum terbukti, dan alasan penolakan dicatat (insufficient_coverage, failed_performance) alih-alih disembunyikan dalam satu skor.")
    p("<b>Data yang bergeser diam-diam.</b> Sebelum LK06, file raw lokal ternyata berbeda dari pointer DVC (720 baris lokal dibanding 936 baris versi v2). "
      "Training tetap berjalan, hanya saja dengan data yang salah. Pipeline LK08 selalu memulihkan data dari remote DVC dan memverifikasi hash MD5 "
      "serta tag Git sebelum training. Jika data tidak sesuai, run berhenti dengan error yang terlihat.")
    p("<b>Lingkungan yang hanya benar di laptop.</b> Ekspor model memakai skops dan kode memakai PyYAML, tetapi keduanya sempat tidak tercantum di "
      "requirements.txt karena kebetulan sudah terpasang secara transitif. Di laptop semua lancar. Runner GitHub selalu memasang dependency dari nol, "
      "sehingga dependency yang lupa dicatat langsung membuat build gagal, bukan muncul berminggu-minggu kemudian di server produksi.")
    p("<b>Langkah yang dilewati.</b> Pada alur manual, urutan test, training, evaluasi, dan registrasi bergantung pada disiplin orang yang menjalankannya. "
      "Satu langkah yang terlewat cukup untuk meloloskan model yang belum diuji. Dengan workflow, urutan itu menjadi kode: registrasi tidak bisa "
      "terjadi bila evaluasi gagal, dan register_candidate.py mengevaluasi ulang serta mencocokkan hash artefak sebelum menulis ke registry. "
      "Model yang pernah gagal tidak dapat didaftarkan hanya dengan menjalankan perintah registrasi.")
    p("<b>Skalabilitas.</b> Pemeriksaan manual mungkin masih sanggup dilakukan untuk satu model dan satu perubahan per minggu. Begitu ada banyak "
      "kontributor, perubahan harian, dan data yang terus bertambah dari Airflow, pemeriksaan manual menjadi titik paling lemah sekaligus paling lambat. "
      "Otomatisasi membuat biaya setiap pemeriksaan hampir nol sehingga pemeriksaan bisa dilakukan pada setiap commit. Setiap run juga meninggalkan "
      "jejak yang bisa diaudit: commit, hash data, metrik, keputusan gate, dan versi model. Dalam arti itu, otomatisasi adalah tulang punggung AI yang "
      "dapat diskalakan. Tanpanya, kualitas model bergantung pada ingatan dan ketelitian orang per orang.")

    # 7
    h("7 Keterbatasan")
    table([["Keterbatasan", "Dampak"],
           ["Kelas 2 hanya terwakili oleh skenario simulasi", "Kelulusan gate menunjukkan kesesuaian dengan aturan label, bukan validasi lapangan"],
           ["Aturan gate gabungan ditetapkan setelah melihat hasil lokal", "Ambang tetap 0,85, tetapi keputusan ini perlu diuji ulang saat snapshot baru memiliki extreme weather alami"],
           ["Store MLflow per-run di runner", "Versi Staging tersimpan sebagai artifact run, bukan pada registry terpusat"],
           ["API stage MLflow sudah deprecated", "Stage dipakai karena diminta tugas; migrasi ke alias perlu dilakukan kemudian"],
           ["Push langsung ke main", "Pull request tidak dibuat karena keterbatasan akses saat pengerjaan; trigger PR tetap terdefinisi di workflow"],
           ["PR dari fork tidak menerima secrets", "Pipeline pada fork akan berhenti di tahap pemulihan DVC dengan pesan error eksplisit"]],
          [205, 290])

    # Appendix
    page()
    h("Lampiran A. .github/workflows/mlops-automation.yaml")
    p("<br/>".join(escape(line).replace(" ", "&#160;") for line in workflow.splitlines()), code)
    p("Referensi", sub)
    for label, url in [
        ("GitHub Actions: events that trigger workflows", "https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows"),
        ("GitHub Actions: workflow commands (annotations)", "https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions"),
        ("MLflow Model Registry workflows", "https://mlflow.org/docs/latest/ml/model-registry/workflow/"),
        ("DVC pull", "https://dvc.org/doc/command-reference/pull"),
    ]:
        p(f"{escape(label)}. {link(url)}", small)
    document.build(story)
    print(PDF)


if __name__ == "__main__":
    build()
