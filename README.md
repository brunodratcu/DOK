# DOK — Diagnostic of Kings

App de mesa pro Raspberry Pi 4B: tela de boas-vindas com **hora e clima
em tempo real**, e uma aba **DOK** com chat de texto usando a API da
Anthropic diretamente (sem intermediário, sem OpenRouter).

**Home Assistant não faz mais parte deste projeto.** Voz ainda não foi
implementada — fica pra uma próxima fase, depois de decidir o hardware
de microfone/alto-falante.

## Estrutura

```
dok/
├── app.py                  # servidor Flask
├── agents/
│   ├── agent_loop.py           # loop de decisão-ação pra aba Projetos
│   └── claude_agent.py           # chamada à Anthropic com tool use
├── mcp_client/
│   └── client.py                # conecta no servidor dok-tools
├── claude_client/
│   └── client.py                # chamada direta à API de Mensagens da Anthropic
├── openrouter_client/
│   └── client.py                # chamada à API da OpenRouter (alternativa gratuita)
├── projects_store.py                 # histórico da aba Projetos
├── chat_store.py              # persistência das conversas (JSON)
├── paths.py                   # resolve caminhos (funciona empacotado ou não)
├── dok_app.py                  # ponto de entrada do app (janela nativa)
├── build_windows.bat            # gera dok.exe (rodar no Windows)
├── build_linux.sh                # gera o binário Linux (rodar no Pi)
├── dok_cli.py               # firmware CLI (chaves, créditos)
├── dok                       # atalho pra rodar o CLI (./dok ...)
├── dok.desktop                # ícone/launcher da área de trabalho
├── requirements.txt
├── config/
│   └── config.yaml         # personalidade, chaves, modelo, clima
├── data/
│   └── chats.json            # conversas salvas (criado automaticamente)
├── templates/
│   ├── index.html            # tela de boas-vindas (clima/hora)
│   └── dok.html                # tela DOK (chats)
└── static/
    ├── css/style.css           # tela de boas-vindas
    ├── css/dok.css               # tela de chat
    ├── js/app.js
    ├── js/dok.js
    ├── icon/dok.png
    └── generated/               # QR code de créditos gerado
```

## O app de verdade — executável com ícone (Windows e Pi)

O DOK roda como **app nativo**, não como site aberto no navegador: uma
janela própria, sem barra de endereço, ícone na área de trabalho, clique
e abre. Isso é feito com `pywebview` (janela nativa do sistema) +
`PyInstaller` (empacota tudo num único executável).

**Importante:** o build tem que rodar **no próprio sistema de destino**
— gera o `.exe` rodando no Windows, gera o binário Linux rodando no Pi.
Não dá pra gerar um a partir do outro (isso vale pra qualquer ferramenta
de empacotamento, não é limitação específica daqui).

### No notebook Windows

```
build_windows.bat
```

Isso instala as dependências e gera `dist\dok.exe`. Depois:

```
xcopy /E /I config dist\config
```

(copia a config pra dentro de `dist`, porque é lá que o `.exe` vai
gravar sua chave e histórico de chat)

Dê dois cliques em `dist\dok.exe` — abre a janela do app direto,
sem terminal, sem navegador. Pra deixar um atalho na área de trabalho,
clique direito no `dok.exe` → **Enviar para → Área de trabalho (criar
atalho)**.

### No Raspberry Pi

```
chmod +x build_linux.sh
./build_linux.sh
```

Isso instala as dependências de sistema (WebKitGTK, necessário pra
janela nativa no Linux), monta o ambiente virtual, e gera `dist/dok`.
Depois:

```
cp -r config dist/
```

Ajuste `dok.desktop` pro caminho real (`Exec=/home/SEU_USUARIO/dok/dist/dok`),
dê permissão, e copie pra área de trabalho — mesmo processo de sempre
(`chmod +x`, `cp` pra `~/Desktop` e `~/.local/share/applications`,
`gio set ... metadata::trusted true`).

### Ajustando a janela

Em `config/config.yaml`, seção `app`:

```yaml
app:
  width: 480
  height: 320
  fullscreen: false    # true no Pi, se quiser tela cheia tipo o kiosk de antes
  resizable: true       # false no Pi, já que não tem mouse pra redimensionar
```

## Modo alternativo — servidor + navegador (pra desenvolvimento)

