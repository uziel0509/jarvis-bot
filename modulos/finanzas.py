"""
MÓDULO 5 — Asistente Financiero Personal
Jarvis 3.0 — Solo registra, aconseja y alerta. NO da consejos de inversión.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

PERFILES_DIR = Path(os.getenv("PERFILES_DIR", "/root/jarvis/perfiles"))


def _path(user_id: int) -> Path:
    return PERFILES_DIR / str(user_id) / "finanzas.json"


def _cargar(user_id: int) -> dict:
    p = _path(user_id)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {
        "ingresos": [],
        "gastos": [],
        "limite_mensual": 0,
        "pagos_recurrentes": [],
    }


def _guardar(user_id: int, data: dict):
    p = _path(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Registros ──────────────────────────────────────────────────────────────

def registrar_gasto(user_id: int, monto: float, categoria: str, descripcion: str = "") -> str:
    data = _cargar(user_id)
    data["gastos"].append({
        "monto": monto,
        "categoria": categoria,
        "descripcion": descripcion,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    _guardar(user_id, data)

    mes = datetime.now().strftime("%Y-%m")
    total_mes = sum(g["monto"] for g in data["gastos"] if g["fecha"].startswith(mes))

    alerta = ""
    if data["limite_mensual"] > 0 and total_mes > data["limite_mensual"]:
        alerta = f"
⚠️ *Alerta:* Superaste tu límite de S/ {data['limite_mensual']:.2f}"
    elif data["limite_mensual"] > 0 and total_mes > data["limite_mensual"] * 0.8:
        alerta = f"
⚠️ Ya usaste el 80% de tu límite mensual (S/ {data['limite_mensual']:.2f})"

    return (
        f"✅ Gasto registrado: *S/ {monto:.2f}* en {categoria}
"
        f"💸 Total gastado este mes: S/ {total_mes:.2f}"
        f"{alerta}"
    )


def registrar_ingreso(user_id: int, monto: float, descripcion: str = "") -> str:
    data = _cargar(user_id)
    data["ingresos"].append({
        "monto": monto,
        "descripcion": descripcion,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    _guardar(user_id, data)
    return f"✅ Ingreso registrado: *S/ {monto:.2f}*"


def configurar_limite(user_id: int, limite: float) -> str:
    data = _cargar(user_id)
    data["limite_mensual"] = limite
    _guardar(user_id, data)
    return f"✅ Límite mensual configurado: S/ {limite:.2f}"


def agregar_pago_recurrente(user_id: int, nombre: str, monto: float, dia_mes: int) -> str:
    data = _cargar(user_id)
    data["pagos_recurrentes"].append({"nombre": nombre, "monto": monto, "dia_mes": dia_mes})
    _guardar(user_id, data)
    return f"✅ Pago recurrente: *{nombre}* — S/ {monto:.2f} cada día {dia_mes}"


# ── Resúmenes ───────────────────────────────────────────────────────────────

def resumen_mensual(user_id: int) -> str:
    data = _cargar(user_id)
    mes = datetime.now().strftime("%Y-%m")
    gastos_mes  = [g for g in data["gastos"]   if g["fecha"].startswith(mes)]
    ingresos_mes = [i for i in data["ingresos"] if i["fecha"].startswith(mes)]

    total_gastos   = sum(g["monto"] for g in gastos_mes)
    total_ingresos = sum(i["monto"] for i in ingresos_mes)
    balance = total_ingresos - total_gastos

    # Categorías
    cats: dict = {}
    for g in gastos_mes:
        cats[g["categoria"]] = cats.get(g["categoria"], 0) + g["monto"]
    cat_txt = "
".join(
        f"  • {c}: S/ {m:.2f}" for c, m in sorted(cats.items(), key=lambda x: -x[1])
    ) or "  Sin gastos registrados"

    estado = "🟢 Positivo" if balance >= 0 else "🔴 Negativo"

    # Proyección fin de mes
    proyeccion = ""
    dia = datetime.now().day
    if total_gastos > 0 and data["limite_mensual"] > 0 and dia > 0:
        proy = (total_gastos / dia) * 30
        if proy > data["limite_mensual"]:
            proyeccion = f"
⚠️ *Proyección:* gastarás ~S/ {proy:.2f} este mes (límite: S/ {data['limite_mensual']:.2f})"

    return (
        f"📊 *Resumen Financiero — {datetime.now().strftime('%B %Y')}*

"
        f"💰 Ingresos: S/ {total_ingresos:.2f}
"
        f"💸 Gastos:   S/ {total_gastos:.2f}
"
        f"📈 Balance:  S/ {balance:.2f} ({estado})

"
        f"*Por categoría:*
{cat_txt}"
        f"{proyeccion}"
    )


def check_pagos_hoy(user_id: int) -> str:
    """Retorna string con pagos recurrentes de hoy, o vacío si no hay."""
    data = _cargar(user_id)
    hoy = datetime.now().day
    pagos = [p for p in data["pagos_recurrentes"] if p["dia_mes"] == hoy]
    if not pagos:
        return ""
    lista = "
".join(f"  • {p['nombre']}: S/ {p['monto']:.2f}" for p in pagos)
    return f"🔔 *Pagos recurrentes de hoy:*
{lista}"


def prompt_interpretar_finanzas(texto: str) -> str:
    """Prompt para que el orquestador extraiga intención financiera del texto."""
    return f"""El estudiante envió este mensaje relacionado con sus finanzas:
"{texto}"

Determina la intención y extrae los datos. Responde SOLO en JSON:
{{
  "intencion": "registrar_gasto|registrar_ingreso|ver_resumen|configurar_limite|agregar_pago_recurrente|consulta_general",
  "monto": null,
  "categoria": null,
  "descripcion": null,
  "limite": null,
  "nombre_pago": null,
  "dia_mes": null
}}
Si no puedes extraer un campo, ponlo como null."""
