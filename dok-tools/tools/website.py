"""Checagem de site: status HTTP, tempo de resposta, validade do SSL."""
import socket
import ssl
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests


def check_website(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    result = {
        "url": url, "status_code": None, "response_time_ms": None,
        "ssl_valid": None, "ssl_days_left": None, "error": None,
    }

    try:
        resp = requests.get(url, timeout=10, allow_redirects=True)
        result["status_code"] = resp.status_code
        result["response_time_ms"] = round(resp.elapsed.total_seconds() * 1000)
    except requests.exceptions.RequestException as exc:
        result["error"] = f"Falha ao acessar o site: {exc}"
        return result

    if url.startswith("https://"):
        try:
            hostname = urlparse(url).hostname
            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=8) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
            expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
            expires = expires.replace(tzinfo=timezone.utc)
            days_left = (expires - datetime.now(timezone.utc)).days
            result["ssl_valid"] = days_left > 0
            result["ssl_days_left"] = days_left
        except Exception as exc:
            result["ssl_valid"] = False
            result["error"] = (result["error"] or "") + f" | SSL: {exc}"

    return result
