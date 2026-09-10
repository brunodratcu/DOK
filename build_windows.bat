@echo off
REM build_windows.bat — gera dok.exe. Rode este script DENTRO da pasta
REM do projeto, no seu notebook Windows (não funciona rodado no Pi).

echo === Instalando dependencias ===
pip install -r requirements.txt

echo === Empacotando com PyInstaller ===
pyinstaller --onefile --windowed --name dok ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    dok_app.py

echo.
echo === Pronto ===
echo O executavel esta em dist\dok.exe
echo.
echo IMPORTANTE: copie a pasta "config" pra dentro de dist\ antes de
echo rodar o dok.exe pela primeira vez (senao ele nao acha onde salvar
echo sua chave da Anthropic/OpenRouter):
echo.
echo   xcopy /E /I config dist\config
echo.
pause
