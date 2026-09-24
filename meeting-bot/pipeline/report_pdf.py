"""Formal PDF export for the super admin dashboard ("laporan resmi kantor" —
the user's own words) — replaces a plain CSV dump with a proper document:
letterhead, an executive summary table, a meeting-volume breakdown, and a
detail table of every meeting, styled with this app's own colors (see
constants/theme.js on the frontend) rather than reportlab's defaults, so it
reads as Notulis's own report rather than a generic library output.
"""

import io
from datetime import datetime

from reportlab.lib import colors as pdf_colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Mirrors frontend/constants/theme.js's palette, not reportlab's defaults —
# the whole point of a letterhead is that it's recognizably this app's own.
_INK = pdf_colors.HexColor("#1B1F2B")
_INK_SOFT = pdf_colors.HexColor("#4A5064")
_BORDER = pdf_colors.HexColor("#E4E0D2")
_SURFACE_SUNKEN = pdf_colors.HexColor("#F1EEE4")
_GOLD_DEEP = pdf_colors.HexColor("#8A6416")


def _format_idr(n: int) -> str:
    return f"Rp {n:,.0f}".replace(",", ".")


def _format_mb(bytes_: int | None) -> str:
    if bytes_ is None:
        return "—"
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


def generate_report(stats: dict, meetings: list[dict], generated_by: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
        title="Laporan Sistem Notulis",
    )
    base = getSampleStyleSheet()
    title_style = ParagraphStyle("NotulisTitle", parent=base["Title"], fontSize=22, textColor=_INK, spaceAfter=2)
    subtitle_style = ParagraphStyle("NotulisSubtitle", parent=base["Normal"], fontSize=10, textColor=_INK_SOFT)
    section_style = ParagraphStyle(
        "NotulisSection", parent=base["Heading2"], fontSize=13, textColor=_GOLD_DEEP, spaceBefore=18, spaceAfter=8
    )
    footer_style = ParagraphStyle("NotulisFooter", parent=base["Normal"], fontSize=8, textColor=_INK_SOFT)

    m = stats["meetings"]
    success_rate = round(m["completed"] / max(1, m["total"]) * 100)

    elements = [
        Paragraph("NOTULIS", title_style),
        Paragraph("Laporan Sistem: Rapat, Pengguna, dan Biaya Operasional", subtitle_style),
        Paragraph(
            f"Dibuat: {datetime.now().strftime('%d %B %Y, %H:%M')} WIB &nbsp;·&nbsp; Oleh: {generated_by}",
            subtitle_style,
        ),
        Spacer(1, 4),
        Paragraph("Ringkasan Eksekutif", section_style),
        Table(
            [
                ["Total Rapat Sepanjang Waktu", str(m["total"])],
                ["Rapat Bulan Ini", str(m["this_month"])],
                ["Tingkat Keberhasilan Rapat", f"{success_rate}% ({m['failed']} gagal)"],
                ["Total Pengguna Terdaftar", str(stats["users_total"])],
                ["Pendapatan Berjalan (MRR)", _format_idr(stats["mrr_idr"])],
                ["Biaya OpenAI API", f"${stats['openai_cost']['total_usd']:.4f} ({stats['openai_cost']['call_count']} panggilan)"],
                ["Penyimpanan R2 Terpakai", _format_mb(stats["storage_bytes"])],
            ],
            colWidths=[9 * cm, 8 * cm],
            style=_table_style(header=False),
        ),
        Paragraph("Volume Rapat", section_style),
        Table(
            [["Periode", "Jumlah Rapat"], ["Hari Ini", str(m["today"])], ["Minggu Ini", str(m["this_week"])], ["Bulan Ini", str(m["this_month"])], ["Total", str(m["total"])]],
            colWidths=[9 * cm, 8 * cm],
            style=_table_style(),
        ),
        Paragraph("Detail Rapat", section_style),
    ]

    detail_rows = [["Judul", "Platform", "Tanggal", "Durasi", "Status"]]
    for meeting in meetings:
        duration = f"{meeting['duration_minutes']:.1f} mnt" if meeting.get("duration_minutes") else "—"
        detail_rows.append(
            [
                Paragraph(meeting["title"], ParagraphStyle("cell", fontSize=8.5, textColor=_INK)),
                meeting["platform"],
                meeting["created_at"][:10],
                duration,
                meeting["status"],
            ]
        )
    elements.append(Table(detail_rows, colWidths=[6.5 * cm, 3 * cm, 3 * cm, 2.5 * cm, 2 * cm], repeatRows=1, style=_table_style()))

    elements.append(Spacer(1, 16))
    elements.append(Paragraph("Dokumen ini dibuat otomatis oleh sistem Notulis.", footer_style))

    doc.build(elements)
    return buf.getvalue()


