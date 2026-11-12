"""/billing/*: paket langganan lewat Xendit (checkout, batal, webhook)."""

import os
import uuid

import requests
from flask import Blueprint, jsonify, redirect, request, session

from pipeline import auth_store, billing_store
from pipeline.xendit_client import create_subscription_session, deactivate_recurring_plan

from . import common
from .common import login_required

bp = Blueprint("billing", __name__)


@bp.get("/billing/return")
def billing_return():
    status = request.args.get("status", "cancel")
    if status == "success":
        return redirect(f"{common.LOCAL_FRONTEND_URL}/checkout-sukses")
    return redirect(f"{common.LOCAL_FRONTEND_URL}/billing?checkout=cancel")


@bp.get("/billing/status")
@login_required
def billing_status():
    plan, inherited = billing_store.effective_plan(session["user_id"])
    return jsonify(
        {
            **billing_store.get_subscription(session["user_id"]),
            "plan": plan,
            "inherited_from_team": inherited,
            "weekly_quota": common.weekly_quota(session["user_id"]),
        }
    )


@bp.post("/billing/checkout")
@login_required
def billing_checkout():
    """Mulai checkout Xendit dan kembalikan url tujuan user. Paket baru berubah saat
    webhook melaporkan payment_session.completed."""
    plan = (request.get_json(force=True) or {}).get("plan")
    if plan not in billing_store.PLAN_PRICES:
        return jsonify({"error": f"unknown plan '{plan}', expected one of {list(billing_store.PLAN_PRICES)}"}), 400

    user_id = session["user_id"]
    reference_id = f"{user_id}-{plan}-{uuid.uuid4().hex[:8]}"
    # placeholder kalau common.PUBLIC_URL tidak diisi: checkout tetap jalan tapi user tidak kembali ke aplikasi
    return_base = common.PUBLIC_URL or "https://example.com"
    try:
        # tidak dinamai `session`, itu milik flask
        checkout_session = create_subscription_session(
            reference_id=reference_id,
            plan_amount=billing_store.PLAN_PRICES[plan],
            email=auth_store.get_user(user_id)["email"],
            success_url=f"{return_base}/billing/return?status=success",
            cancel_url=f"{return_base}/billing/return?status=cancel",
        )
    except requests.HTTPError as e:
        return jsonify({"error": f"Xendit error: {e.response.text}"}), 502

    billing_store.start_checkout(plan, checkout_session["payment_session_id"], account_id=user_id)
    return jsonify({"checkout_url": checkout_session["payment_link_url"]})


@bp.post("/billing/checkout/cancel")
@login_required
def billing_checkout_cancel():
    """User keluar dari halaman Xendit, lupakan checkout yang belum dibayar."""
    billing_store.clear_pending(session["user_id"])
    return jsonify(billing_store.get_subscription(session["user_id"]))


@bp.post("/billing/cancel")
@login_required
def billing_cancel():
    """Turun ke Free di akhir periode berbayar. Menonaktifkan plan Xendit menghentikan tagihan berikutnya,
    jadi ulangi manual kalau itu gagal."""
    plan_id = billing_store.cancel_subscription(session["user_id"])
    if plan_id:
        try:
            deactivate_recurring_plan(plan_id)
        except requests.HTTPError as e:
            print(f"[billing] failed to deactivate Xendit plan {plan_id}: {e}")
    return jsonify(billing_store.get_subscription(session["user_id"]))


@bp.post("/billing/webhook")
def billing_webhook():
    """Event siklus Xendit, diverifikasi dengan token statis dari dashboard. Nama field-nya perkiraan dari dokumen mereka,
    event mentahnya dicetak supaya bisa dicek."""
    token = request.headers.get("x-callback-token")
    if not token or token != os.environ.get("XENDIT_WEBHOOK_TOKEN"):
        return jsonify({"error": "invalid webhook token"}), 401

    event = request.get_json(force=True) or {}
    print(f"[billing] webhook received: {event}")
    event_type = event.get("event")
    data = event.get("data", {})

    if event_type == "payment_session.completed":
        session_id = data.get("payment_session_id") or data.get("id")
        plan_id = data.get("recurring_plan_id")
        if session_id and plan_id:
            billing_store.activate_subscription(session_id, plan_id)
    elif event_type == "recurring.cycle.succeeded":
        plan_id = data.get("recurring_plan_id") or data.get("plan_id")
        if plan_id:
            billing_store.extend_subscription(plan_id)
    elif event_type == "recurring.cycle.failed":
        plan_id = data.get("recurring_plan_id") or data.get("plan_id")
        if plan_id:
            billing_store.mark_past_due(plan_id)

    return jsonify({"received": True})
