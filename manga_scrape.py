"""
manga_batch_ingest.py — lê TODOS os links de capítulos de um único
arquivo .txt (pode misturar obras e sites à vontade, em qualquer
ordem) e baixa cada capítulo já organizado por obra, sem precisar
rodar um comando por obra.

Como a classificação funciona
------------------------------
Cada link é comparado contra os SITE_PROFILES abaixo. Um perfil
descreve, pra um site específico: como reconhecer a obra e o número
do capítulo a partir da própria URL, e qual seletor CSS pega as
imagens de leitura naquele site.

Você tem 3 sites → cadastra 3 perfis. Depois disso, todos os links
dos 3 sites podem ficar juntos no mesmo links.txt, em qualquer ordem
— o script separa sozinho por obra.

Se um link não bater com nenhum SITE_PROFILE cadastrado, entra o
FALLBACK genérico: tenta adivinhar obra e capítulo pela estrutura
comum da URL, e tenta uma lista de seletores CSS usuais em sites de
mangá. Funciona bem na maioria dos casos, mas sem garantia — por
isso o ideal é preencher os 3 perfis reais assim que você tiver um
link de exemplo de cada site.

Formato do links.txt
---------------------
Um link por linha. Linhas em branco e linhas começando com # são
ignoradas (pra você poder anotar/organizar o arquivo):

    # One Piece
    https://site1.com/one-piece/capitulo-1150/
    https://site1.com/one-piece/capitulo-1151/

    # Jujutsu Kaisen
    https://site2.com/manga/jujutsu-kaisen-chapter-271/

Uso:
    python manga_batch_ingest.py links.txt ./manga_incoming
"""
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-archive-bot/1.0)"}
REQUEST_DELAY = 0.6
TIMEOUT = 15

# =====================================================================
# CADASTRE AQUI OS 3 SITES QUE VOCÊ USA. Me manda um link de exemplo
# de cada um que eu preencho isso certinho — o que está aqui embaixo
# é só exemplo de FORMATO, não vai bater com nada de verdade ainda.
# =====================================================================
SITE_PROFILES = [
    # {
    #     "name": "site1",
    #     "domain": "site1.com",
    #     # grupo nomeado (?P<work>...) captura o nome da obra na URL
    #     "work_pattern": re.compile(r"site1\.com/(?P<work>[^/]+)/capitulo-\d+"),
    #     # grupo nomeado (?P<num>...) captura o número do capítulo
    #     "chapter_pattern": re.compile(r"capitulo-(?P<num>\d+)"),
    #     "image_selector": ".reading-content img",
    # },
]

# Seletores comuns em sites de mangá — usados pelo fallback quando um
# link não bate com nenhum SITE_PROFILE. Tenta cada um até achar
# imagens.
FALLBACK_SELECTORS = [
    ".reading-content img",
    "#readerarea img",
    ".page-break img",
    "img.wp-manga-chapter-img",
    ".chapter-content img",
    "article img",
]

_CHAPTER_RE = re.compile(
    r"(?:chapter|capitulo|cap[ií]tulo|cap|ch)[\s_\-]*0*(?P<num>\d+)", re.IGNORECASE
)
_TRAILING_NUM_RE = re.compile(r"(\d+)/?$")


def classify_url(url: str) -> dict:
    """Devolve {work, chapter, image_selector, matched} pra um link."""
    for profile in SITE_PROFILES:
        if profile["domain"] not in url:
            continue
        work_m = profile["work_pattern"].search(url)
        chapter_m = profile["chapter_pattern"].search(url)
        if work_m and chapter_m:
            return {
                "work": work_m.group("work").replace("-", " ").strip(),
                "chapter": int(chapter_m.group("num")),
                "image_selector": profile["image_selector"],
                "matched": profile["name"],
            }

    # --- fallback genérico: nenhum perfil cadastrado bateu ---
    return _classify_fallback(url)


