"""/admin/*: statistik sistem, worker perekam, manajemen pengguna, dan laporan PDF. Hanya super admin."""

import psycopg2.errors
from flask import Blueprint, jsonify, request, session

from pipeline import admin_stats, auth_store, billing_store, join_queue, meetings_store, report_pdf

from . import common
from .common import super_admin_required

bp = Blueprint("admin", __name__)


@bp.get("/admin/stats")
@super_admin_required
def admin_stats_route():
    """Jumlah rapat, MRR, biaya OpenAI, penyimpanan R2, dan jumlah user untuk dashboard admin."""
    return jsonify(admin_stats.get_stats())


@bp.get("/admin/workers")
@super_admin_required
def admin_workers():
    """Worker perekam yang hidup (detak Redis), kosong kalau Redis tidak terjangkau."""
    try:
        return jsonify(sorted(join_queue.workers(), key=lambda w: w["id"]))
    except Exception as e:
        print(f"[admin] workers: {e}")
        return jsonify([])


@bp.get("/admin/users")
@super_admin_required
def admin_users_list():
    plans = billing_store.plans_by_user()
    team_plans = billing_store.team_plans()

    def plan_of(uid):
        own = plans.get(uid, "free")
        return own if own != "free" else team_plans.get(uid, "free")

    return jsonify([{**u, "plan": plan_of(u["id"])} for u in auth_store.list_users()])


@bp.post("/admin/users")
@super_admin_required
def admin_users_create():
    data = request.get_json(silent=True) or {}
    email, password, name = data.get("email"), data.get("password"), data.get("name")
    role = data.get("role") or "user"
    if not email or not password or not name:
        return jsonify({"error": "email, password, dan nama wajib diisi"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password minimal 8 karakter"}), 400
    if role not in auth_store.ROLES:
        return jsonify({"error": "Peran tidak dikenal"}), 400
    try:
        return jsonify(auth_store.create_user(email, password, name, role))
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Email sudah terdaftar"}), 409


@bp.patch("/admin/users/<user_id>")
@super_admin_required
def admin_users_update(user_id):
    """Ganti nama, ubah peran, atau (non)aktifkan. Menonaktifkan menggantikan menghapus:
    rapat tetap menunjuk ke users.id. Admin tidak bisa mengunci dirinya sendiri
    (menonaktifkan atau menurunkan akunnya sendiri)."""
    data = request.get_json(silent=True) or {}
    name, role, active = data.get("name"), data.get("role"), data.get("active")
    if name is not None and not str(name).strip():
        return jsonify({"error": "Nama tidak boleh kosong"}), 400
    if role is not None and role not in auth_store.ROLES:
        return jsonify({"error": "Peran tidak dikenal"}), 400
    if user_id == session["user_id"] and (active is False or (role is not None and role != "super_admin")):
        return jsonify({"error": "Kamu tidak bisa menonaktifkan atau menurunkan akunmu sendiri"}), 400
    target = auth_store.get_user(user_id)
    if target is None:
        return jsonify({"error": "Pengguna tidak ditemukan"}), 404
    if role is not None and target["role"] == "super_admin" and role != "super_admin":
        return jsonify({"error": "Super Admin tidak bisa diturunkan menjadi User"}), 400
    user = auth_store.update_user(user_id, name=str(name).strip() if name is not None else None, role=role, active=active)
    common.active_cache.pop(user_id, None)
    return jsonify(user)


@bp.post("/admin/users/<user_id>/reset-password")
@super_admin_required
def admin_users_reset_password(user_id):
    password = (request.get_json(silent=True) or {}).get("password") or ""
    if len(password) < 8:
        return jsonify({"error": "Password minimal 8 karakter"}), 400
    if auth_store.get_user(user_id) is None:
        return jsonify({"error": "Pengguna tidak ditemukan"}), 404
    auth_store.set_password(user_id, password)
    return jsonify({"ok": True})


@bp.get("/admin/export")
@super_admin_required
def admin_export():
    """PDF resmi dengan angka yang sama seperti di dashboard."""
    admin = auth_store.get_user(session["user_id"])
    pdf_bytes = report_pdf.generate_report(admin_stats.get_stats(), meetings_store.list_meetings(), generated_by=admin["name"])
    return common.pdf(pdf_bytes, "notulis-laporan-sistem.pdf")
