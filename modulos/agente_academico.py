# ─────────────────────────────────────────────────────────────
# AGENTE ACADÉMICO — JARVIS 3.2
# PDF 100% ReportLab puro. Sin matplotlib. Sin PNG de fórmulas.
# Fórmulas como texto Unicode limpio.
# ─────────────────────────────────────────────────────────────
import os, re, io
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── rutas ──
ARCHIVOS_DIR = "/root/jarvis/archivos"
Path(ARCHIVOS_DIR).mkdir(parents=True, exist_ok=True)

# ── colores ──
C_PRIMARY  = colors.HexColor("#1a1a2e")   # azul muy oscuro
C_ACCENT   = colors.HexColor("#4361ee")   # azul eléctrico
C_PASO_BG  = colors.HexColor("#eef2ff")   # azul muy claro para pasos
C_RESULT   = colors.HexColor("#fff3cd")   # amarillo claro para resultado
C_RESULT_B = colors.HexColor("#e67e00")   # naranja para borde resultado
C_EJ_BG    = colors.HexColor("#dbeafe")   # celeste para cabecera ejercicio
C_EJ_LINE  = colors.HexColor("#2563eb")   # azul para línea ejercicio
C_GRAY     = colors.HexColor("#888888")
C_WHITE    = colors.white
C_BLACK    = colors.black

# ── system prompt para el modelo ──
SYSTEM_ACADEMICO = """Eres el motor academico de JARVIS, tutor IA para ingenieria universitaria peruana.

REGLAS DE FORMATO — OBLIGATORIAS SIN EXCEPCION:

1. NUNCA uses LaTeX. Cero \\frac, cero $...$, cero \\int, cero \\sqrt, cero \\text{}.

2. Para subindices y superindices usa caracteres Unicode reales:
   SUBINDICES:  ₀ ₁ ₂ ₃ ₄ ₅ ₆ ₇ ₈ ₉ ₙ ₘ ₐ
   SUPERINDICES: ⁰ ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹ ⁻ ⁺ ⁿ
   EJEMPLOS CORRECTOS:
   - H₂O  CO₂  C₈H₁₈  m⁻¹  10⁶  Nₐ  m³  mg·m⁻³

3. Para fracciones: (numerador / denominador)

4. Para raices: √x

5. Operadores: × · ÷ ± ≤ ≥ ≠ ≈ ∑ ∏ ∞ √ ∫ ∂ Δ

6. Pasos numerados: "Paso 1: [titulo]"

7. Resultado final: "RESULTADO: [valor con unidades]"

8. Para MULTIPLES ejercicios:
   - Cada ejercicio inicia con: ## Ejercicio N: [titulo]
   - Los pasos de CADA ejercicio empiezan desde Paso 1
   - NUNCA continúes la numeración entre ejercicios

9. Para UN solo ejercicio: ## [titulo descriptivo]"""


# ─────────────────────────────────────────────
# POST-PROCESADOR UNICODE
# ─────────────────────────────────────────────
def _fix_unicode(texto: str) -> str:
    """Corrige automáticamente notación 'n' que usa el modelo."""
    # Superíndices negativos: moln1 → mol⁻¹
    for d, r in [('1','⁻¹'),('2','⁻²'),('3','⁻³')]:
        texto = re.sub(rf'([a-zA-Zμ·L])n{d}\b', lambda m,r=r: m.group(1)+r, texto)

    # Potencias: 10n6 → 10⁶, 10n-3 → 10⁻³
    sup = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴',
           '5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹','-':'⁻'}
    def pot(m):
        return m.group(1) + ''.join(sup.get(c,c) for c in m.group(2))
    texto = re.sub(r'(10)n(-?\d+)', pot, texto)

    # Fórmulas químicas comunes
    reemplazos = [
        (r'\bCnHnn\b','C₈H₁₈'),(r'\bC8H18\b','C₈H₁₈'),
        (r'\bCnHnnOn\b','C₆H₁₂O₆'),(r'\bC6H12O6\b','C₆H₁₂O₆'),
        (r'\bCnHnOH\b','C₂H₅OH'),(r'\bC2H5OH\b','C₂H₅OH'),
        (r'\bHnO\b','H₂O'),(r'\bH2O\b','H₂O'),
        (r'\bCOn\b','CO₂'),(r'\bCO2\b','CO₂'),
        (r'\bO2\b','O₂'),(r'\bN2\b','N₂'),
        (r'\bNn\b','Nₐ'),(r'\bNA\b','Nₐ'),
        (r'\bm3\b','m³'),(r'\bcm3\b','cm³'),(r'\bdm3\b','dm³'),
        (r'\bm2\b','m²'),(r'\bkm2\b','km²'),
    ]
    for pat, rep in reemplazos:
        texto = re.sub(pat, rep, texto)
    return texto


