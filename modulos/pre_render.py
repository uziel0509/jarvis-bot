"""
modulos/pre_render.py
Jarvis 3.1 — Agente Pre-Render
Convierte output del LLM a elementos tipados para ReportLab.
Reglas:
  - NUNCA pasa LaTeX crudo a ReportLab
  - Fórmulas LaTeX → imagen PNG vía matplotlib
  - Código → recuadro limpio sin backticks
  - Output = lista de {tipo, contenido}
"""

import re
import io
import base64
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.mathtext as mathtext

logger = logging.getLogger(__name__)

# ─── Tipos de elemento ────────────────────────────────────────
TIPO_TEXTO      = "texto"
TIPO_FORMULA    = "formula_img"   # contenido = bytes PNG
TIPO_CODIGO     = "recuadro_codigo"
TIPO_ESPACIO    = "espacio"
TIPO_TITULO     = "titulo"
TIPO_SUBTITULO  = "subtitulo"


# ─── Detector de LaTeX ────────────────────────────────────────
_RE_DISPLAY = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)
_RE_INLINE  = re.compile(r'(?<!\$)\$([^\$]+?)\$(?!\$)')
_RE_ENV     = re.compile(r'(\\begin\{[^}]+\}.*?\\end\{[^}]+\})', re.DOTALL)
_RE_BLOQUE_CODIGO = re.compile(r'```(\w*)\n?([\s\S]*?)```', re.DOTALL)
_RE_HEADING1 = re.compile(r'^# (.+)$', re.MULTILINE)
_RE_HEADING2 = re.compile(r'^## (.+)$', re.MULTILINE)


def _render_latex_a_png(formula: str, fontsize: int = 14) -> bytes | None:
    """Renderiza una fórmula LaTeX a PNG usando matplotlib. Retorna bytes o None."""
    try:
        formula_clean = formula.strip()
        # Asegurarse que esté envuelta en $...$
        if not formula_clean.startswith('$'):
            formula_clean = f'${formula_clean}$'

        fig = plt.figure(figsize=(0.01, 0.01))
        fig.patch.set_alpha(0)

        text = fig.text(
            0, 0, formula_clean,
            fontsize=fontsize,
            color='black',
            usetex=False
        )

        fig.canvas.draw()
        bbox = text.get_window_extent()
        width  = (bbox.width  + 20) / fig.dpi
        height = (bbox.height + 10) / fig.dpi
        fig.set_size_inches(max(width, 1), max(height, 0.3))

        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight',
                    pad_inches=0.05, dpi=150, transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.warning(f"No se pudo renderizar fórmula: {formula[:50]} — {e}")
        plt.close('all')
        return None


