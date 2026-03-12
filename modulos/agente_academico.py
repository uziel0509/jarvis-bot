"""
modulos/agente_academico.py
Jarvis 3.2 — Agente Academico

Responsabilidades:
- Resolver ejercicios de ingenieria (texto e imagen)
- Generar PDFs 100% limpios — cero LaTeX crudo, formulas como PNG
- Generar Excel, PowerPoint, Word academicos
- Fallback automatico de modelos
"""

import os, re, io, json, logging, asyncio
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, Image as RLImage
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

from modulos.pre_render import (
    procesar_output, elementos_a_texto_plano,
    TIPO_TEXTO, TIPO_FORMULA, TIPO_CODIGO,
    TIPO_ESPACIO, TIPO_TITULO, TIPO_SUBTITULO
)

logger = logging.getLogger(__name__)

ARCHIVOS_DIR = "/root/jarvis/archivos"
Path(ARCHIVOS_DIR).mkdir(parents=True, exist_ok=True)

# Modelos con orden de fallback
MODELO_PESADO = os.getenv("MODELO_EJERCICIOS",        "openai/gpt-oss-120b")
MODELO_MEDIO  = os.getenv("MODELO_EJERCICIOS_RAPIDO", "openai/gpt-oss-20b")
MODELO_CHAT   = os.getenv("MODELO_CHAT",              "llama-3.3-70b-versatile")
MODELO_VISION = os.getenv("MODELO_VISION",            "meta-llama/llama-4-scout-17b-16e-instruct")

FALLBACK_PESADO = [MODELO_PESADO, MODELO_MEDIO, MODELO_CHAT]
FALLBACK_MEDIO  = [MODELO_MEDIO,  MODELO_CHAT]

# ─── Colores PDF ──────────────────────────────────────────────
C_PRIMARY  = colors.HexColor("#1a1a2e")
C_ACCENT   = colors.HexColor("#0f3460")
C_GOLD     = colors.HexColor("#e94560")
C_STEP_BG  = colors.HexColor("#eef2ff")
C_CODE_BG  = colors.HexColor("#f4f4f4")
C_WHITE    = colors.white
C_GRAY     = colors.HexColor("#888888")
C_SUBTITLE = colors.HexColor("#aaaacc")

# ─── System prompt ────────────────────────────────────────────
SYSTEM_ACADEMICO = """Eres el motor academico de JARVIS, tutor IA para ingenieria universitaria peruana.

REGLAS DE FORMATO — OBLIGATORIAS SIN EXCEPCION:

1. NUNCA uses LaTeX. Cero \\frac, cero $...$, cero \\int, cero \\sqrt, cero \\text{}.

2. Para subindices y superindices usa caracteres Unicode reales:
   SUBINDICES:  ₀ ₁ ₂ ₃ ₄ ₅ ₆ ₇ ₈ ₉ ₙ ₘ ₐ
   SUPERINDICES: ⁰ ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹ ⁻ ⁺ ⁿ
   EJEMPLOS CORRECTOS:
   - H₂O (no H2O ni HnO)
   - CO₂ (no CO2 ni COn)
   - m⁻¹ (no m^-1 ni mn1)
   - 10⁶ (no 10^6 ni 10n)
   - C₈H₁₈ (no C8H18 ni CnHnn)
   - Nₐ = 6.022×10²³ (no Na ni Nn)
   - m³ (no m^3 ni mn3)
   - mg·m⁻³ (no mg/m3 ni mg·mn3)

3. Para fracciones usa la barra diagonal: (numerador / denominador)
   Ejemplo: (8 × 28 / 114) no \\frac{8×28}{114}

4. Para raices: √x o sqrt(x)
   Ejemplo: √(x² + y²)

5. Para integrales: ∫f(x)dx de a hasta b

6. Operadores matematicos disponibles: × · ÷ ± ≤ ≥ ≠ ≈ ∑ ∏ ∞ √ ∫ ∂ Δ

7. Pasos numerados: "Paso 1: [titulo del paso]"

8. Resultado final: "RESULTADO: [valor con unidades correctas]"

9. Explica el razonamiento en cada paso, no solo el calculo.

10. Para MULTIPLES ejercicios:
    - Cada ejercicio inicia con: ## Ejercicio N: [titulo descriptivo]
    - Los pasos de CADA ejercicio empiezan desde Paso 1 (NUNCA continuos)
    - Ejercicio 17: Paso 1, Paso 2, Paso 3. RESULTADO. 
    - Ejercicio 18: Paso 1, Paso 2. RESULTADO. (no Paso 4, Paso 5)

11. Para UN solo ejercicio inicia con: ## [titulo descriptivo]

MATERIAS: Calculo, algebra lineal, fisica, estatica, dinamica, resistencia de materiales,
termodinamica, hidraulica, circuitos, estadistica, quimica y todas las de ingenieria."""

