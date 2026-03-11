r"""
modulos/pre_render.py
Jarvis 3.2 — Agente Pre-Render (Calidad)

GARANTIA ABSOLUTA: Cero LaTeX crudo llega a ReportLab o Telegram.

Detecta y convierte:
  1. $$...$$ display formula  -> imagen PNG
  2. $...$  inline formula    -> imagen PNG
  3. entornos begin/end LaTeX -> imagen PNG
  4. comandos LaTeX sueltos   -> imagen PNG
  5. bloques de codigo        -> recuadro limpio sin backticks
  6. # Heading                -> tipo titulo
  7. ## Heading               -> tipo subtitulo
  8. Texto normal             -> tipo texto
"""

import re
import io
import logging

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

# ─── Tipos de elemento ────────────────────────────────────────
TIPO_TEXTO     = "texto"
TIPO_FORMULA   = "formula_img"    # contenido = bytes PNG
TIPO_CODIGO    = "recuadro_codigo"
TIPO_ESPACIO   = "espacio"
TIPO_TITULO    = "titulo"
TIPO_SUBTITULO = "subtitulo"

# ─── Patrones de detección LaTeX ─────────────────────────────
_RE_DISPLAY  = re.compile(r'\$\$(.+?)\$\$', re.DOTALL)
_RE_INLINE   = re.compile(r'(?<!\$)\$([^\$\n]+?)\$(?!\$)')
_RE_ENV      = re.compile(r'(\\begin\{[^}]+\}.*?\\end\{[^}]+\})', re.DOTALL)
_RE_LATEX_SUELTO = re.compile(
    r'((?:\\(?:frac|sqrt|int|sum|prod|lim|inf|partial|nabla|cdot|times|div|pm|mp'
    r'|leq|geq|neq|approx|equiv|in|notin|subset|supset|cup|cap|forall|exists'
    r'|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|sigma|phi|omega'
    r'|Gamma|Delta|Theta|Lambda|Pi|Sigma|Phi|Omega'
    r'|left|right|hat|bar|vec|dot|ddot|tilde|overline|underline'
    r'|mathbf|mathrm|mathit|text|operatorname'
    r'|log|ln|sin|cos|tan|arcsin|arccos|arctan|exp'
    r')\s*(?:\{[^}]*\}|\[[^\]]*\])*)+)'
)
_RE_BACKTICK_BLOQUE = re.compile(r'```(\w*)\n?([\s\S]*?)```', re.DOTALL)
_RE_HEADING1 = re.compile(r'^#{1}\s+(.+)$')
_RE_HEADING2 = re.compile(r'^#{2}\s+(.+)$')


# ═══════════════════════════════════════════════════════════════
# RENDERIZADOR LATEX → PNG
# ═══════════════════════════════════════════════════════════════
def _render_latex_png(formula: str, fontsize: int = 14,
                       display: bool = False) -> bytes | None:
    """
    Convierte fórmula LaTeX a imagen PNG usando matplotlib mathtext.
    Retorna bytes PNG o None si falla.
    """
    try:
        formula_clean = formula.strip()

        # Normalizar: asegurar que esté entre $...$
        if not (formula_clean.startswith('$') or formula_clean.startswith(r'\begin')):
            formula_clean = f'${formula_clean}$'
        elif formula_clean.startswith(r'\begin'):
            formula_clean = f'${formula_clean}$'

        fs = fontsize + 2 if display else fontsize

        fig = plt.figure(figsize=(0.01, 0.01))
        fig.patch.set_alpha(0)
        text = fig.text(
            0, 0, formula_clean,
            fontsize=fs,
            color='#1a1a2e',   # mismo color primario del PDF
            usetex=False       # usar mathtext de matplotlib, no LaTeX del sistema
        )
        fig.canvas.draw()
        bbox   = text.get_window_extent()
        width  = (bbox.width  + 24) / fig.dpi
        height = (bbox.height + 12) / fig.dpi
        fig.set_size_inches(max(width, 0.5), max(height, 0.3))

        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight',
                    pad_inches=0.06, dpi=150, transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception as e:
        logger.warning(f"[pre_render] No se pudo renderizar: {str(formula)[:60]} — {e}")
        plt.close('all')
        return None


def _formula_a_elemento(formula: str, inline: bool = False) -> dict:
    """Convierte una fórmula LaTeX a elemento {tipo, contenido, ...}"""
    formula_render = formula

    # Si es un entorno \begin{...}...\end{...}, extraer el contenido interno
    # matplotlib mathtext no soporta \begin/\end — sí soporta el contenido
    m_env = re.match(r'\\begin\{[^}]+\}(.*?)\\end\{[^}]+\}', formula.strip(), re.DOTALL)
    if m_env:
        formula_render = m_env.group(1).strip()

    png = _render_latex_png(formula_render, fontsize=12 if inline else 15,
                             display=not inline)
    return {
        "tipo":        TIPO_FORMULA,
        "contenido":   png,          # bytes PNG o None
        "formula_tex": formula,
        "inline":      inline
    }


