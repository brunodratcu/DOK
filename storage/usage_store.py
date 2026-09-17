"""Monitoramento local do uso da Anthropic pelo DOK.

Registra somente chamadas feitas pelo próprio DOK e calcula uma estimativa
de custo a partir do bloco ``usage`` devolvido pela Messages API.
Não usa Admin API e não tenta inferir o saldo da conta.
"""
from datetime import datetime, timezone
import os
import sqlite3

import paths

DB_PATH = paths.data_path("data", "usage.db")

# USD por 1 milhão de tokens. Fonte: tabela de preços atual da Claude API.
# O lookup usa prefixo para aceitar IDs datados como claude-haiku-4-5-20251001.
PRICING = {
    "claude-haiku-4-5": {"input": 1.00, "cache_5m": 1.25, "cache_1h": 2.00, "cache_read": 0.10, "output": 5.00},
    "claude-sonnet-5": {"input": 2.00, "cache_5m": 2.50, "cache_1h": 4.00, "cache_read": 0.20, "output": 10.00},
    "claude-sonnet-4-6": {"input": 3.00, "cache_5m": 3.75, "cache_1h": 6.00, "cache_read": 0.30, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "cache_5m": 3.75, "cache_1h": 6.00, "cache_read": 0.30, "output": 15.00},
    "claude-opus-4-7": {"input": 5.00, "cache_5m": 6.25, "cache_1h": 10.00, "cache_read": 0.50, "output": 25.00},
    "claude-opus-4-6": {"input": 5.00, "cache_5m": 6.25, "cache_1h": 10.00, "cache_read": 0.50, "output": 25.00},
    "claude-opus-4-5": {"input": 5.00, "cache_5m": 6.25, "cache_1h": 10.00, "cache_read": 0.50, "output": 25.00},
    "claude-opus-4-1": {"input": 15.00, "cache_5m": 18.75, "cache_1h": 30.00, "cache_read": 1.50, "output": 75.00},
}


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                chat_id TEXT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
                cache_read_input_tokens INTEGER NOT NULL DEFAULT 0,
                cache_5m_input_tokens INTEGER NOT NULL DEFAULT 0,
                cache_1h_input_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_usd REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_created_at ON usage_events(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_chat_id ON usage_events(chat_id)")


def _int(value):
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _pricing_for(model):
    model = (model or "").lower()
    for prefix, pricing in PRICING.items():
        if model.startswith(prefix):
            return pricing
    return None


def calculate_cost(model, usage):
    pricing = _pricing_for(model)
    if not pricing:
        return None

    cache_creation = usage.get("cache_creation") or {}
    input_tokens = _int(usage.get("input_tokens"))
    output_tokens = _int(usage.get("output_tokens"))
    cache_read = _int(usage.get("cache_read_input_tokens"))
    cache_5m = _int(cache_creation.get("ephemeral_5m_input_tokens"))
    cache_1h = _int(cache_creation.get("ephemeral_1h_input_tokens"))

    total = (
        input_tokens * pricing["input"]
        + cache_5m * pricing["cache_5m"]
        + cache_1h * pricing["cache_1h"]
        + cache_read * pricing["cache_read"]
        + output_tokens * pricing["output"]
    ) / 1_000_000
    return round(total, 8)


def record_usage(chat_id, provider, model, usage):
    """Persiste um evento. Falhas de persistência não devem quebrar o chat."""
    try:
        _ensure_db()
        usage = usage or {}
        cache_creation = usage.get("cache_creation") or {}
        cache_creation_total = _int(usage.get("cache_creation_input_tokens"))
        cache_5m = _int(cache_creation.get("ephemeral_5m_input_tokens"))
        cache_1h = _int(cache_creation.get("ephemeral_1h_input_tokens"))

        # Compatibilidade com respostas que trazem apenas o total de criação.
        if not cache_5m and not cache_1h:
            cache_5m = cache_creation_total

        input_tokens = _int(usage.get("input_tokens"))
        output_tokens = _int(usage.get("output_tokens"))
        cache_read = _int(usage.get("cache_read_input_tokens"))
        estimated_cost = calculate_cost(model, usage)

        with _connect() as conn:
            conn.execute("""
                INSERT INTO usage_events (
                    created_at, chat_id, provider, model,
                    input_tokens, output_tokens,
                    cache_creation_input_tokens, cache_read_input_tokens,
                    cache_5m_input_tokens, cache_1h_input_tokens,
                    estimated_cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(), chat_id, provider, model,
                input_tokens, output_tokens, cache_creation_total, cache_read,
                cache_5m, cache_1h, estimated_cost,
            ))

        return {
            "stored": True,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation_total,
            "cache_read_input_tokens": cache_read,
            "estimated_cost_usd": estimated_cost,
        }
    except Exception as exc:
        return {"stored": False, "error": str(exc)}


def _sum(conn, where="", params=()):
    row = conn.execute(f"""
        SELECT COUNT(*) AS requests,
               COALESCE(SUM(input_tokens), 0) AS input_tokens,
               COALESCE(SUM(output_tokens), 0) AS output_tokens,
               COALESCE(SUM(cache_creation_input_tokens), 0) AS cache_creation_input_tokens,
               COALESCE(SUM(cache_read_input_tokens), 0) AS cache_read_input_tokens,
               COALESCE(SUM(cache_5m_input_tokens), 0) AS cache_5m_input_tokens,
               COALESCE(SUM(cache_1h_input_tokens), 0) AS cache_1h_input_tokens,
               SUM(estimated_cost_usd) AS estimated_cost_usd
        FROM usage_events {where}
    """, params).fetchone()
    result = dict(row)
    result["estimated_cost_usd"] = result["estimated_cost_usd"]
    result["total_tokens"] = (
        result["input_tokens"]
        + result["output_tokens"]
        + result["cache_creation_input_tokens"]
        + result["cache_read_input_tokens"]
    )
    return result


def _model_breakdown(conn, where="", params=()):
    rows = conn.execute(f"""
        SELECT model, COUNT(*) AS requests,
               COALESCE(SUM(input_tokens), 0) AS input_tokens,
               COALESCE(SUM(output_tokens), 0) AS output_tokens,
               COALESCE(SUM(cache_creation_input_tokens), 0) AS cache_creation_input_tokens,
               COALESCE(SUM(cache_read_input_tokens), 0) AS cache_read_input_tokens,
               SUM(estimated_cost_usd) AS estimated_cost_usd
        FROM usage_events {where}
        GROUP BY model
        ORDER BY COALESCE(SUM(estimated_cost_usd), 0) DESC, model
    """, params).fetchall()
    return [dict(row) for row in rows]


def get_summary(monthly_budget_usd=0, warning_percent=80):
    _ensure_db()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_30_start = now.timestamp() - 30 * 24 * 60 * 60

    with _connect() as conn:
        today = _sum(conn, "WHERE created_at >= ?", (today_start.isoformat(),))
        month = _sum(conn, "WHERE created_at >= ?", (month_start.isoformat(),))
        last_30 = _sum(conn, "WHERE created_at >= ?", (datetime.fromtimestamp(last_30_start, timezone.utc).isoformat(),))
        models = _model_breakdown(conn, "WHERE created_at >= ?", (month_start.isoformat(),))

    budget = max(float(monthly_budget_usd or 0), 0)
    warning = min(max(float(warning_percent or 80), 0), 100)
    month_cost = float(month["estimated_cost_usd"] or 0)
    remaining = max(budget - month_cost, 0) if budget > 0 else None
    percent = (month_cost / budget * 100) if budget > 0 else None

    return {
        "scope": "local_dok",
        "notice": "Uso e custo são registrados somente pelas chamadas feitas pelo DOK; não representam o saldo da conta Anthropic.",
        "currency": "USD",
        "today": today,
        "month": month,
        "last_30_days": last_30,
        "models_this_month": models,
        "budget": {
            "monthly_usd": budget,
            "used_usd": round(month_cost, 8),
            "remaining_usd": round(remaining, 8) if remaining is not None else None,
            "percent_used": round(percent, 2) if percent is not None else None,
            "warning_percent": warning,
            "warning": bool(percent is not None and percent >= warning),
        },
        "updated_at": now.isoformat(),
    }
