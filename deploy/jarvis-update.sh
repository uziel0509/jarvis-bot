#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# jarvis-update — Actualiza Jarvis desde GitHub
# Uso: jarvis-update
# ═══════════════════════════════════════════════════════════════

set -e

JARVIS_DIR="/root/jarvis"
SERVICE_NAME="jarvis"
LOG_FILE="/var/log/jarvis_update.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "═══════════════════════════════════════"
echo "  🤖 JARVIS UPDATE — $TIMESTAMP"
echo "═══════════════════════════════════════"

cd "$JARVIS_DIR"

COMMIT_ANTES=$(git rev-parse --short HEAD 2>/dev/null || echo "sin-git")
echo "📌 Versión actual: $COMMIT_ANTES"

echo "⬇️  Descargando cambios de GitHub..."
git pull origin main

COMMIT_DESPUES=$(git rev-parse --short HEAD)
echo "✅ Nueva versión: $COMMIT_DESPUES"

if [ "$COMMIT_ANTES" = "$COMMIT_DESPUES" ]; then
    echo "ℹ️  Sin cambios nuevos. Jarvis ya está actualizado."
    exit 0
fi

# SIEMPRE instalar dependencias (no solo cuando requirements.txt cambia)
echo "📦 Instalando/verificando dependencias..."
pip install -r requirements.txt -q --break-system-packages
echo "✅ Dependencias OK"

echo "🔄 Reiniciando Jarvis..."
systemctl restart "$SERVICE_NAME"
sleep 4

if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Jarvis corriendo correctamente"
    echo ""
    echo "📋 Cambios aplicados:"
    git log "$COMMIT_ANTES".."$COMMIT_DESPUES" --oneline
else
    echo "❌ ERROR: Jarvis no arrancó después del update"
    echo "📋 Últimas líneas del log:"
    journalctl -u "$SERVICE_NAME" -n 30 --no-pager
    exit 1
fi

echo "[$TIMESTAMP] Update: $COMMIT_ANTES → $COMMIT_DESPUES" >> "$LOG_FILE"

echo ""
echo "═══════════════════════════════════════"
echo "  ✅ Update completado exitosamente"
echo "═══════════════════════════════════════"
