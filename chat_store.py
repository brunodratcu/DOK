"""
Armazenamento simples das conversas do DOK, em JSON.
Sem banco de dados — leve o suficiente pro Pi, fácil de inspecionar.
"""
import json
import os
import time
import uuid

import paths

CHATS_PATH = paths.data_path("data", "chats.json")


def _ensure_store():
    if not os.path.exists(CHATS_PATH):
        with open(CHATS_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)


def _load():
    _ensure_store()
    with open(CHATS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data):
    with open(CHATS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_chats():
    """Lista conversas ordenadas da mais recente pra mais antiga."""
    data = _load()
    items = []
    for chat_id, chat in data.items():
        last_msg = chat["messages"][-1]["content"] if chat["messages"] else ""
        items.append({
            "id": chat_id,
            "title": chat.get("title", "Nova conversa"),
            "preview": last_msg[:60],
            "updated_at": chat.get("updated_at", 0),
        })
    items.sort(key=lambda c: c["updated_at"], reverse=True)
    return items


def get_chat(chat_id):
    data = _load()
    return data.get(chat_id)


def create_chat(first_message=None):
    data = _load()
    chat_id = str(uuid.uuid4())
    title = (first_message[:40] + "…") if first_message and len(first_message) > 40 \
        else (first_message or "Nova conversa")
    data[chat_id] = {
        "title": title,
        "messages": [],
        "updated_at": time.time(),
    }
    _save(data)
    return chat_id


def add_message(chat_id, role, content):
    data = _load()
    if chat_id not in data:
        return False
    data[chat_id]["messages"].append({
        "role": role,
        "content": content,
        "ts": time.time(),
    })
    data[chat_id]["updated_at"] = time.time()
    _save(data)
    return True


def delete_chat(chat_id):
    data = _load()
    if chat_id in data:
        del data[chat_id]
        _save(data)
        return True
    return False
