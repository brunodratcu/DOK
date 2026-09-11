# DOK — arquitetura Python

O DOK continua sendo Python + Flask + pywebview. A reorganização separa responsabilidades sem transformar o projeto em um framework gigante.

## O que é `core/`?

`core` é o **núcleo das regras do DOK**. Ele não deve saber se a interface é Flask, se o modelo é OpenRouter ou Anthropic, nem como o MCP transporta ferramentas.

- `context.py`: prepara o histórico que será enviado ao modelo.
- `usage.py`: normaliza dados de consumo.
- `permissions.py`: decide se uma ferramenta pode ser executada.

A ideia é que `core` seja a camada mais estável. Se amanhã trocar Flask por outra UI, o agente continua igual.

## `providers/`

É a camada que fala com os modelos.

- `base.py`: contrato comum.
- `openrouter.py`: OpenRouter / OpenAI-compatible API.
- `anthropic.py`: Anthropic opcional.

O agente só chama `provider.chat(...)`. Portanto o DOK não é mais preso ao SDK/API de um fabricante.

## `tools/`

É o registro/formato das ferramentas. O DOK já possui ferramentas reais no projeto separado `dok-tools`; aqui nós apenas transformamos as ferramentas MCP para o formato entendido pelo provider.

## `mcp_client/`

É o transporte MCP. Ele continua simples: inicia/conecta ao `dok-tools` por stdio, lista ferramentas e executa ferramentas.

## `agents/`

Contém a inteligência de execução.

- `agent_loop.py`: agente principal. Modelo → tool call → MCP → resultado → modelo.
- `subagents.py`: permite que o agente principal delegue uma tarefa isolada a outro agente.

Sub-agents têm limite próprio de etapas e não recebem a ferramenta de criar outros sub-agents, evitando recursão descontrolada.

## Sem Memory

O DOK deliberadamente **não possui memória de longo prazo**. O histórico da conversa é apenas contexto da sessão persistido pelo `chat_store.py`.

## Fluxo

```text
Flask / Desktop
      ↓
    agents
      ↓
     core
      ↓
   provider
      ↓
 OpenRouter / Anthropic
      ↓
 tool calls
      ↓
     MCP
      ↓
   dok-tools
```

## Próximos passos naturais

1. streaming de respostas;
2. tela de seleção de provider/modelo;
3. mostrar sub-agent e ferramentas na UI;
4. aprovação antes de ferramentas perigosas;
5. fallback de modelos OpenRouter;
6. testes automatizados do agent loop.