SYSTEM_VISION_DESCRIPCION = """Analiza esta imagen de ejercicio academico.
Describe con precision:
1. Tipo de ejercicio (materia y tema)
2. Datos dados (valores, unidades, condiciones)
3. Lo que se pide calcular
4. Diagramas o figuras presentes
5. Texto manuscrito (transcribelo exactamente)
No resuelvas aun, solo describe."""

SYSTEM_VISION_RESOLVER = """Con el analisis de la imagen, resuelve el ejercicio.
OBLIGATORIO: Sin LaTeX. Texto plano. Pasos numerados. RESULTADO al final."""


# ═══════════════════════════════════════════════════════════════
# LLAMADA IA CON FALLBACK
# ═══════════════════════════════════════════════════════════════
def _llamar_fallback(client, mensajes, modelos, max_tokens=4000):
    ultimo_error = None
    for modelo in modelos:
        try:
            resp = client.chat.completions.create(
                model=modelo, messages=mensajes, max_tokens=max_tokens
            )
            logger.info(f"[academico] Modelo usado: {modelo}")
            return resp.choices[0].message.content, modelo
        except Exception as e:
            logger.warning(f"[academico] {modelo} fallo: {e}")
            ultimo_error = e
    raise RuntimeError(f"Todos los modelos fallaron: {ultimo_error}")


# ═══════════════════════════════════════════════════════════════
# RESOLVER EJERCICIO (texto)
# ═══════════════════════════════════════════════════════════════
async def resolver_ejercicio(client, texto, perfil, historial, dificil=False):
    """Retorna (respuesta_texto, modelo_usado)."""
    loop = asyncio.get_event_loop()
    system = SYSTEM_ACADEMICO
    n = perfil.get("nombre", "")
    c = perfil.get("carrera", "")
    ci = perfil.get("ciclo", "")
    if n or c:
        system += f"\n\nALUMNO: {n} | {c} | Ciclo {ci}"

    msgs = [{"role": "system", "content": system}]
    for msg in historial[-6:]:
        msgs.append(msg)
    msgs.append({"role": "user", "content": texto})

    modelos = FALLBACK_PESADO if dificil else FALLBACK_MEDIO
    return await loop.run_in_executor(None, lambda: _llamar_fallback(client, msgs, modelos))


