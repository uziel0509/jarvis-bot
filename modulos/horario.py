"""
MÓDULO 6 — Horario Académico, Recordatorios y Análisis de Exámenes por Foto
Jarvis 3.0

Flujos:
  - Onboarding: Jarvis pide foto del horario → visión extrae → confirma → guarda
  - Recordatorios: antes de clases y exámenes (cron o polling)
  - Post-examen: Jarvis solicita foto del examen → visión extrae errores → 120b analiza → PDF retroalimentación
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

PERFILES_DIR = Path(os.getenv("PERFILES_DIR", "/root/jarvis/perfiles"))
ARCHIVOS_DIR = Path(os.getenv("ARCHIVOS_DIR", "/root/jarvis/archivos"))

DIAS_ES = {
    "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles",
    "thursday": "jueves", "friday": "viernes", "saturday": "sábado", "sunday": "domingo"
}


# ── Paths ───────────────────────────────────────────────────────────────────

def _path_horario(user_id: int) -> Path:
    return PERFILES_DIR / str(user_id) / "horario.json"

def _path_examenes(user_id: int) -> Path:
    return PERFILES_DIR / str(user_id) / "examenes.json"


# ── Carga / Guardado ────────────────────────────────────────────────────────

def _cargar_horario(user_id: int) -> dict:
    p = _path_horario(user_id)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {"clases": [], "examenes": [], "entregas": [], "ciclo": ""}

def _guardar_horario(user_id: int, data: dict):
    p = _path_horario(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _cargar_examenes(user_id: int) -> dict:
    p = _path_examenes(user_id)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {"historial": []}

def _guardar_examenes(user_id: int, data: dict):
    p = _path_examenes(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Onboarding de horario ───────────────────────────────────────────────────

def necesita_horario(user_id: int) -> bool:
    return len(_cargar_horario(user_id)["clases"]) == 0

def mensaje_pedir_foto_horario() -> str:
    return (
        "📅 *Para organizarte mejor, necesito tu horario de clases.*\n\n"
        "Mándame una foto de tu horario. Puede ser:\n"
        "  📸 Foto de tu cuaderno o agenda\n"
        "  🖥️ Captura del sistema de tu universidad\n"
        "  📋 Foto de cualquier lugar donde lo tengas\n\n"
        "Jarvis lo leerá y activará tus recordatorios automáticamente. 🎯"
    )

def guardar_horario_extraido(user_id: int, clases: list) -> str:
    data = _cargar_horario(user_id)
    data["clases"] = clases
    _guardar_horario(user_id, data)

    # Construir resumen por día
    dias: dict = {}
    for c in clases:
        dia = c.get("dia", "?")
        if dia not in dias:
            dias[dia] = []
        dias[dia].append(f"{c.get('hora_inicio','?')}-{c.get('hora_fin','?')}: {c.get('materia','?')}")

    orden = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
    resumen = ""
    for d in orden:
        if d in dias:
            resumen += f"\n*{d.capitalize()}:*\n" + "\n".join(f"  • {h}" for h in dias[d])

    return (
        f"✅ *Horario detectado:*{resumen}\n\n"
        "¿Está correcto? Responde *'sí'* para confirmar o dime qué corregir."
    )


# ── Registro de eventos ─────────────────────────────────────────────────────

def registrar_examen(user_id: int, materia: str, fecha: str, hora: str = "") -> str:
    data = _cargar_horario(user_id)
    data["examenes"].append({
        "materia": materia,
        "fecha": fecha,
        "hora": hora,
        "notificado_1dia": False,
        "analizado": False
    })
    _guardar_horario(user_id, data)
    return f"✅ Examen registrado: *{materia}* — {fecha} {hora}"

def registrar_entrega(user_id: int, descripcion: str, fecha: str, hora: str = "") -> str:
    data = _cargar_horario(user_id)
    data["entregas"].append({
        "descripcion": descripcion,
        "fecha": fecha,
        "hora": hora,
        "notificado": False
    })
    _guardar_horario(user_id, data)
    return f"✅ Entrega registrada: *{descripcion}* — {fecha} {hora}"


# ── Resumen diario ──────────────────────────────────────────────────────────

def resumen_hoy(user_id: int) -> str:
    data = _cargar_horario(user_id)
    hoy_en = datetime.now().strftime("%A").lower()
    hoy_es = DIAS_ES.get(hoy_en, hoy_en)
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    fecha_manana = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    clases_hoy   = [c for c in data["clases"]   if c.get("dia","").lower() == hoy_es]
    examenes_hoy = [e for e in data["examenes"] if e.get("fecha","") == fecha_hoy]
    entregas_hoy = [e for e in data["entregas"] if e.get("fecha","") == fecha_hoy]
    exam_manana  = [e for e in data["examenes"] if e.get("fecha","") == fecha_manana]

    if not any([clases_hoy, examenes_hoy, entregas_hoy, exam_manana]):
        return "📅 Hoy no tienes clases ni eventos registrados."

    txt = f"🌅 *Resumen de hoy — {datetime.now().strftime('%d/%m/%Y')}*\n"

    if clases_hoy:
        txt += "\n*📚 Clases:*\n"
        for c in sorted(clases_hoy, key=lambda x: x.get("hora_inicio","00:00")):
            txt += f"  • {c.get('hora_inicio','?')}-{c.get('hora_fin','?')}: {c.get('materia','?')}\n"

    if examenes_hoy:
        txt += "\n*🧪 Examen HOY:*\n"
        for e in examenes_hoy:
            txt += f"  ⚠️ {e['materia']} a las {e.get('hora','?')}\n"

    if entregas_hoy:
        txt += "\n*📝 Entregas hoy:*\n"
        for e in entregas_hoy:
            txt += f"  • {e['descripcion']} a las {e.get('hora','?')}\n"

    if exam_manana:
        txt += "\n*⏰ Examen MAÑANA — repasa hoy:*\n"
        for e in exam_manana:
            txt += f"  ⚠️ {e['materia']} a las {e.get('hora','?')}\n"

    return txt


# ── Análisis post-examen ────────────────────────────────────────────────────

def get_examenes_sin_analizar(user_id: int) -> list:
    """Devuelve exámenes que ya pasaron y no han sido analizados."""
    data = _cargar_horario(user_id)
    hoy = datetime.now().strftime("%Y-%m-%d")
    return [
        e for e in data["examenes"]
        if e.get("fecha","") <= hoy and not e.get("analizado", False)
    ]

def mensaje_pedir_foto_examen(materia: str) -> str:
    return (
        f"📝 *¿Cómo te fue en el examen de {materia}?*\n\n"
        "Si quieres saber en qué fallaste y qué mejorar, "
        "mándame una foto de tu examen con tus respuestas. 📸\n\n"
        "_Identifico errores conceptuales, errores de cálculo y te doy un plan de mejora._"
    )

def guardar_resultado_examen(user_id: int, materia: str, errores: list,
                              patron: str, pdf_path: str = "") -> str:
    data_ex = _cargar_examenes(user_id)
    data_ex["historial"].append({
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "materia": materia,
        "errores": errores,
        "patron_debilidad": patron,
        "pdf": pdf_path
    })
    _guardar_examenes(user_id, data_ex)

    # Marcar como analizado en horario
    data_h = _cargar_horario(user_id)
    for e in data_h["examenes"]:
        if e.get("materia","").lower() == materia.lower():
            e["analizado"] = True
    _guardar_horario(user_id, data_h)
    return f"✅ Análisis del examen de *{materia}* guardado."


# ── Prompts para el modelo de visión ───────────────────────────────────────

PROMPT_EXTRAER_HORARIO = """Analiza esta imagen de un horario universitario.
Extrae todos los cursos visibles. Responde SOLO con este JSON exacto, sin texto adicional:
{
  "clases": [
    {
      "materia": "nombre del curso",
      "dia": "lunes|martes|miércoles|jueves|viernes|sábado",
      "hora_inicio": "HH:MM",
      "hora_fin": "HH:MM",
      "aula": "aula si se ve, sino string vacío"
    }
  ],
  "confianza": "alta|media|baja"
}
Si la imagen no es clara, pon confianza: baja y extrae lo que puedas."""

PROMPT_ANALIZAR_EXAMEN = """Analiza esta imagen de un examen universitario de ingeniería.
Extrae las preguntas, respuestas del alumno y correcciones del profesor si las hay.
Responde SOLO con este JSON exacto, sin texto adicional:
{
  "materia": "nombre si se identifica, sino string vacío",
  "preguntas": [
    {
      "numero": 1,
      "enunciado": "texto del problema",
      "respuesta_alumno": "lo que escribió el alumno",
      "correccion_profesor": "nota del profesor en rojo u otra tinta, o string vacío",
      "estado": "correcto|incorrecto|parcial"
    }
  ],
  "errores_conceptuales": ["concepto 1 mal entendido", "concepto 2"],
  "errores_calculo": ["error matemático 1"],
  "temas_reforzar": ["tema 1", "tema 2"],
  "nota_estimada": "si se ve la nota, sino string vacío"
}"""
