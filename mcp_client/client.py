"""
mcp_client/client.py — cliente MCP (fastmcp) que conecta no
dok-tools via stdio.

IMPORTANTE: antes, cada chamada (list_tools, e cada call_tool)
abria e derrubava um processo novo do dok-tools. Num turno com
3-4 ferramentas chamadas em sequência, isso significa 3-4 processos
sendo criados e mortos rapidinho — no Windows isso é uma causa real
de erro "Connection closed" (spawn de subprocess via asyncio tem
comportamento diferente fora da thread principal, e resulta em
transporte instável sob esse padrão de uso). Agora a conexão é
aberta UMA VEZ por turno do agente e reaproveitada pra todas as
chamadas daquele turno — mais rápido e mais robusto.
"""
import asyncio
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

if sys.platform == "win32":
    # Subprocess (stdio) do MCP só funciona de forma confiável com o
    # ProactorEventLoop no Windows — garante isso mesmo se outra
    # biblioteca tiver alterado a policy padrão.
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def _make_client(server_path: str, python_cmd: str = None):
    if python_cmd:
        transport = PythonStdioTransport(server_path, python_cmd=python_cmd)
        return Client(transport)
    return Client(Path(server_path))


def _extract_result(result):
    """`.data` do fastmcp vem como None quando a ferramenta devolve
    um dict vazio ({}) — usa `.structured_content` como respaldo."""
    return result.data if result.data is not None else result.structured_content


# --- API de sessão única (uso recomendado — evita spawns repetidos) ---

class MCPSession:
    """Abra uma vez (`async with MCPSession(...) as session`), use
    `await session.list_tools()` e `await session.call_tool(...)`
    quantas vezes precisar, tudo na mesma conexão/processo.

    A conexão (spawn do processo + handshake) tenta de novo algumas
    vezes com espera crescente antes de desistir — no Windows, um
    antivírus escaneando o python.exe recém-criado (comum logo depois
    de extrair/atualizar arquivos) pode atrasar o handshake o
    suficiente pra estourar "Connection closed" na primeira tentativa,
    mesmo com o processo saudável."""

    CONNECT_RETRIES = 3
    CONNECT_BACKOFF_SECONDS = (0.5, 1.5, 3.0)

    def __init__(self, server_path: str, python_cmd: str = None):
        self._server_path = server_path
        self._python_cmd = python_cmd
        self._client = None

    async def __aenter__(self):
        last_exc = None
        for attempt in range(self.CONNECT_RETRIES):
            client = _make_client(self._server_path, self._python_cmd)
            try:
                await client.__aenter__()
                self._client = client
                return self
            except Exception as exc:
                last_exc = exc
                if attempt < self.CONNECT_RETRIES - 1:
                    await asyncio.sleep(self.CONNECT_BACKOFF_SECONDS[attempt])
        raise last_exc

    async def __aexit__(self, *exc_info):
        if self._client is not None:
            await self._client.__aexit__(*exc_info)

    async def list_tools(self):
        tools = await self._client.list_tools()
        return [
            {"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
            for t in tools
        ]

    async def call_tool(self, name: str, arguments: dict):
        result = await self._client.call_tool(name, arguments)
        return _extract_result(result)


# --- API antiga, síncrona, de chamada única — mantida só pra scripts
# avulsos (ex: dok_cli.py) que fazem UMA chamada isolada, sem loop de
# agente. Não use dentro de um loop de várias ferramentas. ---

def list_tools(server_path: str, python_cmd: str = None):
    async def _list():
        async with MCPSession(server_path, python_cmd) as session:
            return await session.list_tools()
    return asyncio.run(_list())


def call_tool(server_path: str, name: str, arguments: dict, python_cmd: str = None):
    async def _call():
        async with MCPSession(server_path, python_cmd) as session:
            return await session.call_tool(name, arguments)
    return asyncio.run(_call())
