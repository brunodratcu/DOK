"""Provider OpenRouter usando a API compatível com OpenAI."""
import requests
from .base import Provider, ProviderError

URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
TIMEOUT = 90

class OpenRouterProvider(Provider):
    name = "openrouter"

    def __init__(self, api_key, http_referer="https://github.com/brunodratcu/dok", app_title="DOK"):
        self.api_key = api_key
        self.http_referer = http_referer
        self.app_title = app_title

    def chat(self, *, model, system_prompt, messages, tools=None, max_tokens=800):
        if not self.api_key:
            raise ProviderError("Chave da OpenRouter não configurada. Rode: ./dok key openrouter set")
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.http_referer,
            "X-Title": self.app_title,
        }
        try:
            r = requests.post(URL, headers=headers, json=payload, timeout=TIMEOUT)
            data = r.json()
        except requests.exceptions.Timeout as exc:
            raise ProviderError("A OpenRouter demorou demais para responder.") from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderError(f"Falha de conexão com a OpenRouter: {exc}") from exc
        except ValueError as exc:
            raise ProviderError("A OpenRouter devolveu uma resposta inválida.") from exc
        if r.status_code != 200:
            detail = data.get("error", {}).get("message", r.text)
            raise ProviderError(f"Erro da OpenRouter ({r.status_code}): {detail}")
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        usage = data.get("usage") or {}
        return {
            "text": (msg.get("content") or "").strip(),
            "tool_calls": msg.get("tool_calls") or [],
            "finish_reason": choice.get("finish_reason"),
            "usage": usage,
            "raw": data,
        }

def list_free_models():
    try:
        r = requests.get(MODELS_URL, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception as exc:
        return False, f"Falha ao consultar modelos: {exc}"
    free = []
    for m in data:
        pricing = m.get("pricing", {})
        try:
            if float(pricing.get("prompt", "1")) == 0 and float(pricing.get("completion", "1")) == 0:
                free.append({"id": m.get("id"), "name": m.get("name"), "context_length": m.get("context_length")})
        except (TypeError, ValueError):
            pass
    free.sort(key=lambda x: x["id"] or "")
    return True, free
