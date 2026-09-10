"""
projects_store.py — histórico da aba Projetos.

Diferente do chat_store.py (várias conversas separadas), Projetos é
uma sessão única e contínua — faz mais sentido pra tarefas agenticas
recorrentes (diagnóstico de rede, etc.) do que múltiplas conversas
paralelas. Pode evoluir pra múltiplas sessões depois, se precisar.
"""
import json

import paths

PROJECTS_PATH = paths.data_path("data", "projects.json")


def _ensure_store():
    import os
    if not os.path.exists(PROJECTS_PATH):
        with open(PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump({"messages": []}, f)


def get_history():
    _ensure_store()
    with open(PROJECTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["messages"]


def add_exchange(user_text, assistant_text):
    _ensure_store()
    with open(PROJECTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["messages"].append({"role": "user", "content": user_text})
    data["messages"].append({"role": "assistant", "content": assistant_text})
    with open(PROJECTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_history():
    with open(PROJECTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"messages": []}, f)
