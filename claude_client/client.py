"""Cliente da Messages API da Anthropic com retorno do usage real."""
import requests

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
TIMEOUT = 60


def send_message(api_key, model, system_prompt, messages, max_tokens=400):
    """
    Retorna (ok, texto_ou_erro, usage).

    ``usage`` é o bloco devolvido pela Anthropic na resposta 200.
    Nenhuma Admin API é usada.
    """
    if not api_key:
        return False, "Chave da Anthropic não configurada. Rode: ./dok key anthropic set", {}

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
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)

        try:
            data = resp.json()
        except ValueError:
            data = {}

        if resp.status_code != 200:
            detail = data.get("error", {}).get("message", resp.text)
            return False, f"Erro da API ({resp.status_code}): {detail}", {}

        text_blocks = [
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        usage = data.get("usage") or {}
        return True, "\n".join(text_blocks).strip() or "(resposta vazia)", usage
    except requests.exceptions.Timeout:
        return False, "A API demorou demais pra responder. Tenta de novo.", {}
    except requests.exceptions.RequestException as exc:
        return False, f"Falha de conexão com a Anthropic: {exc}", {}
    except Exception as exc:
        return False, f"Falha inesperada: {exc}", {}
