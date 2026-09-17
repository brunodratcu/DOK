"""
chat_store.py — múltiplas conversas, persistidas em SQLite.
Mesma interface pública de antes (list_chats, get_chat, create_chat,
add_exchange, delete_chat) — só a implementação interna mudou de JSON
pra SQLite. Limite de MAX_CHATS conversas: ao criar uma nova além do
limite, apaga a mais antiga (FIFO por updated_at).
"""
import sqlite3
import time
import uuid
from contextlib import contextmanager

import paths

DB_PATH = paths.data_path("data", "chats.db")
MAX_CHATS = 12

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Nova conversa',
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_schema():
    with _connect() as conn:
        conn.executescript(_SCHEMA)


_ensure_schema()


def list_chats():
    """Lista as conversas, mais recente primeiro."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        items = []
        for row in rows:
            last = conn.execute(
                "SELECT content FROM messages WHERE conversation_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            preview = (last["content"] if last else "")[:60]
            items.append({
                "id": row["id"], "title": row["title"],
                "preview": preview, "updated_at": row["updated_at"],
            })
        return items


def get_chat(chat_id):
    with _connect() as conn:
        conv = conn.execute(
            "SELECT title, updated_at FROM conversations WHERE id = ?", (chat_id,)
        ).fetchone()
        if not conv:
            return None
        msgs = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (chat_id,),
        ).fetchall()
        return {
            "title": conv["title"],
            "updated_at": conv["updated_at"],
            "messages": [{"role": m["role"], "content": m["content"]} for m in msgs],
        }


def _enforce_limit(conn):
    count = conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"]
    if count >= MAX_CHATS:
        oldest = conn.execute(
            "SELECT id FROM conversations ORDER BY updated_at ASC LIMIT 1"
        ).fetchone()
        if oldest:
            conn.execute("DELETE FROM conversations WHERE id = ?", (oldest["id"],))


def create_chat():
    chat_id = str(uuid.uuid4())
    with _connect() as conn:
        _enforce_limit(conn)
        conn.execute(
            "INSERT INTO conversations (id, title, updated_at) VALUES (?, ?, ?)",
            (chat_id, "Nova conversa", time.time()),
        )
    return chat_id


def add_exchange(chat_id, user_text, assistant_text):
    now = time.time()
    with _connect() as conn:
        conv = conn.execute(
            "SELECT title FROM conversations WHERE id = ?", (chat_id,)
        ).fetchone()
        if not conv:
            return False

        msg_count = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE conversation_id = ?", (chat_id,)
        ).fetchone()["c"]

        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
            (chat_id, "user", user_text, now),
        )
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
            (chat_id, "assistant", assistant_text, now),
        )

        new_title = conv["title"]
        if conv["title"] == "Nova conversa" and msg_count == 0:
            new_title = user_text[:40] + ("…" if len(user_text) > 40 else "")

        conn.execute(
            "UPDATE conversations SET updated_at = ?, title = ? WHERE id = ?",
            (now, new_title, chat_id),
        )
    return True


def delete_chat(chat_id):
    with _connect() as conn:
        cur = conn.execute("DELETE FROM conversations WHERE id = ?", (chat_id,))
        return cur.rowcount > 0
