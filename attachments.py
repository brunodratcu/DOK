"""Leitura local de anexos antes de enviar a mensagem ao modelo.

O caminho do arquivo nunca é enviado como se fosse o conteúdo. O backend local
abre o arquivo primeiro e entrega texto ou imagens ao provider.
"""
from __future__ import annotations

import base64
import io
import mimetypes
import os
from pathlib import Path

import fitz


TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".json", ".jsonl", ".yaml", ".yml",
    ".csv", ".tsv", ".xml", ".html", ".htm", ".css", ".js", ".jsx",
    ".ts", ".tsx", ".py", ".pyw", ".java", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".go", ".rs", ".php", ".rb", ".sh", ".bash", ".sql",
    ".toml", ".ini", ".cfg", ".conf", ".log", ".env",
}

def _read_text(path: Path, max_chars: int = 30_000) -> str:
    with path.open("rb") as f:
        data = f.read(max(64 * 1024, max_chars * 4) + 1)
    return data.decode("utf-8", errors="replace")[:max_chars]

def _pdf_attachment(path: Path, max_chars: int = 24_000, max_pages: int = 6) -> dict:
    doc = fitz.open(str(path))
    try:
        page_count = len(doc)
        text_parts = []
        total = 0
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                piece = f"\n--- Página {i + 1} ---\n{text}"
                remaining = max_chars - total
                if remaining <= 0:
                    break
                text_parts.append(piece[:remaining])
                total += len(piece)

        text = "".join(text_parts).strip()
        result = {
            "kind": "pdf",
            "path": str(path),
            "page_count": page_count,
            "text": text,
            "text_available": bool(text),
            "images": [],
        }

        # PDF sem camada de texto: renderiza poucas páginas para visão.
        # Não materializa o capítulo inteiro na RAM.
        if not text:
            for i in range(min(page_count, max_pages)):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
                buf = pix.tobytes("jpeg", jpg_quality=78)
                encoded = base64.b64encode(buf).decode("ascii")
                result["images"].append({
                    "page": i + 1,
                    "data_url": f"data:image/jpeg;base64,{encoded}",
                })
        return result
    finally:
        doc.close()

def read_attachment(path: str, max_chars: int = 30_000) -> dict:
    """Abre localmente um anexo e devolve conteúdo pronto para o modelo."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Caminho do anexo vazio.")

    target = Path(os.path.expandvars(os.path.expanduser(path.strip()))).resolve()
    if not target.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {target}")
    if not target.is_file():
        raise IsADirectoryError(f"O anexo não é um arquivo: {target}")

    if target.suffix.lower() == ".pdf":
        return _pdf_attachment(target, max_chars=max_chars)

    if target.suffix.lower() in TEXT_EXTENSIONS or target.suffix.lower() == "":
        return {
            "kind": "text",
            "path": str(target),
            "text": _read_text(target, max_chars=max_chars),
            "images": [],
        }

    # Tenta texto mesmo para extensões desconhecidas; só declara binário se
    # houver bytes nulos ou UTF-8 claramente inválido.
    raw = target.read_bytes()[: min(target.stat().st_size, 64 * 1024)]
    if b"\x00" not in raw:
        try:
            raw.decode("utf-8")
            return {
                "kind": "text",
                "path": str(target),
                "text": _read_text(target, max_chars=max_chars),
                "images": [],
            }
        except UnicodeDecodeError:
            pass

    return {
        "kind": "binary",
        "path": str(target),
        "text": "",
        "images": [],
        "message": f"Formato binário não suportado para leitura automática: {target.suffix or 'sem extensão'}",
    }
