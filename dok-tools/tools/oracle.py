"""
oracle.py — o Oráculo: lê PDFs de manga (ou qualquer HQ/documento
visual), interpreta em BLOCOS pequenos de páginas (controla memória e
tamanho de chamada), e mantém memória por obra em markdown:

    data/oracle/<Nome da Obra>/
        chapters.md   — histórico completo, um capítulo é anexado por vez
        work.md       — memória cumulativa (personagens, linha do tempo, etc.)

O nome da obra é INFERIDO do nome do arquivo — não precisa organizar
em pastas por obra. Processamento pesado sempre na nuvem (API);
localmente só abre página por bloco, nunca o PDF inteiro de uma vez —
pensado pra caber na memória de um Raspberry Pi.

Todas as chamadas de IA passam pelo providers.py deste projeto (não
reimplementa HTTP aqui) — troca de modelo/provedor sem duplicar código.
"""
import os
import re

import yaml
import pymupdf
import base64

from providers import create_provider

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "..", "config", "config.yaml")
ORACLE_ROOT = os.path.join(BASE_DIR, "..", "data", "oracle")

DEFAULT_BLOCK_SIZE = 4
TEXT_PDF_MIN_CHARS_PAGE = 200
UNCLASSIFIED_WORK = "obra-nao-classificada"

# --- Inferência de obra/capítulo pelo nome do arquivo (sem hardcode) ---

_CHAPTER_MARKER_RE = re.compile(
    r"(?i)^(?P<work>.*?)[\s_\-]*(?:chapter|cap[ií]tulo|cap\.?|ch\.?)[\s_\-]*(?P<num>\d+)"
)
_TRAILING_NUM_RE = re.compile(r"^(?P<work>.*?)[\s_\-]+(?P<num>\d+)$")


def _infer_work_and_chapter(filename: str):
    stem = os.path.splitext(filename)[0]
    m = _CHAPTER_MARKER_RE.match(stem)
    if m:
        work = m.group("work").strip(" _-.")
        return (work or UNCLASSIFIED_WORK), int(m.group("num"))
    m = _TRAILING_NUM_RE.match(stem)
    if m:
        work = m.group("work").strip(" _-.")
        return (work or UNCLASSIFIED_WORK), int(m.group("num"))
    return UNCLASSIFIED_WORK, None