# ═══════════════════════════════════════════════════════════════
# ANALIZAR IMAGEN DE EJERCICIO
# ═══════════════════════════════════════════════════════════════
async def analizar_imagen_ejercicio(client, img_bytes, caption, perfil):
    """
    Pipeline 2 pasos: vision describe → modelo pesado resuelve.
    Retorna (descripcion, solucion, modelo_usado).
    """
    import base64
    loop    = asyncio.get_event_loop()
    img_b64 = base64.b64encode(img_bytes).decode()

    def paso1():
        instruccion = caption if caption else SYSTEM_VISION_DESCRIPCION
        return client.chat.completions.create(
            model=MODELO_VISION,
            messages=[{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": instruccion}
            ]}],
            max_tokens=1500
        )

    resp1       = await loop.run_in_executor(None, paso1)
    descripcion = resp1.choices[0].message.content

    n = perfil.get("nombre", "")
    c = perfil.get("carrera", "")
    system = SYSTEM_ACADEMICO + (f"\n\nALUMNO: {n} | {c}" if n or c else "")

    msgs2 = [
        {"role": "system",    "content": system},
        {"role": "user",      "content": f"Analice esta imagen:\n\n{descripcion}"},
        {"role": "assistant", "content": "Entendido. Resolviendo paso a paso."},
        {"role": "user",      "content": SYSTEM_VISION_RESOLVER}
    ]
    solucion, modelo = await loop.run_in_executor(
        None, lambda: _llamar_fallback(client, msgs2, FALLBACK_PESADO)
    )
    return descripcion, solucion, modelo


# ═══════════════════════════════════════════════════════════════
# ESTILOS PDF
# ═══════════════════════════════════════════════════════════════
def _estilos():
    return {
        "titulo_doc": ParagraphStyle(
            'TituloDoc', fontSize=20, fontName='Helvetica-Bold',
            textColor=C_WHITE, alignment=TA_CENTER, spaceAfter=6),
        "sub_doc": ParagraphStyle(
            'SubDoc', fontSize=12, fontName='Helvetica',
            textColor=C_SUBTITLE, alignment=TA_CENTER, spaceAfter=4),
        "body": ParagraphStyle(
            'Body', fontSize=11, fontName='Helvetica',
            textColor=C_PRIMARY, alignment=TA_JUSTIFY,
            spaceAfter=8, leading=16),
        "titulo_sec": ParagraphStyle(
            'TituloSec', fontSize=14, fontName='Helvetica-Bold',
            textColor=C_ACCENT, spaceBefore=14, spaceAfter=6),
        "sub_sec": ParagraphStyle(
            'SubSec', fontSize=12, fontName='Helvetica-Bold',
            textColor=C_ACCENT, spaceBefore=10, spaceAfter=4),
        "paso_header": ParagraphStyle(
            'PasoHeader', fontSize=12, fontName='Helvetica-Bold',
            textColor=C_ACCENT, spaceAfter=4, spaceBefore=6),
        "paso_body": ParagraphStyle(
            'PasoBody', fontSize=11, fontName='Helvetica',
            textColor=C_PRIMARY, leftIndent=10, leading=16),
        "codigo": ParagraphStyle(
            'Codigo', fontSize=10, fontName='Courier',
            textColor=C_PRIMARY, leftIndent=8, leading=14),
        "resultado": ParagraphStyle(
            'Resultado', fontSize=13, fontName='Helvetica-Bold',
            textColor=C_WHITE, alignment=TA_CENTER, spaceAfter=4),
    }


def _escapar(texto):
    """Escapar caracteres especiales de ReportLab."""
    return (texto.replace('&', '&amp;')
                 .replace('<', '&lt;')
                 .replace('>', '&gt;')
                 .replace('**', ''))


# ═══════════════════════════════════════════════════════════════
# CREAR PDF ACADEMICO — GARANTIA CERO LATEX CRUDO
# ═══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# POST-PROCESADOR UNICODE — corrige lo que el modelo no respeta
# ─────────────────────────────────────────────
import re as _re

