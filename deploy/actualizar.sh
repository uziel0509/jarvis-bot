#!/bin/bash
# JARVIS 3.0 — Script de actualización desde GitHub
set -e
echo "=== Actualizando JARVIS 3.0 ==="
cd /root/jarvis
git pull origin main
pip install -r requirements.txt --break-system-packages -q
systemctl restart jarvis
echo "=== JARVIS actualizado y reiniciado ==="
systemctl status jarvis --no-pager | head -5
