import os
from datetime import datetime, timedelta, timezone

import requests

# Per https://docs.xendit.co/apidocs/create-session and
# https://docs.xendit.co/docs/how-subscriptions-work — a Payment Session with
# session_type=SUBSCRIPTION does customer creation + payment-method-linking +
# recurring-plan-creation in one hosted checkout flow, instead of manually
# orchestrating separate Customer / Payment Token / Recurring Plan API calls.
_BASE_URL = "https://api.xendit.co"


def _auth():
    # Xendit uses HTTP Basic auth with the secret key as the username and an
    # empty password.
    return (os.environ["XENDIT_SECRET_KEY"], "")


def create_subscription_session(reference_id: str, plan_amount: int, email: str, success_url: str, cancel_url: str) -> dict:
    """Creates the hosted checkout session. Returns Xendit's response dict —
    notably `payment_link_url` (redirect the user here) and
    `payment_session_id` (store it; the payment_session.completed webhook
    references it back so we know which pending checkout to activate)."""
    # Must be >= the checkout session's own expiry (Xendit rejects
    # anchor_date <= expires_at), so "now" isn't valid — push the first
    # charge out a day, past whatever expiry window the session gets. Also
    # capped at day 28 (Xendit doesn't accept a higher day-of-month for a
    # monthly anchor).
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
            # Required by Xendit whenever customer.type is INDIVIDUAL — a
            # placeholder name until this app has real user accounts/profiles
            # to pull one from (see CLAUDE.md's "Known POC gaps").
            "individual_detail": {"given_names": "Notulis"},
        },
        "success_return_url": success_url,
        "cancel_return_url": cancel_url,
    }
    resp = requests.post(f"{_BASE_URL}/sessions", json=body, auth=_auth(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def deactivate_recurring_plan(plan_id: str) -> dict:
    """Stops future charges for a plan (recurring.plan.inactivated webhook
    fires on success) — per
    https://docs.xendit.co/apidocs/deactivate-subscription-plan-2."""
    resp = requests.patch(f"{_BASE_URL}/recurring/plans/{plan_id}", json={"status": "INACTIVE"}, auth=_auth(), timeout=15)
    resp.raise_for_status()
    return resp.json()
