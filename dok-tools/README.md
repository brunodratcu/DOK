# dok-tools

Servidor MCP independente do DOK. Ele expõe ferramentas de diagnóstico,
Oráculo de mangás e, agora, quatro ferramentas locais de filesystem em modo
**somente leitura**:

- `list_directory` — lista arquivos e subpastas.
- `read_file` — lê arquivos de texto.
- `search_files` — procura arquivos por nome (`pattern`) e/ou texto (`query`).
- `file_info` — retorna metadados de arquivo ou diretório.

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

## As outras ferramentas

Diagnóstico:

- `check_network_tool`
- `check_website_tool`
- `check_device_mac_tool`
- `whois_domain_tool`

Oráculo:

- `oracle_ingest_tool`
- `oracle_query_tool`
- `oracle_status_tool`

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
├── requirements.txt
├── config/
│   └── config.yaml
├── data/
│   └── oracle/
└── tools/
    ├── device.py
    ├── domain.py
    ├── filesystem.py
    ├── network.py
    ├── oracle.py
    └── website.py
```
