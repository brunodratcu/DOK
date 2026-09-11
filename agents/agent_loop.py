"""
agent_loop.py — orquestra o ciclo decisão-ação-observação descrito
antes: pergunta do usuário -> Claude decide se quer uma ferramenta ->
se quiser, o DOK executa de verdade via MCP -> resultado volta pro
Claude -> repete até ele responder com texto final em vez de pedir
outra ferramenta.

Usado só pela aba Projetos — a aba Chats continua simples e barata,
sem ferramentas.
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


def run(api_key, model, system_prompt, history, user_text, tools_server_path, max_tokens=800, tools_python_cmd=None):
    """
    history: lista de {"role": ..., "content": ...} já no formato da API
             (mensagens anteriores da sessão de Projetos)
    Retorna (ok: bool, resposta_final: str, trace: list) — trace é uma
    lista legível do que aconteceu (útil pra mostrar na UI o que foi
    verificado, não só a resposta final).
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
            return False, response, trace

        content_blocks = response.get("content", [])
        stop_reason = response.get("stop_reason")

        # Guarda a resposta do assistente (pode ter texto + tool_use juntos)
        messages.append({"role": "assistant", "content": content_blocks})

        if stop_reason != "tool_use":
            # Terminou de decidir — junta os blocos de texto como resposta final
            final_text = "\n".join(
                b.get("text", "") for b in content_blocks if b.get("type") == "text"
            ).strip()
            return True, final_text or "(sem resposta de texto)", trace

        # Tem pelo menos um pedido de ferramenta — executa cada um de verdade
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

    return False, "O DOK tentou várias etapas e não chegou a uma resposta final. Tenta reformular a pergunta.", trace
