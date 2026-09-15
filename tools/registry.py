"""Registro único de ferramentas MCP — traduz pro formato OpenAI-compatible."""
import json

def mcp_to_openai(tools):
    return [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}} for t in tools]

def parse_tool_arguments(call):
    try:
        return json.loads(call.get("function", {}).get("arguments") or "{}")
    except json.JSONDecodeError:
        return {}
