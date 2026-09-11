"""
chat_store.py — múltiplas conversas, persistidas num único JSON.
Cada conversa: id, título (derivado da primeira mensagem), mensagens,
timestamp de atualização (pra ordenar a lista da mais recente).
"""
import json
import os
import time
import uuid

import paths

CHATS_PATH = paths.data_path("data", "chats.json")


def _ensure():
    os.makedirs(os.path.dirname(CHATS_PATH), exist_ok=True)
    if not os.path.exists(CHATS_PATH):
        with open(CHATS_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)


def _load():
    _ensure()
    with open(CHATS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data):
    with open(CHATS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_chats():
    """Lista as conversas, mais recente primeiro."""
    data = _load()
    items = []
    for chat_id, chat in data.items():
        last = chat["messages"][-1]["content"] if chat["messages"] else ""
        items.append({
            "id": chat_id,
            "title": chat.get("title", "Nova conversa"),
            "preview": last[:60],
            "updated_at": chat.get("updated_at", 0),
        })
    items.sort(key=lambda c: c["updated_at"], reverse=True)
    return items


def get_chat(chat_id):
    return _load().get(chat_id)


def create_chat():
    data = _load()
    chat_id = str(uuid.uuid4())
    data[chat_id] = {"title": "Nova conversa", "messages": [], "updated_at": time.time()}
    _save(data)
    return chat_id


def add_exchange(chat_id, user_text, assistant_text):
    data = _load()
    if chat_id not in data:
        return False
    chat = data[chat_id]
    chat["messages"].append({"role": "user", "content": user_text})
    chat["messages"].append({"role": "assistant", "content": assistant_text})
    chat["updated_at"] = time.time()
    # título vira a primeira mensagem do usuário, só na primeira troca
    if chat["title"] == "Nova conversa" and len(chat["messages"]) == 2:
        chat["title"] = user_text[:40] + ("…" if len(user_text) > 40 else "")
    _save(data)
    return True


def delete_chat(chat_id):
    data = _load()
    if chat_id in data:
        del data[chat_id]
        _save(data)
        return True
    return False
