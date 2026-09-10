"""
Checagem de dispositivo por endereço MAC — só funciona na rede local
(limitação real do ARP, não do código: ele não alcança fora da LAN).
"""
import re
import subprocess

import requests


def _normalize_mac(mac: str) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", mac).lower()


def _lookup_vendor(mac: str) -> str:
    """Consulta pública de fabricante pelo prefixo do MAC. Best-effort —
    se estiver offline ou a API estiver fora, retorna 'desconhecido'
    em vez de quebrar a ferramenta inteira."""
    try:
        resp = requests.get(f"https://api.macvendors.com/{mac}", timeout=4)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass
    return "desconhecido (offline ou fora do banco de dados)"


def check_device_mac(mac_address: str) -> dict:
    target = _normalize_mac(mac_address)
    result = {
        "mac_address": mac_address, "online_now": False,
        "current_ip": None, "vendor": None, "error": None,
    }

    if len(target) != 12:
        result["error"] = "MAC address em formato inválido."
        return result

    try:
        proc = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=8)
        output = proc.stdout
    except Exception as exc:
        result["error"] = f"Falha ao ler a tabela ARP: {exc}"
        return result

    # Formatos variam entre Windows/Linux/Mac — procura qualquer sequência
    # de 12 hex separada por : ou - em cada linha e compara normalizado.
    for line in output.splitlines():
        found = re.findall(r"(?:[0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}", line)
        for raw_mac in found:
            if _normalize_mac(raw_mac) == target:
                ip_match = re.search(r"(\d{1,3}\.){3}\d{1,3}", line)
                result["online_now"] = True
                result["current_ip"] = ip_match.group(0) if ip_match else None
                break
        if result["online_now"]:
            break

    result["vendor"] = _lookup_vendor(mac_address)
    return result
