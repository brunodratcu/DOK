"""
thread_store.py — histórico de uma conversa contínua única (não uma
lista de várias conversas). Usado tanto pela aba Chats quanto pela
Projetos — cada uma aponta pro seu próprio arquivo.
"""
import json
import os


def _ensure(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"messages": []}, f)


def get_history(path):
    _ensure(path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["messages"]


def add_exchange(path, user_text, assistant_text):
    _ensure(path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["messages"].append({"role": "user", "content": user_text})
    data["messages"].append({"role": "assistant", "content": assistant_text})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_history(path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"messages": []}, f)
