# ═══════════════════════════════════════════════════════════════
# AGENTE ACADÉMICO — JARVIS 3.2
# ───────────────────────────────────────────────────────────────
# Arquitectura: Modelo → JSON estructurado → PDF profesional fijo
# Sin matplotlib. Sin parseo de texto. Sin regex frágiles.
# El PDF siempre se ve perfecto sin importar qué modelo responde.
# ═══════════════════════════════════════════════════════════════

import os, re, json, logging
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, HRFlowable, KeepTogether
)

logger = logging.getLogger(__name__)

ARCHIVOS_DIR = "/root/jarvis/archivos"

# ── Registrar fuentes DejaVu Unicode (sub/superíndices perfectos) ──
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONT_DIR = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("DejaVu",      f"{_FONT_DIR}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", f"{_FONT_DIR}/DejaVuSans-Bold.ttf"))
_FONT      = "DejaVu"
_FONT_BOLD = "DejaVu-Bold"
Path(ARCHIVOS_DIR).mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT — exige JSON puro al modelo
# ═══════════════════════════════════════════════════════════════
SYSTEM_JSON = """Eres el motor académico de JARVIS, tutor IA para ingeniería universitaria peruana.

REGLA ABSOLUTA N°1: Responde ÚNICAMENTE con JSON válido.
- Cero texto antes del JSON
- Cero texto después del JSON
- Cero bloques ```json``` ni ```
- Solo el objeto JSON, nada más

ESTRUCTURA OBLIGATORIA DEL JSON:
{
  "titulo": "Tema general del ejercicio",
  "ejercicios": [
    {
      "titulo": "Ejercicio N: descripción corta del problema",
      "datos": [
        "Variable 1: valor con unidades",
        "Variable 2: valor con unidades"
      ],
      "pasos": [
        {
          "num": 1,
          "titulo": "Nombre del paso",
          "calculo": "Desarrollo del cálculo completo\npuede tener múltiples líneas\ncon operaciones y resultados intermedios"
        }
      ],
      "resultado": "Valor final con unidades y opción si el problema tiene alternativas"
    }
  ]
}

REGLA ABSOLUTA N°2 — Caracteres Unicode reales (NUNCA la letra n como reemplazo):
SUBÍNDICES:   ₀ ₁ ₂ ₃ ₄ ₅ ₆ ₇ ₈ ₉ ₙ ₘ ₐ
SUPERÍNDICES: ⁰ ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹ ⁻ ⁺ ⁿ

CORRECTO:   H₂O  CO₂  C₈H₁₈  mol⁻¹  10⁶  Nₐ  m³  mg·m⁻³
INCORRECTO: HnO  COn  CnHnn  moln1  10n6  Nn  mn  mg·mn3

OPERADORES: × · ÷ ± ≤ ≥ ≠ ≈ ∑ √ ∫ ∂ Δ →
FRACCIONES: (numerador / denominador)

REGLA N°3 — Pasos:
- Cada ejercicio tiene sus propios pasos empezando desde num=1
- NUNCA continúes la numeración entre ejercicios
- Cada paso tiene título descriptivo y cálculo detallado

REGLA N°4 — Múltiples ejercicios:
- Si el alumno manda varios ejercicios, el array "ejercicios" tendrá múltiples objetos
- Cada ejercicio es completamente independiente"""


# ═══════════════════════════════════════════════════════════════
# COLORES Y ESTILOS PDF
# ═══════════════════════════════════════════════════════════════
C_PRIMARY   = colors.HexColor("#0f0c29")   # fondo portada top
C_DARK      = colors.HexColor("#1a1a6e")   # fondo portada bottom
C_ACCENT    = colors.HexColor("#4361ee")   # azul eléctrico
C_ACCENT2   = colors.HexColor("#3a0ca3")   # violeta para variedad
C_PASO_BG   = colors.HexColor("#f0f4ff")   # fondo azul muy claro pasos
C_PASO_LINE = colors.HexColor("#4361ee")   # borde izquierdo pasos
C_EJ_BG     = colors.HexColor("#e8f0fe")   # fondo cabecera ejercicio
C_EJ_LINE   = colors.HexColor("#1a56db")   # borde inferior ejercicio
C_RESULT_BG = colors.HexColor("#fef9e7")   # fondo resultado amarillo
C_RESULT_L  = colors.HexColor("#f39c12")   # borde resultado naranja
C_DATO_BG   = colors.HexColor("#f8fafc")   # fondo datos conocidos
C_GRAY      = colors.HexColor("#6b7280")
C_TEXT      = colors.HexColor("#1f2937")
C_TEXT_SOFT = colors.HexColor("#374151")


