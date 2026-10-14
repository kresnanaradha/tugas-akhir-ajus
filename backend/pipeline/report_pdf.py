"""Ekspor PDF (reportlab): laporan sistem admin, laporan milik user sendiri, dan
perbandingan dua rapat. Warna mengikuti frontend/constants/theme.js."""

import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors as pdf_colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_PLATFORM_LABEL = {"google_meet": "Google Meet", "zoom": "Zoom", "upload": "Upload"}

_INK = pdf_colors.HexColor("#1B1F2B")
_INK_SOFT = pdf_colors.HexColor("#4A5064")
_BORDER = pdf_colors.HexColor("#ECE8DC")
_SURFACE_SUNKEN = pdf_colors.HexColor("#F1EEE4")
_GOLD_DEEP = pdf_colors.HexColor("#8A6416")


def _format_idr(n: int) -> str:
    return f"Rp {n:,.0f}".replace(",", ".")


def _format_mb(bytes_: int | None) -> str:
    if bytes_ is None:
        return "-"
    return f"{bytes_ / (1024 ** 2):.1f} MB"


def _table_style(header: bool = True) -> TableStyle:
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, _BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), _INK),
            ("TEXTCOLOR", (0, 0), (-1, 0), pdf_colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [pdf_colors.white, _SURFACE_SUNKEN]),
        ]
    return TableStyle(style)


def _styles(title_size: int = 22) -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("NotulisTitle", parent=base["Title"], fontSize=title_size, textColor=_INK, spaceAfter=2),
        "subtitle": ParagraphStyle("NotulisSubtitle", parent=base["Normal"], fontSize=10, textColor=_INK_SOFT),
        "section": ParagraphStyle(
            "NotulisSection", parent=base["Heading2"], fontSize=13, textColor=_GOLD_DEEP, spaceBefore=18, spaceAfter=8
        ),
        "footer": ParagraphStyle("NotulisFooter", parent=base["Normal"], fontSize=8, textColor=_INK_SOFT),
    }


def _header(styles: dict, subtitle: str, generated_by: str) -> list:
    stamp = f"Dibuat: {datetime.now().strftime('%d %B %Y, %H:%M')} WIB &nbsp;&middot;&nbsp; Oleh: {escape(generated_by)}"
    return [
        Paragraph("NOTULIS", styles["title"]),
        Paragraph(subtitle, styles["subtitle"]),
        Paragraph(stamp, styles["subtitle"]),
    ]


def _build(title: str, elements: list, margin=2 * cm) -> bytes:
    buf = io.BytesIO()
    SimpleDocTemplate(
        buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=margin, rightMargin=margin, title=title
    ).build(elements)
    return buf.getvalue()


def _volume_table(m: dict) -> Table:
    rows = [["Periode", "Jumlah Rapat"], ["Hari Ini", m["today"]], ["Minggu Ini", m["this_week"]], ["Bulan Ini", m["this_month"]], ["Total", m["total"]]]
    return Table([[a, str(b)] for a, b in rows], colWidths=[9 * cm, 8 * cm], style=_table_style())


def _detail_table(meetings: list[dict]) -> Table:
    cell = ParagraphStyle("cell", fontSize=8.5, textColor=_INK)
    rows = [["Judul", "Platform", "Tanggal", "Durasi", "Status"]]
    for m in meetings:
        duration = f"{m['duration_minutes']:.1f} mnt" if m.get("duration_minutes") else "-"
        rows.append([Paragraph(escape(m["title"]), cell), _PLATFORM_LABEL.get(m["platform"], m["platform"]), m["created_at"][:10], duration, m["status"]])
    return Table(rows, colWidths=[6.5 * cm, 3 * cm, 3 * cm, 2.5 * cm, 2 * cm], repeatRows=1, style=_table_style())


