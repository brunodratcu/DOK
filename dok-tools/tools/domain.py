"""Consulta WHOIS pública de um domínio — só dados de registro, sem credenciais."""
import whois


def _stringify(value):
    if isinstance(value, list):
        value = value[0] if value else None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if value is not None else None


def whois_domain(domain: str) -> dict:
    result = {
        "domain": domain, "registrar": None, "created": None,
        "expires": None, "name_servers": None, "error": None,
    }
    try:
        data = whois.whois(domain)
        result["registrar"] = _stringify(data.registrar)
        result["created"] = _stringify(data.creation_date)
        result["expires"] = _stringify(data.expiration_date)
        ns = data.name_servers
        if ns:
            result["name_servers"] = [str(n).lower() for n in (ns if isinstance(ns, list) else [ns])]
    except Exception as exc:
        result["error"] = f"Falha na consulta WHOIS: {exc}"

    return result
