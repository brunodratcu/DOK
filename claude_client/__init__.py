"""Pacote do cliente da Anthropic. Reexporta o conteúdo de client.py
pra manter `claude_client.send_message(...)` funcionando igual antes,
mesmo com o código agora organizado em pasta."""
from .client import send_message