def generate_report(stats: dict, meetings: list[dict], generated_by: str) -> bytes:
    """Laporan admin: angka seluruh sistem, angka dashboard plus semua rapat."""
    s = _styles()
    m = stats["meetings"]
    success_rate = round(m["completed"] / max(1, m["total"]) * 100)
    cost = stats["openai_cost"]

    summary = Table(
        [
            ["Total Rapat Sepanjang Waktu", str(m["total"])],
            ["Rapat Bulan Ini", str(m["this_month"])],
            ["Tingkat Keberhasilan Rapat", f"{success_rate}% ({m['failed']} gagal)"],
            ["Total Pengguna Terdaftar", str(stats["users_total"])],
            ["Pendapatan Berjalan (MRR)", _format_idr(stats["mrr_idr"])],
            ["Biaya OpenAI API", f"${cost['total_usd']:.4f} ({cost['call_count']} panggilan)"],
            ["Penyimpanan R2 Terpakai", _format_mb(stats["storage_bytes"])],
        ],
        colWidths=[9 * cm, 8 * cm],
        style=_table_style(header=False),
    )
    return _build("Laporan Sistem Notulis", [
        *_header(s, "Laporan Sistem: Rapat, Pengguna, dan Biaya Operasional", generated_by),
        Spacer(1, 4),
        Paragraph("Ringkasan Eksekutif", s["section"]),
        summary,
        Paragraph("Volume Rapat", s["section"]),
        _volume_table(m),
        Paragraph("Detail Rapat", s["section"]),
        _detail_table(meetings),
        Spacer(1, 16),
        Paragraph("Dokumen ini dibuat otomatis oleh sistem Notulis.", s["footer"]),
    ])


def generate_user_report(stats: dict, meetings: list[dict], generated_by: str) -> bytes:
    """Laporan milik user sendiri: tata letak sama dengan versi admin tanpa MRR, biaya, penyimpanan, dan jumlah user."""
    s = _styles()
    m = stats["meetings"]
    success_rate = round(m["completed"] / max(1, m["total"]) * 100)

    summary = Table(
        [
            ["Total Rapat", str(m["total"])],
            ["Total Durasi", f"{stats['total_duration_minutes'] / 60:.1f} jam"],
            ["Tingkat Keberhasilan", f"{success_rate}% ({m['failed']} gagal)"],
            *[[_PLATFORM_LABEL.get(p, p), str(n)] for p, n in stats["platform_counts"].items()],
        ],
        colWidths=[9 * cm, 8 * cm],
        style=_table_style(header=False),
    )
    return _build("Laporan Rapat Notulis", [
        *_header(s, "Laporan Rapat", generated_by),
        Spacer(1, 4),
        Paragraph("Ringkasan", s["section"]),
        summary,
        Paragraph("Volume Rapat", s["section"]),
        _volume_table(m),
        Paragraph("Detail Rapat", s["section"]),
        _detail_table(meetings),
        Spacer(1, 16),
        Paragraph("Dokumen ini dibuat otomatis oleh sistem Notulis.", s["footer"]),
    ])


