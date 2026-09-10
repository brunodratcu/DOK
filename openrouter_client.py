"""
Cliente mínimo pra API da OpenRouter (openrouter.ai) — compatível com o
formato de chat completions da OpenAI. Usado como alternativa gratuita
à API paga da Anthropic.
"""
import requests

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
TIMEOUT = 30


def send_message(api_key, model, system_prompt, messages, max_tokens=400):
    """
    messages: lista de {"role": "user"|"assistant", "content": "texto"}
    Retorna (ok: bool, texto_ou_erro: str)
    """
    if not api_key:
        return False, "Chave da OpenRouter não configurada. Rode: ./dok key openrouter set"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # Opcionais, recomendados pela OpenRouter pra identificar o app
        "HTTP-Referer": "https://github.com/brunodratcu/dok",
        "X-Title": "DOK",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        if resp.status_code != 200:
            detail = resp.json().get("error", {}).get("message", resp.text)
            return False, f"Erro da OpenRouter ({resp.status_code}): {detail}"

        data = resp.json()
        choice = data["choices"][0]["message"]["content"]
        return True, (choice or "").strip() or "(resposta vazia)"
    except requests.exceptions.Timeout:
        return False, "A OpenRouter demorou demais pra responder. Tenta de novo."
    except (KeyError, IndexError):
        return False, "Resposta em formato inesperado da OpenRouter."
    except Exception as exc:
        return False, f"Falha de conexão: {exc}"


def list_free_models():
    """
    Consulta o catálogo público da OpenRouter e retorna só os modelos
    gratuitos (preço de prompt E completion = 0). Não precisa de chave.
    Retorna (ok: bool, lista_ou_erro).
    """
    try:
        resp = requests.get(MODELS_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as exc:
        return False, f"Falha ao consultar modelos: {exc}"

    free = []
    for m in data:
        pricing = m.get("pricing", {})
        try:
            prompt_price = float(pricing.get("prompt", "1"))
            completion_price = float(pricing.get("completion", "1"))
        except (TypeError, ValueError):
            continue
        if prompt_price == 0 and completion_price == 0:
            free.append({
                "id": m.get("id"),
                "name": m.get("name"),
                "context_length": m.get("context_length"),
            })

    free.sort(key=lambda m: m["id"])
    return True, free