def _fix_unicode_notacion(texto: str) -> str:
    """
    Convierte notación con 'n' que usa el modelo en caracteres Unicode reales.
    Ejemplo: moln1 → mol⁻¹, 10n6 → 10⁶, mn3 → m³, HnO → H₂O
    """
    # Superíndices negativos: mn1 → m⁻¹, moln1 → mol⁻¹, sn1 → s⁻¹
    sup_neg = {'1': '⁻¹', '2': '⁻²', '3': '⁻³'}
    for d, r in sup_neg.items():
        texto = _re.sub(rf'([a-zA-Zμ·])n{d}\b', lambda m: m.group(1) + r, texto)

    # Superíndices positivos en potencias: 10n6 → 10⁶, 10n3 → 10³
    sup_map = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵',
               '6':'⁶','7':'⁷','8':'⁸','9':'⁹'}
    def fix_potencia(m):
        base, exp = m.group(1), m.group(2)
        exp_uni = ''.join(sup_map.get(c, c) for c in exp)
        return base + exp_uni
    # 10n6, 10n-3, 10n-6
    texto = _re.sub(r'(10)n(-?\d+)', fix_potencia, texto)
    texto = _re.sub(r'(\d+)n(\d)', fix_potencia, texto)

    # Subíndices en fórmulas químicas conocidas
    quimicos = [
        (r'\bC8H18\b', 'C₈H₁₈'), (r'\bC8H1[Ee]\b', 'C₈H₁₈'),
        (r'\bCnHnn\b', 'C₈H₁₈'),  # octano abreviado con n
        (r'\bCO2\b', 'CO₂'),       (r'\bH2O\b', 'H₂O'),
        (r'\bO2\b', 'O₂'),         (r'\bN2\b', 'N₂'),
        (r'\bNH3\b', 'NH₃'),       (r'\bH2SO4\b', 'H₂SO₄'),
        (r'\bHCl\b', 'HCl'),       (r'\bNaCl\b', 'NaCl'),
        (r'\bCO2\b', 'CO₂'),       (r'\bCH4\b', 'CH₄'),
        (r'\bC6H12O6\b', 'C₆H₁₂O₆'),
        (r'\bC2H5OH\b', 'C₂H₅OH'), (r'\bCnHnOH\b', 'C₂H₅OH'),
        (r'\bCnHnnOn\b', 'C₆H₁₂O₆'),
        (r'\bHnO\b', 'H₂O'),       (r'\bCOn\b', 'CO₂'),
    ]
    for pat, rep in quimicos:
        texto = _re.sub(pat, rep, texto)

    # m³, cm³, dm³
    texto = _re.sub(r'\bm3\b', 'm³', texto)
    texto = _re.sub(r'\bcm3\b', 'cm³', texto)
    texto = _re.sub(r'\bdm3\b', 'dm³', texto)
    texto = _re.sub(r'\bkm2\b', 'km²', texto)
    texto = _re.sub(r'\bm2\b', 'm²', texto)

    # Nₐ (número de Avogadro)
    texto = _re.sub(r'\bNn\b', 'Nₐ', texto)
    texto = _re.sub(r'\bNA\b', 'Nₐ', texto)

    return texto

