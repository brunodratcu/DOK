"""Ferramentas locais de filesystem, somente leitura.

As funções deste módulo não conhecem o MCP. Elas recebem parâmetros simples
e devolvem dicionários, ficando fáceis de testar e reutilizar.

Acesso é limitado a diretórios explicitamente autorizados na configuração
do dok-tools. Caminhos são resolvidos antes da checagem para impedir escapes
por ``..`` ou links simbólicos.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Iterable

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"

DEFAULT_MAX_READ_CHARS = 40_000
DEFAULT_MAX_RESULTS = 200
DEFAULT_MAX_SEARCH_FILE_BYTES = 5 * 1024 * 1024


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _allowed_roots() -> list[Path]:
    cfg = _load_config().get("filesystem", {})
    if cfg.get("allow_all", False):
        # O DOK é um app local: quando habilitado, caminhos escolhidos pelo
        # usuário podem estar em qualquer volume/pasta do sistema operacional.
        # A resolução normal de Path continua impedindo caminhos inválidos.
        return [Path("/").resolve()] if os.name != "nt" else [Path.cwd().anchor and Path(Path.cwd().anchor).resolve()]

    configured = cfg.get("allowed_paths") or []

    roots: list[Path] = []
    for raw in configured:
        if not raw:
            continue
        path = Path(os.path.expandvars(os.path.expanduser(str(raw))))
        if not path.is_absolute():
            path = BASE_DIR.parent / path
        try:
            roots.append(path.resolve())
        except OSError:
            continue

    # Sem configuração, o comportamento seguro é permitir somente o projeto
    # DOK. O usuário pode adicionar Documentos, Downloads, pasta de mangás etc.
    # no config.yaml.
    if not roots:
        roots.append(BASE_DIR.parent.resolve())
    return roots


def _resolve_allowed(path: str) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("O caminho é obrigatório.")

    raw = Path(os.path.expandvars(os.path.expanduser(path.strip())))
    if not raw.is_absolute():
        # Caminhos relativos continuam relativos ao projeto; anexos do SO
        # normalmente chegam como caminhos absolutos.
        raw = BASE_DIR.parent / raw

    try:
        resolved = raw.resolve(strict=False)
    except OSError as exc:
        raise ValueError(f"Não foi possível resolver o caminho: {exc}") from exc

    # Em modo desktop, os caminhos escolhidos pelo usuário podem estar em
    # qualquer volume do sistema (inclusive outro drive no Windows).
    if _load_config().get("filesystem", {}).get("allow_all", False):
        return resolved

    for root in _allowed_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue

    allowed = ", ".join(str(p) for p in _allowed_roots())
    raise PermissionError(
        f"Acesso negado: o caminho está fora das pastas autorizadas. "
        f"Pastas autorizadas: {allowed}"
    )


def _display_path(path: Path) -> str:
    return str(path)


def _config_limits() -> tuple[int, int, int]:
    cfg = _load_config().get("filesystem", {})
    max_read_chars = int(cfg.get("max_read_chars", DEFAULT_MAX_READ_CHARS))
    max_results = int(cfg.get("max_results", DEFAULT_MAX_RESULTS))
    max_search_file_bytes = int(
        cfg.get("max_search_file_bytes", DEFAULT_MAX_SEARCH_FILE_BYTES)
    )
    return max(1, max_read_chars), max(1, max_results), max(1, max_search_file_bytes)


def list_directory(path: str = ".") -> dict:
    """Lista os arquivos e subpastas de um diretório autorizado.

    Retorna nomes, tipo e tamanho. Não lê o conteúdo dos arquivos.
    """
    target = _resolve_allowed(path)
    if not target.exists():
        raise FileNotFoundError(f"Diretório não encontrado: {path}")
    if not target.is_dir():
        raise NotADirectoryError(f"Não é um diretório: {path}")

    _, configured_max_results, _ = _config_limits()
    entries = []
    all_items = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    for item in all_items[:configured_max_results]:
        try:
            stat = item.stat()
            entries.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size_bytes": stat.st_size if item.is_file() else None,
            })
        except OSError as exc:
            entries.append({
                "name": item.name,
                "type": "unknown",
                "error": str(exc),
            })

    return {
        "path": _display_path(target),
        "entries": entries,
        "count": len(entries),
        "truncated": len(all_items) > configured_max_results,
        "max_results": configured_max_results,
    }


def _is_probably_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def read_file(path: str, max_chars: int | None = None) -> dict:
    """Lê um arquivo de texto autorizado, com limite de tamanho.

    O limite evita despejar arquivos gigantes no contexto do modelo. Arquivos
    binários não são lidos por esta ferramenta.
    """
    target = _resolve_allowed(path)
    if not target.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    if not target.is_file():
        raise IsADirectoryError(f"Não é um arquivo: {path}")

    configured_max, _, _ = _config_limits()
    requested_limit = int(max_chars) if max_chars is not None else configured_max
    limit = min(configured_max, max(1, requested_limit))
    # Evita carregar arquivos gigantes na memória: ainda podemos ler até o
    # limite configurado + uma pequena margem para detectar truncamento.
    max_bytes = max(limit * 4, 64 * 1024)
    with target.open("rb") as f:
        data = f.read(max_bytes + 1)

    if not _is_probably_text(data[: min(len(data), 64 * 1024)]):
        raise ValueError("O arquivo parece ser binário; read_file lê apenas texto.")

    text = data.decode("utf-8", errors="replace")
    truncated = len(text) > limit or len(data) > max_bytes
    if truncated:
        text = text[:limit]

    return {
        "path": _display_path(target),
        "content": text,
        "size_bytes": target.stat().st_size,
        "truncated": truncated,
        "max_chars": limit,
    }


def read_file_range(path: str, start_line: int, end_line: int) -> dict:
    """Lê só um trecho (por número de linha) de um arquivo de texto —
    evita carregar o arquivo inteiro quando só uma parte importa.
    Linhas contadas a partir de 1, inclusive nas duas pontas."""
    target = _resolve_allowed(path)
    if not target.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    if not target.is_file():
        raise IsADirectoryError(f"Não é um arquivo: {path}")
    if start_line < 1 or end_line < start_line:
        raise ValueError("Intervalo de linhas inválido.")

    with target.open("rb") as f:
        head = f.read(64 * 1024)
    if not _is_probably_text(head):
        raise ValueError("O arquivo parece ser binário; read_file_range lê apenas texto.")

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    selected = lines[start_line - 1 : end_line]

    return {
        "path": _display_path(target),
        "content": "\n".join(selected),
        "start_line": start_line,
        "end_line": min(end_line, total),
        "total_lines": total,
    }


def _iter_files(root: Path) -> Iterable[Path]:
    # os.walk é usado para continuar mesmo quando uma subpasta não pode ser
    # lida; o resultado daquela área simplesmente não aparece na busca.
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not Path(current, d).is_symlink()]
        for filename in files:
            path = Path(current, filename)
            if path.is_symlink():
                continue
            yield path


def search_files(
    path: str = ".",
    query: str | None = None,
    pattern: str | None = None,
    max_results: int | None = None,
) -> dict:
    """Pesquisa arquivos dentro de uma pasta autorizada.

    ``query`` procura texto dentro de arquivos UTF-8 pequenos o suficiente.
    ``pattern`` filtra nomes com glob, por exemplo ``*.py`` ou ``config.*``.
    Se nenhum dos dois for informado, lista os arquivos encontrados.
    """
    root = _resolve_allowed(path)
    if not root.exists():
        raise FileNotFoundError(f"Caminho não encontrado: {path}")
    if not root.is_dir():
        raise NotADirectoryError(f"A busca precisa começar em um diretório: {path}")

    _, configured_max_results, max_file_bytes = _config_limits()
    limit = max(1, int(max_results or configured_max_results))
    query = query.strip() if isinstance(query, str) else None
    pattern = pattern.strip() if isinstance(pattern, str) else None
    if query == "":
        query = None
    if pattern == "":
        pattern = None

    matches = []
    scanned = 0
    for file_path in _iter_files(root):
        if len(matches) >= limit:
            break
        if pattern and not fnmatch.fnmatch(file_path.name, pattern):
            continue
        scanned += 1

        item = {"path": _display_path(file_path), "name": file_path.name}
        if query is not None:
            try:
                if file_path.stat().st_size > max_file_bytes:
                    continue
                data = file_path.read_bytes()
                if not _is_probably_text(data):
                    continue
                text = data.decode("utf-8", errors="replace")
                if query.casefold() not in text.casefold():
                    continue
                line_numbers = [
                    index
                    for index, line in enumerate(text.splitlines(), start=1)
                    if query.casefold() in line.casefold()
                ]
                item["matching_lines"] = line_numbers[:20]
            except (OSError, UnicodeError):
                continue

        try:
            item["size_bytes"] = file_path.stat().st_size
        except OSError:
            item["size_bytes"] = None
        matches.append(item)

    return {
        "path": _display_path(root),
        "query": query,
        "pattern": pattern,
        "matches": matches,
        "count": len(matches),
        "truncated": len(matches) >= limit,
        "max_results": limit,
        "scanned_candidates": scanned,
    }


def file_info(path: str) -> dict:
    """Retorna metadados de um arquivo ou diretório autorizado."""
    target = _resolve_allowed(path)
    if not target.exists():
        raise FileNotFoundError(f"Caminho não encontrado: {path}")

    stat = target.stat()
    return {
        "path": _display_path(target),
        "name": target.name,
        "type": "directory" if target.is_dir() else "file",
        "size_bytes": stat.st_size,
        "modified_timestamp": stat.st_mtime,
        "created_timestamp": getattr(stat, "st_ctime", None),
        "readable": os.access(target, os.R_OK),
        "writable": os.access(target, os.W_OK),
    }


def write_file(path: str, content: str, overwrite: bool = False) -> dict:
    """Cria um arquivo novo (ou sobrescreve, se overwrite=True) numa
    pasta autorizada. Bloqueado por padrão via permissions.deny no
    config do DOK — precisa ser explicitamente liberado."""
    target = _resolve_allowed(path)
    if target.exists() and not overwrite:
        raise FileExistsError(
            f"Arquivo já existe: {path}. Use overwrite=true pra sobrescrever."
        )
    if not isinstance(content, str):
        raise ValueError("O conteúdo precisa ser texto.")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {
        "path": _display_path(target),
        "bytes_written": len(content.encode("utf-8")),
        "overwritten": target.exists() and overwrite,
    }


def edit_file(path: str, old_text: str, new_text: str) -> dict:
    """Substitui um trecho EXATO de um arquivo existente por outro.
    old_text precisa aparecer exatamente uma vez — evita edição
    ambígua ou destruição acidental de conteúdo. Bloqueado por padrão
    via permissions.deny no config do DOK."""
    target = _resolve_allowed(path)
    if not target.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    if not target.is_file():
        raise IsADirectoryError(f"Não é um arquivo: {path}")

    content = target.read_text(encoding="utf-8")
    count = content.count(old_text)
    if count == 0:
        raise ValueError("old_text não encontrado no arquivo — confira o texto exato.")
    if count > 1:
        raise ValueError(
            f"old_text encontrado {count} vezes — precisa ser único. "
            "Inclua mais contexto ao redor pra tornar a busca exata."
        )

    new_content = content.replace(old_text, new_text, 1)
    target.write_text(new_content, encoding="utf-8")
    return {"path": _display_path(target), "replaced": True}