def _safe_dirname(work: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", work).strip() or UNCLASSIFIED_WORK


def _work_dir(work: str) -> str:
    path = os.path.join(ORACLE_ROOT, _safe_dirname(work))
    os.makedirs(path, exist_ok=True)
    return path


def _chapters_md_path(work: str) -> str:
    return os.path.join(_work_dir(work), "chapters.md")


def _work_md_path(work: str) -> str:
    return os.path.join(_work_dir(work), "work.md")


# --- Config ---

def _load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# --- Descoberta de PDFs (recursiva, sem exigir pasta por obra) ---

def discover_pdfs(folder_path: str):
    found = []
    folder_path = os.path.abspath(folder_path)
    for root, _, files in os.walk(folder_path):
        for fname in sorted(files):
            if not fname.lower().endswith(".pdf"):
                continue
            work, chapter = _infer_work_and_chapter(fname)
            found.append({
                "work": work, "chapter": chapter,
                "path": os.path.join(root, fname), "filename": fname,
            })
    return found


# --- PDF: texto ou visual? ---

def _is_text_pdf(path, sample_pages=3, min_chars_per_page=TEXT_PDF_MIN_CHARS_PAGE):
    doc = pymupdf.open(path)
    try:
        n = min(len(doc), sample_pages)
        total = sum(len(doc.load_page(i).get_text().strip()) for i in range(n))
        return (total / max(n, 1)) >= min_chars_per_page
    finally:
        doc.close()


def _extract_pdf_text(path, max_pages=300):
    doc = pymupdf.open(path)
    try:
        n = min(len(doc), max_pages)
        return "\n\n".join(doc.load_page(i).get_text() for i in range(n)).strip()
    finally:
        doc.close()


def _render_block(doc, start, end, zoom=1.5):
    """Renderiza só um bloco de páginas por vez — nunca o PDF inteiro
    na memória de uma vez."""
    images = []
    for i in range(start, end):
        pix = doc.load_page(i).get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        images.append(base64.b64encode(pix.tobytes("jpeg")).decode("ascii"))
    return images


# --- Pipeline de um capítulo: blocos -> consolidação (via Provider) ---

def _analyze_block(images_b64, work, chapter, block_index, total_blocks, provider, model):
    content = [{"type": "text", "text": (
        f"Bloco {block_index + 1} de {total_blocks} do capítulo {chapter} da obra "
        f"'{work}'. Descreva em detalhe o que acontece nestas páginas específicas: "
        "eventos, personagens presentes, diálogos importantes. Não resuma a obra "
        "inteira, só o que está visível aqui. Não invente nada."
    )}]
    for img in images_b64:
        content.append({"type": "image_b64", "media_type": "image/jpeg", "data": img})
    return provider.chat(
        model=model,
        system_prompt="Você descreve com precisão o conteúdo visual de páginas de mangá, sem inventar nada.",
        content=content, max_tokens=1000,
    )


def _consolidate_chapter(block_texts, work, chapter, provider, model):
    joined = "\n\n---\n\n".join(f"Bloco {i + 1}:\n{t}" for i, t in enumerate(block_texts))
    prompt = (
        f"Descrições dos blocos de páginas do capítulo {chapter} da obra '{work}', em ordem:\n\n"
        f"{joined}\n\n"
        "Consolide num resumo único e coerente do capítulo, em markdown:\n"
        "**Resumo:** (parágrafo detalhado)\n**Personagens:** (lista)\n"
        "**Eventos-chave:** (lista)\n**Falas marcantes:** (lista, se houver)\n"
        "Não invente nada além do que está nos blocos acima."
    )
    return provider.chat(
        model=model,
        system_prompt="Você consolida análises de mangá num resumo de capítulo coerente e fiel.",
        content=[{"type": "text", "text": prompt}], max_tokens=1500,
    )


def _summarize_text_chapter(text, work, chapter, provider, model):
    prompt = (
        f"Resuma o capítulo {chapter} da obra '{work}' a partir deste texto, em markdown:\n"
        "**Resumo:** (parágrafo)\n**Personagens:** (lista)\n**Eventos-chave:** (lista)\n\n"
        f"Texto:\n{text[:20000]}"
    )
    return provider.chat(
        model=model,
        system_prompt="Você resume capítulos de texto com precisão, sem inventar.",
        content=[{"type": "text", "text": prompt}], max_tokens=1500,
    )


# --- Memória persistente (chapters.md + work.md) ---

def _chapter_already_processed(work, chapter):
    path = _chapters_md_path(work)
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        return f"## Capítulo {chapter}\n" in f.read()


def _append_chapter(work, chapter, consolidated_md):
    path = _chapters_md_path(work)
    is_new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# {work}\n\n")
        f.write(f"## Capítulo {chapter}\n\n{consolidated_md}\n\n")


def _update_work_memory(work, latest_chapter_md, provider, model):
    path = _work_md_path(work)
    existing = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
    prompt = (
        f"Memória cumulativa atual da obra '{work}':\n"
        f"{existing or '(vazia — este é o primeiro capítulo)'}\n\n"
        f"Capítulo recém-processado:\n{latest_chapter_md}\n\n"
        "Atualize a memória cumulativa incorporando esse capítulo, em markdown com "
        "seções: Personagens, Relações, Linha do Tempo, Conflitos, Revelações e "
        "Mistérios, Estado Atual da História. Preserve o conhecimento anterior; "
        "só adicione o que está sustentado pelos capítulos."
    )
    new_content = provider.chat(
        model=model,
        system_prompt="Você mantém a memória cumulativa e fiel de uma obra de mangá.",
        content=[{"type": "text", "text": prompt}], max_tokens=2000,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {work} — Memória\n\n{new_content}")
    return new_content


# --- Orquestração ---

def oracle_ingest(folder_path: str, block_size: int = DEFAULT_BLOCK_SIZE):
    cfg = _load_config()
    provider, model = create_provider(cfg)
    if not provider.api_key:
        return {"ok": False, "error": f"Chave da {provider.name} não configurada em dok-tools/config/config.yaml"}

    report = {"ok": True, "provider": provider.name, "chapters_added": [], "chapters_skipped": [], "errors": []}

    for item in discover_pdfs(folder_path):
        work, chapter = item["work"], item["chapter"]
        if chapter is None:
            report["errors"].append(f"Não consegui identificar o capítulo de {item['filename']}")
            continue
        if _chapter_already_processed(work, chapter):
            report["chapters_skipped"].append(f"{work} cap {chapter} (já processado)")
            continue

        try:
            if _is_text_pdf(item["path"]):
                text = _extract_pdf_text(item["path"])
                consolidated = _summarize_text_chapter(text, work, chapter, provider, model)
            else:
                doc = pymupdf.open(item["path"])
                try:
                    total_pages = len(doc)
                    total_blocks = max(1, (total_pages + block_size - 1) // block_size)
                    block_texts = []
                    for b in range(total_blocks):
                        start, end = b * block_size, min((b + 1) * block_size, total_pages)
                        images = _render_block(doc, start, end)
                        block_texts.append(_analyze_block(
                            images, work, chapter, b, total_blocks, provider, model
                        ))
                        images = None
                finally:
                    doc.close()
                consolidated = _consolidate_chapter(block_texts, work, chapter, provider, model)

            _append_chapter(work, chapter, consolidated)
            _update_work_memory(work, consolidated, provider, model)
            report["chapters_added"].append(f"{work} cap {chapter}")
        except Exception as exc:
            report["errors"].append(f"{work} cap {chapter}: {exc}")

    return report


def oracle_query(work: str = None):
    if not os.path.isdir(ORACLE_ROOT):
        return {}
    if work:
        path = _work_md_path(work)
        if not os.path.exists(path):
            return {"error": f"Nenhum conhecimento registrado pra '{work}'"}
        with open(path, "r", encoding="utf-8") as f:
            return {"work": work, "memory": f.read()}
    result = {}
    for name in sorted(os.listdir(ORACLE_ROOT)):
        path = os.path.join(ORACLE_ROOT, name, "work.md")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                result[name] = f.read()
    return result


def oracle_status():
    if not os.path.isdir(ORACLE_ROOT):
        return {}
    result = {}
    for name in sorted(os.listdir(ORACLE_ROOT)):
        chapters_path = os.path.join(ORACLE_ROOT, name, "chapters.md")
        count = 0
        if os.path.exists(chapters_path):
            with open(chapters_path, "r", encoding="utf-8") as f:
                count = f.read().count("\n## Capítulo")
        result[name] = {"chapters_ingested": count}
    return result
