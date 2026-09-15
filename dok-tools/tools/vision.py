"""
vision.py — descreve uma imagem (foto, screenshot, etc.) autorizada
na máquina local, via IA de visão. Reaproveita a mesma proteção de
caminho do filesystem.py e o mesmo providers.py do Oráculo — nenhuma
lógica HTTP própria aqui.
"""
import base64
import os

import yaml

from tools.filesystem import _resolve_allowed, _display_path
from providers import create_provider

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "config.yaml")

_SUPPORTED_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB — evita mandar foto gigante de celular sem necessidade


def _load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def describe_image(path: str, question: str = None) -> dict:
    """
    Descreve o conteúdo visual de uma imagem autorizada. `question`
    opcional foca a análise (ex: "tem gente nesta foto?") — sem isso,
    faz uma descrição geral.
    """
    target = _resolve_allowed(path)
    if not target.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    if not target.is_file():
        raise IsADirectoryError(f"Não é um arquivo: {path}")

    ext = target.suffix.lower()
    media_type = _SUPPORTED_EXT.get(ext)
    if not media_type:
        raise ValueError(f"Formato de imagem não suportado: {ext} (suportados: {', '.join(_SUPPORTED_EXT)})")

    size = target.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise ValueError(f"Imagem grande demais ({size} bytes, limite {MAX_IMAGE_BYTES}).")

    data = target.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")

    cfg = _load_config()
    provider, model = create_provider(cfg)
    if not provider.api_key:
        raise ValueError(f"Chave da {provider.name} não configurada em dok-tools/config/config.yaml")

    prompt = question or "Descreva em detalhe o que aparece nesta imagem — não invente nada que não esteja visível."
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_b64", "media_type": media_type, "data": b64},
    ]
    description = provider.chat(
        model=model,
        system_prompt="Você descreve imagens com precisão, sem inventar nada que não esteja visível.",
        content=content, max_tokens=800,
    )

    return {"path": _display_path(target), "description": description}
