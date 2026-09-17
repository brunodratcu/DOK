"""
providers.py — abstração mínima de provedor de IA, usada pelo Oráculo.

Não importa nada do projeto dok/ — o dok-tools é independente por
design (pode ser plugado até no Claude Desktop sem o dok/ presente).
Por isso existe esta versão própria em vez de reaproveitar
dok/providers/: são dois pacotes deliberadamente separados, com a
MESMA forma (mesmo padrão de arquitetura), não o MESMO código.
"""
import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def normalize_content(content, target):
    """
    Converte blocos NEUTROS de conteúdo pro formato nativo de cada
    API. Formato neutro:
        {"type": "text", "text": "..."}
        {"type": "image_b64", "media_type": "image/jpeg", "data": "..."}
    target: "anthropic" ou "openai".
    """
    if content is None or isinstance(content, str):
        return content
    converted = []
    for block in content:
        btype = block.get("type")
        if btype == "text":
            converted.append({"type": "text", "text": block.get("text", "")})
        elif btype == "image_b64":
            media_type = block.get("media_type", "image/jpeg")
            data = block.get("data", "")
            if target == "anthropic":
                converted.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
            else:
                converted.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}})
        else:
            converted.append(block)
    return converted


class ProviderError(Exception):
    pass


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key):
        self.api_key = api_key

    def chat(self, *, model, system_prompt, content, max_tokens=1500):
        """
        Retorna sempre um dict: {"text", "finish_reason", "usage",
        "http_status", "error"} — nunca lança por causa de resposta
        vazia ou HTTP != 200, quem chama decide o que fazer (é assim
        que dá pra detectar resposta vazia e logar o motivo real,
        em vez de aceitar silenciosamente).
        """
        if not self.api_key:
            raise ProviderError("Chave da Anthropic não configurada em dok-tools/config/config.yaml")
        payload = {
            "model": model, "max_tokens": max_tokens, "system": system_prompt,
            "messages": [{"role": "user", "content": normalize_content(content, "anthropic")}],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
        try:
            resp = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=120)
        except requests.exceptions.RequestException as exc:
            return {"text": "", "finish_reason": "request_exception", "usage": {}, "http_status": None, "error": str(exc)}

        try:
            data = resp.json()
        except ValueError:
            data = {}

        if resp.status_code != 200:
            error_msg = data.get("error", {}).get("message", resp.text[:500])
            return {"text": "", "finish_reason": "http_error", "usage": {}, "http_status": resp.status_code, "error": error_msg}

        text = "\n".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
        return {
            "text": text,
            "finish_reason": data.get("stop_reason"),
            "usage": data.get("usage", {}),
            "http_status": resp.status_code,
            "error": None,
        }


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, api_key):
        self.api_key = api_key

    def chat(self, *, model, system_prompt, content, max_tokens=1500):
        if not self.api_key:
            raise ProviderError("Chave da OpenRouter não configurada em dok-tools/config/config.yaml")
        payload = {
            "model": model, "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": normalize_content(content, "openai")},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/brunodratcu/dok", "X-Title": "DOK Oracle",
        }
        try:
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
        except requests.exceptions.RequestException as exc:
            return {"text": "", "finish_reason": "request_exception", "usage": {}, "http_status": None, "error": str(exc)}

        try:
            data = resp.json()
        except ValueError:
            data = {}

        if resp.status_code != 200:
            error_msg = data.get("error", {}).get("message", resp.text[:500])
            return {"text": "", "finish_reason": "http_error", "usage": {}, "http_status": resp.status_code, "error": error_msg}

        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message", {}).get("content") or "").strip()
        return {
            "text": text,
            "finish_reason": choice.get("finish_reason"),
            "usage": data.get("usage", {}),
            "http_status": resp.status_code,
            "error": None,
        }


def create_provider(cfg):
    """Lê `provider:` do config e devolve (objeto_provider, model)."""
    provider_name = cfg.get("provider", "anthropic")
    section = cfg.get(provider_name, {})
    api_key = section.get("api_key", "")
    model = section.get("model", "")
    if provider_name == "openrouter":
        return OpenRouterProvider(api_key), model
    return AnthropicProvider(api_key), model