# ─────────────────────────────────────────────
# ESTILOS
# ─────────────────────────────────────────────
def _estilos():
    return {
        "titulo_doc": ParagraphStyle(
            "titulo_doc", fontName="Helvetica-Bold",
            fontSize=22, textColor=C_WHITE, spaceAfter=4, leading=28
        ),
        "sub_doc": ParagraphStyle(
            "sub_doc", fontName="Helvetica",
            fontSize=11, textColor=colors.HexColor("#ccccff"), leading=16
        ),
        "titulo_ej": ParagraphStyle(
            "titulo_ej", fontName="Helvetica-Bold",
            fontSize=13, textColor=C_EJ_LINE, spaceAfter=2, leading=18
        ),
        "cuerpo": ParagraphStyle(
            "cuerpo", fontName="Helvetica",
            fontSize=10, textColor=C_BLACK, leading=15, spaceAfter=2
        ),
        "paso_titulo": ParagraphStyle(
            "paso_titulo", fontName="Helvetica-Bold",
            fontSize=10, textColor=C_ACCENT, leading=14
        ),
        "paso_cuerpo": ParagraphStyle(
            "paso_cuerpo", fontName="Helvetica",
            fontSize=10, textColor=C_BLACK, leading=14
        ),
        "resultado": ParagraphStyle(
            "resultado", fontName="Helvetica-Bold",
            fontSize=11, textColor=C_RESULT_B, leading=16
        ),
        "codigo": ParagraphStyle(
            "codigo", fontName="Courier",
            fontSize=9, textColor=colors.HexColor("#1a1a1a"),
            leading=13, leftIndent=8
        ),
        "pie": ParagraphStyle(
            "pie", fontName="Helvetica",
            fontSize=8, textColor=C_GRAY
        ),
    }


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _esc(texto: str) -> str:
    """Escapa caracteres especiales para ReportLab Paragraph."""
    return (texto
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _bloque_paso(numero, titulo, lineas_cuerpo, W, estilos):
    """Devuelve un Table con el bloque visual de un paso."""
    contenido = []
    if titulo:
        contenido.append(
            Paragraph(f"Paso {numero}: {_esc(titulo)}", estilos["paso_titulo"])
        )
    for l in lineas_cuerpo:
        if l.strip():
            contenido.append(
                Paragraph(_esc(l.strip()), estilos["paso_cuerpo"])
            )
    if not contenido:
        return None
    t = Table([[contenido]], colWidths=[W - 0.4*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), C_PASO_BG),
        ('LEFTPADDING',   (0,0), (-1,-1), 12),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
        ('TOPPADDING',    (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LINERIGHT',     (0,0), (0,-1),  3, C_ACCENT),
        ('ROWBACKGROUNDS',(0,0), (-1,-1), [C_PASO_BG]),
    ]))
    return t


def _bloque_resultado(texto, W, estilos):
    """Devuelve un Table con el bloque visual del resultado."""
    t = Table(
        [[Paragraph(f"✓  {_esc(texto)}", estilos["resultado"])]],
        colWidths=[W - 0.4*cm]
    )
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), C_RESULT),
        ('LINEBELOW',     (0,0), (-1,-1), 2, C_RESULT_B),
        ('LINETOP',       (0,0), (-1,-1), 2, C_RESULT_B),
        ('LEFTPADDING',   (0,0), (-1,-1), 14),
        ('TOPPADDING',    (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    return t


def _bloque_ejercicio(titulo, W, estilos):
    """Cabecera visual para cada ejercicio."""
    t = Table(
        [[Paragraph(f"📌  {_esc(titulo)}", estilos["titulo_ej"])]],
        colWidths=[W]
    )
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), C_EJ_BG),
        ('LINEBELOW',     (0,0), (-1,-1), 2.5, C_EJ_LINE),
        ('LEFTPADDING',   (0,0), (-1,-1), 14),
        ('TOPPADDING',    (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 9),
    ]))
    return t


