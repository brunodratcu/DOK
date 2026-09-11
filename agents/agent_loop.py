"""Orquestrador central do DOK: modelo -> ferramenta/MCP -> resultado -> modelo."""
import mcp_client
from core.permissions import is_allowed
from core.usage import normalize_usage
from tools.registry import mcp_to_openai, parse_tool_arguments, DELEGATE_TOOL

MAX_TURNS = 6

def _sum_usage(total, new):
    for k, v in (new or {}).items():
        if isinstance(v, (int, float)):
            total[k] = total.get(k, 0) + v

def run_agent(provider, *, model, system_prompt, history, user_text, tools_server_path, max_tokens=800, tools_python_cmd=None, max_turns=MAX_TURNS, delegate=None, permissions_cfg=None):
    try:
        mcp_tools = mcp_client.list_tools(tools_server_path, python_cmd=tools_python_cmd)
    except Exception as exc:
        mcp_tools = []
        unavailable = f"Servidor MCP indisponível: {exc}"
    else:
        unavailable = None
    tools = mcp_to_openai(mcp_tools)
    if delegate:
        tools.append(DELEGATE_TOOL)
    messages = list(history) + [{"role": "user", "content": user_text}]
    trace = [f"MCP: {len(mcp_tools)} ferramenta(s) disponível(is)"]
    if unavailable: trace.append(unavailable)
    usage = {}
    for _ in range(max_turns):
        try:
            response = provider.chat(model=model, system_prompt=system_prompt, messages=messages, tools=tools, max_tokens=max_tokens)
        except Exception as exc:
            return False, str(exc), trace, usage
        _sum_usage(usage, normalize_usage(response.get("usage")))
        tool_calls = response.get("tool_calls") or []
        text = response.get("text", "")
        if not tool_calls:
            return True, text or "(sem resposta de texto)", trace, usage
        assistant_msg = {"role": "assistant", "content": text or None, "tool_calls": tool_calls}
        messages.append(assistant_msg)
        for call in tool_calls:
            name = call.get("function", {}).get("name", "")
            args = parse_tool_arguments(call)
            if not is_allowed(name, permissions_cfg or {}):
                result = "Ferramenta bloqueada pela política de permissões do DOK."
            elif name == "run_subagent" and delegate:
                result = delegate(args.get("task", ""), args.get("role", ""))
            else:
                trace.append(f"Ferramenta: {name}({args})")
                try:
                    result = mcp_client.call_tool(tools_server_path, name, args, python_cmd=tools_python_cmd)
                    trace.append(f"Resultado: {result}")
                except Exception as exc:
                    result = f"Erro ao executar {name}: {exc}"
                    trace.append(result)
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": str(result)})
    return False, "O DOK atingiu o limite de etapas sem concluir a tarefa.", trace, usage

def run(**kwargs):
    from providers import create_provider
    cfg = kwargs.pop("config")
    provider = create_provider(cfg)
    return run_agent(provider, **kwargs)
