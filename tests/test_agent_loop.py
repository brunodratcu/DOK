from agents.agent_loop import run_agent
import agents.agent_loop as loop


class FakeProvider:
    def __init__(self):
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"text": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "ping", "arguments": "{}"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 1}}
        return {"text": "feito", "tool_calls": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}


class FakeSession:
    """Substitui MCPSession nos testes — mesma interface (async context
    manager com list_tools/call_tool), sem precisar de um subprocesso
    dok-tools real."""
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def list_tools(self):
        return [{"name": "ping", "description": "test", "input_schema": {"type": "object", "properties": {}}}]

    async def call_tool(self, name, arguments):
        return {"ok": True}


def test_agent_executes_mcp_tool(monkeypatch):
    monkeypatch.setattr(loop, "MCPSession", FakeSession)
    ok, reply, trace, usage = run_agent(FakeProvider(), model="x", system_prompt="x", history=[], user_text="oi", tools_server_path="x")
    assert ok and reply == "feito"
    assert usage["prompt_tokens"] == 5


def test_subagent_delegation_does_not_nest_event_loop(monkeypatch):
    """Regressão: chamar run_subagent de dentro de um turno já rodando
    (via `asyncio.run()`) não pode tentar abrir um SEGUNDO
    `asyncio.run()` — isso derruba com 'cannot be called from a
    running event loop'. O delegate precisa ser async e usar
    `run_agent_async` (com await), nunca `run_agent` (que faz
    asyncio.run) de dentro do loop."""
    monkeypatch.setattr(loop, "MCPSession", FakeSession)

    class DelegatingProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"text": "", "tool_calls": [{"id": "1", "type": "function", "function": {
                    "name": "run_subagent", "arguments": '{"task": "pesquisa", "role": "pesquisador"}'
                }}], "usage": {}}
            return {"text": "resultado final com ajuda do sub-agente", "tool_calls": [], "usage": {}}

    async def delegate(task, role):
        # Simula o SubAgentManager.run_async chamando run_agent_async
        # de novo, DENTRO do mesmo loop — é exatamente o caminho que
        # quebrava antes da correção.
        ok, reply, _, _ = await loop.run_agent_async(
            DelegatingProvider(), model="x", system_prompt="x", history=[],
            user_text=task, tools_server_path="x", max_tokens=700,
            tools_python_cmd=None, max_turns=2, delegate=None, permissions_cfg={},
        )
        return reply if ok else f"falhou: {reply}"

    ok, reply, trace, usage = run_agent(
        DelegatingProvider(), model="x", system_prompt="x", history=[],
        user_text="pesquisa algo", tools_server_path="x", delegate=delegate,
    )
    assert ok
    assert "resultado final" in reply
