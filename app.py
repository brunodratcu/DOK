"""
DOK — Diagnostic of Kings
App Flask: tela de boas-vindas (clima/hora) + DOK (chats de texto).
Home Assistant foi removido deste projeto.
"""
import os
import yaml
import requests
from flask import Flask, render_template, jsonify, request

import claude_client
import openrouter_client
import chat_store
import projects_store
import paths
from agents import agent_loop
import usage_store

CONFIG_PATH = paths.data_path("config", "config.yaml")

app = Flask(
    __name__,
    template_folder=paths.resource_path("templates"),
    static_folder=paths.resource_path("static"),
)

WEATHER_CODES = {
    0: "céu limpo", 1: "predomínio de sol", 2: "parcialmente nublado",
    3: "nublado", 45: "névoa", 48: "névoa com geada",
    51: "garoa fraca", 53: "garoa", 55: "garoa forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte",
    71: "neve fraca", 73: "neve", 75: "neve forte",
    80: "pancadas de chuva", 81: "pancadas de chuva", 82: "pancadas fortes",
    95: "tempestade", 96: "tempestade com granizo", 99: "tempestade forte",
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# --- Telas ---

@app.route("/")
def index():
    cfg = load_config()
    return render_template("index.html", dok_name=cfg["personality"]["name"])


@app.route("/dok")
def dok_screen():
    cfg = load_config()
    return render_template("dok.html", dok_name=cfg["personality"]["name"])


# --- Clima ---

@app.route("/api/weather")
def api_weather():
    cfg = load_config()
    loc = cfg["location"]
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "current_weather": "true",
                "timezone": loc.get("timezone", "auto"),
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()["current_weather"]
        code = data.get("weathercode", 0)
        return jsonify({
            "ok": True,
            "location": loc["name"],
            "temperature": round(data["temperature"]),
            "description": WEATHER_CODES.get(code, "condição desconhecida"),
            "windspeed": data.get("windspeed"),
        })
    except Exception:
        return jsonify({
            "ok": False,
            "location": loc["name"],
            "message": "Não foi possível buscar o clima agora."
        })


# --- Créditos ---

@app.route("/generated/<path:filename>")
def serve_generated(filename):
    from flask import send_from_directory
    return send_from_directory(paths.data_path("generated"), filename)


def _usage_response():
    cfg = load_config()
    qr_path = paths.data_path("generated", "credits_qr.png")
    qr_available = os.path.exists(qr_path)
    monitor = cfg.get("monitor", {})

    try:
        summary = usage_store.get_summary(
            monthly_budget_usd=monitor.get("monthly_budget_usd", 0),
            warning_percent=monitor.get("warning_percent", 80),
        )
        return jsonify({
            "ok": True,
            "configured": bool(cfg.get("anthropic", {}).get("api_key")),
            "message": "Monitoramento local do DOK. Não representa o saldo da conta Anthropic.",
            "usage": summary,
            "qr_available": qr_available,
            "qr_url": "/generated/credits_qr.png" if qr_available else None,
            "billing_url": "https://console.anthropic.com/settings/billing",
        })
    except Exception as exc:
        return jsonify({
            "ok": False,
            "configured": bool(cfg.get("anthropic", {}).get("api_key")),
            "message": f"Não foi possível ler o monitoramento local: {exc}",
            "qr_available": qr_available,
            "qr_url": "/generated/credits_qr.png" if qr_available else None,
            "billing_url": "https://console.anthropic.com/settings/billing",
        }), 500


@app.route("/api/usage")
def api_usage():
    return _usage_response()


@app.route("/api/credits")
def api_credits():
    # Alias mantido para não quebrar a interface/integrações antigas.
    return _usage_response()


# --- Chats (DOK) ---

@app.route("/api/chats")
def api_list_chats():
    return jsonify(chat_store.list_chats())


@app.route("/api/chats/<chat_id>")
def api_get_chat(chat_id):
    chat = chat_store.get_chat(chat_id)
    if not chat:
        return jsonify({"ok": False, "message": "Conversa não encontrada."}), 404
    return jsonify({"ok": True, "chat": chat})


@app.route("/api/chats", methods=["POST"])
def api_create_chat():
    chat_id = chat_store.create_chat()
    return jsonify({"ok": True, "id": chat_id})


@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def api_delete_chat(chat_id):
    ok = chat_store.delete_chat(chat_id)
    return jsonify({"ok": ok})


@app.route("/api/chats/<chat_id>/message", methods=["POST"])
def api_send_message(chat_id):
    body = request.get_json(force=True, silent=True) or {}
    user_text = (body.get("message") or "").strip()

    if not user_text:
        return jsonify({"ok": False, "message": "Mensagem vazia."}), 400

    chat = chat_store.get_chat(chat_id)
    if not chat:
        return jsonify({"ok": False, "message": "Conversa não encontrada."}), 404

    cfg = load_config()
    provider = cfg.get("provider", "anthropic")

    # monta o histórico recente (limitado, pra controlar custo)
    provider_cfg = cfg[provider]
    history_limit = provider_cfg.get("history_limit", 12)
    recent = chat["messages"][-history_limit:]
    api_messages = [{"role": m["role"], "content": m["content"]} for m in recent]
    api_messages.append({"role": "user", "content": user_text})

    chat_store.add_message(chat_id, "user", user_text)

    usage = {}
    if provider == "openrouter":
        ok, reply = openrouter_client.send_message(
            api_key=provider_cfg["api_key"],
            model=provider_cfg["model"],
            system_prompt=cfg["personality"]["system_prompt"],
            messages=api_messages,
            max_tokens=provider_cfg.get("max_tokens", 400),
        )
    else:
        ok, reply, usage = claude_client.send_message(
            api_key=provider_cfg["api_key"],
            model=provider_cfg["model"],
            system_prompt=cfg["personality"]["system_prompt"],
            messages=api_messages,
            max_tokens=provider_cfg.get("max_tokens", 400),
        )

    usage_info = {}
    if ok:
        chat_store.add_message(chat_id, "assistant", reply)
        if provider == "anthropic" and usage:
            usage_info = usage_store.record_usage(
                chat_id=chat_id,
                provider=provider,
                model=provider_cfg["model"],
                usage=usage,
            )

    return jsonify({"ok": ok, "reply": reply, "provider": provider, "usage": usage_info})


@app.route("/api/openrouter/free-models")
def api_openrouter_free_models():
    """Lista os modelos gratuitos disponíveis na OpenRouter agora mesmo."""
    ok, result = openrouter_client.list_free_models()
    if not ok:
        return jsonify({"ok": False, "message": result})
    return jsonify({"ok": True, "models": result})


@app.route("/api/projects/history")
def api_projects_history():
    return jsonify(projects_store.get_history())


@app.route("/api/projects/clear", methods=["POST"])
def api_projects_clear():
    projects_store.clear_history()
    return jsonify({"ok": True})


@app.route("/api/projects/message", methods=["POST"])
def api_projects_message():
    """
    Aba Projetos: usa o loop de agente com ferramentas (MCP), sempre
    via Anthropic — modelos gratuitos da OpenRouter são inconsistentes
    demais com tool use pra confiar numa tarefa de diagnóstico real.
    """
    body = request.get_json(force=True, silent=True) or {}
    user_text = (body.get("message") or "").strip()
    if not user_text:
        return jsonify({"ok": False, "message": "Mensagem vazia."}), 400

    cfg = load_config()
    ant = cfg["anthropic"]
    tools_cfg = cfg.get("tools_server", {})
    tools_server_path = tools_cfg.get("path", "../dok-tools/server.py")
    tools_python_cmd = tools_cfg.get("python")

    # histórico curto — tarefas de diagnóstico não precisam de contexto longo
    history_raw = projects_store.get_history()[-6:]
    history = [{"role": m["role"], "content": m["content"]} for m in history_raw]

    ok, reply, trace = agent_loop.run(
        api_key=ant["api_key"],
        model=ant["model"],
        system_prompt=cfg["personality"]["system_prompt"],
        history=history,
        user_text=user_text,
        tools_server_path=tools_server_path,
        tools_python_cmd=tools_python_cmd,
        max_tokens=ant.get("max_tokens", 800),
    )

    if ok:
        projects_store.add_exchange(user_text, reply)

    return jsonify({"ok": ok, "reply": reply, "trace": trace})


if __name__ == "__main__":
    cfg = load_config()
    app.run(
        host=cfg["server"]["host"],
        port=cfg["server"]["port"],
        debug=cfg["server"]["debug"],
    )