def crear_pdf_academico(contenido, user_id, titulo="Solucion de Ejercicio", perfil=None):
    """
    Genera PDF profesional con cero LaTeX crudo.

    TODO el contenido pasa por procesar_output() de pre_render:
      - Formulas LaTeX → imagen PNG (matplotlib)
      - Codigo → recuadro limpio
      - Pasos numerados → bloques con fondo

    Retorna ruta del PDF generado.
    """
    perfil = perfil or {}
    # Post-procesar el contenido para corregir notación Unicode
    contenido = _fix_unicode_notacion(contenido)
    nombre = perfil.get("nombre", "Alumno")
    carrera = perfil.get("carrera", "")
    uni     = perfil.get("universidad", "")

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    path    = f"{ARCHIVOS_DIR}/solucion_{user_id}_{ts}.pdf"
    estilo  = _estilos()

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2.5*cm
    )
    W = doc.width  # ancho util

    story = []

    # ── Pie de pagina ──
    def pie(canvas, doc_):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(C_GRAY)
        canvas.drawCentredString(
            A4[0]/2, 1.5*cm,
            f"JARVIS 3.2 — {datetime.now().strftime('%d/%m/%Y %H:%M')} — Uso academico"
        )
        canvas.setStrokeColor(colors.HexColor("#dddddd"))
        canvas.line(2*cm, 1.8*cm, A4[0]-2*cm, 1.8*cm)
        canvas.restoreState()

    # ── Portada ──
    info = nombre + (f" — {carrera}" if carrera else "") + (f" | {uni}" if uni else "")
    fecha = datetime.now().strftime("%d de %B de %Y")

    # Portada limpia — barra de color acento (no negro completo)
    portada = Table([
        [Paragraph("📘 JARVIS 3.2", estilo["titulo_doc"])],
        [Paragraph(_escapar(titulo), estilo["sub_doc"])],
        [Paragraph(
            f"{_escapar(info)}<br/><font size='10' color='#aaaacc'>{fecha}</font>",
            estilo["sub_doc"]
        )],
    ], colWidths=[W])
    portada.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1, 0), C_PRIMARY),   # Solo fila titulo oscura
        ('BACKGROUND',    (0,1), (-1,-1), C_ACCENT),    # Resto azul acento
        ('TOPPADDING',    (0,0), (-1, 0), 18),
        ('BOTTOMPADDING', (0,-1),(-1,-1), 18),
        ('LEFTPADDING',   (0,0), (-1,-1), 20),
        ('RIGHTPADDING',  (0,0), (-1,-1), 20),
    ]))
    story.append(portada)
    story.append(Spacer(1, 0.5*cm))

    # ══════════════════════════════════════════════════════════
    # NUCLEO: procesar_output garantiza cero LaTeX crudo
    # ══════════════════════════════════════════════════════════
    elementos  = procesar_output(contenido)
    RE_PASO    = re.compile(r'^(?:Paso\s+(\d+)|(\d+)\.)\s*[:\-]?\s*(.*)', re.IGNORECASE)
    RE_RESULT  = re.compile(r'^RESULTADO\s*[:\-]\s*(.*)', re.IGNORECASE)
    RE_EJERCICIO = re.compile(r'^#{1,2}\s*(?:Ejercicio\s+\d+|Problema\s+\d+)[:\s]*(.*)', re.IGNORECASE)

    resultado_final = None
    i = 0
    num_paso = 0

    while i < len(elementos):
        el   = elementos[i]
        tipo = el["tipo"]

        if tipo == TIPO_TITULO:
            story.append(Spacer(1, 0.3*cm))
            # Cabecera de ejercicio con fondo destacado
            t_ej = Table([[Paragraph(
                f"📌 {_escapar(el['contenido'])}", estilo["titulo_sec"]
            )]], colWidths=[W])
            t_ej.setStyle(TableStyle([
                ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor("#e8eeff")),
                ('LEFTPADDING',   (0,0), (-1,-1), 14),
                ('TOPPADDING',    (0,0), (-1,-1), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('LINEBELOW',     (0,0), (-1,-1), 2, C_ACCENT),
            ]))
            story.append(t_ej)
            story.append(Spacer(1, 0.2*cm))
            num_paso = 0  # resetear pasos por ejercicio

        elif tipo == TIPO_SUBTITULO:
            contenido_sub = el["contenido"]
            # Si es encabezado de ejercicio — destacarlo y resetear pasos
            es_ej = bool(_re.match(
                r'^(Ejercicio|Problema|Ej\.?)\s*\d+', contenido_sub, _re.IGNORECASE
            ))
            if es_ej:
                story.append(Spacer(1, 0.35*cm))
                t_ej = Table([[Paragraph(
                    f"📌 {_escapar(contenido_sub)}", estilo["titulo_sec"]
                )]], colWidths=[W])
                t_ej.setStyle(TableStyle([
                    ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor("#e8eeff")),
                    ('LEFTPADDING',   (0,0), (-1,-1), 14),
                    ('TOPPADDING',    (0,0), (-1,-1), 8),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                    ('LINEBELOW',     (0,0), (-1,-1), 2, C_ACCENT),
                ]))
                story.append(t_ej)
                story.append(Spacer(1, 0.15*cm))
                num_paso = 0  # resetear pasos por ejercicio
            else:
                story.append(Spacer(1, 0.1*cm))
                story.append(Paragraph(_escapar(contenido_sub), estilo["sub_sec"]))

        elif tipo == TIPO_ESPACIO:
            story.append(Spacer(1, 0.2*cm))

        # Formulas → imagen PNG (cero LaTeX en el PDF)
        elif tipo == TIPO_FORMULA:
            png = el["contenido"]
            if png:
                buf = io.BytesIO(png)
                img = RLImage(buf)
                inline = el.get("inline", False)
                max_w  = W * (0.45 if inline else 0.85)
                if img.drawWidth > max_w:
                    ratio = max_w / img.drawWidth
                    img.drawWidth  = max_w
                    img.drawHeight = img.drawHeight * ratio
                t = Table([[img]], colWidths=[W])
                t.setStyle(TableStyle([
                    ('ALIGN',         (0,0), (-1,-1), 'CENTER'),
                    ('BACKGROUND',    (0,0), (-1,-1), C_STEP_BG),
                    ('TOPPADDING',    (0,0), (-1,-1), 8),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ]))
                story.append(t)
                story.append(Spacer(1, 0.1*cm))
            else:
                # No se pudo renderizar — mostrar texto limpio del formula_tex
                tex = el.get("formula_tex", "formula")
                story.append(Paragraph(f"[Formula: {_escapar(tex[:80])}]",
                                       estilo["paso_body"]))

        # Bloques de codigo → recuadro limpio sin backticks
        elif tipo == TIPO_CODIGO:
            codigo = el["contenido"]
            lang   = el.get("lenguaje", "")
            items  = []
            if lang:
                items.append(Paragraph(
                    f"<b>{lang.upper()}</b>",
                    ParagraphStyle('Lang', fontSize=9, fontName='Helvetica-Bold',
                                   textColor=C_GRAY)
                ))
            for lc in codigo.split('\n'):
                lc_safe = _escapar(lc) or " "
                items.append(Paragraph(lc_safe, estilo["codigo"]))
            t = Table([items], colWidths=[W])
            t.setStyle(TableStyle([
                ('BACKGROUND',    (0,0), (-1,-1), C_CODE_BG),
                ('TOPPADDING',    (0,0), (-1,-1), 10),
                ('BOTTOMPADDING', (0,0), (-1,-1), 10),
                ('LEFTPADDING',   (0,0), (-1,-1), 14),
                ('RIGHTPADDING',  (0,0), (-1,-1), 14),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.2*cm))

        elif tipo == TIPO_TEXTO:
            texto = el["contenido"]

            # ¿Es resultado final?
            m = RE_RESULT.match(texto.strip())
            if m:
                resultado_final = m.group(1).strip()
                i += 1
                continue

            # ¿Es un paso numerado?
            m = RE_PASO.match(texto.strip())
            if m:
                num_paso += 1
                encabezado = (m.group(3) or f"Parte {num_paso}").replace('**','').strip()

                items_paso = [
                    Paragraph(f"Paso {num_paso}: {_escapar(encabezado)}",
                               estilo["paso_header"])
                ]

                # Consumir elementos siguientes del mismo paso
                j = i + 1
                while j < len(elementos):
                    sig = elementos[j]
                    # Parar si es otro paso, resultado, titulo o subtitulo
                    if sig["tipo"] == TIPO_TEXTO:
                        if RE_PASO.match(sig["contenido"].strip()) or \
                           RE_RESULT.match(sig["contenido"].strip()):
                            break
                    if sig["tipo"] in (TIPO_TITULO, TIPO_SUBTITULO):
                        break

                    if sig["tipo"] == TIPO_FORMULA:
                        png = sig["contenido"]
                        if png:
                            buf = io.BytesIO(png)
                            img = RLImage(buf)
                            max_w2 = W * 0.75
                            if img.drawWidth > max_w2:
                                ratio = max_w2 / img.drawWidth
                                img.drawWidth  = max_w2
                                img.drawHeight = img.drawHeight * ratio
                            items_paso.append(img)
                    elif sig["tipo"] == TIPO_TEXTO:
                        items_paso.append(
                            Paragraph(_escapar(sig["contenido"]), estilo["paso_body"])
                        )
                    elif sig["tipo"] == TIPO_ESPACIO:
                        items_paso.append(Spacer(1, 0.1*cm))
                    j += 1

                i = j  # saltar lo procesado

                t = Table([items_paso], colWidths=[W - cm])
                t.setStyle(TableStyle([
                    ('BACKGROUND',    (0,0), (-1,-1), C_STEP_BG),
                    ('TOPPADDING',    (0,0), (-1,-1), 8),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                    ('LEFTPADDING',   (0,0), (-1,-1), 12),
                    ('RIGHTPADDING',  (0,0), (-1,-1), 12),
                ]))
                story.append(t)
                story.append(Spacer(1, 0.2*cm))
                continue

            else:
                story.append(Paragraph(_escapar(texto), estilo["body"]))

        i += 1

    # ── Resultado final ──
    if resultado_final:
        story.append(Spacer(1, 0.4*cm))
        r_safe = _escapar(resultado_final)
        t = Table([
            [Paragraph("RESULTADO FINAL", estilo["resultado"])],
            [Paragraph(r_safe,            estilo["resultado"])],
        ], colWidths=[W])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), C_GOLD),
            ('TOPPADDING',    (0,0), (-1,-1), 12),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('LEFTPADDING',   (0,0), (-1,-1), 16),
            ('RIGHTPADDING',  (0,0), (-1,-1), 16),
        ]))
        story.append(t)

    doc.build(story, onFirstPage=pie, onLaterPages=pie)
    logger.info(f"[academico] PDF limpio generado: {path}")
    return path


