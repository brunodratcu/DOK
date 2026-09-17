# dok-tools

Servidor MCP independente do DOK. Ele expõe ferramentas de diagnóstico,
Oráculo de mangás e ferramentas locais de filesystem:

- `list_directory` — lista arquivos e subpastas.
- `read_file` — lê arquivos de texto inteiros.
- `read_file_range` — lê só um trecho (por linha) de um arquivo grande.
- `search_files` — procura arquivos por nome (`pattern`) e/ou texto (`query`).
- `file_info` — retorna metadados de arquivo ou diretório.
- `write_file` — cria/sobrescreve um arquivo (bloqueada por padrão).
- `edit_file` — substitui um trecho exato de um arquivo (bloqueada por padrão).

As duas últimas (`write_file`, `edit_file`) vêm desativadas por padrão em
`dok/config/config.yaml` → `permissions.deny`. Remova da lista quando
quiser ativar escrita de verdade.

## Filesystem local

As quatro ferramentas rodam no mesmo computador que inicia o `dok-tools`,
porque o DOK abre o servidor MCP por `stdio`. Elas não usam internet para
ler os arquivos.

Por segurança, o acesso é limitado às pastas declaradas em:

```text
 dok-tools/config/config.yaml
```

Exemplo Windows:

```yaml
filesystem:
  allowed_paths:
    - "C:/Users/SEU_USUARIO/Documents"
    - "D:/Mangas"
  max_read_chars: 40000
  max_results: 200
  max_search_file_bytes: 5242880
```

Exemplo Linux/Raspberry Pi:

```yaml
filesystem:
  allowed_paths:
    - "~/Documents"
    - "~/mangas"
  max_read_chars: 40000
  max_results: 200
  max_search_file_bytes: 5242880
```

Caminhos relativos são resolvidos a partir da pasta do DOK. Se nenhuma pasta
for configurada, a raiz do próprio projeto `dok/` é usada. Caminhos fora das
raízes autorizadas são bloqueados, inclusive tentativas de escapar com `..`
ou links simbólicos.

### Limites

- `read_file` lê apenas texto UTF-8 e limita o conteúdo retornado.
- `search_files` ignora arquivos binários e, por padrão, não inspeciona
  arquivos maiores que 5 MB.
- `list_directory` e `search_files` limitam a quantidade de resultados.
- Nenhuma das quatro ferramentas altera, cria ou apaga arquivos.

## Diagnóstico

- `check_network_tool`
- `check_website_tool`
- `check_device_mac_tool`
- `whois_domain_tool`

## PDF com texto — leitura direta, sem IA

- `read_pdf_text_tool(path, max_pages=100)` — pra PDFs "normais"
  (curso, artigo, contrato, relatório) que têm texto de verdade
  embutido. Extração direta via PyMuPDF, **sem gastar chamada de
  IA** — mais rápido e mais barato que o Oráculo, que é pra
  mangá/HQ (imagem, sem texto extraível). Se o PDF acabar sendo
  majoritariamente imagem, o resultado avisa e sugere usar
  `oracle_ingest_tool` no lugar.

## Visão — descrever fotos

- `describe_image_tool(path, question=None)` — jpg, png, gif, webp.
  Usa o mesmo `providers.py` do Oráculo (troca de provedor sem
  duplicar código). `question` opcional foca a análise ("tem gente
  nesta foto?"); sem isso, descrição geral.

## Oráculo — leitura de mangá em blocos, memória por obra

- `oracle_ingest_tool(folder_path, block_size=4)`
- `oracle_query_tool(work=None)`
- `oracle_status_tool()`

### Confiabilidade

Antes, uma resposta vazia da IA era aceita como válida — o capítulo
acabava salvo vazio em `chapters.md`/`work.md`. Agora:

```
resposta vazia -> retry (até 3 tentativas) -> se continuar vazia -> FAILED
```

Um capítulo que falha **nunca** é salvo — fica de fora do relatório
em `chapters_failed`, com o motivo formatado como
`Capítulo X, Bloco Y/Z: <motivo>`, incluindo `finish_reason`, status
HTTP e uso de tokens da última tentativa (pra diagnosticar de verdade,
não só saber que falhou).

**Checkpoint por bloco:** se o bloco 5 de 11 falhar (mesmo após retry),
os blocos 1-4 que já deram certo ficam salvos num arquivo
`.in_progress.json` dentro da pasta da obra. Rodar `oracle_ingest_tool`
de novo **retoma do bloco 5**, sem reprocessar os anteriores.

**Hash do arquivo:** um capítulo só é considerado "já processado" se
o hash do PDF bater com o que foi salvo — se o arquivo mudar (novo
scan, versão diferente com o mesmo nome), ele é reprocessado
automaticamente em vez de ser pulado silenciosamente.

**Notas compactas:** cada bloco de páginas gera notas curtas
(~400-500 tokens), não prosa longa — mais barato e reduz risco de a
resposta ser cortada no meio.

**Não precisa mais organizar por pasta.** Jogue os PDFs numa pasta só —
o nome da obra é **inferido do nome do arquivo**:

```text
"Two Blue Vortex Chapter 001.pdf"  -> obra: Two Blue Vortex, capítulo: 1
"Naruto Next Generation_12.pdf"    -> obra: Naruto Next Generation, capítulo: 12
"Chapter_001.pdf"                  -> obra: obra-nao-classificada, capítulo: 1
```

**Leitura em blocos:** cada capítulo é processado em blocos pequenos de
páginas (`block_size`, padrão 4), não o PDF inteiro numa chamada só —
controla memória (importante no Pi) e reduz o custo de qualquer chamada
individual. Os textos de cada bloco são transitórios: usados só pra
consolidar o capítulo, depois descartados.

**Detecção automática de tipo:** se o PDF tiver texto extraível (não é
o caso normal de mangá, mas pode ser de um capítulo com script/roteiro),
o Oráculo resume direto do texto, sem gastar chamada de visão.

**Memória, por obra, em markdown** (não é mais um JSON único):

```text
data/oracle/
    Two Blue Vortex/
        chapters.md   # histórico completo — cada capítulo é anexado aqui
        work.md        # memória cumulativa: personagens, linha do tempo,
                          conflitos, revelações, estado atual
```

`oracle_query_tool` só lê o `work.md` já pronto — nunca reprocessa PDF.
Capítulo já processado (confirmado pelo cabeçalho em `chapters.md`) é
pulado automaticamente, sem gastar chamada de IA de novo.

## Teste

Instale as dependências:

```bash
pip install -r requirements.txt
```

No Raspberry Pi OS, se necessário:

```bash
pip install --break-system-packages -r requirements.txt
```

Para testar as quatro funções sem iniciar o MCP:

```bash
python -m unittest tests.test_filesystem
```

Para testar como servidor MCP, use o MCP Inspector:

```bash
npx @modelcontextprotocol/inspector python server.py
```

No DOK, nenhuma alteração no cliente MCP é necessária: o cliente já chama
`list_tools()` e descobre automaticamente as novas ferramentas.

## Estrutura

```text
dok-tools/
├── server.py
├── providers.py          # abstração de IA própria (Anthropic/OpenRouter) — usada pelo Oráculo e Visão
├── requirements.txt
├── config/
│   └── config.yaml
├── data/
│   └── oracle/
│       └── <Nome da Obra>/
│           ├── chapters.md
│           └── work.md
└── tools/
    ├── device.py
    ├── domain.py
    ├── filesystem.py
    ├── network.py
    ├── oracle.py
    ├── pdf.py
    ├── vision.py
    └── website.py
```
