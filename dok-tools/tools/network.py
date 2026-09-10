"""Checagem de rede: ping + resolução DNS. Só leitura, sem scan."""
import platform
import socket
import subprocess


def check_network(host: str) -> dict:
    result = {"host": host, "resolved_ip": None, "reachable": False,
               "avg_latency_ms": None, "error": None}

    try:
        result["resolved_ip"] = socket.gethostbyname(host)
    except socket.gaierror as exc:
        result["error"] = f"Não foi possível resolver o host: {exc}"
        return result

    count_flag = "-n" if platform.system().lower() == "windows" else "-c"
    try:
        proc = subprocess.run(
            ["ping", count_flag, "3", host],
            capture_output=True, text=True, timeout=10,
        )
        output = proc.stdout
        result["reachable"] = proc.returncode == 0

        # Extrai a latência média — formatos variam entre SOs, tenta os dois padrões comuns
        for line in output.splitlines():
            lower = line.lower()
            if "average" in lower or "média" in lower or "avg" in lower:
                for token in line.replace("=", " ").replace("/", " ").split():
                    try:
                        result["avg_latency_ms"] = float(token)
                        break
                    except ValueError:
                        continue
    except subprocess.TimeoutExpired:
        result["error"] = "Ping demorou demais (timeout)."
    except Exception as exc:
        result["error"] = f"Falha ao executar ping: {exc}"

    return result
