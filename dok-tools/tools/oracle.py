"""
oracle.py — o Oráculo: lê PDFs de manga em BLOCOS pequenos de páginas
com retry e checkpoint por bloco, e mantém memória por obra em
markdown:

    data/oracle/<Nome da Obra>/
        chapters.md          — histórico completo, um capítulo por vez
        work.md                — memória cumulativa da obra
        .in_progress.json       — checkpoint de bloco (removido quando
                                    o capítulo termina com sucesso)

Confiabilidade (a correção central):
    resposta vazia -> aceita como válida -> capítulo vazio salvo   ❌ ANTES
    resposta vazia -> retry -> se continuar vazia -> FAILED         ✅ AGORA

Nunca reprocessa um capítulo inteiro por causa de UM bloco que falhou
— o checkpoint guarda os blocos que já deram certo.

Pra 1GB de RAM: nada de banco vetorial, embeddings, indexação pesada,
nem PDF inteiro carregado de uma vez — um bloco de páginas por vez,
liberado da memória assim que processado.
"""
import base64
import hashlib
import json
import os
import re

import pymupdf
import yaml

from providers import create_provider

# pytesseract/Pillow são OPCIONAIS — só usados pelo caminho de OCR
# (pastas de imagem JPEG). Import atrasado (lazy) de propósito: um
# import quebrado aqui não pode derrubar o processo do servidor MCP
# inteiro (server.py importa este módulo no topo do arquivo — se isso
# lançar ImportError, NENHUMA ferramenta funciona, não só o Oráculo).
def _load_ocr_deps():
    try:
        import pytesseract
        from PIL import Image
        return pytesseract, Image
    except ImportError as exc:
        raise RuntimeError(
            "OCR indisponível: instale as dependências com "
            "'pip install pytesseract Pillow' e o binário do Tesseract "
            "(apt install tesseract-ocr tesseract-ocr-por no Linux/Pi; "
            "instalador oficial + PATH no Windows). "
            f"Detalhe: {exc}"
        ) from exc


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
OCR_LANG = "eng+por"  # inglês e português, conforme os mangás que você lê

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "..", "config", "config.yaml")
ORACLE_ROOT = os.path.join(BASE_DIR, "..", "data", "oracle")

DEFAULT_BLOCK_SIZE = 4
BLOCK_MAX_TOKENS = 450        # notas compactas, não prosa — controla custo e risco de corte
CONSOLIDATE_MAX_TOKENS = 800
WORK_MEMORY_MAX_TOKENS = 1200
MAX_RETRIES = 2                # tentativas EXTRAS além da primeira (total = 1 + MAX_RETRIES)
TEXT_PDF_MIN_CHARS_PAGE = 200
UNCLASSIFIED_WORK = "obra-nao-classificada"

# --- Inferência de obra/capítulo pelo nome do arquivo ---

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


def _state_path(work: str) -> str:
    return os.path.join(_work_dir(work), ".in_progress.json")


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


_DIR_CHAPTER_RE = re.compile(r"(?i)(?:chapter|cap[ií]tulo|cap\.?|ch\.?)[\s_\-]*0*(?P<num>\d+)")


def _infer_chapter_from_dirname(dirname: str):
    """Extrai o número do capítulo do nome da pasta (ex: 'capitulo_036',
    'ch-36', '36')."""
    m = _DIR_CHAPTER_RE.search(dirname)
    if m:
        return int(m.group("num"))
    m = re.search(r"(\d+)\s*$", dirname.strip())
    return int(m.group(1)) if m else None


def discover_image_chapters(folder_path: str):
    """Descobre capítulos como PASTAS de imagens JPEG baixadas direto
    da web (sem passar por PDF), na estrutura:
        <folder_path>/<Obra>/<pasta_do_capitulo>/*.jpg
    Gerado pelo manga_scrape.py.
    """
    found = []
    folder_path = os.path.abspath(folder_path)
    if not os.path.isdir(folder_path):
        return found
    for work_name in sorted(os.listdir(folder_path)):
        work_path = os.path.join(folder_path, work_name)
        if not os.path.isdir(work_path):
            continue
        for chapter_dir in sorted(os.listdir(work_path)):
            chapter_path = os.path.join(work_path, chapter_dir)
            if not os.path.isdir(chapter_path):
                continue
            images = sorted(
                f for f in os.listdir(chapter_path)
                if f.lower().endswith(IMAGE_EXTS)
            )
            if not images:
                continue
            chapter = _infer_chapter_from_dirname(chapter_dir)
            if chapter is None:
                continue
            found.append({
                "work": work_name, "chapter": chapter,
                "image_paths": [os.path.join(chapter_path, f) for f in images],
            })
    return found


