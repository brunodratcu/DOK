#!/bin/bash
# build_linux.sh — gera o binário do DOK pro Linux/Raspberry Pi.
# Rode este script DENTRO da pasta do projeto, no próprio Pi
# (não dá pra gerar o binário ARM do Pi rodando isso num notebook x86).
# Sem venv: instala tudo no Python global do sistema.
set -e

echo "=== Dependências de sistema (webview precisa do WebKitGTK) ==="
sudo apt update
sudo apt install -y python3-gi gir1.2-webkit2-4.1

echo "=== Dependências Python (global, sem venv) ==="
pip install --break-system-packages -r requirements.txt

echo "=== Empacotando com PyInstaller ==="
python3 -m PyInstaller --onefile --name dok \
    --add-data "templates:templates" \
    --add-data "static:static" \
    dok_app.py

echo ""
echo "=== Pronto ==="
echo "O binário está em dist/dok"
echo ""
echo "IMPORTANTE: copie a pasta config pra dentro de dist/ antes de"
echo "rodar pela primeira vez:"
echo ""
echo "  cp -r config dist/"
echo ""
echo "Pra deixar um ícone na área de trabalho, ajuste o dok.desktop"
echo "pra apontar Exec= pro caminho de dist/dok (veja o README)."
