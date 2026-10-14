import os
from datetime import datetime, timedelta, timezone

import requests

# Payment Session dengan session_type=SUBSCRIPTION: customer, metode pembayaran, dan plan berulang dalam satu
# checkout yang dihosting (docs.xendit.co/apidocs/create-session)
_BASE_URL = "https://api.xendit.co"


def _auth():
    # basic auth: secret key sebagai username, password kosong
    return (os.environ["XENDIT_SECRET_KEY"], "")


def create_subscription_session(reference_id: str, plan_amount: int, email: str, success_url: str, cancel_url: str) -> dict:
    """Buat checkout yang dihosting. Mengembalikan respons Xendit: `payment_link_url` untuk tujuan redirect dan
    `payment_session_id`, yang dikirim balik oleh webhook payment_session.completed."""
    # anchor_date harus setelah sesi kedaluwarsa, jadi tagihan pertama sehari lagi (dan paling tinggi tanggal 28,
    # Xendit tidak menerima tanggal lebih tinggi untuk anchor bulanan)
    anchor = datetime.now(timezone.utc) + timedelta(days=1)
    if anchor.day > 28:
        anchor = anchor.replace(day=28)
    anchor_date = anchor.strftime("%Y-%m-%dT%H:%M:%SZ")

    body = {
        "reference_id": reference_id,
        "session_type": "SUBSCRIPTION",
        "mode": "PAYMENT_LINK",
        "currency": "IDR",
        "amount": plan_amount,
        "country": "ID",
        "subscription": {
            "schedule": {
                "interval": "MONTH",
                "interval_count": 1,
                "anchor_date": anchor_date,
                "retry_interval": "DAY",
                "retry_interval_count": 3,
                "total_retry": 3,
                "failed_cycle_action": "STOP",
            },
        },
        "customer": {
            "type": "INDIVIDUAL",
            "reference_id": reference_id,
            "email": email,
            # wajib untuk customer INDIVIDUAL, placeholder sampai kita mengirim nama asli
            "individual_detail": {"given_names": "Notulis"},
        },
        "success_return_url": success_url,
        "cancel_return_url": cancel_url,
    }
    resp = requests.post(f"{_BASE_URL}/sessions", json=body, auth=_auth(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def deactivate_recurring_plan(plan_id: str) -> dict:
    """Hentikan tagihan berikutnya untuk sebuah plan (docs.xendit.co/apidocs/deactivate-subscription-plan-2)."""
    resp = requests.patch(f"{_BASE_URL}/recurring/plans/{plan_id}", json={"status": "INACTIVE"}, auth=_auth(), timeout=15)
    resp.raise_for_status()
    return resp.json()