def _meeting_cell(meeting: dict) -> list:
    """Satu kolom rapat dalam perbandingan. Sel tabel menerima daftar flowable, dan teksnya
    lewat escape() karena Paragraph membacanya sebagai markup."""
    title = ParagraphStyle("cellTitle", fontSize=12, textColor=_INK, fontName="Helvetica-Bold", spaceAfter=2)
    meta = ParagraphStyle("cellMeta", fontSize=8, textColor=_INK_SOFT, spaceAfter=10)
    heading = ParagraphStyle("cellHeading", fontSize=9, textColor=_GOLD_DEEP, fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("cellBody", fontSize=8.5, textColor=_INK, leading=12)

    summary = meeting.get("summary") or {}
    platform = _PLATFORM_LABEL.get(meeting["platform"], meeting["platform"])
    duration = f"{meeting['duration_minutes']:.1f} mnt" if meeting.get("duration_minutes") else "-"

    flow = [
        Paragraph(escape(meeting["title"]), title),
        Paragraph(f"{platform} &middot; {escape(meeting['created_at'][:10])} &middot; {duration}", meta),
    ]
    if not summary:
        return flow + [Paragraph("Rapat ini belum punya ringkasan.", body)]

    topics = summary.get("topics_discussed") or []
    flow.append(Paragraph(f"TOPIK DIBAHAS ({len(topics)})", heading))
    flow.append(Paragraph(escape(", ".join(topics)) or "&ndash;", body))

    # dipendekkan: seluruh perbandingan adalah satu baris tabel dan reportlab tidak bisa memecah baris antar halaman
    text = (summary.get("short_summary") or summary.get("executive_summary") or "").strip()
    if len(text) > 500:
        text = text[:500].rsplit(" ", 1)[0] + "..."
    flow.append(Paragraph("RINGKASAN", heading))
    flow.append(Paragraph(escape(text) or "&ndash;", body))

    decisions = summary.get("key_decisions") or []
    flow.append(Paragraph(f"KEPUTUSAN UTAMA ({len(decisions)})", heading))
    flow += [Paragraph(f"&#8226; {escape(d)}", body) for d in decisions]

    items = summary.get("action_items") or []
    done = sum(1 for a in items if a.get("done"))
    flow.append(Paragraph(f"ACTION ITEM ({done}/{len(items)} selesai)", heading))
    for a in items:
        mark = "&#9745;" if a.get("done") else "&#9744;"
        who = " ".join(f"({escape(x)})" for x in (a.get("assignee"), a.get("due")) if x)
        flow.append(Paragraph(f"{mark} {escape(a.get('task') or '')} {who}", body))
    return flow


def _analysis_flow(analysis: dict | None) -> list:
    """Blok perbandingan AI di bawah tabel, kosong kalau tidak ada."""
    if not analysis:
        return []
    heading = ParagraphStyle("anHeading", fontSize=9, textColor=_GOLD_DEEP, fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("anBody", fontSize=9, textColor=_INK, leading=13)
    title = ParagraphStyle("anTitle", fontSize=12, textColor=_INK, fontName="Helvetica-Bold", spaceAfter=2)

    flow = [Paragraph("PERBANDINGAN AI", title)]
    flow += [Paragraph(escape(analysis[k]), body) for k in ("about_a", "about_b") if analysis.get(k)]
    for name, key in (("KESAMAAN", "similarities"), ("PERBEDAAN", "differences"), ("PERKEMBANGAN", "progress")):
        if analysis.get(key):
            flow.append(Paragraph(name, heading))
            flow += [Paragraph(f"&#8226; {escape(x)}", body) for x in analysis[key]]
    if analysis.get("conclusion"):
        flow.append(Paragraph("KESIMPULAN", heading))
        flow.append(Paragraph(escape(analysis["conclusion"]), body))
    return flow + [Spacer(1, 16)]


def generate_comparison_report(meeting_a: dict, meeting_b: dict, generated_by: str, analysis: dict | None = None) -> bytes:
    """Dua rapat berdampingan (satu baris tabel, satu sel per rapat), lalu perbandingan AI."""
    s = _styles(title_size=20)
    box = ("BOX", (0, 0), (0, 0), 1, _BORDER), ("BOX", (1, 0), (1, 0), 1, _BORDER)
    pad = [(side, (0, 0), (-1, -1), 10) for side in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")]
    side_by_side = Table(
        [[_meeting_cell(meeting_a), _meeting_cell(meeting_b)]],
        colWidths=[8.7 * cm, 8.7 * cm],
        style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), *box, *pad]),
    )
    return _build("Perbandingan Rapat Notulis", [
        *_header(s, "Perbandingan Rapat", generated_by),
        Spacer(1, 14),
        side_by_side,
        Spacer(1, 16),
        *_analysis_flow(analysis),
        Paragraph("Dokumen ini dibuat otomatis oleh sistem Notulis.", s["footer"]),
    ], margin=1.5 * cm)