def _estilos():
    return {
        "portada_title": ParagraphStyle(
            "portada_title",
            fontName=_FONT_BOLD, fontSize=26,
            textColor=colors.white, leading=32, spaceAfter=4
        ),
        "portada_sub": ParagraphStyle(
            "portada_sub",
            fontName=_FONT, fontSize=12,
            textColor=colors.HexColor("#a5b4fc"), leading=18
        ),
        "portada_info": ParagraphStyle(
            "portada_info",
            fontName=_FONT, fontSize=10,
            textColor=colors.HexColor("#818cf8"), leading=15
        ),
        "ej_titulo": ParagraphStyle(
            "ej_titulo",
            fontName=_FONT_BOLD, fontSize=12,
            textColor=C_EJ_LINE, leading=17
        ),
        "seccion": ParagraphStyle(
            "seccion",
            fontName=_FONT_BOLD, fontSize=9,
            textColor=C_GRAY, leading=13,
            spaceAfter=3
        ),
        "dato": ParagraphStyle(
            "dato",
            fontName=_FONT, fontSize=10,
            textColor=C_TEXT_SOFT, leading=15
        ),
        "paso_titulo": ParagraphStyle(
            "paso_titulo",
            fontName=_FONT_BOLD, fontSize=10,
            textColor=C_ACCENT, leading=14
        ),
        "paso_calculo": ParagraphStyle(
            "paso_calculo",
            fontName=_FONT, fontSize=10,
            textColor=C_TEXT, leading=15
        ),
        "resultado_label": ParagraphStyle(
            "resultado_label",
            fontName=_FONT_BOLD, fontSize=9,
            textColor=C_RESULT_L, leading=13
        ),
        "resultado_valor": ParagraphStyle(
            "resultado_valor",
            fontName=_FONT_BOLD, fontSize=12,
            textColor=colors.HexColor("#92400e"), leading=17
        ),
        "pie": ParagraphStyle(
            "pie",
            fontName=_FONT, fontSize=8,
            textColor=C_GRAY
        ),
    }


# ═══════════════════════════════════════════════════════════════
# HELPERS — constructores de bloques visuales
# ═══════════════════════════════════════════════════════════════
def _e(texto):
    """Escapa HTML para ReportLab."""
    return str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _portada(titulo, nombre, carrera, uni, fecha, W, s):
    """Portada con gradiente azul oscuro."""
    filas = [
        [Paragraph("JARVIS 3.2", s["portada_title"])],
        [Paragraph(_e(titulo), s["portada_sub"])],
        [Spacer(1, 0.1*cm)],
        [Paragraph(f"{_e(nombre)}", s["portada_info"])],
        [Paragraph(f"{_e(carrera)}  {'|  ' + _e(uni) if uni else ''}", s["portada_info"])],
        [Paragraph(f"<font color='#6366f1'>{fecha}</font>", s["portada_info"])],
    ]
    t = Table(filas, colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,1),   C_PRIMARY),
        ("BACKGROUND",    (0,2), (-1,-1), C_DARK),
        ("TOPPADDING",    (0,0), (0,0),   22),
        ("BOTTOMPADDING", (0,-1),(-1,-1), 18),
        ("TOPPADDING",    (0,1), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (0,0),   4),
        ("LEFTPADDING",   (0,0), (-1,-1), 24),
        ("RIGHTPADDING",  (0,0), (-1,-1), 16),
    ]))
    return t


def _cabecera_ejercicio(titulo, W, s):
    """Bloque azul celeste para el título del ejercicio."""
    t = Table(
        [[Paragraph(_e(titulo), s["ej_titulo"])]],
        colWidths=[W]
    )
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_EJ_BG),
        ("LINEBELOW",     (0,0), (-1,-1), 3,   C_EJ_LINE),
        ("LINETOP",       (0,0), (-1,-1), 0.5, C_EJ_LINE),
        ("LEFTPADDING",   (0,0), (-1,-1), 16),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
        ("TOPPADDING",    (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 11),
    ]))
    return t


def _bloque_datos(datos, W, s):
    """Bloque gris suave con los datos conocidos del ejercicio."""
    filas = [[Paragraph("DATOS CONOCIDOS", s["seccion"])]]
    for dato in datos:
        filas.append([Paragraph(f"  •  {_e(dato)}", s["dato"])])
    t = Table(filas, colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_DATO_BG),
        ("LINELEFT",      (0,0), (0,-1),  3, C_GRAY),
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (0,0),   8),
        ("BOTTOMPADDING", (0,-1),(-1,-1), 8),
        ("TOPPADDING",    (0,1), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (0,-2),  3),
    ]))
    return t


