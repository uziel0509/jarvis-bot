#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# jarvis-update — Comando para actualizar Jarvis desde GitHub
# Instalación: bash deploy/install.sh
# Uso diario:  jarvis-update
# ═══════════════════════════════════════════════════════════════

set -e

JARVIS_DIR="/root/jarvis"
SERVICE_NAME="jarvis"
LOG_FILE="/var/log/jarvis_update.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "═══════════════════════════════════════"
echo "  🤖 JARVIS UPDATE — $TIMESTAMP"
echo "═══════════════════════════════════════"

# ── 1. Ir al directorio
cd "$JARVIS_DIR"

# ── 2. Ver qué commit hay actualmente
COMMIT_ANTES=$(git rev-parse --short HEAD 2>/dev/null || echo "sin-git")
echo "📌 Versión actual: $COMMIT_ANTES"

# ── 3. Pull desde GitHub
echo "⬇️  Descargando cambios de GitHub..."
git pull origin main

# ── 4. Ver el nuevo commit
COMMIT_DESPUES=$(git rev-parse --short HEAD)
echo "✅ Nueva versión: $COMMIT_DESPUES"

# ── 5. Si no hubo cambios, salir
if [ "$COMMIT_ANTES" = "$COMMIT_DESPUES" ]; then
    echo "ℹ️  Sin cambios nuevos. Jarvis ya está actualizado."
    exit 0
fi

# ── 6. Instalar nuevas dependencias si requirements.txt cambió
if git diff "$COMMIT_ANTES" "$COMMIT_DESPUES" --name-only | grep -q "requirements.txt"; then
    echo "📦 Instalando nuevas dependencias..."
    source "$JARVIS_DIR/venv/bin/activate"
    pip install -r requirements.txt -q
    echo "✅ Dependencias actualizadas"
fi

# ── 7. Reiniciar el servicio
echo "🔄 Reiniciando Jarvis..."
systemctl restart "$SERVICE_NAME"
sleep 3

# ── 8. Verificar que arrancó bien
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Jarvis corriendo correctamente"
    echo ""
    echo "📋 Cambios aplicados:"
    git log "$COMMIT_ANTES".."$COMMIT_DESPUES" --oneline
else
    echo "❌ ERROR: Jarvis no arrancó después del update"
    echo "📋 Últimas líneas del log:"
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager
    exit 1
fi

# ── 9. Guardar log
echo "[$TIMESTAMP] Update: $COMMIT_ANTES → $COMMIT_DESPUES" >> "$LOG_FILE"

echo ""
echo "═══════════════════════════════════════"
echo "  ✅ Update completado exitosamente"
echo "═══════════════════════════════════════"
