"""/teams/*: buat team, undang, gabung, keluar, dan atur anggota."""

from flask import Blueprint, jsonify, request, session

from pipeline import auth_store, billing_store, mailer, team_store

from . import common
from .common import login_required

bp = Blueprint("teams", __name__)


@bp.get("/teams/me")
@login_required
def get_my_team():
    """None kalau tidak punya team, selain itu {team, members}."""
    user = auth_store.get_user(session["user_id"])
    if not user["team_id"]:
        return jsonify(None)
    return jsonify({"team": team_store.get_team(user["team_id"]), "members": team_store.list_members(user["team_id"])})


@bp.post("/teams")
@login_required
def create_team():
    """Buat team dengan pemanggil sebagai admin. Butuh paket Team dan belum punya team."""
    user = auth_store.get_user(session["user_id"])
    if user["team_id"]:
        return jsonify({"error": "Anda sudah tergabung dalam sebuah team"}), 400
    if billing_store.get_subscription(session["user_id"])["plan"] != "team":
        return jsonify({"error": "Membuat team memerlukan paket Team"}), 402
    name = (request.get_json(silent=True) or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "Nama team wajib diisi"}), 400
    return jsonify(team_store.create_team(name, session["user_id"]))


@bp.patch("/teams/<team_id>")
@login_required
def rename_my_team(team_id):
    user = auth_store.get_user(session["user_id"])
    if user["team_id"] != team_id or user["team_role"] != "admin":
        return jsonify({"error": "Hanya admin team yang bisa mengubah ini"}), 403
    name = (request.get_json(silent=True) or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "Nama team wajib diisi"}), 400
    team_store.rename_team(team_id, name)
    return jsonify(team_store.get_team(team_id))


@bp.post("/teams/invite")
@login_required
def invite_to_team():
    """Hanya admin. Tautannya tetap dikembalikan walau email gagal terkirim."""
    user = auth_store.get_user(session["user_id"])
    if not user["team_id"] or user["team_role"] != "admin":
        return jsonify({"error": "Hanya admin team yang bisa mengundang anggota"}), 403
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip() or None
    invite = team_store.create_invite(user["team_id"], user["id"], email=email)
    invite_url = f"{common.LOCAL_FRONTEND_URL}/team/gabung/{invite['token']}"
    if email:
        try:
            team = team_store.get_team(user["team_id"])
            mailer.send_team_invite_email(email, team["name"], user["name"], invite_url)
        except Exception as e:
            print(f"[team] failed to send invite email to {email}: {e}")
    return jsonify({"token": invite["token"], "invite_url": invite_url, "expires_at": invite["expires_at"].strftime("%Y-%m-%dT%H:%M:%S")})


@bp.get("/teams/invite/<token>")
@login_required
def preview_team_invite(token):
    """Supaya halaman gabung bisa menampilkan nama team sebelum user bergabung."""
    invite = team_store.get_invite(token)
    if invite is None:
        return jsonify({"error": "Tautan undangan tidak valid atau sudah kedaluwarsa"}), 404
    team = team_store.get_team(invite["team_id"])
    return jsonify({"team_name": team["name"]})


@bp.post("/teams/join")
@login_required
def join_team():
    user = auth_store.get_user(session["user_id"])
    if user["team_id"]:
        return jsonify({"error": "Anda sudah tergabung dalam sebuah team. Keluar dulu untuk gabung team lain."}), 400
    token = (request.get_json(silent=True) or {}).get("token")
    team = team_store.accept_invite(token, session["user_id"])
    if team is None:
        return jsonify({"error": "Tautan undangan tidak valid atau sudah kedaluwarsa"}), 404
    return jsonify(team)


@bp.post("/teams/leave")
@login_required
def leave_team():
    user = auth_store.get_user(session["user_id"])
    if not user["team_id"]:
        return jsonify({"error": "Anda belum tergabung dalam team apa pun"}), 400
    team_store.remove_member(session["user_id"])
    return jsonify({"left": True})


@bp.delete("/teams/members/<user_id>")
@login_required
def remove_team_member(user_id):
    admin = auth_store.get_user(session["user_id"])
    target = auth_store.get_user(user_id)
    if not admin["team_id"] or admin["team_role"] != "admin":
        return jsonify({"error": "Hanya admin team yang bisa mengeluarkan anggota"}), 403
    if target is None or target["team_id"] != admin["team_id"]:
        return jsonify({"error": "Pengguna bukan anggota team ini"}), 404
    team_store.remove_member(user_id)
    return jsonify({"removed": True})


@bp.patch("/teams/members/<user_id>")
@login_required
def update_team_member_role(user_id):
    admin = auth_store.get_user(session["user_id"])
    target = auth_store.get_user(user_id)
    if not admin["team_id"] or admin["team_role"] != "admin":
        return jsonify({"error": "Hanya admin team yang bisa mengubah peran anggota"}), 403
    if target is None or target["team_id"] != admin["team_id"]:
        return jsonify({"error": "Pengguna bukan anggota team ini"}), 404
    role = (request.get_json(silent=True) or {}).get("role")
    if role not in ("admin", "member"):
        return jsonify({"error": "role harus 'admin' atau 'member'"}), 400
    team_store.set_role(user_id, admin["team_id"], role)
    return jsonify({"role": role})
