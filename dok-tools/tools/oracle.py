"""
oracle.py — o Oráculo: lê pastas de PDF de manga, interpreta via IA de
visão, e mantém UM ÚNICO arquivo de conhecimento consolidado (não um
arquivo por capítulo). Processamento pesado sempre na nuvem (API) —
localmente só converte PDF em imagem, nada de modelo rodando aqui.

Funciona como um mini-agente: para cada capítulo novo, primeiro
interpreta as páginas (visão), depois funde esse resumo no resumo
geral da obra (um segundo passo, mais barato, só texto) — é assim que
"resume a obra inteira" se mantém atualizado sem reprocessar tudo.
"""
import base64
import io
import json
import os
import re
import time

import requests
import yaml
import pymupdf  # PyMuPDF — só conversão PDF->imagem, sem processamento pesado local

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "..", "config", "config.yaml")
KNOWLEDGE_PATH = os.path.join(BASE_DIR, "..", "data", "oracle", "knowledge.json")

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

CHAPTER_NUM_RE = re.compile(r"(\d+)")


# --- Config e armazenamento (arquivo único) ---

def _load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_knowledge():
    if not os.path.exists(KNOWLEDGE_PATH):
        return {}
    with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_knowledge(data):
    os.makedirs(os.path.dirname(KNOWLEDGE_PATH), exist_ok=True)
    with open(KNOWLEDGE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --- Descoberta de arquivos ---

def discover_pdfs(folder_path: str):
    """
    Convenção assumida: pasta_raiz/NOME_DA_OBRA/algo_com_numero.pdf
    (ex: mangas/nng/capitulo_012.pdf, mangas/tbv/cap_07.pdf).
    O nome da obra é a subpasta de primeiro nível; o número do
    capítulo é extraído do nome do arquivo (ou da pasta, se o PDF
    estiver direto dentro da pasta da obra sem subpastas por capítulo).
    """
    found = []
    folder_path = os.path.abspath(folder_path)
    for work_name in sorted(os.listdir(folder_path)):
        work_dir = os.path.join(folder_path, work_name)
        if not os.path.isdir(work_dir):
            continue
        for root, _, files in os.walk(work_dir):
            for fname in sorted(files):
                if not fname.lower().endswith(".pdf"):
                    continue
                match = CHAPTER_NUM_RE.search(fname) or CHAPTER_NUM_RE.search(os.path.basename(root))
                chapter_num = int(match.group(1)) if match else None
                found.append({
                    "work": work_name.lower(),
                    "chapter": chapter_num,
                    "path": os.path.join(root, fname),
                    "filename": fname,
                })
    return found


# --- Conversão PDF -> imagens (leve, local) ---

def _pdf_to_b64_images(pdf_path: str, max_pages: int = 40, zoom: float = 1.5):
    images = []
    doc = pymupdf.open(pdf_path)
    try:
        for page_index in range(min(len(doc), max_pages)):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            img_bytes = pix.tobytes("jpeg")
            images.append(base64.b64encode(img_bytes).decode("ascii"))
    finally:
        doc.close()
    return images


# --- Chamadas à Anthropic ---

def _call_anthropic(api_key, model, system_prompt, content_blocks, max_tokens=1500):
    headers = {
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": content_blocks}],
    }
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    text = "\n".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return text.strip()


def _interpret_chapter(images_b64, work, chapter_num, api_key, model):
    """Uma chamada de visão por capítulo (todas as páginas juntas numa
    mensagem só — mais barato que uma chamada por página)."""
    content = [{"type": "text", "text": (
        f"Estas são as páginas do capítulo {chapter_num} da obra '{work}', em ordem. "
        "Analise SOMENTE o que está desenhado/escrito nas imagens — não invente nada "
        "que não esteja visível. Responda em JSON puro, sem markdown, no formato: "
        '{"summary": "resumo detalhado do que acontece neste capítulo", '
        '"characters": ["nome1", "nome2"], "key_events": ["evento1", "evento2"], '
        '"notable_quotes": ["fala marcante 1"]}'
    )}]
    for img_b64 in images_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64},
        })

    raw = _call_anthropic(
        api_key, model,
        system_prompt="Você extrai fatos de páginas de mangá com precisão, sem inventar nada.",
        content_blocks=content,
        max_tokens=1500,
    )
    try:
        cleaned = raw.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"summary": raw, "characters": [], "key_events": [], "notable_quotes": []}


def _merge_into_overall_summary(existing_summary, chapter_summary, work, chapter_num, api_key, model):
    """Segundo passo, só texto (barato): funde o resumo do capítulo novo
    no resumo geral da obra, mantendo detalhe."""
    prompt = (
        f"Resumo geral atual da obra '{work}':\n{existing_summary or '(ainda não há resumo — este é o primeiro capítulo processado)'}\n\n"
        f"Resumo do capítulo {chapter_num}, recém-processado:\n{chapter_summary}\n\n"
        "Reescreva o resumo geral da obra incorporando esse capítulo novo. "
        "Mantenha o máximo de detalhe relevante (personagens, eventos, arcos), "
        "em prosa corrida, sem inventar nada além do que já estava nos dois textos acima."
    )
    return _call_anthropic(
        api_key, model,
        system_prompt="Você mantém um resumo cumulativo detalhado e fiel de uma obra, capítulo a capítulo.",
        content_blocks=[{"type": "text", "text": prompt}],
        max_tokens=2000,
    )


# --- Orquestração (o "agente") ---

def oracle_ingest(folder_path: str):
    cfg = _load_config()
    api_key = cfg["anthropic"]["api_key"]
    model = cfg["anthropic"]["model"]
    if not api_key:
        return {"ok": False, "error": "Chave da Anthropic não configurada em dok-tools/config/config.yaml"}

    knowledge = _load_knowledge()
    pdfs = discover_pdfs(folder_path)

    report = {"ok": True, "chapters_added": [], "chapters_skipped": [], "errors": []}

    for item in pdfs:
        work = item["work"]
        chapter_num = item["chapter"]
        if chapter_num is None:
            report["errors"].append(f"Não achei número de capítulo em {item['filename']}")
            continue

        knowledge.setdefault(work, {"overall_summary": "", "chapters": {}})
        if str(chapter_num) in knowledge[work]["chapters"]:
            report["chapters_skipped"].append(f"{work} cap {chapter_num} (já processado)")
            continue

        try:
            images = _pdf_to_b64_images(item["path"])
            chapter_data = _interpret_chapter(images, work, chapter_num, api_key, model)
            knowledge[work]["chapters"][str(chapter_num)] = chapter_data
            knowledge[work]["overall_summary"] = _merge_into_overall_summary(
                knowledge[work]["overall_summary"],
                chapter_data.get("summary", ""),
                work, chapter_num, api_key, model,
            )
            _save_knowledge(knowledge)  # salva a cada capítulo — não perde progresso se cair
            report["chapters_added"].append(f"{work} cap {chapter_num}")
        except Exception as exc:
            report["errors"].append(f"{work} cap {chapter_num}: {exc}")

    return report


def oracle_query(work: str = None):
    knowledge = _load_knowledge()
    if work:
        return knowledge.get(work.lower(), {"error": f"Nenhum conhecimento registrado pra '{work}'"})
    return knowledge


def oracle_status():
    knowledge = _load_knowledge()
    return {
        work: {
            "chapters_ingested": len(data.get("chapters", {})),
            "has_overall_summary": bool(data.get("overall_summary")),
        }
        for work, data in knowledge.items()
    }
