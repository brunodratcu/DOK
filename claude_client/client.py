"""Compatibilidade: prefira providers.anthropic."""
from providers.anthropic import AnthropicProvider

def send_message(api_key, model, system_prompt, messages, max_tokens=400):
    try:
        r = AnthropicProvider(api_key).chat(model=model, system_prompt=system_prompt, messages=messages, max_tokens=max_tokens)
        return True, r["text"], r.get("usage", {})
    except Exception as exc:
        return False, str(exc), {}
