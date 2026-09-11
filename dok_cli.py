#!/usr/bin/env python3
"""
dok_cli.py — Firmware CLI do DOK.

Roda via SSH pra configurar/desconfigurar chaves e gerar o QR de compra
de créditos. Não lida com dados de pagamento em nenhum momento — isso é
sempre feito no navegador, no Console da Anthropic.

Uso:
    ./dok key anthropic set
    ./dok key anthropic unset
    ./dok key anthropic status
    ./dok key weather set
    ./dok key weather unset
    ./dok key weather status
    ./dok credits qr
    ./dok status
"""
import argparse
import getpass
import os
import sys

import yaml

import paths

CONFIG_PATH = paths.data_path("config", "config.yaml")
QR_OUTPUT_PATH = paths.data_path("generated", "credits_qr.png")
BILLING_URL = "https://openrouter.ai/settings/credits"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def mask_key(key: str) -> str:
    if not key:
        return "(não configurada)"
    if len(key) <= 10:
        return "•" * len(key)
    return f"{key[:7]}{'•' * 8}{key[-4:]}"


def cmd_key_set(provider: str):
    cfg = load_config()
    prompts = {
        "anthropic": "Cole a chave da Anthropic (sk-ant-...): ",
        "weather": "Cole a chave do provedor de clima: ",
        "openrouter": "Cole a chave da OpenRouter (sk-or-...): ",
    }
    key = getpass.getpass(prompts[provider])

    if not key.strip():
        print("Nada digitado — operação cancelada.")
        return

    if provider == "anthropic":
        if not key.startswith("sk-ant-"):
            confirm = input(
                "Isso não parece uma chave da Anthropic (não começa com "
                "'sk-ant-'). Salvar mesmo assim? [s/N] "
            )
            if confirm.strip().lower() != "s":
                print("Operação cancelada.")
                return
        cfg["anthropic"]["api_key"] = key.strip()
    elif provider == "openrouter":
        cfg["openrouter"]["api_key"] = key.strip()
    else:
        cfg["weather"]["api_key"] = key.strip()

    save_config(cfg)
    print(f"Chave salva: {mask_key(key.strip())}")


def cmd_key_unset(provider: str):
    cfg = load_config()
    if provider == "anthropic":
        cfg["anthropic"]["api_key"] = ""
    elif provider == "openrouter":
        cfg["openrouter"]["api_key"] = ""
    else:
        cfg["weather"]["api_key"] = ""
    save_config(cfg)
    print(f"Chave de {provider} removida.")


def cmd_key_status(provider: str):
    cfg = load_config()
    key = cfg[provider]["api_key"] if provider in ("anthropic", "openrouter") else cfg["weather"]["api_key"]
    print(f"{provider}: {mask_key(key)}")


def cmd_provider_set(provider: str):
    cfg = load_config()
    cfg["provider"] = provider
    save_config(cfg)
    print(f"Provedor ativo: {provider}")
    key = cfg[provider]["api_key"]
    if not key:
        print(f"Atenção: a chave do {provider} ainda não está configurada.")
        print(f"Rode: ./dok key {provider} set")


def cmd_provider_status():
    cfg = load_config()
    print(f"Provedor ativo: {cfg.get('provider', 'anthropic')}")


def cmd_models_list():
    print("Consultando modelos gratuitos na OpenRouter agora mesmo...\n")
    from providers.openrouter import list_free_models
    ok, result = list_free_models()
    if not ok:
        print(f"Erro: {result}")
        return
    if not result:
        print("Nenhum modelo gratuito encontrado no momento.")
        return

    print(f"{len(result)} modelos gratuitos disponíveis:\n")
    for m in result:
        ctx = f"{m['context_length']:,}".replace(",", ".") if m["context_length"] else "?"
        print(f"  {m['id']:<45} contexto: {ctx}")

    print("\nPra usar um deles:")
    print('  nano config/config.yaml   # troque openrouter.model pelo ID copiado acima')
    print("  ./dok provider set openrouter")
    print("\nOu, se não quiser escolher, deixe o padrão 'openrouter/free' — ele")
    print("escolhe um modelo grátis disponível automaticamente a cada chamada.")


def cmd_credits_qr():
    try:
        import qrcode
    except ImportError:
        print("Biblioteca 'qrcode' não instalada. Rode: pip install qrcode[pil]")
        sys.exit(1)

    os.makedirs(os.path.dirname(QR_OUTPUT_PATH), exist_ok=True)
    img = qrcode.make(BILLING_URL)
    img.save(QR_OUTPUT_PATH)
    print(f"QR code gerado em: {QR_OUTPUT_PATH}")
    print(f"Aponta pra: {BILLING_URL}")
    print("Esse QR também aparece automaticamente no ícone de créditos do app.")


def cmd_status():
    cfg = load_config()
    print("=== Status do DOK ===")
    print(f"Provedor ativo    : {cfg.get('provider', 'anthropic')}")
    print(f"Anthropic API key : {mask_key(cfg['anthropic']['api_key'])}")
    print(f"Anthropic modelo  : {cfg['anthropic']['model']}")
    print(f"OpenRouter API key: {mask_key(cfg['openrouter']['api_key'])}")
    print(f"OpenRouter modelo : {cfg['openrouter']['model']}")
    print(f"Provedor de clima : {cfg['weather']['provider']}")
    print(f"Chave de clima    : {mask_key(cfg['weather']['api_key'])}")
    print(f"Localização       : {cfg['location']['name']}")


def main():
    parser = argparse.ArgumentParser(prog="dok", description="Firmware CLI do DOK")
    sub = parser.add_subparsers(dest="command", required=True)

    p_key = sub.add_parser("key", help="Gerenciar chaves de API")
    key_sub = p_key.add_subparsers(dest="provider", required=True)
    for provider_name in ("anthropic", "weather", "openrouter"):
        p_provider = key_sub.add_parser(provider_name)
        provider_sub = p_provider.add_subparsers(dest="action", required=True)
        provider_sub.add_parser("set")
        provider_sub.add_parser("unset")
        provider_sub.add_parser("status")

    p_provider_cmd = sub.add_parser("provider", help="Trocar o provedor de IA ativo")
    provider_cmd_sub = p_provider_cmd.add_subparsers(dest="action", required=True)
    p_provider_set = provider_cmd_sub.add_parser("set")
    p_provider_set.add_argument("name", choices=["anthropic", "openrouter"])
    provider_cmd_sub.add_parser("status")

    p_models = sub.add_parser("models", help="Modelos disponíveis")
    models_sub = p_models.add_subparsers(dest="action", required=True)
    models_sub.add_parser("list")

    p_credits = sub.add_parser("credits", help="Créditos e compra")
    credits_sub = p_credits.add_subparsers(dest="action", required=True)
    credits_sub.add_parser("qr")

    sub.add_parser("status", help="Status geral do DOK")

    args = parser.parse_args()

    if args.command == "key":
        if args.action == "set":
            cmd_key_set(args.provider)
        elif args.action == "unset":
            cmd_key_unset(args.provider)
        elif args.action == "status":
            cmd_key_status(args.provider)
    elif args.command == "provider":
        if args.action == "set":
            cmd_provider_set(args.name)
        elif args.action == "status":
            cmd_provider_status()
    elif args.command == "models":
        if args.action == "list":
            cmd_models_list()
    elif args.command == "credits":
        if args.action == "qr":
            cmd_credits_qr()
    elif args.command == "status":
        cmd_status()


if __name__ == "__main__":
    main()
