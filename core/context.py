"""Contexto mínimo: limita histórico e mantém a mensagem do projeto em formato previsível."""
def build_history(chat, limit=12):
    messages = chat.get("messages", [])[-limit:]
    return [{"role": m["role"], "content": m["content"]} for m in messages]
