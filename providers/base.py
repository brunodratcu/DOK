"""Contrato comum dos provedores de modelos usados pelo DOK."""
from abc import ABC, abstractmethod

class ProviderError(Exception):
    pass


def normalize_content(content, target):
    """
    Converte blocos de conteúdo NEUTROS (independentes de provedor)
    pro formato nativo esperado por cada API. Isso é o que permite o
    Oráculo (e qualquer outro chamador) montar mensagens com imagem
    UMA vez, sem saber se vai sair pra Anthropic ou OpenRouter — quem
    sabe disso é só o Provider.

    Formato neutro de entrada (o que quem chama monta):
        {"type": "text", "text": "..."}
        {"type": "image_b64", "media_type": "image/jpeg", "data": "..."}

    target: "anthropic" ou "openai" (OpenRouter usa formato OpenAI).
    Se `content` já for string (ou None), devolve sem alterar.
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
                converted.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                })
            else:  # openai / openrouter
                converted.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{data}"},
                })
        else:
            converted.append(block)  # tipo já nativo (ex: veio de outro fluxo) — passa direto
    return converted


class Provider(ABC):
    name = "base"

    @abstractmethod
    def chat(self, *, model, system_prompt, messages, tools=None, max_tokens=800, tool_choice="auto"):
        """Retorna uma resposta normalizada do modelo.

        tool_choice: "auto" (modelo decide) ou "required" (força o
        modelo a chamar alguma ferramenta nesta rodada — usado quando
        detectamos um caminho de arquivo na mensagem do usuário, já
        que modelos gratuitos tendem a não decidir usar a ferramenta
        sozinhos mesmo quando ela ajudaria).

        `messages[i]["content"]` pode ser uma string OU uma lista de
        blocos no formato neutro (veja `normalize_content` acima) —
        use `normalize_content(content, self.name)` pra traduzir pro
        formato nativo da sua API antes de montar o payload."""
        raise NotImplementedError
