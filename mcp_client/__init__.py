"""Pacote do cliente MCP (conecta no servidor dok-tools). Reexporta
client.py — MCPSession é o uso recomendado (uma conexão por turno);
list_tools/call_tool ficam pra chamada avulsa isolada (ex: dok_cli.py)."""
from .client import list_tools, call_tool, MCPSession
