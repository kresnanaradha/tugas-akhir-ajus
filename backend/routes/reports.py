"""Halaman Laporan (/reports/*) dan Perbandingan Rapat (/perbandingan/*)."""

from flask import Blueprint, jsonify, request, session

from pipeline import artifacts, auth_store, meetings_store, report_pdf, report_stats
from pipeline.summarize import compare_meetings

from . import common
from .common import login_required

bp = Blueprint("reports", __name__)


@bp.get("/reports/stats")
@login_required
def reports_stats_route():
    """Seperti /admin/stats tapi hanya rapat user ini (halaman Laporan)."""
    return jsonify(report_stats.get_stats(session["user_id"]))


@bp.get("/reports/team")
@login_required
def reports_team():
    """Pemakaian team si pemanggil (null kalau tidak punya team) untuk halaman Laporan."""
    return jsonify(report_stats.team_usage(session["user_id"]))


@bp.get("/reports/action-items")
@login_required
def reports_action_items():
    """Semua action item di seluruh rapat user ini. Dipisah dari /reports/stats karena membaca
    tiap ringkasan dari R2 dan lambat saat cache dingin."""
    return jsonify(report_stats.action_item_rollup(session["user_id"]))


@bp.get("/reports/export")
@login_required
def reports_export():
    """Versi PDF halaman Laporan."""
    user = auth_store.get_user(session["user_id"])
    pdf_bytes = report_pdf.generate_user_report(
        report_stats.get_stats(session["user_id"]),
        meetings_store.list_meetings(session["user_id"]),
        generated_by=user["name"],
    )
    return common.pdf(pdf_bytes, "notulis-laporan-rapat.pdf")


_comparison_cache: dict = {}


def _load_two_meetings():
    """Dua rapat dalam permintaan perbandingan beserta ringkasannya, atau respons error."""
    a_id, b_id = request.args.get("a"), request.args.get("b")
    if not a_id or not b_id:
        return None, (jsonify({"error": "Parameter a dan b (id rapat) wajib diisi"}), 400)
    meeting_a, meeting_b = meetings_store.get_meeting(a_id), meetings_store.get_meeting(b_id)
    if meeting_a is None or meeting_b is None or not (common.can_view_meeting(meeting_a) and common.can_view_meeting(meeting_b)):
        return None, (jsonify({"error": "Salah satu rapat tidak ditemukan"}), 404)
    for m in (meeting_a, meeting_b):
        m["summary"] = artifacts.load_summary(m["id"]) if m["recording"] else None
    return (meeting_a, meeting_b), None


def _comparison_analysis(meeting_a, meeting_b):
    """Perbandingan AI dua rapat, None kalau salah satu belum punya ringkasan. Di-cache supaya membuka halaman lagi atau
    ekspor PDF tidak memanggil model lagi. ponytail: dict di dalam proses, hilang saat restart"""
    if not meeting_a["summary"] or not meeting_b["summary"]:
        return None
    key = (meeting_a["id"], meeting_b["id"], hash(str(meeting_a["summary"]) + str(meeting_b["summary"])))
    if key not in _comparison_cache:
        _comparison_cache[key] = compare_meetings(meeting_a, meeting_a["summary"], meeting_b, meeting_b["summary"])
    return _comparison_cache[key]


@bp.get("/perbandingan/analisis")
@login_required
def perbandingan_analisis():
    """Perbandingan AI yang tampil di bagian atas halaman Perbandingan."""
    pair, error = _load_two_meetings()
    if error:
        return error
    try:
        return jsonify(_comparison_analysis(*pair))
    except Exception as e:
        print(f"[perbandingan] AI comparison failed: {e}")
        return jsonify({"error": "Perbandingan AI gagal dibuat"}), 502


@bp.get("/perbandingan/export")
@login_required
def perbandingan_export():
    """PDF halaman Perbandingan, lengkap dengan perbandingan AI kalau ada."""
    pair, error = _load_two_meetings()
    if error:
        return error
    meeting_a, meeting_b = pair
    try:
        analysis = _comparison_analysis(meeting_a, meeting_b)
    except Exception as e:
        print(f"[perbandingan] AI comparison failed for the PDF: {e}")
        analysis = None  # PDF berdampingan tetap berguna

    user = auth_store.get_user(session["user_id"])
    pdf_bytes = report_pdf.generate_comparison_report(meeting_a, meeting_b, generated_by=user["name"], analysis=analysis)
    return common.pdf(pdf_bytes, "notulis-perbandingan-rapat.pdf")
