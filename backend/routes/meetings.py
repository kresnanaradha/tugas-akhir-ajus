"""/meetings/*: daftar dan detail rapat, rekaman, edit transkrip, action item, Knowledge Base, berbagi ke team,
proses ulang, dan hapus."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from flask import Blueprint, jsonify, redirect, request, session

from pipeline import artifacts, job_queue, knowledge_base, meetings_store, report_stats, storage
from pipeline.summarize import short_summary, summarize

from . import common
from .common import login_required

bp = Blueprint("meetings", __name__)


# thread untuk membaca objek R2 secara paralel di halaman detail rapat
_R2_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="r2")


@bp.get("/meetings")
@login_required
def meetings():
    return jsonify(meetings_store.list_meetings(session["user_id"]))


@bp.get("/meetings/<meeting_id>")
@login_required
def meeting_detail(meeting_id):
    record, error = common.load_meeting(meeting_id)
    if error:
        return error

    # rapat yang masih direkam belum punya apa-apa di R2
    if record["recording"]:
        # lima objek R2 dibaca bersamaan (tiap satu 0,1 sampai 0,45 detik, dulu berurutan). Klien boto3 dibuat dulu di sini
        # karena pembuatan klien dari beberapa thread sekaligus tidak aman
        storage._get_client()
        futures = {
            "transcript": _R2_POOL.submit(artifacts.load_transcript, meeting_id),
            "fixed_transcript": _R2_POOL.submit(artifacts.load_fixed_transcript, meeting_id),
            "summary": _R2_POOL.submit(artifacts.load_summary, meeting_id),
            "segments": _R2_POOL.submit(artifacts.load_segments, meeting_id),  # tidak ada untuk rekaman lama
        }
        info_future = _R2_POOL.submit(storage.head, record["recording"])
        for key, future in futures.items():
            record[key] = future.result()

        info = info_future.result()
        if info:
            record["file_size_bytes"] = info["size"]
            record["file_extension"] = os.path.splitext(record["recording"])[1].lstrip(".")

    record["can_edit"] = common.can_edit_meeting(record)  # frontend menyembunyikan tombol ubah untuk penonton
    return jsonify(record)


@bp.get("/meetings/<meeting_id>/recording")
@login_required
def meeting_recording(meeting_id):
    """Redirect ke url R2 bertanda tangan (scrubbing tetap jalan). Lewat rapat supaya tidak ada yang bisa
    meminta key sembarang."""
    record, error = common.load_meeting(meeting_id)
    if error:
        return error
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404
    if storage.head(record["recording"]) is None:
        return jsonify({"error": "Recording file not found"}), 404
    return redirect(storage.presigned_url(record["recording"]))


@bp.post("/meetings/<meeting_id>/transcript")
@login_required
def update_transcript(meeting_id):
    """Simpan transkrip yang diedit (dan perbaikan pembicara/teks per baris, urutan sama dengan segments.json),
    lalu buat ulang ringkasan dari situ."""
    record, error = common.load_meeting(meeting_id, edit=True)
    if error:
        return error
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404

    body = request.get_json(force=True) or {}
    transcript = body.get("transcript")
    line_speakers = body.get("line_speakers") or []
    line_texts = body.get("line_texts") or []
    if not transcript or not transcript.strip():
        return jsonify({"error": "transcript is required"}), 400

    artifacts.save_fixed_transcript(meeting_id, transcript)

    result = {"fixed_transcript": transcript}

    if line_speakers or line_texts:
        segments = artifacts.load_segments(meeting_id)
        if segments:
            changed = False
            if line_speakers and len(segments) == len(line_speakers):
                for seg, label in zip(segments, line_speakers):
                    if label:
                        seg["speaker"] = label
                changed = True
            if line_texts and len(segments) == len(line_texts):
                for seg, text in zip(segments, line_texts):
                    seg["text"] = text
                changed = True
            if changed:
                artifacts.save_segments(meeting_id, segments)
                result["segments"] = segments

    try:
        result["summary"] = summarize(transcript, meeting_id)
    except Exception as e:
        result["summary_error"] = str(e)
    return jsonify(result)


_summary_lock = threading.Lock()


@bp.post("/meetings/<meeting_id>/short-summary")
@login_required
def meeting_short_summary(meeting_id):
    """Tambahkan ringkasan singkat ke rapat yang diringkas sebelum kolom itu ada."""
    _, error = common.load_meeting(meeting_id, edit=True)
    if error:
        return error
    transcript = artifacts.load_fixed_transcript(meeting_id) or artifacts.load_transcript(meeting_id)
    if not transcript or artifacts.load_summary(meeting_id) is None:
        return jsonify({"error": "Rapat ini belum punya transkrip dan ringkasan"}), 404

    text = short_summary(transcript, meeting_id)
    with _summary_lock:
        summary = artifacts.load_summary(meeting_id) or {}
        summary["short_summary"] = text
        artifacts.save_summary(meeting_id, summary)
    return jsonify(summary)


@bp.post("/meetings/<meeting_id>/action-items/<int:index>/toggle")
@login_required
def toggle_action_item(meeting_id, index):
    """Atur status selesai satu action item tanpa membuat ulang ringkasan."""
    record, error = common.load_meeting(meeting_id, edit=True)
    if error:
        return error
    if not record["recording"]:
        return jsonify({"error": "Recording not available yet"}), 404

    # baca-ubah-tulis summary.json: lock mencegah dua klik cepat saling menghapus.
    # ponytail: satu lock untuk semua, per rapat kalau suatu saat berebut
    with _summary_lock:
        summary = artifacts.load_summary(meeting_id)
        if summary is None:
            return jsonify({"error": "No summary for this meeting yet"}), 404

        items = summary.get("action_items") or []
        if index < 0 or index >= len(items):
            return jsonify({"error": "Invalid action item index"}), 400

        done = (request.get_json(silent=True) or {}).get("done")
        items[index]["done"] = bool(done) if done is not None else not items[index].get("done", False)
        artifacts.save_summary(meeting_id, summary)
    report_stats.invalidate_action_item_cache(session["user_id"])
    return jsonify(summary)


@bp.put("/meetings/<meeting_id>/action-items")
@login_required
def replace_action_items(meeting_id):
    """Ganti seluruh daftar action item ({"items": [{task, assignee, due, done}]})."""
    _, error = common.load_meeting(meeting_id, edit=True)
    if error:
        return error
    raw = (request.get_json(silent=True) or {}).get("items")
    if not isinstance(raw, list):
        return jsonify({"error": "items must be a list"}), 400

    def text(value):
        return (value.strip() or None) if isinstance(value, str) else None

    items = []
    for it in raw:
        task = text(it.get("task")) if isinstance(it, dict) else None
        if not task:
            return jsonify({"error": "Setiap action item butuh isi tugas"}), 400
        items.append(
            {"task": task, "assignee": text(it.get("assignee")), "due": text(it.get("due")), "done": bool(it.get("done"))}
        )

    with _summary_lock:
        summary = artifacts.load_summary(meeting_id)
        if summary is None:
            return jsonify({"error": "No summary for this meeting yet"}), 404
        summary["action_items"] = items
        artifacts.save_summary(meeting_id, summary)
    report_stats.invalidate_action_item_cache(session["user_id"])
    return jsonify(summary)


@bp.post("/meetings/<meeting_id>/knowledge-base")
@login_required
def meeting_knowledge_base(meeting_id):
    """Masukkan atau keluarkan rapat dari Knowledge Base ({"enabled": bool})."""
    _, error = common.load_meeting(meeting_id, edit=True)
    if error:
        return error
    enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
    if enabled:
        # menyalakan butuh Pro/Team, mematikan selalu boleh (turun paket tidak membuat rapat tersangkut)
        if not common.kb_allowed(session["user_id"]):
            return jsonify({"error": "Knowledge Base adalah fitur paket Pro/Team. Upgrade untuk memakainya."}), 402
        summary = artifacts.load_summary(meeting_id)
        if summary is None:
            return jsonify({"error": "No summary for this meeting yet"}), 404
        knowledge_base.index_meeting(meeting_id, summary)
    else:
        knowledge_base.remove_meeting(meeting_id)
    meetings_store.update_meeting(meeting_id, in_kb=enabled)
    return jsonify({"in_kb": enabled})


@bp.get("/knowledge-base/search")
@login_required
def knowledge_base_search():
    """Pencarian semantik di rapat yang dimasukkan user ke Knowledge Base, plus satu jawaban singkat dari
    GPT-4o mini. `results` tetap dikembalikan walau jawabannya gagal."""
    if not common.kb_allowed(session["user_id"]):
        return jsonify({"error": "Knowledge Base adalah fitur paket Pro/Team. Upgrade untuk memakainya."}), 402

    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "q is required"}), 400

    # hanya rapat yang bisa dilihat user ini dan sudah di-opt in
    allowed = [m["id"] for m in meetings_store.list_meetings(session["user_id"]) if m.get("in_kb")]
    matches = knowledge_base.search(query, allowed)
    results = []
    for m in matches:
        meeting = meetings_store.get_meeting(m["meeting_id"])
        if meeting is None:
            continue  # potongan basi dari rapat yang sudah dihapus, lewati saja jangan error
        results.append(
            {
                "meeting_id": m["meeting_id"],
                "meeting_title": meeting["title"],
                "meeting_created_at": meeting["created_at"],
                "meeting_platform": meeting["platform"],
                "kind": m["kind"],
                "text": m["text"],
                "similarity": m["similarity"],
            }
        )
    return jsonify({"answer": knowledge_base.answer(query, results), "results": results})


@bp.post("/meetings/<meeting_id>/share-team")
@login_required
def share_meeting_with_team(meeting_id):
    """Opt in per rapat ({"enabled": bool}), ada di team tidak otomatis membagikan apa pun."""
    record = meetings_store.get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if record.get("user_id") != session["user_id"]:
        return jsonify({"error": "Hanya pemilik rapat yang bisa membagikannya"}), 403
    enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
    meetings_store.update_meeting(meeting_id, shared_with_team=enabled)
    return jsonify({"shared_with_team": enabled})


@bp.post("/meetings/<meeting_id>/process")
@login_required
def meeting_process_now(meeting_id):
    """Kirim rekaman ke transkriber: yang disimpan tanpa AI (status "limited") atau yang pemrosesannya gagal ("failed",
    proses ulang). Kuota mingguan Free tetap berlaku untuk rekaman bot, upload tidak terkena kuota mingguan."""
    record, error = common.load_meeting(meeting_id, edit=True)
    if error:
        return error
    if record["status"] not in ("limited", "failed"):
        return jsonify({"error": "Rapat ini tidak menunggu pemrosesan"}), 409
    if not record.get("recording"):
        return jsonify({"error": "Rapat ini tidak punya rekaman untuk diproses (bot gagal bergabung)"}), 409
    duration = record.get("duration_minutes") or 0
    weekly = common.weekly_quota(record["user_id"]) if record.get("user_id") and record.get("url") else None
    if weekly:
        remaining = weekly["remaining"]
        # rapat gagal minggu ini sudah ikut terhitung di "used", jangan ditagih dua kali
        if record["status"] == "failed" and datetime.strptime(record["created_at"], "%Y-%m-%dT%H:%M:%S") >= common.week_start():
            remaining += duration
        if duration > remaining:
            return jsonify({"error": f"Sisa kuota minggu ini {remaining:g} menit, rapat ini {duration:g} menit. Upgrade ke Pro untuk memprosesnya."}), 402
    meetings_store.update_meeting(meeting_id, status="processing")
    job_queue.enqueue_transcription(meeting_id, record["recording"], record.get("estimated_participants"))
    return jsonify({"status": "processing"})


_LIVE_STATUSES = ("joining", "recording", "stopping", "processing")


@bp.delete("/meetings/<meeting_id>")
@login_required
def delete_meeting_route(meeting_id):
    """Hapus folder R2, potongan Knowledge Base, dan baris db. Hanya pemilik atau super admin, dan tidak saat rapat
    masih berjalan. Baris usage tetap ada supaya total biaya admin tidak menyusut."""
    record = meetings_store.get_meeting(meeting_id)
    if record is None:
        return jsonify({"error": "Meeting not found"}), 404
    if session.get("role") != "super_admin" and record.get("user_id") != session["user_id"]:
        return jsonify({"error": "Hanya pemilik rapat yang bisa menghapusnya"}), 403
    if record["status"] in _LIVE_STATUSES:
        return jsonify({"error": "Rapat masih berjalan, tunggu sampai selesai"}), 409

    # R2 dulu: kalau gagal tidak ada yang lain disentuh dan hapus bisa diulang.
    storage.delete_prefix(f"{meeting_id}/")
    try:
        knowledge_base.remove_meeting(meeting_id)
    except Exception as e:
        print(f"[knowledge_base] failed to remove meeting {meeting_id}: {e}")
    meetings_store.delete_meeting(meeting_id)
    return jsonify({"deleted": meeting_id})
