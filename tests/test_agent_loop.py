import os
import tempfile

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
        return [
            {"name": "ping", "description": "test", "input_schema": {"type": "object", "properties": {}}},
            {"name": "edit_file", "description": "edita arquivo", "input_schema": {"type": "object", "properties": {}}},
        ]

    async def call_tool(self, name, arguments):
        if name == "edit_file":
            # Simula a ferramenta real: escreve o new_text de verdade
            # no arquivo, pro Verification Engine ter algo real pra checar.
            path = arguments["path"]
            with open(path, "a", encoding="utf-8") as f:
                f.write(arguments["new_text"])
            return {"path": path, "replaced": True}
        return {"ok": True}


def test_agent_executes_mcp_tool(monkeypatch):
    monkeypatch.setattr(loop, "MCPSession", FakeSession)
    ok, reply, trace, usage = run_agent(FakeProvider(), model="x", system_prompt="x", history=[], user_text="oi", tools_server_path="x")
    assert ok and reply == "feito"
    assert usage["prompt_tokens"] == 5


def test_edit_file_triggers_verification_and_passes(monkeypatch):
    """Depois de um edit_file bem-sucedido, o Verification Engine roda
    sozinho e o resultado (com 'passed': true) volta como parte da
    observação da ferramenta."""
    monkeypatch.setattr(loop, "MCPSession", FakeSession)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "arquivo.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("x = 1\n")

        class EditingProvider:
            def __init__(self):
                self.calls = 0
                self.seen_tool_messages = []

            def chat(self, *, messages, **kwargs):
                self.calls += 1
                # Guarda a última mensagem de "tool" que o loop mandou de volta
                tool_msgs = [m for m in messages if m.get("role") == "tool"]
                if tool_msgs:
                    self.seen_tool_messages.append(tool_msgs[-1]["content"])
                if self.calls == 1:
                    return {"text": "", "tool_calls": [{"id": "1", "type": "function", "function": {
                        "name": "edit_file",
                        "arguments": f'{{"path": "{path}", "old_text": "x = 1", "new_text": "x = 2"}}'
                    }}], "usage": {}}
                return {"text": "editei e verifiquei", "tool_calls": [], "usage": {}}

        provider = EditingProvider()
        ok, reply, trace, usage = run_agent(
            provider, model="x", system_prompt="x", history=[],
            user_text="edita o arquivo", tools_server_path="x",
        )

        assert ok
        # A verificação de fato rodou e chegou no modelo, com passed=True
        assert any("'passed': True" in msg for msg in provider.seen_tool_messages)
        assert any("Verificação:" in t for t in trace)


def test_verification_catches_python_syntax_error(monkeypatch):
    """Se o edit_file deixar o arquivo com sintaxe Python inválida, a
    camada de sintaxe do Verification Engine tem que pegar isso."""
    from core.verification import verify_file

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "quebrado.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("def funcao(:\n    pass\n")  # sintaxe inválida de propósito

        resultado = verify_file(path)
        assert resultado["passed"] is False
        syntax_check = next(c for c in resultado["checks"] if c["check"] == "syntax")
        assert syntax_check["passed"] is False