def procesar_output(texto_crudo: str) -> list:
    """
    Procesa el output del LLM y retorna lista de elementos tipados.
    Returns:
        Lista de dicts: [{"tipo": "texto"|"formula_img"|"recuadro_codigo"|"espacio", "contenido": ...}]
    """
    elementos = []
    if not texto_crudo:
        return elementos

    lineas = texto_crudo.split('\n')
    en_bloque_codigo = False
    codigo_acumulado = []
    lenguaje_codigo = ""
    texto_acumulado = []

    def _flush_texto():
        if texto_acumulado:
            bloque = '\n'.join(texto_acumulado).strip()
            if bloque:
                elementos.append({"tipo": TIPO_TEXTO, "contenido": bloque})
            texto_acumulado.clear()

    i = 0
    while i < len(lineas):
        linea = lineas[i]

        # ── Inicio bloque código
        if linea.strip().startswith('```'):
            _flush_texto()
            en_bloque_codigo = True
            lenguaje_codigo = linea.strip()[3:].strip()
            codigo_acumulado = []
            i += 1
            continue

        # ── Fin bloque código
        if en_bloque_codigo:
            if linea.strip() == '```':
                en_bloque_codigo = False
                codigo = '\n'.join(codigo_acumulado)
                if codigo.strip():
                    elementos.append({
                        "tipo": TIPO_CODIGO,
                        "contenido": codigo,
                        "lenguaje": lenguaje_codigo
                    })
                codigo_acumulado = []
            else:
                codigo_acumulado.append(linea)
            i += 1
            continue

        # ── Heading 1
        m = _RE_HEADING1.match(linea)
        if m:
            _flush_texto()
            elementos.append({"tipo": TIPO_TITULO, "contenido": m.group(1)})
            i += 1
            continue

        # ── Heading 2
        m = _RE_HEADING2.match(linea)
        if m:
            _flush_texto()
            elementos.append({"tipo": TIPO_SUBTITULO, "contenido": m.group(1)})
            i += 1
            continue

        # ── Línea vacía → espacio
        if not linea.strip():
            _flush_texto()
            # Solo agregar espacio si el último elemento no es ya un espacio
            if elementos and elementos[-1]["tipo"] != TIPO_ESPACIO:
                elementos.append({"tipo": TIPO_ESPACIO, "contenido": ""})
            i += 1
            continue

        # ── Detectar fórmulas LaTeX en la línea
        # Display: $$...$$
        m_display = _RE_DISPLAY.search(linea)
        if m_display:
            # Texto antes de la fórmula
            antes = linea[:m_display.start()].strip()
            if antes:
                texto_acumulado.append(antes)
                _flush_texto()

            formula = m_display.group(1).strip()
            png = _render_latex_a_png(formula, fontsize=16)
            if png:
                elementos.append({"tipo": TIPO_FORMULA, "contenido": png, "formula_tex": formula})
            else:
                texto_acumulado.append(f"[Fórmula: {formula}]")
                _flush_texto()

            despues = linea[m_display.end():].strip()
            if despues:
                texto_acumulado.append(despues)
            i += 1
            continue

        # Inline: $...$
        if _RE_INLINE.search(linea):
            # Convertir todo inline LaTeX en imágenes pequeñas o texto plano
            partes = _RE_INLINE.split(linea)
            _flush_texto()
            for j, parte in enumerate(partes):
                if j % 2 == 0:  # texto normal
                    if parte.strip():
                        texto_acumulado.append(parte)
                else:  # fórmula inline
                    png = _render_latex_a_png(parte.strip(), fontsize=12)
                    if png:
                        _flush_texto()
                        elementos.append({"tipo": TIPO_FORMULA, "contenido": png,
                                          "formula_tex": parte, "inline": True})
                    else:
                        texto_acumulado.append(f"[{parte}]")
            _flush_texto()
            i += 1
            continue

        # ── Línea normal → acumular texto
        texto_acumulado.append(linea)
        i += 1

    # Flush final
    if en_bloque_codigo and codigo_acumulado:
        elementos.append({
            "tipo": TIPO_CODIGO,
            "contenido": '\n'.join(codigo_acumulado),
            "lenguaje": lenguaje_codigo
        })
    _flush_texto()

    return elementos


def elementos_a_texto_plano(elementos: list) -> str:
    """
    Convierte lista de elementos a texto plano para enviar por Telegram.
    Las fórmulas se representan como texto descriptivo.
    """
    lineas = []
    for el in elementos:
        tipo = el["tipo"]
        if tipo == TIPO_TEXTO:
            lineas.append(el["contenido"])
        elif tipo == TIPO_TITULO:
            lineas.append(f"\n*{el['contenido']}*")
        elif tipo == TIPO_SUBTITULO:
            lineas.append(f"\n_{el['contenido']}_")
        elif tipo == TIPO_FORMULA:
            tex = el.get("formula_tex", "fórmula")
            lineas.append(f"[📐 {tex}]")
        elif tipo == TIPO_CODIGO:
            lang = el.get("lenguaje", "")
            lineas.append(f"\n```{lang}\n{el['contenido']}\n```")
        elif tipo == TIPO_ESPACIO:
            lineas.append("")
    return '\n'.join(lineas)