# ─────────────────────────────────────────────
# PARSER DE CONTENIDO
# ─────────────────────────────────────────────
RE_EJ     = re.compile(r'^#{1,2}\s*(Ejercicio\s+\d+.*|Problema\s+\d+.*)', re.IGNORECASE)
RE_TITULO = re.compile(r'^#{1,2}\s+(.+)$')
RE_PASO   = re.compile(r'^(?:\*\*)?(?:Paso\s+(\d+)|(\d+)\.)\s*[:\-]?\s*(?:\*\*)?\s*(.*)', re.IGNORECASE)
RE_RESULT = re.compile(r'^(?:\*\*)?(?:RESULTADO|Respuesta|RESPUESTA)\s*[:\-]\s*(?:\*\*)?\s*(.*)', re.IGNORECASE)
RE_BULLET = re.compile(r'^[-•*]\s+(.+)')
RE_BOLD   = re.compile(r'\*\*(.+?)\*\*')


def _limpiar_markdown(txt):
    """Quita ** del texto para ReportLab."""
    return RE_BOLD.sub(r'<b>\1</b>', txt)


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────
def crear_pdf_academico(contenido, user_id, titulo="Solución", perfil=None):
    """
    Genera PDF profesional 100% ReportLab.
    Sin matplotlib. Sin PNG. Solo texto Unicode limpio.
    """
    perfil  = perfil or {}
    nombre  = perfil.get("nombre", "Alumno")
    carrera = perfil.get("carrera", "")
    uni     = perfil.get("universidad", "")
    fecha   = datetime.now().strftime("%-d de %B de %Y")
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    path    = f"{ARCHIVOS_DIR}/solucion_{user_id}_{ts}.pdf"

    # Post-procesar
    contenido = _fix_unicode(contenido)

    estilos = _estilos()

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2.5*cm
    )
    W = doc.width

    story = []

    # ── pie de página ──
    def pie(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(C_GRAY)
        canvas.drawCentredString(A4[0]/2, 1.2*cm, f"JARVIS 3.2  ·  Página {doc_.page}")
        canvas.restoreState()

    # ── portada ──
    info = nombre
    if carrera: info += f"  —  {carrera}"
    if uni:     info += f"  |  {uni}"

    portada = Table([
        [Paragraph("JARVIS 3.2", estilos["titulo_doc"])],
        [Paragraph(_esc(titulo),  estilos["sub_doc"])],
        [Paragraph(f"{_esc(info)}<br/><font size='9' color='#aaaacc'>{fecha}</font>",
                   estilos["sub_doc"])],
    ], colWidths=[W])
    portada.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (0,0),  C_PRIMARY),
        ('BACKGROUND',    (0,1), (-1,-1), colors.HexColor("#2d3561")),
        ('TOPPADDING',    (0,0), (0,0),  18),
        ('BOTTOMPADDING', (0,-1),(-1,-1),16),
        ('LEFTPADDING',   (0,0), (-1,-1),20),
        ('RIGHTPADDING',  (0,0), (-1,-1),12),
    ]))
    story.append(portada)
    story.append(Spacer(1, 0.6*cm))

    # ── parsear contenido ──
    lineas = contenido.split('\n')
    i = 0
    num_paso  = 0
    en_paso   = False
    paso_tit  = ""
    paso_body = []
    buffer    = []   # texto libre acumulado

    def flush_buffer():
        for bl in buffer:
            if bl.strip():
                story.append(Paragraph(_esc(_limpiar_markdown(bl)), estilos["cuerpo"]))
        buffer.clear()

    def flush_paso():
        nonlocal en_paso, paso_tit, paso_body, num_paso
        if en_paso:
            blq = _bloque_paso(num_paso, paso_tit, paso_body, W, estilos)
            if blq:
                story.append(Spacer(1, 0.15*cm))
                story.append(blq)
            en_paso   = False
            paso_tit  = ""
            paso_body = []

    while i < len(lineas):
        linea = lineas[i].rstrip()

        # ── ejercicio (## Ejercicio N) ──
        m = RE_EJ.match(linea.strip())
        if m:
            flush_buffer()
            flush_paso()
            num_paso = 0   # resetear pasos
            story.append(Spacer(1, 0.4*cm))
            story.append(_bloque_ejercicio(m.group(1).strip(), W, estilos))
            story.append(Spacer(1, 0.2*cm))
            i += 1
            continue

        # ── título genérico (## Texto) ──
        m = RE_TITULO.match(linea.strip())
        if m:
            flush_buffer()
            flush_paso()
            story.append(Spacer(1, 0.25*cm))
            story.append(Paragraph(
                f"<b>{_esc(m.group(1))}</b>", estilos["cuerpo"]
            ))
            story.append(Spacer(1, 0.1*cm))
            i += 1
            continue

        # ── RESULTADO ──
        m = RE_RESULT.match(linea.strip())
        if m:
            flush_buffer()
            flush_paso()
            txt = m.group(1).strip() or ""
            # recoger líneas siguientes que sean parte del resultado
            j = i + 1
            while j < len(lineas) and lineas[j].strip() and not RE_PASO.match(lineas[j]):
                txt += " " + lineas[j].strip()
                j += 1
            story.append(Spacer(1, 0.2*cm))
            story.append(_bloque_resultado(txt, W, estilos))
            story.append(Spacer(1, 0.2*cm))
            i = j
            continue

        # ── Paso N ──
        m = RE_PASO.match(linea.strip())
        if m:
            flush_buffer()
            flush_paso()
            num_paso += 1
            en_paso  = True
            paso_tit = (m.group(3) or "").strip()
            paso_body = []
            i += 1
            # recoger cuerpo del paso
            while i < len(lineas):
                sig = lineas[i].rstrip()
                if not sig.strip():
                    i += 1
                    break
                if RE_PASO.match(sig.strip()) or RE_RESULT.match(sig.strip()) or RE_EJ.match(sig.strip()):
                    break
                paso_body.append(sig)
                i += 1
            continue

        # ── bullets ──
        m = RE_BULLET.match(linea.strip())
        if m:
            flush_paso()
            buffer.append(f"• {m.group(1)}")
            i += 1
            continue

        # ── línea vacía ──
        if not linea.strip():
            flush_paso()
            if buffer:
                flush_buffer()
                story.append(Spacer(1, 0.1*cm))
            i += 1
            continue

        # ── texto libre ──
        if en_paso:
            paso_body.append(linea)
        else:
            buffer.append(linea)
        i += 1

    # flush final
    flush_buffer()
    flush_paso()

    doc.build(story, onFirstPage=pie, onLaterPages=pie)
    return path


