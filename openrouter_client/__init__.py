"""Pacote do cliente da OpenRouter. Reexporta client.py pra manter
`openrouter_client.send_message(...)` e `.list_free_models(...)`
funcionando igual antes."""
from .client import send_message, list_free_models
