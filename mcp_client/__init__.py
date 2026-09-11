"""Pacote do cliente MCP (conecta no servidor dok-tools). Reexporta
client.py pra manter `mcp_client.list_tools(...)` e `.call_tool(...)`
funcionando igual antes."""
from .client import list_tools, call_tool
