"""Orquestrador central do DOK: modelo -> ferramenta/MCP -> resultado -> modelo.

Todo o turno (listar ferramentas + todas as chamadas de ferramenta
que o modelo pedir) roda dentro de UMA sessão MCP só, aberta uma vez
— evita abrir/derrubar um processo novo do dok-tools a cada
ferramenta chamada (ver mcp_client/client.py pra detalhes de por
que isso importa)."""
import asyncio
import re

from mcp_client import MCPSession
from core.permissions import is_allowed
from core.usage import normalize_usage
from tools.registry import mcp_to_openai, parse_tool_arguments, DELEGATE_TOOL

MAX_TURNS = 6

# Detecta menção a caminho de arquivo/pasta na mensagem — usado pra
# FORÇAR o uso de ferramenta na primeira rodada, porque modelos
# gratuitos tendem a "saber" o caminho e mesmo assim responder em
# prosa que não têm acesso, em vez de chamar read_file/list_directory
# sozinhos (mesmo quando a API deles diz suportar tool use).
_PATH_PATTERN = re.compile(
    r"([a-zA-Z]:\\[^\s]+|/[^\s]+/[^\s]+|~/[^\s]+|\.\/[^\s]+)"
)

def _looks_like_path(text):
    return bool(_PATH_PATTERN.search(text or ""))

def _sum_usage(total, new):
    for k, v in (new or {}).items():
        if isinstance(v, (int, float)):
            total[k] = total.get(k, 0) + v


async def run_agent_async(provider, *, model, system_prompt, history, user_text,
                           tools_server_path, max_tokens, tools_python_cmd,
                           max_turns, delegate, permissions_cfg):
    """
    Versão async pura — use `await run_agent_async(...)` quando já
    estiver dentro de um loop assíncrono em execução (é o caso do
    sub-agente, chamado de dentro do turno do agente principal).
    Nunca chame `asyncio.run()` daqui de dentro — abrir um loop novo
    dentro de um loop já rodando derruba com
    "asyncio.run() cannot be called from a running event loop".
    """
    trace = []
    usage = {}

    async with MCPSession(tools_server_path, tools_python_cmd) as session:
        try:
            mcp_tools = await session.list_tools()
        except Exception as exc:
            mcp_tools = []
            trace.append(f"Servidor MCP indisponível: {exc}")

        tools = mcp_to_openai(mcp_tools)
        if delegate:
            tools.append(DELEGATE_TOOL)
        messages = list(history) + [{"role": "user", "content": user_text}]
        trace.append(f"MCP: {len(mcp_tools)} ferramenta(s) disponível(is)")

        # Só força na PRIMEIRA rodada — depois disso o modelo já viu o
        # resultado da ferramenta (ou decidiu não precisar), e forçar de
        # novo em toda rodada causaria loop chamando ferramenta à toa.
        force_tool_choice = "required" if (tools and _looks_like_path(user_text)) else "auto"
        if force_tool_choice == "required":
            trace.append("Caminho de arquivo detectado na mensagem — forçando uso de ferramenta.")

        for turn_index in range(max_turns):
            tool_choice = force_tool_choice if turn_index == 0 else "auto"
            try:
                response = provider.chat(
                    model=model, system_prompt=system_prompt, messages=messages,
                    tools=tools, max_tokens=max_tokens, tool_choice=tool_choice,
                )
            except Exception as exc:
                return False, str(exc), trace, usage

            _sum_usage(usage, normalize_usage(response.get("usage")))
            tool_calls = response.get("tool_calls") or []
            text = response.get("text", "")
            if not tool_calls:
                return True, text or "(sem resposta de texto)", trace, usage

            messages.append({"role": "assistant", "content": text or None, "tool_calls": tool_calls})

            for call in tool_calls:
                name = call.get("function", {}).get("name", "")
                args = parse_tool_arguments(call)
                if not is_allowed(name, permissions_cfg or {}):
                    result = "Ferramenta bloqueada pela política de permissões do DOK."
                elif name == "run_subagent" and delegate:
                    result = await delegate(args.get("task", ""), args.get("role", ""))
                else:
                    trace.append(f"Ferramenta: {name}({args})")
                    try:
                        result = await session.call_tool(name, args)
                        trace.append(f"Resultado: {result}")
                    except Exception as exc:
                        result = f"Erro ao executar {name}: {exc}"
                        trace.append(result)
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": str(result)})

    return False, "O DOK atingiu o limite de etapas sem concluir a tarefa.", trace, usage


def run_agent(provider, *, model, system_prompt, history, user_text, tools_server_path,
              max_tokens=800, tools_python_cmd=None, max_turns=MAX_TURNS,
              delegate=None, permissions_cfg=None):
    """Entrada síncrona — use esta a partir de código comum (ex: rota
    Flask). Abre o loop assíncrono do zero. NÃO chame isto de dentro
    de outro código async (use `run_agent_async` com `await` nesse caso)."""
    return asyncio.run(run_agent_async(
        provider, model=model, system_prompt=system_prompt, history=history,
        user_text=user_text, tools_server_path=tools_server_path, max_tokens=max_tokens,
        tools_python_cmd=tools_python_cmd, max_turns=max_turns, delegate=delegate,
        permissions_cfg=permissions_cfg,
    ))


def run(**kwargs):
    from providers import create_provider
    cfg = kwargs.pop("config")
    provider = create_provider(cfg)
    return run_agent(provider, **kwargs)
