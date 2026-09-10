"""
paths.py — resolve caminhos de forma que funcione tanto rodando
`python app.py` direto quanto empacotado como executável (PyInstaller).

Duas categorias de caminho:
- resource_path: arquivos somente-leitura empacotados dentro do exe
  (templates, static). Quando empacotado, ficam num diretório temporário
  extraído pelo PyInstaller (sys._MEIPASS).
- data_path: arquivos que precisam ser lidos E escritos em runtime
  (config.yaml, chats.json). Esses SEMPRE ficam ao lado do executável
  real, nunca dentro do bundle — senão qualquer alteração se perderia
  a cada reinício.
"""
import os
import sys


def _is_frozen():
    return getattr(sys, "frozen", False)


def resource_path(*parts):
    if _is_frozen():
        base = sys._MEIPASS  # pasta temporária onde o PyInstaller extrai os dados
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def data_path(*parts):
    if _is_frozen():
        base = os.path.dirname(sys.executable)  # pasta onde o .exe/binário está
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path
