"""
migrate_chats_json_to_sqlite.py — roda UMA vez pra importar as
conversas antigas de data/chats.json pro novo data/chats.db.
Depois de confirmar que migrou certo, apague o chats.json.

Uso (sempre a partir da RAIZ do projeto, não de dentro de storage/):
    python -m storage.migrate_chats_json_to_sqlite
"""
import json
import os

from storage import chat_store  # já cria o schema do SQLite ao importar
import paths

OLD_JSON_PATH = paths.data_path("data", "chats.json")


def main():
    if not os.path.exists(OLD_JSON_PATH):
        print("Nenhum chats.json encontrado — nada pra migrar.")
        return

    with open(OLD_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data:
        print("chats.json vazio — nada pra migrar.")
        return

    # ordena pelas mais antigas primeiro, pra respeitar o limite de 12
    # do jeito certo (as mais recentes sobrevivem se passar do teto)
    items = sorted(data.items(), key=lambda kv: kv[1].get("updated_at", 0))

    imported = 0
    for chat_id, chat in items:
        with chat_store._connect() as conn:
            chat_store._enforce_limit(conn)
            conn.execute(
                "INSERT OR REPLACE INTO conversations (id, title, updated_at) VALUES (?,?,?)",
                (chat_id, chat.get("title", "Nova conversa"), chat.get("updated_at", 0)),
            )
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (chat_id,))
            for m in chat.get("messages", []):
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
                    (chat_id, m["role"], m["content"], chat.get("updated_at", 0)),
                )
        imported += 1

    print(f"Migradas {imported} conversa(s) pra {chat_store.DB_PATH}")
    print(f"Confira com a UI e depois apague: {OLD_JSON_PATH}")


if __name__ == "__main__":
    main()
