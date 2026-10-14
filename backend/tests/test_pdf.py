"""Ketiga ekspor PDF terbentuk dengan data palsu biasa (tanpa database).

Jalankan: python -m tests.test_pdf   (dari backend/)"""
from pipeline import report_pdf

counts = {"today": 0, "this_week": 1, "this_month": 2, "total": 3, "completed": 2, "failed": 1}
meetings = [
    {"title": "Rapat <A> & B", "platform": "zoom", "created_at": "2026-10-01T10:00:00", "duration_minutes": 12.5, "status": "completed",
     "summary": {"short_summary": "Singkat.", "topics_discussed": ["x"], "key_decisions": ["y"], "action_items": [{"task": "z", "done": True}]}},
    {"title": "Tanpa ringkasan", "platform": "upload", "created_at": "2026-10-02T10:00:00", "duration_minutes": None, "status": "failed"},
]

admin = {"meetings": counts, "users_total": 4, "mrr_idr": 99000, "openai_cost": {"total_usd": 0.5, "call_count": 7}, "storage_bytes": None}
assert report_pdf.generate_report(admin, meetings, "Admin").startswith(b"%PDF")

user = {"meetings": counts, "total_duration_minutes": 90, "platform_counts": {"zoom": 2, "upload": 1}}
assert report_pdf.generate_user_report(user, meetings, "User").startswith(b"%PDF")

analysis = {"about_a": "Rapat A membahas x.", "about_b": "Rapat B membahas y.", "similarities": [], "differences": ["beda"], "progress": [], "conclusion": "ok"}
assert report_pdf.generate_comparison_report(meetings[0], meetings[1], "User", analysis).startswith(b"%PDF")
assert report_pdf.generate_comparison_report(meetings[0], meetings[0], "User").startswith(b"%PDF")
print("ok")
