# ─────────────────────────────────────────────────────────────
# AGENTE ACADÉMICO — JARVIS 3.2
# Arquitectura: Modelo → JSON → PDF fijo
# Sin matplotlib. Sin parseo de texto. Sin regex frágiles.
# ─────────────────────────────────────────────────────────────
import os, re, json
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, HRFlowable
)

ARCHIVOS_DIR = "/root/jarvis/archivos"
Path(ARCHIVOS_DIR).mkdir(parents=True, exist_ok=True)

# ── Colores ──
C_PRIMARY  = colors.HexColor("#1a1a2e")
C_DARK     = colors.HexColor("#2d3561")
C_ACCENT   = colors.HexColor("#4361ee")
C_PASO_BG  = colors.HexColor("#eef2ff")
C_EJ_BG    = colors.HexColor("#dbeafe")
C_EJ_LINE  = colors.HexColor("#2563eb")
C_RESULT   = colors.HexColor("#fff3cd")
C_RESULT_B = colors.HexColor("#e67e00")
C_GRAY     = colors.HexColor("#888888")

# ── System prompt — pide JSON estricto ──
SYSTEM_JSON = """Eres el motor académico de JARVIS. Resuelves ejercicios universitarios de ingeniería.

REGLA ABSOLUTA: Responde ÚNICAMENTE con JSON válido. Sin texto antes ni después. Sin bloques ```json```.

ESTRUCTURA OBLIGATORIA:
{
  "ejercicios": [
    {
      "titulo": "Ejercicio N: descripción corta",
      "datos": ["dato 1", "dato 2", "..."],
      "pasos": [
        {"num": 1, "titulo": "título del paso", "calculo": "desarrollo del cálculo"},
        {"num": 2, "titulo": "título del paso", "calculo": "desarrollo del cálculo"}
      ],
      "resultado": "valor con unidades y opción si aplica"
    }
  ]
}

REGLAS DE FORMATO DENTRO DEL JSON:
- Subíndices Unicode: H₂O CO₂ C₈H₁₈ m⁻¹ 10⁶ Nₐ m³ mol⁻¹
- NUNCA uses n como reemplazo: NUNCA escribas HnO moln1 10n6
- Fracciones: (numerador / denominador)
- Potencias: 10⁶ 10⁻³ x² (Unicode real)
- Operadores: × · ÷ ± ≤ ≥ ≈ √ Δ
- Si hay múltiples ejercicios, el array tiene múltiples objetos
- Los pasos de cada ejercicio empiezan desde num=1"""


# ─────────────────────────────────────────────
# HELPERS PDF
# ─────────────────────────────────────────────
def _e(t):
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _estilos():
    return {
        "titulo_doc": ParagraphStyle("td", fontName="Helvetica-Bold",
            fontSize=22, textColor=colors.white, leading=28),
        "sub_doc": ParagraphStyle("sd", fontName="Helvetica",
            fontSize=11, textColor=colors.HexColor("#ccccff"), leading=16),
        "ej_tit": ParagraphStyle("et", fontName="Helvetica-Bold",
            fontSize=13, textColor=C_EJ_LINE, leading=18),
        "cuerpo": ParagraphStyle("cu", fontName="Helvetica",
            fontSize=10, textColor=colors.black, leading=15),
        "paso_tit": ParagraphStyle("pt", fontName="Helvetica-Bold",
            fontSize=10, textColor=C_ACCENT, leading=14),
        "paso_body": ParagraphStyle("pb", fontName="Helvetica",
            fontSize=10, textColor=colors.black, leading=14),
        "resultado": ParagraphStyle("re", fontName="Helvetica-Bold",
            fontSize=11, textColor=C_RESULT_B, leading=16),
        "dato": ParagraphStyle("da", fontName="Helvetica",
            fontSize=10, textColor=colors.HexColor("#333333"), leading=14),
    }

def _bloque_ejercicio(titulo, W, s):
    t = Table([[Paragraph(_e(titulo), s["ej_tit"])]], colWidths=[W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_EJ_BG),
        ("LINEBELOW",     (0,0), (-1,-1), 2.5, C_EJ_LINE),
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    return t

def _bloque_paso(num, titulo, calculo, W, s):
    items = [Paragraph(f"Paso {num}: {_e(titulo)}", s["paso_tit"])]
    for linea in calculo.split("\n"):
        if linea.strip():
            items.append(Paragraph(_e(linea.strip()), s["paso_body"]))
    t = Table([[items]], colWidths=[W - 0.4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_PASO_BG),
        ("LINERIGHT",     (0,0), (0,-1),  3, C_ACCENT),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ]))
    return t