# ═══════════════════════════════════════════════════════════════
# GENERAR ESTRUCTURA ARCHIVOS (Excel / PPTX / Word)
# ═══════════════════════════════════════════════════════════════
async def generar_estructura_archivo(client, tipo, solicitud, perfil):
    """
    Genera JSON estructurado para crear Excel, PPTX o Word.
    Retorna dict o None si falla.
    """
    loop = asyncio.get_event_loop()
    n    = perfil.get("nombre", "")
    c    = perfil.get("carrera", "")
    ctx  = f"Alumno: {n} | {c}" if n or c else ""

    plantillas = {
        "excel": f"""Genera un Excel para: {solicitud}
{ctx}
Responde SOLO JSON valido sin texto extra:
{{"titulo":"...","hojas":[{{"nombre":"...","encabezados":["col1","col2"],"datos":[["v1","v2"]],"formulas":{{"C2":"=A2*B2"}},"totales":true}}]}}""",
        "presentacion": f"""Genera una presentacion para: {solicitud}
{ctx}
Responde SOLO JSON valido sin texto extra:
{{"titulo":"...","slides":[{{"titulo":"...","contenido":["punto 1","punto 2"],"notas":"..."}}]}}
Minimo 6 slides.""",
        "documento": f"""Genera un documento Word para: {solicitud}
{ctx}
Responde SOLO JSON valido sin texto extra:
{{"titulo":"...","secciones":[{{"heading":"...","contenido":"..."}}]}}"""
    }

    prompt = plantillas.get(tipo)
    if not prompt:
        return None

    try:
        raw, modelo = await loop.run_in_executor(
            None,
            lambda: _llamar_fallback(
                client,
                [{"role": "user", "content": prompt}],
                FALLBACK_MEDIO,
                max_tokens=3000
            )
        )
        raw_clean = re.sub(r'^```(?:json)?\n?', '', raw.strip())
        raw_clean = re.sub(r'\n?```$', '', raw_clean.strip())
        return json.loads(raw_clean)
    except Exception as e:
        logger.error(f"[academico] Error estructura {tipo}: {e}")
        return None
