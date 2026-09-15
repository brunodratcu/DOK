"""
Executor de sub-agents. Um sub-agent recebe uma tarefa, usa MCP e
devolve um resultado ao agente principal.

IMPORTANTE: `run_async` chama `run_agent_async` DIRETAMENTE (com
`await`), reaproveitando o loop assíncrono que já está rodando —
nunca `asyncio.run()` aqui, porque isso já está sendo chamado de
DENTRO de um turno do agente principal, que já tem um loop aberto.
Abrir um segundo com `asyncio.run()` derruba com "cannot be called
from a running event loop".
"""
from .agent_loop import run_agent_async


class SubAgentManager:
    def __init__(self, provider, mcp_server_path, mcp_python=None, max_turns=4):
        self.provider = provider
        self.mcp_server_path = mcp_server_path
        self.mcp_python = mcp_python
        self.max_turns = max_turns

    async def run_async(self, task, role, model, system_prompt, max_tokens=700, permissions_cfg=None):
        prompt = (
            f"Você é um sub-agente do DOK. Papel: {role or 'especialista'}. "
            f"Execute somente esta tarefa:\n{task}\n"
            "Entregue um resultado objetivo ao agente principal."
        )
        return await run_agent_async(
            self.provider, model=model, system_prompt=system_prompt + "\n" + prompt,
            history=[], user_text=task, tools_server_path=self.mcp_server_path,
            tools_python_cmd=self.mcp_python, max_tokens=max_tokens,
            max_turns=self.max_turns, delegate=None, permissions_cfg=permissions_cfg,
        )