def _bloque_resultado(texto, W, s):
    t = Table(
        [[Paragraph(f"✓  RESULTADO: {_e(texto)}", s["resultado"])]],
        colWidths=[W - 0.4*cm]
    )
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), C_RESULT),
        ("LINETOP",       (0,0), (-1,-1), 2, C_RESULT_B),
        ("LINEBELOW",     (0,0), (-1,-1), 2, C_RESULT_B),
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("TOPPADDING",    (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 9),
    ]))
    return t


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL — recibe JSON del modelo
# ─────────────────────────────────────────────
def crear_pdf_desde_json(datos_json, user_id, titulo="Solución", perfil=None):
    """
    datos_json: dict con estructura {"ejercicios": [...]}
    Genera PDF profesional 100% desde JSON estructurado.
    """
    perfil  = perfil or {}
    nombre  = perfil.get("nombre", "Alumno")
    carrera = perfil.get("carrera", "")
    uni     = perfil.get("universidad", "")
    fecha   = datetime.now().strftime("%d de %B de %Y")
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    path    = f"{ARCHIVOS_DIR}/solucion_{user_id}_{ts}.pdf"

    s   = _estilos()
    doc = SimpleDocTemplate(path, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2.5*cm)
    W = doc.width
    story = []

    # pie de página
    def pie(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(C_GRAY)
        canvas.drawCentredString(
            A4[0]/2, 1.2*cm,
            f"JARVIS 3.2  ·  Página {doc_.page}"
        )
        canvas.restoreState()

    # portada
    info = nombre
    if carrera: info += f"  —  {carrera}"
    if uni:     info += f"  |  {uni}"

    portada = Table([
        [Paragraph("JARVIS 3.2", s["titulo_doc"])],
        [Paragraph(_e(titulo),   s["sub_doc"])],
        [Paragraph(
            f"{_e(info)}<br/><font size='9' color='#aaaacc'>{fecha}</font>",
            s["sub_doc"]
        )],
    ], colWidths=[W])
    portada.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,0),   C_PRIMARY),
        ("BACKGROUND",    (0,1), (-1,-1), C_DARK),
        ("TOPPADDING",    (0,0), (0,0),   18),
        ("BOTTOMPADDING", (0,-1),(-1,-1), 16),
        ("LEFTPADDING",   (0,0), (-1,-1), 20),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
    ]))
    story.append(portada)
    story.append(Spacer(1, 0.7*cm))

    # ejercicios
    ejercicios = datos_json.get("ejercicios", [])
    for idx, ej in enumerate(ejercicios):
        if idx > 0:
            story.append(HRFlowable(width=W, thickness=0.5, color=C_GRAY))
            story.append(Spacer(1, 0.3*cm))

        # cabecera ejercicio
        story.append(_bloque_ejercicio(ej.get("titulo", f"Ejercicio {idx+1}"), W, s))
        story.append(Spacer(1, 0.2*cm))

        # datos conocidos
        datos = ej.get("datos", [])
        if datos:
            story.append(Paragraph("<b>Datos conocidos:</b>", s["cuerpo"]))
            for dato in datos:
                story.append(Paragraph(f"  • {_e(dato)}", s["dato"]))
            story.append(Spacer(1, 0.2*cm))

        # pasos
        for paso in ej.get("pasos", []):
            story.append(_bloque_paso(
                paso.get("num", "?"),
                paso.get("titulo", ""),
                paso.get("calculo", ""),
                W, s
            ))
            story.append(Spacer(1, 0.12*cm))

        # resultado
        resultado = ej.get("resultado", "")
        if resultado:
            story.append(Spacer(1, 0.1*cm))
            story.append(_bloque_resultado(resultado, W, s))

        story.append(Spacer(1, 0.4*cm))

    doc.build(story, onFirstPage=pie, onLaterPages=pie)
    return path


# ─────────────────────────────────────────────
# FUNCIÓN PÚBLICA — llama al modelo y genera PDF
# ─────────────────────────────────────────────
def resolver_y_generar_pdf(client, texto, user_id, titulo, perfil):
    """
    1. Llama al modelo pidiendo JSON estructurado
    2. Parsea el JSON
    3. Genera PDF desde el JSON
    Retorna ruta del PDF
    """
    msgs = [
        {"role": "system", "content": SYSTEM_JSON},
        {"role": "user",   "content": texto}
    ]

    # intentar con modelo pesado primero, fallback a versatile
    for modelo in ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"]:
        try:
            resp = client.chat.completions.create(
                model=modelo, messages=msgs, max_tokens=4000
            )
            raw = resp.choices[0].message.content.strip()
            # limpiar posibles bloques ```json
            raw = re.sub(r'^```json\s*|^```\s*|```$', '', raw, flags=re.MULTILINE).strip()
            datos = json.loads(raw)
            return crear_pdf_desde_json(datos, user_id, titulo, perfil), datos
        except json.JSONDecodeError:
            continue
        except Exception:
            continue

    raise RuntimeError("No se pudo obtener JSON válido del modelo")


# ─────────────────────────────────────────────
# OTRAS FUNCIONES DEL AGENTE
# ─────────────────────────────────────────────
def analizar_imagen_ejercicio(client, img_bytes, caption, perfil):
    import base64
    b64 = base64.b64encode(img_bytes).decode()
    msgs = [{
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text",
             "text": f"{SYSTEM_JSON}\n\nResuelve este ejercicio. {caption or ''}"}
        ]
    }]
    resp = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=msgs, max_tokens=4000
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r'^```json\s*|^```\s*|```$', '', raw, flags=re.MULTILINE).strip()
    datos = json.loads(raw)
    return datos


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