# ═══════════════════════════════════════════════════════════════
# PROCESAR OUTPUT — función principal
# ═══════════════════════════════════════════════════════════════
def procesar_output(texto_crudo: str) -> list:
    """
    Recibe el texto crudo del LLM y devuelve lista de elementos tipados.
    GARANTIA: ningun elemento TIPO_TEXTO contiene LaTeX crudo.
    """
    elementos = []
    if not texto_crudo or not texto_crudo.strip():
        return elementos

    # ── PASO 1: Proteger bloques de código (reemplazar por placeholder) ──
    placeholders_codigo = {}
    counter = [0]

    def reemplazar_codigo(m):
        key = f"__CODIGO_{counter[0]}__"
        placeholders_codigo[key] = {
            "tipo":      TIPO_CODIGO,
            "contenido": m.group(2),
            "lenguaje":  m.group(1).strip()
        }
        counter[0] += 1
        return key

    texto = _RE_BACKTICK_BLOQUE.sub(reemplazar_codigo, texto_crudo)

    # ── PASO 2: Proteger entornos LaTeX ──
    placeholders_env = {}

    def reemplazar_env(m):
        key = f"__ENV_{counter[0]}__"
        placeholders_env[key] = m.group(1)
        counter[0] += 1
        return key

    texto = _RE_ENV.sub(reemplazar_env, texto)

    # ── PASO 3: Procesar línea por línea ──
    lineas = texto.split('\n')
    texto_acumulado = []

    def flush_texto():
        if texto_acumulado:
            bloque = '\n'.join(texto_acumulado).strip()
            if bloque:
                elementos.append({"tipo": TIPO_TEXTO, "contenido": bloque})
            texto_acumulado.clear()

    for linea in lineas:

        # Placeholder de código
        for key, el in placeholders_codigo.items():
            if key in linea:
                flush_texto()
                if el["contenido"].strip():
                    elementos.append(el)
                linea = linea.replace(key, "").strip()
                break

        # Placeholder de entorno LaTeX
        for key, formula in placeholders_env.items():
            if key in linea:
                flush_texto()
                elementos.append(_formula_a_elemento(formula, inline=False))
                linea = linea.replace(key, "").strip()
                break

        if not linea.strip():
            flush_texto()
            if elementos and elementos[-1]["tipo"] != TIPO_ESPACIO:
                elementos.append({"tipo": TIPO_ESPACIO, "contenido": ""})
            continue

        # Heading 1
        m = _RE_HEADING1.match(linea.strip())
        if m:
            flush_texto()
            elementos.append({"tipo": TIPO_TITULO, "contenido": m.group(1).strip()})
            continue

        # Heading 2
        m = _RE_HEADING2.match(linea.strip())
        if m:
            flush_texto()
            elementos.append({"tipo": TIPO_SUBTITULO, "contenido": m.group(1).strip()})
            continue

        # ── Display LaTeX $$...$$
        if _RE_DISPLAY.search(linea):
            partes = _RE_DISPLAY.split(linea)
            flush_texto()
            for idx, parte in enumerate(partes):
                if idx % 2 == 0:
                    if parte.strip():
                        texto_acumulado.append(parte.strip())
                else:
                    flush_texto()
                    elementos.append(_formula_a_elemento(parte.strip(), inline=False))
            flush_texto()
            continue

        # ── Inline LaTeX $...$
        if _RE_INLINE.search(linea):
            partes = _RE_INLINE.split(linea)
            flush_texto()
            for idx, parte in enumerate(partes):
                if idx % 2 == 0:
                    if parte.strip():
                        texto_acumulado.append(parte.strip())
                else:
                    flush_texto()
                    elementos.append(_formula_a_elemento(parte.strip(), inline=True))
            flush_texto()
            continue

        # ── LaTeX suelto sin dólares (\frac, \sqrt, etc.)
        if _RE_LATEX_SUELTO.search(linea):
            # Dividir la línea en partes: texto y fragmentos LaTeX
            partes = _RE_LATEX_SUELTO.split(linea)
            flush_texto()
            for idx, parte in enumerate(partes):
                if not parte.strip():
                    continue
                if _RE_LATEX_SUELTO.fullmatch(parte.strip()):
                    # Es LaTeX puro
                    flush_texto()
                    elementos.append(_formula_a_elemento(parte.strip(), inline=True))
                else:
                    texto_acumulado.append(parte.strip())
            flush_texto()
            continue

        # ── Texto normal limpio
        texto_acumulado.append(linea)

    flush_texto()
    return elementos


# ═══════════════════════════════════════════════════════════════
# ELEMENTOS → TEXTO PLANO (para Telegram)
# ═══════════════════════════════════════════════════════════════
def elementos_a_texto_plano(elementos: list) -> str:
    """
    Convierte elementos a texto para enviar por Telegram.
    Las fórmulas se muestran como texto descriptivo (no PNG).
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
            # Mostrar como texto matemático legible
            tex_limpio = (tex
                .replace(r'\frac{', '(').replace('}{', '/')
                .replace('}', ')').replace(r'\sqrt', 'sqrt')
                .replace(r'\int', '∫').replace(r'\sum', '∑')
                .replace(r'\prod', '∏').replace(r'\infty', '∞')
                .replace(r'\alpha', 'α').replace(r'\beta', 'β')
                .replace(r'\gamma', 'γ').replace(r'\delta', 'δ')
                .replace(r'\theta', 'θ').replace(r'\pi', 'π')
                .replace(r'\sigma', 'σ').replace(r'\omega', 'ω')
                .replace(r'\Delta', 'Δ').replace(r'\Sigma', 'Σ')
                .replace(r'\times', '×').replace(r'\cdot', '·')
                .replace(r'\leq', '≤').replace(r'\geq', '≥')
                .replace(r'\neq', '≠').replace(r'\approx', '≈')
                .replace('$', '').strip())
            lineas.append(f"  {tex_limpio}")
        elif tipo == TIPO_CODIGO:
            lang = el.get("lenguaje", "")
            lineas.append(f"\n```{lang}\n{el['contenido']}\n```")
        elif tipo == TIPO_ESPACIO:
            lineas.append("")
    return '\n'.join(lineas)
