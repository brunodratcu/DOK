"""
pdf.py — lê o texto de um PDF "normal" (curso, artigo, relatório,
contrato) que tem texto de verdade embutido — diferente do Oráculo,
que é pra mangá/HQ (imagem, sem texto extraível, precisa de IA de
visão). Extração direta via PyMuPDF, sem gastar chamada de IA —
mais rápido e mais barato pra esse caso.
"""
import pymupdf

from tools.filesystem import _resolve_allowed, _display_path

MIN_CHARS_PER_PAGE = 200   # mesmo limiar do Oráculo, pra avisar se o PDF é majoritariamente imagem
MAX_CONTENT_CHARS = 40000  # mesmo limite do read_file, evita estourar o contexto do modelo


def read_pdf_text(path: str, max_pages: int = 100) -> dict:
    target = _resolve_allowed(path)
    if not target.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    if target.suffix.lower() != ".pdf":
        raise ValueError(f"Não é um PDF: {path}")

    doc = pymupdf.open(str(target))
    try:
        total_pages = len(doc)
        pages_to_read = min(total_pages, max_pages)
        parts = [doc.load_page(i).get_text() for i in range(pages_to_read)]
    finally:
        doc.close()

    text = "\n\n".join(parts).strip()
    avg_chars_per_page = len(text) / max(pages_to_read, 1)
    is_text_pdf = avg_chars_per_page >= MIN_CHARS_PER_PAGE

    content = text[:MAX_CONTENT_CHARS]
    truncated = len(text) > MAX_CONTENT_CHARS or pages_to_read < total_pages

    return {
        "path": _display_path(target),
        "total_pages": total_pages,
        "pages_read": pages_to_read,
        "content": content,
        "truncated": truncated,
        "is_text_pdf": is_text_pdf,
        "note": None if is_text_pdf else (
            "Pouco texto extraído — este PDF pode ser majoritariamente "
            "imagem (ex: mangá/HQ digitalizada). Pra esse caso, use "
            "oracle_ingest_tool em vez desta ferramenta."
        ),
    }
