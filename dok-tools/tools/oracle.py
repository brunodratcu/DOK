"""Memória narrativa do DOK baseada em três Markdown por obra.

Etapas:
1. pages.md    -> leitura detalhada das páginas, em ordem.
2. chapter.md  -> registro consolidado de cada capítulo.
3. work.md     -> memória cumulativa da obra.

Não há banco de dados nem JSON de conhecimento. Os Markdown são a fonte
persistente e legível da memória. A obra só é definida depois que o capítulo
foi completamente interpretado, usando o nome do arquivo como identificador.
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path

import pymupdf
import requests
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"
DEFAULT_MEMORY_ROOT = BASE_DIR / "data" / "oracle"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
CHAPTER_NUM_RE = re.compile(r"(?i)(?:chapter|cap(?:itulo)?|cap)?[^0-9]{0,8}(\d+)")


def _load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _provider_config(cfg):
    provider = cfg.get("provider", "openrouter")
    section = cfg.get(provider, {}) or {}
    api_key = section.get("api_key") or os.getenv("OPENROUTER_API_KEY" if provider == "openrouter" else "ANTHROPIC_API_KEY", "")
    return provider, api_key, section.get("model", "")


def _memory_root() -> Path:
    cfg = _load_config().get("oracle", {})
    raw = cfg.get("memory_path")
    if raw:
        path = Path(os.path.expandvars(os.path.expanduser(str(raw))))
        if not path.is_absolute():
            path = BASE_DIR / path
        return path.resolve()
    return DEFAULT_MEMORY_ROOT


def _safe_name(name: str) -> str:
    name = re.sub(r"[^\w\- .]+", "", name, flags=re.UNICODE).strip(" .")
    name = re.sub(r"\s+", " ", name)
    return name or "obra-nao-classificada"


def _infer_work_name(filename: str) -> str:
    """Extrai o nome da obra do nome do documento, sem mapa de obras.

    Exemplos:
      Two Blue Vortex Chapter 001.pdf -> Two Blue Vortex
      naruto_next_generation_12.pdf    -> naruto next generation
      Chapter_001.pdf                  -> obra-nao-classificada
    """
    stem = Path(filename).stem
    stem = re.sub(r"(?i)[._\- ]*(?:chapter|cap(?:itulo)?)[._\- ]*\d+.*$", "", stem)
    stem = re.sub(r"(?i)[._\- ]+\d{1,4}$", "", stem)
    stem = re.sub(r"[_\-.]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" -._")
    if not stem or stem.lower() in {"chapter", "cap", "capitulo", "manga"}:
        return "obra-nao-classificada"
    return stem


def _chapter_number(filename: str) -> int | None:
    matches = list(re.finditer(r"\d+", Path(filename).stem))
    if not matches:
        return None
    # O último número é normalmente o número do capítulo.
    return int(matches[-1].group())


def _work_dir(work: str) -> Path:
    return _memory_root() / _safe_name(work)


def _paths(work: str):
    root = _work_dir(work)
    return root / "pages.md", root / "chapters.md", root / "work.md"


def _append(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n\n")


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _pdf_page_images(pdf_path: str, start: int, end: int, zoom: float = 1.35):
    images = []
    doc = pymupdf.open(pdf_path)
    try:
        end = min(end, len(doc))
        for index in range(start, end):
            page = doc.load_page(index)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            images.append((index + 1, base64.b64encode(pix.tobytes("jpeg")).decode("ascii")))
    finally:
        doc.close()
    return images


def _call_openrouter(api_key, model, system_prompt, content, max_tokens=1800):
    if not api_key:
        raise ValueError("Chave da OpenRouter não configurada.")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/brunodratcu/dok",
        "X-Title": "DOK",
    }
    r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(data.get("error", {}).get("message", r.text))
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()


def _call_anthropic(api_key, model, system_prompt, content, max_tokens=1800):
    if not api_key:
        raise ValueError("Chave da Anthropic não configurada.")
    headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    payload = {"model": model, "max_tokens": max_tokens, "system": system_prompt, "messages": [{"role": "user", "content": content}]}
    r = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=180)
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(data.get("error", {}).get("message", r.text))
    return "\n".join(x.get("text", "") for x in data.get("content", []) if x.get("type") == "text").strip()


def _call_ai(provider, api_key, model, system_prompt, content, max_tokens=1800):
    if provider == "openrouter":
        return _call_openrouter(api_key, model, system_prompt, content, max_tokens)
    return _call_anthropic(api_key, model, system_prompt, content, max_tokens)


def _vision_content(pages):
    blocks = [{"type": "text", "text": "Analise todas as páginas abaixo na ordem. Descreva fatos visíveis, diálogos legíveis, ações, personagens, cenário, continuidade e informações narrativas. NÃO resuma pulando páginas. Se algo não puder ser lido, marque como [ilegível]. Separe claramente cada página."}]
    for page_num, b64 in pages:
        blocks.append({"type": "text", "text": f"\n--- PÁGINA {page_num} ---"})
        blocks.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    return blocks


def _analyze_pages(pdf_path, start, end, provider, api_key, model):
    pages = _pdf_page_images(pdf_path, start, end)
    return _call_ai(
        provider, api_key, model,
        "Você é um leitor de mangá extremamente cuidadoso. Sua prioridade é cobertura completa das páginas e fidelidade ao que está visível.",
        _vision_content(pages),
        max_tokens=2200,
    )


def _chapter_consolidation(page_notes: str, filename: str, chapter_num: int | None, provider, api_key, model):
    prompt = (
        f"Documento: {filename}\nCapítulo: {chapter_num or 'não identificado'}\n\n"
        "Registros detalhados das páginas:\n" + page_notes + "\n\n"
        "Transforme isso em um REGISTRO COMPLETO DO CAPÍTULO. Preserve a ordem dos acontecimentos, "
        "não omita acontecimentos relevantes, identifique personagens e relações somente quando sustentados "
        "pelas páginas, registre revelações, conflitos, mudanças de cenário e falas importantes. "
        "Não invente. Não faça um resumo de duas linhas: este documento será a fonte para a memória futura. "
        "Use Markdown com os títulos: Resumo detalhado, Personagens, Acontecimentos, Revelações, Pendências e Observações."
    )
    return _call_ai(
        provider, api_key, model,
        "Você consolida a leitura de um capítulo de mangá sem perder informação narrativa.",
        prompt,
        max_tokens=2800,
    )


def _update_work_memory(existing: str, chapter_record: str, work: str, chapter_num: int | None, provider, api_key, model):
    prompt = (
        f"MEMÓRIA ATUAL DA OBRA '{work}':\n{existing or '(primeiro capítulo)'}\n\n"
        f"NOVO REGISTRO — CAPÍTULO {chapter_num or '?'}:\n{chapter_record}\n\n"
        "Atualize a memória cumulativa da obra. Não apague fatos anteriores só porque o novo capítulo não os menciona. "
        "Incorpore somente fatos sustentados pelos registros. Preserve nomes, acontecimentos, relações, mistérios, "
        "estado atual dos personagens e continuidade. Não invente e não transforme hipótese em fato. "
        "Escreva em Markdown, de forma compacta mas suficientemente detalhada para responder futuramente a perguntas sobre a obra."
    )
    return _call_ai(
        provider, api_key, model,
        "Você mantém a memória cumulativa e fiel de uma obra de mangá, capítulo após capítulo.",
        prompt,
        max_tokens=3200,
    )


def oracle_register_chapter(file_path: str) -> dict:
    """Registra um único capítulo. O arquivo local é aberto pelo DOK.

    São gerados/atualizados exatamente três Markdown: pages.md, chapters.md e work.md.
    """
    target = Path(os.path.abspath(os.path.expanduser(file_path)))
    if not target.exists() or not target.is_file():
        return {"ok": False, "error": f"Arquivo não encontrado: {file_path}"}
    if target.suffix.lower() != ".pdf":
        return {"ok": False, "error": "O registro de capítulo atualmente espera um PDF."}

    cfg = _load_config()
    provider, api_key, model = _provider_config(cfg)
    work = _infer_work_name(target.name)
    chapter_num = _chapter_number(target.name)
    pages_path, chapters_path, work_path = _paths(work)
    existing_chapters = _read(chapters_path)
    marker = f"## Capítulo {chapter_num}" if chapter_num is not None else f"## {target.name}"
    if marker in existing_chapters:
        return {"ok": True, "skipped": True, "work": work, "chapter": chapter_num, "message": "Este capítulo já está registrado."}

    oracle_cfg = cfg.get("oracle", {}) or {}
    batch_size = max(1, int(oracle_cfg.get("pages_per_batch", 4)))
    zoom = float(oracle_cfg.get("render_zoom", 1.35))
    # Passa o zoom pela função sem manter imagens na memória entre lotes.
    doc = pymupdf.open(str(target))
    total_pages = len(doc)
    doc.close()

    page_notes_parts = []
    for start in range(0, total_pages, batch_size):
        end = min(start + batch_size, total_pages)
        pages = _pdf_page_images(str(target), start, end, zoom=zoom)
        notes = _call_ai(
            provider, api_key, model,
            "Você é um leitor de mangá extremamente cuidadoso. Cubra TODAS as páginas recebidas, na ordem. Não pule páginas. Diferencie texto legível de interpretação visual e marque incertezas.",
            _vision_content(pages),
            max_tokens=2200,
        )
        block = f"### Páginas {start + 1}–{end}\n\n{notes}"
        page_notes_parts.append(block)
        _append(pages_path, f"# Leitura do capítulo {chapter_num or target.name}\n\n**Arquivo:** `{target.name}`\n\n{block}")

    page_notes = "\n\n".join(page_notes_parts)
    chapter_record = _chapter_consolidation(page_notes, target.name, chapter_num, provider, api_key, model)
    _append(chapters_path, f"{marker} — `{target.name}`\n\n{chapter_record}")

    existing_work = _read(work_path)
    updated_work = _update_work_memory(existing_work, chapter_record, work, chapter_num, provider, api_key, model)
    work_path.parent.mkdir(parents=True, exist_ok=True)
    work_path.write_text(f"# Memória da obra: {work}\n\n{updated_work.strip()}\n", encoding="utf-8")

    return {
        "ok": True,
        "work": work,
        "chapter": chapter_num,
        "pages": total_pages,
        "files": [str(p) for p in (pages_path, chapters_path, work_path)],
        "message": f"Capítulo registrado: {work} — capítulo {chapter_num or '?'} ({total_pages} páginas).",
    }


def oracle_ingest(folder_path: str) -> dict:
    """Mantém compatibilidade: registra todos os PDFs encontrados recursivamente."""
    root = Path(os.path.abspath(os.path.expanduser(folder_path)))
    if not root.is_dir():
        return {"ok": False, "error": f"Pasta não encontrada: {folder_path}"}
    results = []
    for pdf in sorted(root.rglob("*.pdf")):
        results.append(oracle_register_chapter(str(pdf)))
    return {"ok": all(r.get("ok") for r in results), "chapters": results}


def oracle_query(work: str = None):
    root = _memory_root()
    if work:
        path = _work_dir(work) / "work.md"
        return {"ok": path.exists(), "work": work, "memory": _read(path)}
    works = []
    if root.exists():
        for p in sorted(root.iterdir()):
            if p.is_dir() and (p / "work.md").exists():
                works.append(p.name)
    return {"ok": True, "works": works}


def oracle_status():
    root = _memory_root()
    result = {}
    if not root.exists():
        return result
    for work_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        chapters = _read(work_dir / "chapters.md")
        result[work_dir.name] = {
            "has_pages": (work_dir / "pages.md").exists(),
            "has_chapters": bool(chapters),
            "has_work_memory": (work_dir / "work.md").exists(),
        }
    return result
