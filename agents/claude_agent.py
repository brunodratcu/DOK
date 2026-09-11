"""Compatibilidade antiga. O código novo usa providers.*."""
from providers.anthropic import AnthropicProvider

def call_with_tools(api_key, model, system_prompt, messages, tools, max_tokens=800):
    try:
        r = AnthropicProvider(api_key).chat(model=model, system_prompt=system_prompt, messages=messages, tools=tools, max_tokens=max_tokens)
        return True, r["raw"]
    except Exception as exc:
        return False, str(exc)
