"""
claude_agent.py — chamada à Messages API da Anthropic COM ferramentas.

Diferente do claude_client.py (chat simples): aqui a resposta pode
vir contendo um pedido de "tool_use" em vez de texto — quem decide o
que fazer com isso é o agent_loop.py, este módulo só faz a chamada
HTTP crua e devolve a resposta inteira.

Ferramentas exigem um modelo forte o suficiente pra usar bem — por
isso este módulo é usado só com a Anthropic, não com os modelos
gratuitos da OpenRouter (que costumam ser inconsistentes com tool use).
"""
import requests

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
TIMEOUT = 60


def call_with_tools(api_key, model, system_prompt, messages, tools, max_tokens=800):
    """
    Retorna (ok: bool, resposta_completa: dict_ou_str).
    Em caso de sucesso, resposta_completa é o JSON bruto da API
    (contém 'content' com blocos de texto e/ou tool_use, e 'stop_reason').
    """
    if not api_key:
        return False, "Chave da Anthropic não configurada. Rode: ./dok key anthropic set"

    headers = {
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": messages,
        "tools": tools,
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        if resp.status_code != 200:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except ValueError:
                detail = resp.text
            return False, f"Erro da API ({resp.status_code}): {detail}"
        return True, resp.json()
    except requests.exceptions.Timeout:
        return False, "A API demorou demais pra responder. Tenta de novo."
    except Exception as exc:
        return False, f"Falha de conexão: {exc}"
