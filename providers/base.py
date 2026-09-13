"""Contrato comum dos provedores de modelos usados pelo DOK."""
from abc import ABC, abstractmethod

class ProviderError(Exception):
    pass

class Provider(ABC):
    name = "base"

    @abstractmethod
    def chat(self, *, model, system_prompt, messages, tools=None, max_tokens=800, tool_choice="auto"):
        """Retorna uma resposta normalizada do modelo.

        tool_choice: "auto" (modelo decide) ou "required" (força o
        modelo a chamar alguma ferramenta nesta rodada — usado quando
        detectamos um caminho de arquivo na mensagem do usuário, já
        que modelos gratuitos tendem a não decidir usar a ferramenta
        sozinhos mesmo quando ela ajudaria)."""
        raise NotImplementedError
