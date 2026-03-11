# 🤖 Jarvis 3.0 — Bot de Telegram con IA para estudiantes de ingeniería

Bot de Telegram inteligente con pipeline multi-modelo, asistente financiero, gestión de horario académico y análisis de exámenes por foto.

## 🏗️ Arquitectura

```
CAPA 1  — Limpieza        llama-3.1-8b-instant
CAPA 2  — Orquestador     llama-3.3-70b-versatile
CAPA 3  — Ejecución       gpt-oss-120b / gpt-oss-20b / llama-4-scout (visión) / whisper (voz)
CAPA 4  — Pre-Render      pre_render.py → ReportLab (PDF limpio, sin LaTeX crudo)
MÓDULO 5 — Finanzas       finanzas.py
MÓDULO 6 — Horario        horario.py (onboarding por foto, análisis de exámenes)
```

## 📁 Estructura

```
jarvis/
├── bot.py                  # Bot principal
├── modulos/
│   ├── finanzas.py         # Módulo financiero personal
│   ├── horario.py          # Horario, recordatorios y análisis de exámenes
│   └── pre_render.py       # Limpieza de output antes del PDF
├── deploy/
│   ├── install.sh          # Instalación inicial en VPS
│   └── jarvis-update.sh    # Actualización desde GitHub
├── perfiles/               # Datos por estudiante (gitignored)
├── historial/              # Historial de conversaciones (gitignored)
├── archivos/               # PDFs y archivos generados (gitignored)
├── requirements.txt
└── .env.example
```

## 🚀 Instalación en VPS

```bash
# 1. Clonar el repo
git clone https://github.com/uziel0509/jarvis-bot.git /root/jarvis
cd /root/jarvis

# 2. Instalar todo
bash deploy/install.sh

# 3. Configurar tokens
nano .env

# 4. Arrancar
systemctl start jarvis
```

## 🔄 Actualizar desde GitHub

```bash
jarvis-update
```

## ⚙️ Variables de entorno (.env)

```env
TELEGRAM_TOKEN=...
GROQ_API_KEY=...
PERFILES_DIR=/root/jarvis/perfiles
HISTORIAL_DIR=/root/jarvis/historial
ARCHIVOS_DIR=/root/jarvis/archivos
```

## 📦 Módulos nuevos (v3.1)

### Módulo 5 — Finanzas (`modulos/finanzas.py`)
- Registro de gastos e ingresos
- Límite mensual con alertas
- Pagos recurrentes
- Resumen mensual con proyección

### Módulo 6 — Horario (`modulos/horario.py`)
- Onboarding por foto: manda foto del horario → se extrae automáticamente
- Recordatorios antes de clases y exámenes
- Post-examen: manda foto del examen → Jarvis analiza errores y genera PDF de retroalimentación

### Capa 4 — Pre-Render (`modulos/pre_render.py`)
- Convierte LaTeX a imágenes PNG antes del PDF
- Elimina bloques de código markdown
- ReportLab solo recibe elementos limpios y tipados
