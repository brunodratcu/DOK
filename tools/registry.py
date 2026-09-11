"""Registro único de ferramentas. MCP e sub-agents entram aqui sem acoplar o agent ao transporte."""
import json

DELEGATE_TOOL = {
    "type": "function",
    "function": {
        "name": "run_subagent",
        "description": "Delega uma tarefa isolada a um sub-agente. Use para pesquisa, análise, revisão ou trabalho que possa ser separado da conversa principal.",
        "parameters": {"type": "object", "properties": {"task": {"type": "string"}, "role": {"type": "string"}}, "required": ["task"]},
    },
}

def mcp_to_openai(tools):
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}} for t in tools]

def parse_tool_arguments(call):
    try:
        return json.loads(call.get("function", {}).get("arguments") or "{}")
    except json.JSONDecodeError:
        return {}
