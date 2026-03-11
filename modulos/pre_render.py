"""
CAPA 4 — Agente Pre-Render
Jarvis 3.0

Responsabilidad única: recibir el output crudo del modelo solucionador
y convertirlo en elementos limpios y tipados que ReportLab puede renderizar
SIN LaTeX crudo, SIN bloques de código con backticks, SIN símbolos raros.

Reglas absolutas:
  1. NUNCA pasar LaTeX crudo a ReportLab → siempre renderizar a imagen PNG
  2. NUNCA incluir bloques ``` en el PDF
  3. Código Python/MATLAB → pseudocódigo en texto plano o recuadro limpio
  4. Toda fórmula matemática → imagen PNG via matplotlib/sympy
  5. Output = lista de elementos tipados {tipo, contenido}
"""
import re
import io
import os
import base64
import tempfile
from pathlib import Path
from typing import List, Dict

# matplotlib para renderizar fórmulas
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.mathtext
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False

ARCHIVOS_DIR = Path(os.getenv("ARCHIVOS_DIR", "/root/jarvis/archivos"))


# ── Tipos de elementos ──────────────────────────────────────────────────────
# Cada elemento tiene: {"tipo": str, "contenido": any}
# tipos: "texto", "formula_img", "tabla", "recuadro_codigo", "espacio"


def limpiar_texto_simple(texto: str) -> str:
    """Elimina caracteres de markdown que no deben ir en el PDF."""
    texto = re.sub(r'\*\*(.+?)\*\*', r'', texto)   # **bold** → bold
    texto = re.sub(r'\*(.+?)\*',   r'', texto)      # *italic* → italic
    texto = re.sub(r'#{1,6}\s*',   '',    texto)       # headers
    texto = re.sub(r'`([^`]+)`',   r'', texto)       # `inline code`
    return texto.strip()


def latex_a_imagen(formula: str, font_size: int = 14) -> bytes | None:
    """
    Convierte una fórmula LaTeX a imagen PNG en bytes.
    Retorna None si falla.
    """
    if not MATPLOTLIB_OK:
        return None
    try:
        formula_limpia = formula.strip().strip("$")
        fig, ax = plt.subplots(figsize=(6, 1))
        ax.axis("off")
        ax.text(
            0.5, 0.5,
            f"${formula_limpia}$",
            fontsize=font_size,
            ha="center", va="center",
            transform=ax.transAxes
        )
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight",
                    dpi=150, transparent=True)
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception:
        plt.close("all")
        return None


def _es_bloque_codigo(linea: str) -> bool:
    return linea.strip().startswith("```")


def _es_latex_inline(texto: str) -> bool:
    return bool(re.search(r'\$[^$]+\$|\$\$[^$]+\$\$|\frac|\sum|\int|\begin\{', texto))


def _extraer_formulas_latex(texto: str) -> list:
    """Extrae todas las fórmulas LaTeX de un texto."""
    formulas = []
    # $$...$$ display
    formulas += re.findall(r'\$\$(.+?)\$\$', texto, re.DOTALL)
    # $...$ inline
    formulas += re.findall(r'\$([^$
]+?)\$', texto)
    # egin{...}...nd{...}
    formulas += re.findall(r'(\begin\{[^}]+\}.*?\end\{[^}]+\})', texto, re.DOTALL)
    return formulas


def procesar_output(texto_crudo: str, user_id: int = 0) -> List[Dict]:
    """
    Función principal. Recibe el texto crudo del modelo y retorna
    una lista de elementos listos para ReportLab.

    Returns:
        Lista de dicts: [{"tipo": "texto"|"formula_img"|"recuadro_codigo"|"espacio", "contenido": ...}]
    """
    elementos = []
    lineas = texto_crudo.split("
")
    en_bloque_codigo = False
    codigo_acumulado = []
    lenguaje_codigo = ""

    i = 0
    while i < len(lineas):
        linea = lineas[i]

        # ── Detectar inicio de bloque de código ```
        if _es_bloque_codigo(linea) and not en_bloque_codigo:
            en_bloque_codigo = True
            lenguaje_codigo = linea.strip().replace("```", "").strip()
            codigo_acumulado = []
            i += 1
            continue

        # ── Detectar fin de bloque de código ```
        if _es_bloque_codigo(linea) and en_bloque_codigo:
            en_bloque_codigo = False
            codigo_txt = "
".join(codigo_acumulado)
            # Convertir a pseudocódigo si es Python/MATLAB, sino recuadro limpio
            elementos.append({
                "tipo": "recuadro_codigo",
                "contenido": codigo_txt,
                "lenguaje": lenguaje_codigo or "código"
            })
            codigo_acumulado = []
            i += 1
            continue

        # ── Dentro de bloque de código
        if en_bloque_codigo:
            codigo_acumulado.append(linea)
            i += 1
            continue

        # ── Línea vacía → espacio
        if linea.strip() == "":
            elementos.append({"tipo": "espacio", "contenido": ""})
            i += 1
            continue

        # ── Línea con LaTeX → renderizar como imagen
        if _es_latex_inline(linea):
            formulas = _extraer_formulas_latex(linea)
            # Texto antes de la fórmula (si hay)
            texto_limpio = re.sub(
                r'\$\$.*?\$\$|\$.*?\$|\begin\{.*?\end\{[^}]+\}',
                '', linea, flags=re.DOTALL
            ).strip()
            if texto_limpio:
                elementos.append({"tipo": "texto", "contenido": limpiar_texto_simple(texto_limpio)})

            for formula in formulas:
                img_bytes = latex_a_imagen(formula)
                if img_bytes:
                    elementos.append({"tipo": "formula_img", "contenido": img_bytes})
                else:
                    # Fallback: texto plano sin símbolos
                    formula_txt = formula.replace("\frac", "/").replace("\cdot", "×")
                    elementos.append({"tipo": "texto", "contenido": f"[ {formula_txt} ]"})
            i += 1
            continue

        # ── Línea normal de texto
        elementos.append({"tipo": "texto", "contenido": limpiar_texto_simple(linea)})
        i += 1

    return elementos


def elementos_a_texto_plano(elementos: List[Dict]) -> str:
    """
    Convierte la lista de elementos a texto plano legible.
    Útil para debug o para Telegram (donde no hay PDF).
    """
    partes = []
    for el in elementos:
        t = el["tipo"]
        if t == "texto":
            partes.append(el["contenido"])
        elif t == "formula_img":
            partes.append("[Fórmula matemática]")
        elif t == "recuadro_codigo":
            partes.append(f"[{el.get('lenguaje','Código')}]
{el['contenido']}")
        elif t == "espacio":
            partes.append("")
    return "
".join(partes)


def prompt_prerender_para_modelo(texto_sucio: str) -> str:
    """
    Prompt para que el modelo 70b limpie su propio output antes del PDF.
    Úsalo cuando el output del 120b llegue con LaTeX/markdown mezclado.
    """
    return f"""Tienes este texto con fórmulas matemáticas y posiblemente bloques de código.
Necesito que lo reescribas para un documento PDF profesional.

Reglas ESTRICTAS:
1. Escribe las fórmulas matemáticas en LaTeX puro, encerradas en $...$ o $$...$$
2. NO uses bloques de código con backticks (```). Si hay código, conviértelo a pseudocódigo en texto plano
3. NO uses markdown (no ** para negrita, no # para títulos)
4. Sé claro, ordenado y paso a paso
5. Mantén toda la información importante del original

Texto original:
{texto_sucio}

Texto limpio para PDF:"""
