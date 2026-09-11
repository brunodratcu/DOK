"""
dok-tools — servidor MCP independente.

Este projeto NÃO depende do DOK e não importa nada de lá. Qualquer
cliente MCP (o próprio DOK, o Claude Desktop, o Claude Code) pode se
conectar e usar essas ferramentas sem saber nada sobre o resto.

Rodar sozinho pra testar:
    python server.py
(fica esperando conexão via stdio — não faz nada visível sozinho,
é assim que MCP funciona; use o MCP Inspector ou o client_test.py
pra interagir de verdade)
"""
from fastmcp import FastMCP

from tools.network import check_network
from tools.website import check_website
from tools.device import check_device_mac
from tools.domain import whois_domain
from tools.oracle import oracle_ingest, oracle_query, oracle_status

mcp = FastMCP("dok-tools")


@mcp.tool()
def check_network_tool(host: str) -> dict:
    """Verifica se um host (IP ou domínio) está acessível: ping e
    resolução DNS. Não faz nenhuma alteração, só leitura."""
    return check_network(host)


@mcp.tool()
def check_website_tool(url: str) -> dict:
    """Verifica a saúde de um site: código de status HTTP, tempo de
    resposta, e validade do certificado SSL (dias até expirar)."""
    return check_website(url)


@mcp.tool()
def check_device_mac_tool(mac_address: str) -> dict:
    """Verifica se um dispositivo com o MAC address dado está online
    AGORA na rede local (via tabela ARP), qual IP tem, e o fabricante.
    Só funciona pra dispositivos na mesma rede local — não alcança
    dispositivos remotos, isso é limitação de como ARP funciona."""
    return check_device_mac(mac_address)


@mcp.tool()
def whois_domain_tool(domain: str) -> dict:
    """Consulta o registro público WHOIS de um domínio: registrador,
    data de criação, data de expiração, servidores DNS."""
    return whois_domain(domain)


@mcp.tool()
def oracle_ingest_tool(folder_path: str) -> dict:
    """Processa uma pasta com PDFs de mangá organizados por obra
    (subpasta) e capítulo (nome do arquivo). Interpreta cada capítulo
    novo via IA de visão e atualiza o resumo geral de cada obra.
    Pode demorar — processa vários capítulos, um de cada vez, e salva
    o progresso a cada um (não perde trabalho se for interrompido)."""
    return oracle_ingest(folder_path)


@mcp.tool()
def oracle_query_tool(work: str = None) -> dict:
    """Consulta o conhecimento já processado do Oráculo. Sem 'work',
    devolve todas as obras. Com 'work' (ex: 'nng', 'tbv', 'ds'),
    devolve o resumo geral daquela obra e os capítulos já processados."""
    return oracle_query(work)


@mcp.tool()
def oracle_status_tool() -> dict:
    """Mostra quantos capítulos de cada obra já foram processados —
    útil pra saber o que falta ou o que foi adicionado recentemente."""
    return oracle_status()


if __name__ == "__main__":
    mcp.run(transport="stdio")
