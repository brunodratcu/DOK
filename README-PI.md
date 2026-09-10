# DOK — Guia completo de instalação (do zero)

Este guia cobre: gravar o sistema, ligar a tela touch, corrigir os dois
bugs conhecidos desse setup (Xorg não achando a tela SPI, e boot preso
em modo texto), calibrar o touch, e instalar/rodar o app DOK. Siga na
ordem — cada etapa depende da anterior.

---

## Parte 1 — Sistema operacional

### 1.1 Gravar o cartão

1. Baixe o **Raspberry Pi Imager** e abra
2. Escolha o SO: **Raspberry Pi OS (64-bit)** — a versão completa
   (com desktop), não a Lite
3. Antes de gravar, clique na engrenagem (configurações avançadas) e
   preencha:
   - Hostname (ex: `dok-pi`)
   - Usuário e senha
   - Wi-Fi (rede e senha)
   - **SSH habilitado**
4. Grave, coloque o cartão no Pi, **ainda sem conectar a tela touch**,
   e ligue

### 1.2 Primeiro acesso

```
ssh usuario@dok-pi.local
```

Se o hostname não resolver, ache o IP pelo roteador e use
`ssh usuario@<ip>`.

### 1.3 Forçar boot em modo gráfico (Desktop Autologin)

```
sudo raspi-config nonint do_boot_behaviour B4
```

Confirme pelo comando que realmente importa (ignore o
`get_boot_cli` — ele tem um bug conhecido nessa versão do sistema e
não reflete o estado real):

```
systemctl get-default
```

Deve responder `graphical.target`. Se responder `multi-user.target`,
rode o `do_boot_behaviour B4` de novo.

### 1.4 Atualizar o sistema

```
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

---

## Parte 2 — Tela touch (3.5" resistiva, XPT2046)

### 2.1 Instalação física

Com o Pi **desligado**, encaixe a tela diretamente sobre os 40 pinos
do GPIO — pressão firme e uniforme nas duas bordas, sem folga.

### 2.2 Ativar o overlay da tela

```
sudo nano /boot/firmware/config.txt
```

Adicione no final:

```
dtoverlay=piscreen,drm,speed=18000000,rotate=0
```

(`rotate` pode precisar virar `90`, `180` ou `270` — só dá pra saber
testando depois que a tela acender pela primeira vez)

```
sudo reboot
```

### 2.3 Corrigir o Xorg não achando a tela (bug conhecido)

Esse é o erro mais chato do setup: o Xorg tenta usar a saída HDMI
(que não existe se nada estiver plugado nela) e ignora a tela SPI
por causa de um link quebrado no driver. Sintoma: **a tela fica presa
em modo texto mesmo com boot gráfico configurado certo**.

Confirme o diagnóstico (opcional, só se quiser ver o erro):
```
cat /var/log/Xorg.0.log | tail -60
```
Se aparecer `no screens found` e `No such file or directory` citando
`/dev/dri/by-path/...`, é esse bug mesmo.

**Correção:**

```
sudo nano /etc/X11/xorg.conf.d/20-spi-display.conf
```

```
Section "Device"
    Identifier "SPI-Panel"
    Driver "modesetting"
    Option "kmsdev" "/dev/dri/card2"
EndSection

Section "Screen"
    Identifier "Screen0"
    Device "SPI-Panel"
EndSection

Section "ServerLayout"
    Identifier "DefaultLayout"
    Screen 0 "Screen0"
EndSection
```

> **Nota:** `/dev/dri/card2` foi o número correto no nosso caso
> específico. Se depois de aplicar a tela continuar preta/sem sinal,
> rode `ls /dev/dri/` e `cat /var/log/Xorg.0.log` de novo pra
> confirmar qual card corresponde à tela SPI (procure a linha que
> cita `fe204000.spi` no log) — pode variar dependendo da revisão do
> sistema.

```
sudo systemctl restart lightdm
```

A tela deve acender com o desktop. Se a imagem estiver de lado ou
invertida, volte no `config.txt` (passo 2.2) e troque o `rotate`,
testando `0`, `90`, `180`, `270` até acertar a orientação física.

### 2.4 Impedir a tela de apagar sozinha

Necessário antes de calibrar (senão a calibração trava sem aviso):

```
DISPLAY=:0 xset s off
DISPLAY=:0 xset -dpms
DISPLAY=:0 xset s noblank
```

Pra isso ficar permanente entre reboots, adicione essas 3 linhas ao
autostart (veremos isso de novo na Parte 4, junto do kiosk).

**Se a tela apagar mesmo assim:** não é config, é energia. Rode
`vcgencmd get_throttled` — qualquer coisa diferente de `throttled=0x0`
indica fonte insuficiente. Use uma fonte oficial 5V/3A pro Pi 4B.

---

## Parte 3 — Calibrar o touch

### 3.1 Instalar a ferramenta

```
sudo apt install -y xinput-calibrator evtest
```

### 3.2 Rodar o calibrador (com a tela já sem apagar — passo 2.4 feito)

```
DISPLAY=:0 xinput_calibrator | tee ~/calib_output.txt
```

Toque as 4 miras que aparecerem na tela, com uma caneta/stylus (é
resistiva — o dedo tem menos precisão).

### 3.3 Ler o resultado

```
cat ~/calib_output.txt
```

Vai aparecer algo assim:

```
Section "InputClass"
    Identifier      "calibration"
    MatchProduct    "ADS7846 Touchscreen"
    Option  "Calibration"   "X1 X2 Y1 Y2"
    Option  "SwapAxes"      "0 ou 1"
