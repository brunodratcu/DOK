"""
manga_scrape.py — baixa as páginas de um capítulo direto do site como
JPEGs, SEM passar por PDF. Salva em:

    <destino>/<Obra>/<capitulo_NNN>/page_001.jpg, page_002.jpg, ...

Essa pasta é o que o Oráculo (oracle.py) vai ler depois com OCR local.

IMPORTANTE: a extração dos <img src="..."> do capítulo depende da
estrutura HTML do site — o seletor CSS abaixo é um placeholder.
Ajuste `IMAGE_SELECTOR` pro site que você usa (inspecione o HTML da
página do capítulo, F12 no navegador, e veja qual container/tag
guarda as imagens da leitura).

Uso:
    python manga_scrape.py <url_do_capitulo> <Nome da Obra> <numero_capitulo> <pasta_destino>
"""
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; personal-archive-bot/1.0)"}
REQUEST_DELAY = 0.6  # segundos entre downloads — não martela o site
TIMEOUT = 15

# Ajuste isto pro site que você usa. Exemplos comuns:
#   "#readerarea img"
#   ".reading-content img"
#   "div.page-break img"
IMAGE_SELECTOR = ".reading-content img"


def find_image_urls(chapter_url: str) -> list[str]:
    resp = requests.get(chapter_url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    urls = []
    for img in soup.select(IMAGE_SELECTOR):
        src = img.get("data-src") or img.get("data-lazy-src") or img.get("src")
        if not src:
            continue
        urls.append(urljoin(chapter_url, src.strip()))
    return urls


def download_chapter(chapter_url: str, work: str, chapter_num: int, dest_root: str) -> Path:
    urls = find_image_urls(chapter_url)
    if not urls:
        raise RuntimeError(
            f"Nenhuma imagem encontrada com o seletor '{IMAGE_SELECTOR}'. "
            "Ajuste IMAGE_SELECTOR pro HTML real do site."
        )

    safe_work = "".join(c if c.isalnum() or c in " -_" else "_" for c in work).strip()
    chapter_dir = Path(dest_root) / safe_work / f"capitulo_{chapter_num:03d}"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for i, url in enumerate(urls, start=1):
        out_path = chapter_dir / f"page_{i:03d}.jpg"
        if out_path.exists():
            saved.append(out_path)
            continue  # já baixado — não repete trabalho
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        out_path.write_bytes(r.content)
        saved.append(out_path)
        time.sleep(REQUEST_DELAY)

    print(f"{work} — capítulo {chapter_num}: {len(saved)} página(s) em {chapter_dir}")
    return chapter_dir


def main():
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)
    chapter_url, work, chapter_num, dest_root = sys.argv[1:5]
    download_chapter(chapter_url, work, int(chapter_num), dest_root)


if __name__ == "__main__":
    main()