def _hash_images(image_paths):
    """Hash combinado de todos os arquivos de um capítulo — mesmo
    papel do _file_hash, mas pra várias imagens em vez de um PDF."""
    h = hashlib.sha256()
    for p in image_paths:
        with open(p, "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:16]


def _ocr_chapter_images(image_paths, lang=OCR_LANG):
    """OCR 100% local — nunca sobe imagem pra API. Devolve o texto de
    todas as páginas concatenado, na ordem dos arquivos (page_001,
    page_002, ...). É isso que substitui o PDF+visão: mais rápido
    (sem render do PyMuPDF, sem chamada de rede por bloco) e mais
    barato (texto em vez de imagem no prompt)."""
    pytesseract, Image = _load_ocr_deps()
    parts = []
    for i, path in enumerate(image_paths, start=1):
        img = Image.open(path)
        try:
            text = pytesseract.image_to_string(img, lang=lang, config="--psm 6").strip()
        finally:
            img.close()
        parts.append(f"[Página {i}]\n{text}")
    return "\n\n".join(parts)


def _file_hash(path, chunk_size=65536):
    """Hash curto do conteúdo do arquivo — usado pra saber se um PDF
    já processado mudou (re-scan, arquivo diferente com mesmo nome)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


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


# --- Checkpoint de bloco (retomada) ---

def _load_state(work):
    path = _state_path(work)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_state(work, chapter, file_hash, block_notes, next_block_index):
    with open(_state_path(work), "w", encoding="utf-8") as f:
        json.dump({
            "chapter": chapter, "file_hash": file_hash,
            "block_notes": block_notes, "next_block_index": next_block_index,
        }, f, ensure_ascii=False)


def _clear_state(work):
    path = _state_path(work)
    if os.path.exists(path):
        os.remove(path)


# --- Chamada de IA com retry — a correção central ---

def _is_empty(text):
    return not text or not text.strip()


def _call_with_retry(provider, *, model, system_prompt, content, max_tokens, location):
    """
    Chama o provider; se vier resposta vazia OU erro de API, tenta de
    novo (até MAX_RETRIES vezes extras). Retorna (ok, texto_ou_motivo,
    detalhe_pra_log) — NUNCA aceita vazio como sucesso.
    """
    last_detail = None
    for attempt in range(1 + MAX_RETRIES):
        response = provider.chat(model=model, system_prompt=system_prompt, content=content, max_tokens=max_tokens)
        last_detail = {
            "attempt": attempt + 1,
            "finish_reason": response.get("finish_reason"),
            "http_status": response.get("http_status"),
            "usage": response.get("usage"),
            "error": response.get("error"),
        }
        if response.get("error"):
            continue
        text = response.get("text", "")
        if not _is_empty(text):
            return True, text, last_detail

    return False, f"{location}: resposta vazia após {1 + MAX_RETRIES} tentativa(s). Detalhe: {last_detail}", last_detail


# --- Análise de bloco (notas compactas, não prosa) ---

def _analyze_block(images_b64, work, chapter, block_index, total_blocks, provider, model):
    content = [{"type": "text", "text": (
        f"Bloco {block_index + 1} de {total_blocks} do capítulo {chapter} da obra "
        f"'{work}'. Liste em NOTAS COMPACTAS (não prosa, no máximo ~15 linhas) o que "
        "acontece nestas páginas: eventos (bullet curto), personagens presentes "
        "(nomes), falas importantes (citação curta). Se alguma página não for "
        "conteúdo de mangá (ex: propaganda, capa de site, imagem não relacionada ao "
        "capítulo), diga isso em uma linha e ignore essa página — não recuse a "
        "tarefa inteira por causa disso. Não invente nada."
    )}]
    for img in images_b64:
        content.append({"type": "image_b64", "media_type": "image/jpeg", "data": img})

    location = f"Capítulo {chapter}, Bloco {block_index + 1}/{total_blocks}"
    return _call_with_retry(
        provider, model=model,
        system_prompt="Você descreve com precisão o conteúdo visual de páginas de mangá, em notas compactas, sem inventar nada.",
        content=content, max_tokens=BLOCK_MAX_TOKENS, location=location,
    )


def _consolidate_chapter(block_notes, work, chapter, provider, model):
    joined = "\n\n---\n\n".join(f"Bloco {i + 1}:\n{t}" for i, t in enumerate(block_notes))
    prompt = (
        f"Notas dos blocos de páginas do capítulo {chapter} da obra '{work}', em ordem:\n\n"
        f"{joined}\n\n"
        "Consolide num resumo único e coerente do capítulo, em markdown:\n"
        "**Resumo:** (parágrafo)\n**Personagens:** (lista)\n**Eventos-chave:** (lista)\n"
        "**Falas marcantes:** (lista, se houver)\n"
        "Não invente nada além do que está nas notas acima."
    )
    return _call_with_retry(
        provider, model=model,
        system_prompt="Você consolida notas de mangá num resumo de capítulo coerente e fiel.",
        content=[{"type": "text", "text": prompt}], max_tokens=CONSOLIDATE_MAX_TOKENS,
        location=f"Capítulo {chapter}, consolidação",
    )


def _summarize_text_chapter(text, work, chapter, provider, model):
    prompt = (
        f"Resuma o capítulo {chapter} da obra '{work}' a partir deste texto, em markdown:\n"
        "**Resumo:** (parágrafo)\n**Personagens:** (lista)\n**Eventos-chave:** (lista)\n\n"
        f"Texto:\n{text[:20000]}"
    )
    return _call_with_retry(
        provider, model=model,
        system_prompt="Você resume capítulos de texto com precisão, sem inventar.",
        content=[{"type": "text", "text": prompt}], max_tokens=CONSOLIDATE_MAX_TOKENS,
        location=f"Capítulo {chapter} (texto)",
    )


# --- Memória persistente ---

def _chapter_already_processed(work, chapter, file_hash):
    """Só considera 'já processado' se o capítulo existe E o hash do
    arquivo bate com o que foi salvo — se o PDF mudou (re-scan,
    arquivo diferente com mesmo nome), reprocessa."""
    path = _chapters_md_path(work)
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if f"## Capítulo {chapter}\n" not in content:
        return False
    return f"<!-- source_hash: {file_hash} -->" in content


def _append_chapter(work, chapter, consolidated_md, file_hash, model, total_blocks):
    path = _chapters_md_path(work)
    is_new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# {work}\n\n")
        f.write(f"## Capítulo {chapter}\n\n")
        f.write(f"<!-- source_hash: {file_hash} -->\n")
        f.write(f"<!-- processado_com: {model}, blocos: {total_blocks} -->\n\n")
        f.write(f"{consolidated_md}\n\n")


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
    ok, new_content, detail = _call_with_retry(
        provider, model=model,
        system_prompt="Você mantém a memória cumulativa e fiel de uma obra de mangá.",
        content=[{"type": "text", "text": prompt}], max_tokens=WORK_MEMORY_MAX_TOKENS,
        location=f"Atualização de memória — {work}",
    )
    if not ok:
        return False, new_content  # NÃO sobrescreve work.md com falha
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {work} — Memória\n\n{new_content}")
    return True, new_content


# --- Processamento de um capítulo visual, com checkpoint por bloco ---

def _process_visual_chapter(item, work, chapter, provider, model, block_size, log):
    file_hash = _file_hash(item["path"])
    state = _load_state(work)

    doc = pymupdf.open(item["path"])
    try:
        total_pages = len(doc)
        total_blocks = max(1, (total_pages + block_size - 1) // block_size)

        block_notes = []
        start_block = 0
        if state and state.get("chapter") == chapter and state.get("file_hash") == file_hash:
            block_notes = state.get("block_notes", [])
            start_block = state.get("next_block_index", 0)
            log.append(f"Capítulo {chapter}: retomando do bloco {start_block + 1}/{total_blocks} (checkpoint encontrado).")

        for b in range(start_block, total_blocks):
            start, end = b * block_size, min((b + 1) * block_size, total_pages)
            images = _render_block(doc, start, end)
            ok, text_or_reason, detail = _analyze_block(images, work, chapter, b, total_blocks, provider, model)
            images = None  # libera a memória do bloco antes do próximo

            log.append(f"Capítulo {chapter}, Bloco {b + 1}/{total_blocks}: {'OK' if ok else 'FALHOU'} — {detail}")

            if not ok:
                # salva o progresso até aqui — os blocos que JÁ funcionaram não se perdem
                _save_state(work, chapter, file_hash, block_notes, b)
                return False, f"Capítulo {chapter}, Bloco {b + 1}/{total_blocks}: {text_or_reason}", file_hash, total_blocks

            block_notes.append(text_or_reason)
            _save_state(work, chapter, file_hash, block_notes, b + 1)
    finally:
        doc.close()

    ok, consolidated, detail = _consolidate_chapter(block_notes, work, chapter, provider, model)
    if not ok:
        return False, f"Capítulo {chapter}, consolidação: {consolidated}", file_hash, total_blocks

    _clear_state(work)  # capítulo concluído — não precisa mais do checkpoint
    return True, consolidated, file_hash, total_blocks


# --- Orquestração ---

def oracle_ingest(folder_path: str, block_size: int = DEFAULT_BLOCK_SIZE):
    cfg = _load_config()
    provider, model = create_provider(cfg)
    if not provider.api_key:
        return {"ok": False, "error": f"Chave da {provider.name} não configurada em dok-tools/config/config.yaml"}

    report = {
        "ok": True, "provider": provider.name,
        "chapters_added": [], "chapters_skipped": [], "chapters_failed": [],
        "errors": [], "log": [],
    }

    all_items = (
        [dict(it, source="pdf") for it in discover_pdfs(folder_path)]
        + [dict(it, source="images") for it in discover_image_chapters(folder_path)]
    )

    for item in all_items:
        work, chapter = item["work"], item["chapter"]
        if chapter is None:
            report["errors"].append(f"Não consegui identificar o capítulo de {item.get('filename', item.get('image_paths', ['?'])[0])}")
            continue

        try:
            if item["source"] == "images":
                try:
                    file_hash = _hash_images(item["image_paths"])
                    if _chapter_already_processed(work, chapter, file_hash):
                        report["chapters_skipped"].append(f"{work} cap {chapter} (já processado)")
                        continue
                    text = _ocr_chapter_images(item["image_paths"])
                except RuntimeError as exc:
                    report["chapters_failed"].append(f"{work} cap {chapter}: {exc}")
                    continue
                ok, consolidated, detail = _summarize_text_chapter(text, work, chapter, provider, model)
                total_blocks = 1
                if not ok:
                    report["chapters_failed"].append(f"Capítulo {chapter}: {consolidated}")
                    continue
                _append_chapter(work, chapter, consolidated, file_hash, model, total_blocks)
                work_ok, _ = _update_work_memory(work, consolidated, provider, model)
                if not work_ok:
                    report["errors"].append(f"Capítulo {chapter} salvo, mas atualização da memória da obra falhou.")
                report["chapters_added"].append(f"{work} cap {chapter} (OCR)")
                continue

            file_hash = _file_hash(item["path"])
            if _chapter_already_processed(work, chapter, file_hash):
                report["chapters_skipped"].append(f"{work} cap {chapter} (já processado)")
                continue

            if _is_text_pdf(item["path"]):
                text = _extract_pdf_text(item["path"])
                ok, consolidated, detail = _summarize_text_chapter(text, work, chapter, provider, model)
                total_blocks = 1
                if not ok:
                    report["chapters_failed"].append(f"Capítulo {chapter}: {consolidated}")
                    continue
            else:
                ok, consolidated, file_hash, total_blocks = _process_visual_chapter(
                    item, work, chapter, provider, model, block_size, report["log"]
                )
                if not ok:
                    report["chapters_failed"].append(consolidated)
                    continue

            _append_chapter(work, chapter, consolidated, file_hash, model, total_blocks)
            work_ok, _ = _update_work_memory(work, consolidated, provider, model)
            if not work_ok:
                report["errors"].append(f"Capítulo {chapter} salvo, mas atualização da memória da obra falhou.")
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
        in_progress = os.path.exists(_state_path(name))
        result[name] = {"chapters_ingested": count, "in_progress": in_progress}
    return result