def generate_user_report(stats: dict, meetings: list[dict], generated_by: str) -> bytes:
    """The regular Laporan page's export — one user's own meetings, so it
    skips every admin-only figure (MRR, OpenAI cost, storage, user count)
    generate_report() above shows instead of duplicating that function with
    a pile of conditionals for content that's genuinely a different report,
    not a variant of the same one."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
        title="Laporan Rapat Notulis",
    )
    base = getSampleStyleSheet()
    title_style = ParagraphStyle("NotulisTitle", parent=base["Title"], fontSize=22, textColor=_INK, spaceAfter=2)
    subtitle_style = ParagraphStyle("NotulisSubtitle", parent=base["Normal"], fontSize=10, textColor=_INK_SOFT)
    section_style = ParagraphStyle(
        "NotulisSection", parent=base["Heading2"], fontSize=13, textColor=_GOLD_DEEP, spaceBefore=18, spaceAfter=8
    )
    footer_style = ParagraphStyle("NotulisFooter", parent=base["Normal"], fontSize=8, textColor=_INK_SOFT)

    m = stats["meetings"]
    success_rate = round(m["completed"] / max(1, m["total"]) * 100)
    total_hours = stats["total_duration_minutes"] / 60
    platform_label = {"google_meet": "Google Meet", "zoom": "Zoom", "upload": "Upload"}

    elements = [
        Paragraph("NOTULIS", title_style),
        Paragraph("Laporan Rapat", subtitle_style),
        Paragraph(
            f"Dibuat: {datetime.now().strftime('%d %B %Y, %H:%M')} WIB &nbsp;·&nbsp; Oleh: {generated_by}",
            subtitle_style,
        ),
        Spacer(1, 4),
        Paragraph("Ringkasan", section_style),
        Table(
            [
                ["Total Rapat", str(m["total"])],
                ["Total Durasi", f"{total_hours:.1f} jam"],
                ["Tingkat Keberhasilan", f"{success_rate}% ({m['failed']} gagal)"],
                *[[platform_label.get(p, p), str(n)] for p, n in stats["platform_counts"].items()],
            ],
            colWidths=[9 * cm, 8 * cm],
            style=_table_style(header=False),
        ),
        Paragraph("Volume Rapat", section_style),
        Table(
            [["Periode", "Jumlah Rapat"], ["Hari Ini", str(m["today"])], ["Minggu Ini", str(m["this_week"])], ["Bulan Ini", str(m["this_month"])], ["Total", str(m["total"])]],
            colWidths=[9 * cm, 8 * cm],
            style=_table_style(),
        ),
        Paragraph("Detail Rapat", section_style),
    ]

    detail_rows = [["Judul", "Platform", "Tanggal", "Durasi", "Status"]]
    for meeting in meetings:
        duration = f"{meeting['duration_minutes']:.1f} mnt" if meeting.get("duration_minutes") else "—"
        detail_rows.append(
            [
                Paragraph(meeting["title"], ParagraphStyle("cell", fontSize=8.5, textColor=_INK)),
                platform_label.get(meeting["platform"], meeting["platform"]),
                meeting["created_at"][:10],
                duration,
                meeting["status"],
            ]
        )
    elements.append(Table(detail_rows, colWidths=[6.5 * cm, 3 * cm, 3 * cm, 2.5 * cm, 2 * cm], repeatRows=1, style=_table_style()))

    elements.append(Spacer(1, 16))
    elements.append(Paragraph("Dokumen ini dibuat otomatis oleh sistem Notulis.", footer_style))

    doc.build(elements)
    return buf.getvalue()
