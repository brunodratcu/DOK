"""Contrato comum dos provedores de modelos usados pelo DOK."""
from abc import ABC, abstractmethod

class ProviderError(Exception):
    pass

class Provider(ABC):
    name = "base"

    @abstractmethod
    def chat(self, *, model, system_prompt, messages, tools=None, max_tokens=800):
        """Retorna uma resposta normalizada do modelo."""
        raise NotImplementedError
