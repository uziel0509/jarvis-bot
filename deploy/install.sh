#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# install.sh — Instalación inicial de Jarvis en el VPS
# Ejecutar UNA SOLA VEZ después de clonar el repo
# Uso: bash deploy/install.sh
# ═══════════════════════════════════════════════════════════════

set -e

JARVIS_DIR="/root/jarvis"
SERVICE_NAME="jarvis"

echo "🚀 Instalando Jarvis 3.0..."

# ── 1. Instalar dependencias del sistema
echo "📦 Actualizando sistema..."
apt-get update -qq
apt-get install -y python3-pip python3-venv git ffmpeg -qq

# ── 2. Crear entorno virtual si no existe
if [ ! -d "$JARVIS_DIR/venv" ]; then
    echo "🐍 Creando entorno virtual..."
    python3 -m venv "$JARVIS_DIR/venv"
fi

# ── 3. Instalar dependencias Python
echo "📦 Instalando dependencias Python..."
source "$JARVIS_DIR/venv/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$JARVIS_DIR/requirements.txt"

# ── 4. Crear carpetas de datos
echo "📁 Creando estructura de carpetas..."
mkdir -p "$JARVIS_DIR"/{historial,perfiles,archivos,modulos}
chmod 755 "$JARVIS_DIR"/{historial,perfiles,archivos}

# ── 5. Configurar .env si no existe
if [ ! -f "$JARVIS_DIR/.env" ]; then
    echo "⚙️  Creando .env desde ejemplo..."
    cp "$JARVIS_DIR/.env.example" "$JARVIS_DIR/.env"
    echo ""
    echo "⚠️  IMPORTANTE: Edita el .env con tus tokens:"
    echo "   nano $JARVIS_DIR/.env"
fi

# ── 6. Crear servicio systemd
echo "⚙️  Configurando servicio systemd..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Jarvis 3.0 - Bot Telegram IA
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$JARVIS_DIR
ExecStart=$JARVIS_DIR/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
echo "✅ Servicio systemd configurado"

# ── 7. Instalar comando jarvis-update global
echo "🔧 Instalando comando jarvis-update..."
cp "$JARVIS_DIR/deploy/jarvis-update.sh" /usr/local/bin/jarvis-update
chmod +x /usr/local/bin/jarvis-update
echo "✅ Comando 'jarvis-update' disponible globalmente"

# ── 8. Configurar Git para pulls automáticos
cd "$JARVIS_DIR"
git config pull.rebase false

echo ""
echo "═══════════════════════════════════════"
echo "✅ Instalación completada"
echo ""
echo "Próximos pasos:"
echo "  1. nano $JARVIS_DIR/.env   (agrega tus tokens)"
echo "  2. systemctl start jarvis  (arrancar el bot)"
echo "  3. jarvis-update           (actualizar desde GitHub)"
echo "═══════════════════════════════════════"
