"""Provider Anthropic. Opcional: o DOK não depende dele para usar OpenRouter."""
import requests
from .base import Provider, ProviderError

URL = "https://api.anthropic.com/v1/messages"
class AnthropicProvider(Provider):
    name = "anthropic"
    def __init__(self, api_key):
        self.api_key = api_key
    def chat(self, *, model, system_prompt, messages, tools=None, max_tokens=800):
        if not self.api_key:
            raise ProviderError("Chave da Anthropic não configurada.")

        anthropic_messages = []
        for m in messages:
            role = m.get("role")
            if role == "assistant" and m.get("tool_calls"):
                blocks = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for call in m["tool_calls"]:
                    import json
                    blocks.append({"type": "tool_use", "id": call.get("id"), "name": call.get("function", {}).get("name"), "input": json.loads(call.get("function", {}).get("arguments") or "{}")})
                anthropic_messages.append({"role": "assistant", "content": blocks})
            elif role == "tool":
                anthropic_messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": m.get("tool_call_id"), "content": m.get("content", "")} ]})
            else:
                anthropic_messages.append({"role": role, "content": m.get("content", "")})

        payload = {"model": model, "max_tokens": max_tokens, "system": system_prompt, "messages": anthropic_messages}
        if tools:
            payload["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""), "input_schema": t["function"]["parameters"]} for t in tools]
        try:
            r = requests.post(URL, headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, json=payload, timeout=90)
            data = r.json()
        except Exception as exc:
            raise ProviderError(f"Falha de conexão com a Anthropic: {exc}") from exc
        if r.status_code != 200:
            raise ProviderError(data.get("error", {}).get("message", r.text))
        blocks = data.get("content", [])
        tool_calls, text = [], []
        for b in blocks:
            if b.get("type") == "text": text.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                import json
                tool_calls.append({"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}))}})
        return {"text": "\n".join(text).strip(), "tool_calls": tool_calls, "finish_reason": data.get("stop_reason"), "usage": data.get("usage") or {}, "raw": data}
