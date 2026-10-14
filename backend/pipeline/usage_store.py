from datetime import datetime

import psycopg2.extras

from .db import register_schema, with_conn

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_usage (
    id SERIAL PRIMARY KEY,
    meeting_id TEXT,
    call_type TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL
);
"""
register_schema(_TABLE_SQL)

# USD per 1 juta token, ditulis langsung (OpenAI tidak punya API harga). Cek openai.com/api/pricing kalau terlihat janggal
_PRICING_PER_1M_USD = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


def log_usage(meeting_id: str | None, call_type: str, model: str, usage) -> None:
    """Catat pemakaian token (`response.usage`) dari satu panggilan OpenAI."""

    def _do(conn):
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_usage (meeting_id, call_type, model, prompt_tokens, completion_tokens, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (meeting_id, call_type, model, usage.prompt_tokens, usage.completion_tokens, datetime.now()),
            )
        conn.commit()

    with_conn(_do)


def total_cost() -> dict:
    """{"total_usd", "call_count", "since"}. `since` adalah panggilan pertama yang tercatat: panggilan lama tidak punya data
    token dan tidak diperkirakan, jadi dashboard menulis "sejak <tanggal>", bukan mengklaim sepanjang waktu."""

    def _do(conn):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT model, SUM(prompt_tokens) AS pt, SUM(completion_tokens) AS ct, "
                "COUNT(*) AS n, MIN(created_at) AS since FROM api_usage GROUP BY model"
            )
            return cur.fetchall()

    rows = with_conn(_do)
    total_usd = 0.0
    call_count = 0
    since = None
    for row in rows:
        pricing = _PRICING_PER_1M_USD.get(row["model"], {"input": 0, "output": 0})
        total_usd += (row["pt"] or 0) / 1_000_000 * pricing["input"] + (row["ct"] or 0) / 1_000_000 * pricing["output"]
        call_count += row["n"]
        if row["since"] and (since is None or row["since"] < since):
            since = row["since"]
    return {
        "total_usd": round(total_usd, 4),
        "call_count": call_count,
        "since": since.strftime("%Y-%m-%dT%H:%M:%S") if since else None,
    }