EndSection
```

### 3.4 Converter pro formato do driver (libinput)

O bloco acima é formato `evdev` — nosso sistema usa `libinput`, que
precisa de uma matriz de 9 números em vez desses 4 valores. Pegue os
4 números (`X1 X2 Y1 Y2`) e o `SwapAxes`, e monte a matriz:

- Sem swap (`SwapAxes 0`): `escala_x 0 desloc_x  0 escala_y desloc_y  0 0 1`
- Com swap (`SwapAxes 1`): a matriz troca linhas — peça ajuda nesse
  cálculo específico se cair nesse caso, informando os 4 números e o
  swap.

Fórmula (min/max do dispositivo geralmente 0/4095, confirme com
`evtest` se tiver dúvida):

```
escala_x = 4095 / (X2 - X1)
desloc_x = -X1/4095 * escala_x
escala_y = 4095 / (Y2 - Y1)
desloc_y = -Y1/4095 * escala_y
```

### 3.5 Testar ao vivo antes de gravar

```
DISPLAY=:0 xinput list
```

Ache o ID do "ADS7846 Touchscreen" (era `6` no nosso caso, mas
confirme) e teste:

```
DISPLAY=:0 xinput set-prop <ID> "libinput Calibration Matrix" escala_x 0 desloc_x 0 escala_y desloc_y 0 0 1
```

Toque os 4 cantos e o centro. Ajuste e repita até acertar — não
precisa reiniciar nada entre tentativas.

### 3.6 Gravar definitivo

Quando a matriz estiver boa:

```
sudo nano /etc/X11/xorg.conf.d/40-touch-calibration.conf
```

```
Section "InputClass"
    Identifier "calibration"
    MatchProduct "ADS7846 Touchscreen"
    Driver "libinput"
    Option "CalibrationMatrix" "escala_x 0 desloc_x 0 escala_y desloc_y 0 0 1"
EndSection
```

```
sudo systemctl restart lightdm
```

Teste de novo após o restart pra confirmar que persistiu.

---

## Parte 4 — Instalar e rodar o DOK

### 4.1 Trazer o código pro Pi

Se você tem o repositório no GitHub:
```
git clone https://github.com/brunodratcu/dok.git
cd dok
```
Ou via scp, do seu computador:
```
scp -r dok usuario@dok-pi.local:/home/usuario/
```

### 4.2 Instalar dependências

```
cd ~/dok
sudo apt install -y python3-venv python3-pip
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4.3 Configurar chaves

```
chmod +x dok launch_dok.sh dok_cli.py
./dok key anthropic set          # cole a chave sk-ant-...
./dok key home_assistant set     # cole o Long-Lived Access Token (se for usar a tela Casa)
nano config/config.yaml          # ajuste location (clima) e home_assistant.entities
```

### 4.4 Testar manualmente

```
python app.py
```

Acesse `http://<ip-do-pi>:5000` de outro dispositivo pra conferir
antes de fixar. `Ctrl+C` pra parar o teste.

### 4.5 Deixar rodando sempre (systemd)

```
sudo nano /etc/systemd/system/dok.service
```

```ini
[Unit]
Description=DOK App
After=network-online.target
Wants=network-online.target

[Service]
User=usuario
WorkingDirectory=/home/usuario/dok
ExecStart=/home/usuario/dok/venv/bin/python /home/usuario/dok/app.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl enable dok.service
sudo systemctl start dok.service
sudo systemctl status dok.service
```

### 4.6 Kiosk automático no boot (Chromium tela cheia + tela sempre acesa)

```
mkdir -p ~/.config/autostart
nano ~/.config/autostart/dok-kiosk.desktop
```

```ini
[Desktop Entry]
Type=Application
Name=DOK Kiosk
Exec=sh -c "xset s off; xset -dpms; xset s noblank; chromium-browser --kiosk --incognito --disable-translate --noerrdialogs http://localhost:5000"
X-GNOME-Autostart-enabled=true
```

(isso já embute o passo 2.4 — tela sem apagar — pra sobreviver a
reboots)

```
sudo reboot
```

### 4.7 Ícone na área de trabalho (atalho manual, opcional)

```
nano ~/dok/dok.desktop      # ajuste os caminhos /home/pi/dok pro seu usuário real
chmod +x ~/dok/launch_dok.sh ~/dok/dok.desktop
mkdir -p ~/Desktop ~/.local/share/applications
cp ~/dok/dok.desktop ~/Desktop/
cp ~/dok/dok.desktop ~/.local/share/applications/
gio set ~/Desktop/dok.desktop metadata::trusted true
```

---

## Apêndice — Diagnóstico rápido se algo travar

| Sintoma | Comando de diagnóstico |
|---|---|
| Tela presa em modo texto | `systemctl get-default` (deve ser `graphical.target`) |
| Tela preta / sem sinal | `cat /var/log/Xorg.0.log \| tail -60` |
| Touch impreciso/tremido | `vcgencmd get_throttled` (deve ser `0x0`) |
| Pi sumiu da rede | Testar cabo Ethernet direto; conferir lista de dispositivos no roteador |
| Serviço do DOK não sobe | `sudo journalctl -u dok.service -f` |
| lightdm travado ao reiniciar | `sudo systemctl kill lightdm && sudo systemctl start lightdm` |

**Regra geral:** depois de qualquer mudança de config gráfica, teste
com `sudo systemctl restart lightdm` antes de `sudo reboot` — é mais
rápido pra iterar, e se travar, `kill` resolve sem precisar desligar
o Pi na força.