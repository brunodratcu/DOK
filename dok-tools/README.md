# dok-tools

Servidor MCP independente — **não depende do projeto DOK**, não
importa nada de lá. Expõe 4 ferramentas de diagnóstico:

- `check_network_tool` — ping + resolução DNS de um host
- `check_website_tool` — status HTTP, tempo de resposta, validade SSL
- `check_device_mac_tool` — dispositivo online na rede local (via ARP)
- `whois_domain_tool` — registro público WHOIS de um domínio

Tudo é **leitura**, sem alterar nada, sem scan agressivo — checagens
básicas de saúde, não ferramenta ofensiva.

## Instalar

Sem venv — instala direto no Python global:

```
pip install -r requirements.txt
```

No Raspberry Pi OS (Bookworm ou mais novo), o `pip` bloqueia instalação
global por padrão. Use:

```
pip install --break-system-packages -r requirements.txt
```

## Testar sozinho (sem o DOK)

Este servidor fala MCP, não é um programa que você "roda e vê algo na
tela" — ele fica esperando um cliente se conectar. Pra testar
interativamente, use o **MCP Inspector**:

```
npx @modelcontextprotocol/inspector python server.py
```

Isso abre uma interface web onde você vê as 4 ferramentas listadas e
pode chamar cada uma manualmente, com os resultados reais na tela.

## Usar com o DOK

O DOK já vem configurado pra achar esta pasta automaticamente, contanto
que ela fique **ao lado** da pasta `dok/` (mesmo nível, não uma dentro
da outra):

```
alguma-pasta/
├── dok/
└── dok-tools/
```

Se você mover `dok-tools/` pra outro lugar, ajuste o caminho em
`dok/config/config.yaml` → `tools_server.path`.

## Usar com o Claude Desktop (bônus da arquitetura MCP)

Como é um servidor MCP padrão, funciona também plugado direto no
Claude Desktop, fora do DOK. No arquivo de configuração do Claude
Desktop, adicione:

```json
{
  "mcpServers": {
    "dok-tools": {
      "command": "python",
      "args": ["/caminho/completo/pra/dok-tools/server.py"]
    }
  }
}
```

## Estrutura

```
dok-tools/
├── server.py              # servidor MCP — registra as 4 ferramentas
├── requirements.txt
└── tools/
    ├── network.py            # lógica real de cada ferramenta,
    ├── website.py              # sem nenhuma dependência do MCP —
    ├── device.py                 # são funções Python comuns, testáveis
    └── domain.py                   # isoladas
```

## Adicionando uma ferramenta nova

1. Escreva a função em `tools/` (recebe parâmetros simples, devolve um dict)
2. Registre em `server.py` com `@mcp.tool()`, com um docstring claro —
   é a partir do docstring que o Claude decide quando usar a ferramenta
3. Pronto — nenhuma mudança necessária do lado do DOK, ele descobre a
   ferramenta nova automaticamente na próxima vez que perguntar a lista
