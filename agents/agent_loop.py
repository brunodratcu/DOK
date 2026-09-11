"""
agent_loop.py — orquestra o ciclo decisão-ação-observação: pergunta
do usuário -> Claude decide se quer uma ferramenta -> se quiser, o
DOK executa de verdade via MCP -> resultado volta pro Claude ->
repete até ele responder com texto final em vez de pedir outra
ferramenta.

É o caminho único do chat do DOK agora — ferramentas sempre
disponíveis, sempre via Anthropic (tool use não é confiável nos
modelos gratuitos da OpenRouter).
"""
import mcp_client
from . import claude_agent

MAX_TURNS = 6  # trava de segurança contra loop infinito


def _mcp_tools_to_anthropic_format(mcp_tools):
    """MCP usa 'inputSchema', a Anthropic usa 'input_schema' — resto é igual."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["input_schema"],
        }
        for t in mcp_tools
    ]


def _sum_usage(accumulated, new):
    for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
        accumulated[key] = accumulated.get(key, 0) + (new.get(key) or 0)
    # cache_creation é um sub-dict às vezes — soma os dois formatos possíveis
    new_creation = new.get("cache_creation") or {}
    if new_creation:
        acc_creation = accumulated.setdefault("cache_creation", {})
        for key in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"):
            acc_creation[key] = acc_creation.get(key, 0) + (new_creation.get(key) or 0)
    return accumulated


def run(api_key, model, system_prompt, history, user_text, tools_server_path, max_tokens=800, tools_python_cmd=None):
    """
    Retorna (ok: bool, resposta_final: str, trace: list, usage: dict).
    `usage` é a soma de todas as chamadas feitas nesta rodada (pode ser
    mais de uma, se o Claude pedir ferramentas antes de responder).
    """
    try:
        mcp_tools = mcp_client.list_tools(tools_server_path, python_cmd=tools_python_cmd)
    except Exception as exc:
        mcp_tools = []
        tools_unavailable_note = f"(Aviso: servidor de ferramentas indisponível — {exc}. Respondendo sem ferramentas.)"
    else:
        tools_unavailable_note = None

    anthropic_tools = _mcp_tools_to_anthropic_format(mcp_tools)
    messages = list(history) + [{"role": "user", "content": user_text}]
    trace = []
    total_usage = {}
    if tools_unavailable_note:
        trace.append(tools_unavailable_note)

    for _ in range(MAX_TURNS):
        ok, response = claude_agent.call_with_tools(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            messages=messages,
            tools=anthropic_tools,
            max_tokens=max_tokens,
        )
        if not ok:
            return False, response, trace, total_usage

        if isinstance(response, dict) and response.get("usage"):
            _sum_usage(total_usage, response["usage"])

        content_blocks = response.get("content", [])
        stop_reason = response.get("stop_reason")

        messages.append({"role": "assistant", "content": content_blocks})

        if stop_reason != "tool_use":
            final_text = "\n".join(
                b.get("text", "") for b in content_blocks if b.get("type") == "text"
            ).strip()
            return True, final_text or "(sem resposta de texto)", trace, total_usage

        tool_results = []
        for block in content_blocks:
            if block.get("type") != "tool_use":
                continue
            tool_name = block["name"]
            tool_input = block.get("input", {})
            trace.append(f"Ferramenta: {tool_name}({tool_input})")

            try:
                result = mcp_client.call_tool(tools_server_path, tool_name, tool_input, python_cmd=tools_python_cmd)
                trace.append(f"Resultado: {result}")
                content = str(result)
            except Exception as exc:
                content = f"Erro ao executar a ferramenta: {exc}"
                trace.append(content)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": content,
            })

        messages.append({"role": "user", "content": tool_results})

    return False, "O DOK tentou várias etapas e não chegou a uma resposta final. Tenta reformular a pergunta.", trace, total_usage
