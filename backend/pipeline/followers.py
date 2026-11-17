"""Rapat salinan: User kedua yang memasukkan tautan yang sama dengan rapat yang sedang atau baru direkam tidak memicu bot
kedua (hemat sumber daya, dua bot di rapat yang sama merekam hal yang sama). Ia mendapat rapat sendiri berisi salinan hasil
rapat sumber, jadi perubahannya tidak mengganggu pemilik asli. Rekamannya tetap satu berkas yang ditunjuk bersama."""

from . import artifacts, meetings_store, process


def _copy_artifacts(source_id: str, follower_id: str) -> None:
    for load, save in (
        (artifacts.load_transcript, artifacts.save_transcript),
        (artifacts.load_fixed_transcript, artifacts.save_fixed_transcript),
        (artifacts.load_segments, artifacts.save_segments),
        (artifacts.load_summary, artifacts.save_summary),
    ):
        data = load(source_id)
        if data:
            save(follower_id, data)


def finish_follower(follower_id: str, source: dict) -> None:
    """Salin hasil rapat sumber ke rapat salinan, tandai selesai, lalu kabari pemiliknya lewat email."""
    _copy_artifacts(source["id"], follower_id)
    meetings_store.update_meeting(
        follower_id, status="completed", recording=source["recording"], duration_minutes=source.get("duration_minutes")
    )
    summary = artifacts.load_summary(follower_id)
    if summary:
        process.notify_meeting_ready(follower_id, summary, shared=True)


def copy_results(source_id: str) -> None:
    """Dipanggil setelah rapat sumber selesai diproses: isi semua rapat salinan yang menunggu. Satu yang gagal tidak
    menghentikan yang lain."""
    source = meetings_store.get_meeting(source_id)
    if source is None:
        return
    for follower in meetings_store.list_followers(source_id):
        try:
            finish_follower(follower["id"], source)
        except Exception as e:
            print(f"[followers] failed to copy {source_id} to {follower['id']}: {e}")
