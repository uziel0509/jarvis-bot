#!/bin/bash
# ═══════════════════════════════════════════════
# JARVIS 3.0 — Script de deploy en VPS
# Uso: bash deploy/actualizar.sh
# ═══════════════════════════════════════════════

set -e

JARVIS_DIR="/root/jarvis"
SERVICE="jarvis.service"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  JARVIS 3.0 — Deploy"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Ir al directorio del bot
cd $JARVIS_DIR

# 2. Backup del bot actual
echo "[1/5] Haciendo backup..."
cp bot.py archive/bot_backup_$(date +%Y%m%d_%H%M%S).py 2>/dev/null || true

# 3. Pull desde GitHub
echo "[2/5] Descargando cambios de GitHub..."
git pull origin main

# 4. Instalar/actualizar dependencias
echo "[3/5] Actualizando dependencias..."
pip install -r requirements.txt --quiet --break-system-packages

# 5. Reiniciar servicio
echo "[4/5] Reiniciando servicio..."
systemctl restart $SERVICE

# 6. Verificar que arrancó
sleep 3
STATUS=$(systemctl is-active $SERVICE)
echo "[5/5] Estado del servicio: $STATUS"

if [ "$STATUS" = "active" ]; then
    echo ""
    echo "✅ JARVIS 3.0 desplegado correctamente"
else
    echo ""
    echo "❌ ERROR: El servicio no arrancó"
    echo "Ver logs: journalctl -u jarvis -n 30"
    exit 1
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