def _bloque_paso(num, titulo, calculo, W, s):
    """Bloque azul claro para cada paso numerado."""
    # número del paso — círculo visual con tabla anidada
    num_cell = Table(
        [[Paragraph(f"<b>{num}</b>", ParagraphStyle(
            "num", fontName=_FONT_BOLD, fontSize=11,
            textColor=colors.white, leading=14, alignment=1
        ))]],
        colWidths=[0.65*cm], rowHeights=[0.65*cm]
    )
    num_cell.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_ACCENT),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))

    contenido = [Paragraph(_e(titulo), s["paso_titulo"])]
    for linea in calculo.split("\n"):
        if linea.strip():
            contenido.append(Paragraph(_e(linea.strip()), s["paso_calculo"]))

    fila = [[num_cell, contenido]]
    t = Table(fila, colWidths=[0.85*cm, W - 1.25*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_PASO_BG),
        ("LINELEFT",      (0,0), (0,-1),  0, C_PASO_BG),
        ("LINERIGHT",     (1,0), (1,-1),  0, C_PASO_BG),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0), (0,-1),  10),
        ("RIGHTPADDING",  (0,0), (0,-1),  6),
        ("LEFTPADDING",   (1,0), (1,-1),  10),
        ("RIGHTPADDING",  (1,0), (1,-1),  10),
        ("TOPPADDING",    (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 9),
        ("LINEBELOW",     (0,-1),(-1,-1), 0.5, colors.HexColor("#dde3f0")),
    ]))
    return t


def _bloque_resultado(texto, W, s):
    """Bloque amarillo dorado para el resultado final."""
    contenido = [
        Paragraph("RESULTADO FINAL", s["resultado_label"]),
        Paragraph(_e(texto), s["resultado_valor"]),
    ]
    t = Table([[contenido]], colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_RESULT_BG),
        ("LINETOP",       (0,0), (-1,-1), 2.5, C_RESULT_L),
        ("LINEBELOW",     (0,0), (-1,-1), 2.5, C_RESULT_L),
        ("LINELEFT",      (0,0), (0,-1),  4,   C_RESULT_L),
        ("LEFTPADDING",   (0,0), (-1,-1), 16),
        ("RIGHTPADDING",  (0,0), (-1,-1), 14),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    return t


# ═══════════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — JSON → PDF
# ═══════════════════════════════════════════════════════════════
def crear_pdf_desde_json(datos_json, user_id, perfil=None):
    """
    Recibe dict con estructura {"titulo": ..., "ejercicios": [...]}
    Genera PDF profesional y retorna la ruta del archivo.
    """
    perfil  = perfil or {}
    nombre  = perfil.get("nombre", "Alumno")
    carrera = perfil.get("carrera", "Ingeniería")
    uni     = perfil.get("universidad", "")
    fecha   = datetime.now().strftime("%d de %B de %Y")
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    titulo  = datos_json.get("titulo", "Solución de Ejercicios")
    path    = f"{ARCHIVOS_DIR}/solucion_{user_id}_{ts}.pdf"

    s   = _estilos()
    doc = SimpleDocTemplate(
        path, pagesize=A4,
        rightMargin=1.8*cm, leftMargin=1.8*cm,
        topMargin=2.2*cm, bottomMargin=2.5*cm
    )
    W = doc.width

    # ── pie de página ──
    def _pie(canvas, doc_):
        canvas.saveState()
        canvas.setFont(_FONT, 8)
        canvas.setFillColor(C_GRAY)
        canvas.drawCentredString(
            A4[0] / 2, 1.2*cm,
            f"JARVIS 3.2  ·  {_e(titulo)}  ·  Página {doc_.page}"
        )
        canvas.setStrokeColor(colors.HexColor("#e5e7eb"))
        canvas.setLineWidth(0.5)
        canvas.line(1.8*cm, 1.6*cm, A4[0] - 1.8*cm, 1.6*cm)
        canvas.restoreState()

    story = []

    # ── portada ──
    story.append(_portada(titulo, nombre, carrera, uni, fecha, W, s))
    story.append(Spacer(1, 0.8*cm))

    # ── ejercicios ──
    ejercicios = datos_json.get("ejercicios", [])
    for idx, ej in enumerate(ejercicios):
        if idx > 0:
            story.append(Spacer(1, 0.3*cm))
            story.append(HRFlowable(
                width=W, thickness=0.8,
                color=colors.HexColor("#d1d5db"), spaceAfter=0.3*cm
            ))

        bloques = []

        # cabecera
        bloques.append(_cabecera_ejercicio(
            ej.get("titulo", f"Ejercicio {idx + 1}"), W, s
        ))
        bloques.append(Spacer(1, 0.2*cm))

        # datos conocidos
        datos = ej.get("datos", [])
        if datos:
            bloques.append(_bloque_datos(datos, W, s))
            bloques.append(Spacer(1, 0.25*cm))

        # pasos
        pasos = ej.get("pasos", [])
        for paso in pasos:
            bloques.append(_bloque_paso(
                paso.get("num", "?"),
                paso.get("titulo", ""),
                paso.get("calculo", ""),
                W, s
            ))
            bloques.append(Spacer(1, 0.1*cm))

        # resultado
        resultado = ej.get("resultado", "")
        if resultado:
            bloques.append(Spacer(1, 0.15*cm))
            bloques.append(_bloque_resultado(resultado, W, s))

        story.append(KeepTogether(bloques[:4]))  # cabecera + datos juntos
        for b in bloques[4:]:
            story.append(b)

        story.append(Spacer(1, 0.4*cm))

    doc.build(story, onFirstPage=_pie, onLaterPages=_pie)
    logger.info(f"PDF generado: {path}")
    return path