# ─────────────────────────────────────────────
# OTRAS FUNCIONES DEL AGENTE
# ─────────────────────────────────────────────
def resolver_ejercicio(client, texto, perfil, historial, dificil=False):
    from groq import Groq
    modelo = "openai/gpt-oss-120b" if dificil else "llama-3.3-70b-versatile"
    msgs = [{"role": "system", "content": SYSTEM_ACADEMICO}]
    if historial:
        msgs += historial[-6:]
    msgs.append({"role": "user", "content": texto})
    try:
        resp = client.chat.completions.create(
            model=modelo, messages=msgs, max_tokens=4000
        )
        return resp.choices[0].message.content, modelo
    except Exception:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile", messages=msgs, max_tokens=4000
        )
        return resp.choices[0].message.content, "llama-3.3-70b-versatile"


def analizar_imagen_ejercicio(client, img_bytes, caption, perfil):
    import base64
    b64 = base64.b64encode(img_bytes).decode()
    msgs = [{
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text",
             "text": f"{SYSTEM_ACADEMICO}\n\nResuelve este ejercicio paso a paso. {caption or ''}"}
        ]
    }]
    resp = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=msgs, max_tokens=4000
    )
    solucion = resp.choices[0].message.content
    return "", solucion, "llama-4-scout"


def generar_estructura_archivo(client, tipo, solicitud, perfil):
    import json as _json
    prompt = (
        f"Genera una estructura JSON para un archivo {tipo} sobre: {solicitud}. "
        f"Responde SOLO con JSON válido, sin texto extra."
    )
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000
    )
    txt = resp.choices[0].message.content
    txt = re.sub(r'^```json\s*|^```\s*|```$', '', txt, flags=re.MULTILINE).strip()
    return _json.loads(txt)
