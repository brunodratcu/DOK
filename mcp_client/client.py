"""Cliente MCP síncrono. O servidor continua sendo um projeto separado (dok-tools)."""
import asyncio
from pathlib import Path
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

def _run(coro): return asyncio.run(coro)
def _make_client(server_path, python_cmd=None):
    if python_cmd: return Client(PythonStdioTransport(server_path, python_cmd=python_cmd))
    return Client(Path(server_path))

def list_tools(server_path, python_cmd=None):
    async def _list():
        async with _make_client(server_path, python_cmd) as client:
            tools = await client.list_tools()
            return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema} for t in tools]
    return _run(_list())

def call_tool(server_path, name, arguments, python_cmd=None):
    async def _call():
        async with _make_client(server_path, python_cmd) as client:
            result = await client.call_tool(name, arguments)
            return result.data if result.data is not None else result.structured_content
    return _run(_call())