def _classify_fallback(url: str) -> dict:
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]

    chapter = None
    m = _CHAPTER_RE.search(url)
    if m:
        chapter = int(m.group("num"))
    else:
        m = _TRAILING_NUM_RE.search(url)
        if m:
            chapter = int(m.group(1))

    # nome da obra: primeiro segmento do caminho que não é um número
    # puro nem uma palavra genérica de navegação
    skip_words = {"manga", "read", "chapter", "capitulo", "series", "comic", "en", "pt"}
    work = None
    for part in path_parts:
        clean = re.sub(r"[-_]?(chapter|capitulo|cap|ch)[-_]?\d*$", "", part, flags=re.IGNORECASE)
        if clean and not clean.isdigit() and clean.lower() not in skip_words:
            work = clean.replace("-", " ").replace("_", " ").strip()
            break

    return {
        "work": work or parsed.netloc,
        "chapter": chapter,
        "image_selector": None,  # sinaliza pra tentar FALLBACK_SELECTORS
        "matched": "fallback",
    }


def find_image_urls(chapter_url: str, selector: str = None) -> list[str]:
    resp = requests.get(chapter_url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    selectors_to_try = [selector] if selector else FALLBACK_SELECTORS
    for sel in selectors_to_try:
        imgs = soup.select(sel)
        if imgs:
            urls = []
            for img in imgs:
                src = img.get("data-src") or img.get("data-lazy-src") or img.get("src")
                if src:
                    urls.append(urljoin(chapter_url, src.strip()))
            if urls:
                return urls
    return []


def download_chapter(url: str, info: dict, dest_root: str) -> bool:
    work, chapter = info["work"], info["chapter"]
    if chapter is None:
        print(f"  ✗ Não consegui identificar o número do capítulo: {url}")
        return False

    urls = find_image_urls(url, info["image_selector"])
    if not urls:
        print(f"  ✗ Nenhuma imagem encontrada em: {url}")
        print(f"    (perfil usado: {info['matched']} — talvez precise de um seletor CSS específico)")
        return False

    safe_work = "".join(c if c.isalnum() or c in " -_" else "_" for c in work).strip()
    chapter_dir = Path(dest_root) / safe_work / f"capitulo_{chapter:03d}"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    for i, img_url in enumerate(urls, start=1):
        out_path = chapter_dir / f"page_{i:03d}.jpg"
        if out_path.exists():
            saved += 1
            continue
        try:
            r = requests.get(img_url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            out_path.write_bytes(r.content)
            saved += 1
        except requests.RequestException as exc:
            print(f"    aviso: falhou baixar página {i} ({exc})")
        time.sleep(REQUEST_DELAY)

    print(f"  ✓ {work} — capítulo {chapter}: {saved}/{len(urls)} página(s) em {chapter_dir}")
    return saved > 0


def read_links(txt_path: str) -> list[str]:
    links = []
    for line in Path(txt_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        links.append(line)
    return links


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    txt_path, dest_root = sys.argv[1], sys.argv[2]
    links = read_links(txt_path)
    print(f"{len(links)} link(s) encontrados em {txt_path}\n")

    # classifica tudo primeiro, pra mostrar o resumo antes de baixar
    classified = [(url, classify_url(url)) for url in links]

    by_work = {}
    for url, info in classified:
        by_work.setdefault(info["work"], []).append((url, info["chapter"]))

    print("=== Classificação ===")
    for work, chapters in by_work.items():
        nums = sorted(c for _, c in chapters if c is not None)
        print(f"  {work}: {len(chapters)} capítulo(s) — {nums}")
    print()

    print("=== Baixando ===")
    ok, fail = 0, 0
    for url, info in classified:
        if download_chapter(url, info, dest_root):
            ok += 1
        else:
            fail += 1

    print(f"\nConcluído: {ok} capítulo(s) baixado(s), {fail} falha(s).")
    print(f"Pasta pronta pro Oráculo processar: {dest_root}")


if __name__ == "__main__":
    main()