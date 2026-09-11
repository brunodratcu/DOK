from .base import Provider, ProviderError
from .openrouter import OpenRouterProvider, list_free_models
from .anthropic import AnthropicProvider

def create_provider(cfg):
    name = cfg.get("provider", "openrouter").lower()
    section = cfg.get(name, {})
    if name == "openrouter":
        return OpenRouterProvider(section.get("api_key", ""))
    if name == "anthropic":
        return AnthropicProvider(section.get("api_key", ""))
    raise ProviderError(f"Provedor desconhecido: {name}")
