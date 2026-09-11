from agents.agent_loop import run_agent
import agents.agent_loop as loop

class FakeProvider:
    def __init__(self): self.calls = 0
    def chat(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"text": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "ping", "arguments": "{}"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 1}}
        return {"text": "feito", "tool_calls": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}

def test_agent_executes_mcp_tool(monkeypatch):
    monkeypatch.setattr(loop.mcp_client, "list_tools", lambda *a, **k: [{"name": "ping", "description": "test", "input_schema": {"type": "object", "properties": {}}}])
    monkeypatch.setattr(loop.mcp_client, "call_tool", lambda *a, **k: {"ok": True})
    ok, reply, trace, usage = run_agent(FakeProvider(), model="x", system_prompt="x", history=[], user_text="oi", tools_server_path="x")
    assert ok and reply == "feito"
    assert usage["prompt_tokens"] == 5
