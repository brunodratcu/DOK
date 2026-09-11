"""Executor de sub-agents. Um sub-agent recebe uma tarefa, usa MCP e devolve um resultado ao agente principal."""
from .agent_loop import run_agent

class SubAgentManager:
    def __init__(self, provider, mcp_server_path, mcp_python=None, max_turns=4):
        self.provider = provider
        self.mcp_server_path = mcp_server_path
        self.mcp_python = mcp_python
        self.max_turns = max_turns

    def run(self, task, role, model, system_prompt, max_tokens=700):
        prompt = f"Você é um sub-agente do DOK. Papel: {role or 'especialista'}. Execute somente esta tarefa:\n{task}\nEntregue um resultado objetivo ao agente principal."
        return run_agent(self.provider, model=model, system_prompt=system_prompt + "\n" + prompt, history=[], user_text=task, tools_server_path=self.mcp_server_path, tools_python_cmd=self.mcp_python, max_tokens=max_tokens, max_turns=self.max_turns, delegate=None)
