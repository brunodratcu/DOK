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
from tools.vision import describe_image
from tools.pdf import read_pdf_text
from tools.filesystem import (
    list_directory as fs_list_directory,
    read_file as fs_read_file,
    read_file_range as fs_read_file_range,
    search_files as fs_search_files,
    file_info as fs_file_info,
    write_file as fs_write_file,
    edit_file as fs_edit_file,
)

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
def oracle_ingest_tool(folder_path: str, block_size: int = 4) -> dict:
    """Processa uma pasta com PDFs de mangá/HQ — não precisa organizar
    em subpastas por obra, o nome da obra é inferido do nome de cada
    arquivo (ex: 'Two Blue Vortex Chapter 001.pdf'). Cada capítulo é
    lido em blocos pequenos de páginas (block_size, padrão 4) pra
    controlar memória e custo, depois consolidado. Salva progresso a
    cada capítulo — não perde trabalho se for interrompido. Detecta
    sozinho se o PDF é texto (resume direto) ou visual (usa IA de
    visão)."""
    return oracle_ingest(folder_path, block_size=block_size)


@mcp.tool()
def oracle_query_tool(work: str = None) -> dict:
    """Consulta a memória já processada do Oráculo, sem reprocessar
    nenhum PDF. Sem 'work', devolve a memória de todas as obras. Com
    'work' (o nome inferido da obra), devolve só a memória cumulativa
    dela (personagens, linha do tempo, estado atual da história)."""
    return oracle_query(work)


@mcp.tool()
def oracle_status_tool() -> dict:
    """Mostra quantos capítulos de cada obra já foram processados —
    útil pra saber o que falta ou o que foi adicionado recentemente."""
    return oracle_status()


@mcp.tool()
def list_directory(path: str = ".") -> dict:
    """Lista os arquivos e subpastas de um diretório autorizado na máquina local."""
    return fs_list_directory(path)


@mcp.tool()
def read_file(path: str, max_chars: int = None) -> dict:
    """Lê o conteúdo de um arquivo de texto autorizado na máquina local. Arquivos binários não são lidos."""
    return fs_read_file(path, max_chars=max_chars)


@mcp.tool()
def read_file_range(path: str, start_line: int, end_line: int) -> dict:
    """Lê só um trecho de um arquivo de texto (por número de linha, inclusive nas duas pontas) — use quando só uma parte do arquivo importa, evita gastar contexto com o resto."""
    return fs_read_file_range(path, start_line, end_line)


@mcp.tool()
def search_files(path: str = ".", query: str = None, pattern: str = None, max_results: int = None) -> dict:
    """Pesquisa arquivos em uma pasta autorizada por texto (query) e/ou nome (pattern, como *.py)."""
    return fs_search_files(path, query=query, pattern=pattern, max_results=max_results)


@mcp.tool()
def file_info(path: str) -> dict:
    """Retorna metadados de um arquivo ou diretório autorizado na máquina local."""
    return fs_file_info(path)


@mcp.tool()
def write_file(path: str, content: str, overwrite: bool = False) -> dict:
    """Cria um arquivo novo (ou sobrescreve, se overwrite=true) numa pasta autorizada."""
    return fs_write_file(path, content, overwrite=overwrite)


@mcp.tool()
def edit_file(path: str, old_text: str, new_text: str) -> dict:
    """Substitui um trecho exato (old_text) de um arquivo existente por new_text. old_text precisa ser único no arquivo."""
    return fs_edit_file(path, old_text, new_text)


@mcp.tool()
def describe_image_tool(path: str, question: str = None) -> dict:
    """Descreve o conteúdo visual de uma foto/imagem autorizada (jpg, png, gif, webp) via IA de visão. Use 'question' pra focar a análise em algo específico."""
    return describe_image(path, question=question)


@mcp.tool()
def read_pdf_text_tool(path: str, max_pages: int = 100) -> dict:
    """Lê o TEXTO de um PDF normal (curso, artigo, contrato, relatório) — extração direta, sem IA de visão, rápida e barata. Se o PDF for majoritariamente imagem (ex: mangá/HQ digitalizada), o resultado avisa isso — use oracle_ingest_tool nesse caso em vez desta."""
    return read_pdf_text(path, max_pages=max_pages)


if __name__ == "__main__":
    # show_banner=False é essencial: sem isso, o banner do FastMCP pode
    # vazar pro stdout (bug conhecido, mais comum no Windows com
    # localidade não-inglesa) e corromper o protocolo JSON-RPC que
    # roda sobre esse mesmo canal — causa direta de "Connection closed"
    # de forma consistente, não ocasional.
    mcp.run(transport="stdio", show_banner=False)
