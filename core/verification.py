"""
core/verification.py — Verification Engine mínimo e leve.

Roda automaticamente depois de write_file/edit_file (chamado pelo
agent_loop.py), antes do agente seguir adiante. Três camadas, na
ordem — para na primeira que falhar, não faz sentido checar sintaxe
de um arquivo que nem existe:

    integridade  -> o arquivo existe e é legível?
    conteúdo     -> o texto esperado está de fato lá?
    sintaxe      -> pra tipos conhecidos (.py, .json, .yaml), é válido?

"test" (rodar os testes do projeto) fica fora de propósito por
enquanto — isso depende de execução de comando, que é uma capacidade
categoricamente mais sensível e ainda não tem política de segurança
definida (allowlist, timeout, etc.). Quando essa conversa acontecer,
dá pra estender esse engine com uma camada `test` a mais, sem mudar
a interface de quem já chama `verify_file`.
"""
import ast
import json
import os

try:
    import yaml
except ImportError:
    yaml = None


def check_integrity(path):
    if not path or not os.path.exists(path):
        return False, "Arquivo não existe após a operação."
    if not os.path.isfile(path):
        return False, "Caminho não é um arquivo."
    try:
        with open(path, "rb") as f:
            f.read(1)
    except Exception as exc:
        return False, f"Arquivo existe mas não pôde ser lido: {exc}"
    return True, "Arquivo existe e é legível."


def check_content(path, expected_text=None):
    if expected_text is None:
        return True, "Nenhum conteúdo específico pra verificar."
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as exc:
        return False, f"Falha ao ler o arquivo pra checar conteúdo: {exc}"
    if expected_text in content:
        return True, "Conteúdo esperado encontrado no arquivo."
    return False, "Conteúdo esperado NÃO foi encontrado no arquivo — a alteração pode não ter sido aplicada como esperado."


def _check_python(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()
    try:
        ast.parse(source)
        return True, "Sintaxe Python válida."
    except SyntaxError as exc:
        return False, f"Erro de sintaxe Python: {exc}"


def _check_json(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        try:
            json.load(f)
            return True, "JSON válido."
        except json.JSONDecodeError as exc:
            return False, f"JSON inválido: {exc}"


def _check_yaml(path):
    if yaml is None:
        return True, "PyYAML não disponível neste ambiente — checagem pulada."
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        try:
            yaml.safe_load(f)
            return True, "YAML válido."
        except Exception as exc:
            return False, f"YAML inválido: {exc}"


_SYNTAX_CHECKERS = {
    ".py": _check_python,
    ".json": _check_json,
    ".yaml": _check_yaml,
    ".yml": _check_yaml,
}


def check_syntax(path):
    ext = os.path.splitext(path)[1].lower()
    checker = _SYNTAX_CHECKERS.get(ext)
    if checker is None:
        return True, f"Sem checagem de sintaxe definida pra '{ext or '(sem extensão)'}' — pulado."
    try:
        return checker(path)
    except Exception as exc:
        return False, f"Erro ao rodar checagem de sintaxe: {exc}"


def verify_file(path, expected_text=None):
    """
    Roda as 3 camadas em ordem. Retorna um dict estruturado — vira
    parte da observação que volta pro modelo, então o texto de cada
    `message` importa (é isso que o modelo lê pra decidir corrigir).
    """
    checks = []

    ok, msg = check_integrity(path)
    checks.append({"check": "integrity", "passed": ok, "message": msg})
    if not ok:
        return {"passed": False, "checks": checks}

    ok, msg = check_content(path, expected_text)
    checks.append({"check": "content", "passed": ok, "message": msg})
    if not ok:
        return {"passed": False, "checks": checks}

    ok, msg = check_syntax(path)
    checks.append({"check": "syntax", "passed": ok, "message": msg})

    return {"passed": all(c["passed"] for c in checks), "checks": checks}
