"""Ponto único para futuras aprovações. Por enquanto as ferramentas configuradas são permitidas."""
def is_allowed(tool_name, cfg):
    denied = set(cfg.get("permissions", {}).get("deny", []))
    return tool_name not in denied
