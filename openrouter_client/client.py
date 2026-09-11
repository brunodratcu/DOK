"""Compatibilidade: prefira providers.openrouter."""
from providers.openrouter import OpenRouterProvider, list_free_models

def send_message(api_key, model, system_prompt, messages, max_tokens=400):
    try:
        r = OpenRouterProvider(api_key).chat(model=model, system_prompt=system_prompt, messages=messages, max_tokens=max_tokens)
        return True, r["text"]
    except Exception as exc:
        return False, str(exc)
