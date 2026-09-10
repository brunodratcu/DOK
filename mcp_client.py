"""
mcp_client.py — wrapper síncrono em cima do cliente MCP assíncrono
(fastmcp), pra ser chamado de dentro de rotas Flask comuns sem
precisar reescrever o app inteiro como async.

Conecta na pasta dok-tools/ (projeto independente, path configurável
no config.yaml) via stdio — o DOK inicia o processo do servidor
sozinho quando precisa, e derruba depois.
"""
import asyncio
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport


def _run(coro):
    return asyncio.run(coro)


def _make_client(server_path: str, python_cmd: str = None):
    if python_cmd:
        # Roda o servidor com o Python (e dependências) DELE, não o do DOK —
        # útil se algum dia voltar a usar venvs separados.
        transport = PythonStdioTransport(server_path, python_cmd=python_cmd)
        return Client(transport)
    return Client(Path(server_path))


def list_tools(server_path: str, python_cmd: str = None):
    """Retorna as ferramentas disponíveis no servidor, já convertidas
    pro formato que a API da Anthropic espera em `tools=[...]`."""
    async def _list():
        client = _make_client(server_path, python_cmd)
        async with client:
            tools = await client.list_tools()
            return [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
    return _run(_list())


def call_tool(server_path: str, name: str, arguments: dict, python_cmd: str = None):
    """Chama uma ferramenta específica e devolve o resultado (dict)."""
    async def _call():
        client = _make_client(server_path, python_cmd)
        async with client:
            result = await client.call_tool(name, arguments)
            return result.data
    return _run(_call())