# ═══════════════════════════════════════════════════════════════
# FUNCIÓN PÚBLICA — llama al modelo y genera PDF
# ═══════════════════════════════════════════════════════════════
def resolver_y_generar_pdf(client, texto_ejercicio, user_id, perfil=None):
    """
    1. Llama al modelo con SYSTEM_JSON para obtener JSON estructurado
    2. Parsea el JSON
    3. Genera PDF profesional desde el JSON
    Retorna (ruta_pdf, datos_json)
    """
    perfil = perfil or {}

    msgs = [
        {"role": "system", "content": SYSTEM_JSON},
        {"role": "user",   "content": texto_ejercicio}
    ]

    modelos = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"]
    ultimo_error = None

    for modelo in modelos:
        try:
            resp = client.chat.completions.create(
                model=modelo, messages=msgs, max_tokens=4000,
                temperature=0.2  # baja temperatura = más consistente
            )
            raw = resp.choices[0].message.content.strip()
            # limpiar bloques de código si el modelo los pone igual
            raw = re.sub(r'^```json\s*|^```\s*|```$', '', raw, flags=re.MULTILINE).strip()
            datos = json.loads(raw)
            path  = crear_pdf_desde_json(datos, user_id, perfil)
            logger.info(f"PDF generado con modelo {modelo}")
            return path, datos
        except json.JSONDecodeError as ex:
            logger.warning(f"JSON inválido de {modelo}: {ex}")
            ultimo_error = ex
            continue
        except Exception as ex:
            logger.warning(f"Error con {modelo}: {ex}")
            ultimo_error = ex
            continue

    raise RuntimeError(f"No se pudo generar PDF: {ultimo_error}")


# ═══════════════════════════════════════════════════════════════
# ANÁLISIS DE IMAGEN — ejercicio desde foto
# ═══════════════════════════════════════════════════════════════
def analizar_imagen_y_generar_pdf(client, img_bytes, caption, user_id, perfil=None):
    """
    Recibe imagen con ejercicio, resuelve y genera PDF.
    """
    import base64
    perfil = perfil or {}
    b64    = base64.b64encode(img_bytes).decode()

    msgs = [{
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text",
             "text": f"{SYSTEM_JSON}\n\nResuelve todos los ejercicios que ves en la imagen. {caption or ''}"}
        ]
    }]

    resp = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=msgs, max_tokens=4000, temperature=0.2
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r'^```json\s*|^```\s*|```$', '', raw, flags=re.MULTILINE).strip()
    datos = json.loads(raw)
    path  = crear_pdf_desde_json(datos, user_id, perfil)
    return path, datos


# ═══════════════════════════════════════════════════════════════
# OTRAS FUNCIONES DEL AGENTE
# ═══════════════════════════════════════════════════════════════
def generar_estructura_archivo(client, tipo, solicitud, perfil):
    prompt = (
        f"Genera estructura JSON para un {tipo} sobre: {solicitud}. "
        f"Solo JSON válido, sin texto extra."
    )
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r'^```json\s*|^```\s*|```$', '', raw, flags=re.MULTILINE).strip()
    return json.loads(raw)