Rodar `python app.py` continua funcionando igual antes — sobe um
servidor Flask comum, acessível em `http://localhost:5000` (ou de
outro dispositivo na rede, útil pra testar mudanças rapidamente sem
recompilar o executável a cada alteração). É o jeito mais rápido de
iterar durante o desenvolvimento; o `dok_app.py`/executável é o
produto final que o usuário realmente abre.

## Aba DOK (chat)

Toque no ícone ◆ na tela principal. A aba **Chats** já funciona de
ponta a ponta: nova conversa, histórico salvo, resposta do Claude real
via sua chave. A aba **Projetos** é só um placeholder por enquanto.

**Detalhes de comportamento pra reduzir custo:**
- `history_limit` no `config.yaml` controla quantas mensagens recentes
  são reenviadas como contexto a cada pergunta (padrão: 12) — evita
  que conversas longas fiquem caras
- `max_tokens` limita o tamanho da resposta (padrão: 400)
- O modelo padrão é o **Haiku** (mais barato), configurável em
  `anthropic.model`

## Aba Projetos — diagnóstico com ferramentas reais (MCP)

Diferente da aba Chats (conversa pura), a aba Projetos usa um **agente
com ferramentas de verdade** — o DOK pode checar rede, sites,
dispositivos e domínios de fato, não só descrever de memória.

Isso depende de um segundo projeto, independente deste:
**`dok-tools/`**, que precisa estar na mesma pasta pai:

```
alguma-pasta/
├── dok/          (este projeto)
└── dok-tools/    (as ferramentas)
```

**Instalar:**
```
cd ../dok-tools
pip install -r requirements.txt
# no Pi: pip install --break-system-packages -r requirements.txt
```

Sem venv — os dois projetos instalam no mesmo Python global do
sistema, então não precisa apontar um pro outro nem gerenciar dois
ambientes separados.

**Por que só Anthropic:** ferramentas exigem um modelo consistente
pra decidir quando usá-las — modelos gratuitos da OpenRouter tendem a
ser inconfiáveis nisso. A aba Projetos sempre usa a Anthropic,
independente do que estiver configurado em `provider` pra aba Chats.

Detalhes de arquitetura, como testar o `dok-tools` sozinho, e como
adicionar uma ferramenta nova: veja `dok-tools/README.md`.

## Provedor de IA — Anthropic ou OpenRouter

O DOK suporta dois provedores, trocáveis sem mexer em código:

```
./dok provider status              # ver qual está ativo
./dok provider set anthropic       # usar a API paga da Anthropic
./dok provider set openrouter      # usar a OpenRouter (tem opções gratuitas)
```

**Anthropic:** `./dok key anthropic set` — chave paga por token
(`console.anthropic.com`), qualidade mais alta e consistente.

**OpenRouter:** `./dok key openrouter set` — gere a chave em
`openrouter.ai/keys` (tem cadastro gratuito). O padrão já vem
configurado como `openrouter/free`, um roteador que escolhe sozinho um
modelo gratuito disponível a cada chamada — funciona sem você escolher
nada.

**Quer escolher um modelo específico em vez do roteador automático?**
A lista de modelos gratuitos muda com frequência, então em vez de uma
lista fixa (que ficaria desatualizada), o DOK consulta o catálogo da
OpenRouter na hora:

```
./dok models list
```

Isso imprime os modelos gratuitos disponíveis **agora**, com o ID
exato pra colar em `config.yaml` → `openrouter.model`.

**Nota sobre modelos gratuitos:** eles têm limites de taxa mais
apertados e podem sair do ar ou virar pagos sem aviso — é assim que a
OpenRouter opera essa camada gratuita. O roteador `openrouter/free` já
absorve essa instabilidade escolhendo outro modelo quando um cai; se
preferir travar num modelo específico, fica sujeito a ele ficar
indisponível de vez em quando.

## Firmware CLI

```
./dok key anthropic set / unset / status
./dok key weather set / unset / status
./dok status
./dok credits qr
```

Nenhum dado de cartão passa pelo Pi — o ícone de créditos gera um QR
que aponta pro Console oficial da Anthropic, você paga pelo celular.

## Ícone na área de trabalho

Mesmo processo de antes: ajuste os caminhos em `dok.desktop`, dê
permissão de execução, copie pra `~/Desktop` e
`~/.local/share/applications`, e confie o arquivo com
`gio set ... metadata::trusted true`.

## Próximos passos

- Voz (microfone + STT + TTS) na aba Chats, quando o hardware for
  decidido
- Aba Projetos
- Consulta real de créditos via Usage & Cost Admin API
