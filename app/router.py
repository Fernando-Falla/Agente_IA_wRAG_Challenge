"""Responde una pregunta en lenguaje natural sobre el inventario.

El modo (inventario vs. politicas) ya lo decide la interfaz al elegir el
endpoint (ver app/main.py); aqui solo se resuelve, dentro del inventario,
que funcion de pandas llamar (categoria, stock minimo, vencimiento o
busqueda por texto). Se usa coincidencia directa contra el propio catalogo
en vez de pedirle al LLM que extraiga el filtro: gemma2:2b no soporta
function/tool calling confiable en Ollama, y para cifras de stock/precio no
conviene que el modelo improvise el argumento de busqueda ni el numero.
"""

import re

import pandas as pd

from app.inventory import (
    get_inventory,
    productos_bajo_stock_minimo,
    productos_por_categoria,
    productos_proximos_a_vencer,
)

STOCK_MINIMO_PATTERN = re.compile(r"bajo\s+(el\s+)?(stock\s+)?m[ií]nimo|falta(n)?\s+stock|agotad", re.IGNORECASE)
VENCIMIENTO_PATTERN = re.compile(r"venc|caduc", re.IGNORECASE)
DIAS_PATTERN = re.compile(r"(\d+)\s*d[ií]as")

STOPWORDS = {
    "que", "cual", "cuales", "cuanto", "cuanta", "cuantos", "cuantas", "hay", "de", "del",
    "la", "el", "los", "las", "en", "un", "una", "para", "por", "con", "es", "son", "tenemos",
    "tiene", "tienen", "stock", "inventario", "producto", "productos", "precio", "sku",
    "categoria", "categoría", "hola", "hoy",
}

COLUMNAS_PRODUCTO = [
    "SKU", "Descripción", "Categoría", "Ubicación", "Stock Actual", "Stock Mínimo",
    "Precio de Venta Unitario",
]


def _extraer_categoria(pregunta: str) -> str | None:
    pregunta_lower = pregunta.lower()
    for categoria in get_inventory()["Categoría"].unique():
        if categoria.lower() in pregunta_lower:
            return categoria
    return None


def _buscar_por_tokens(pregunta: str) -> pd.DataFrame:
    """Productos cuya descripcion comparte palabras significativas con la pregunta."""
    tokens = [t for t in re.findall(r"[a-záéíóúñ]+", pregunta.lower()) if t not in STOPWORDS and len(t) > 2]
    df = get_inventory()
    if not tokens:
        return df.iloc[0:0]

    descripciones = df["Descripción"].str.lower()
    scores = pd.Series(0, index=df.index)
    for token in tokens:
        scores += descripciones.str.contains(token, regex=False).astype(int)

    coincidencias = df[scores > 0].copy()
    coincidencias["_score"] = scores[scores > 0]
    return coincidencias.sort_values("_score", ascending=False).drop(columns="_score")


MENSAJE_SIN_COINCIDENCIAS = (
    "No encontré productos que coincidan con tu pregunta en el inventario. "
    "¿Podrías indicar el nombre exacto o la categoría del producto?"
)


def _formatear_resultados(df: pd.DataFrame, columnas: list[str], limite: int = 5, mensaje_vacio: str | None = None) -> str:
    if df.empty:
        return mensaje_vacio or MENSAJE_SIN_COINCIDENCIAS
    filas = df[columnas].head(limite)
    lineas = [", ".join(f"{col}: {fila[col]}" for col in columnas) for _, fila in filas.iterrows()]
    pie = f"\n(mostrando {limite} de {len(df)} resultados)" if len(df) > limite else ""
    return "\n".join(f"- {linea}" for linea in lineas) + pie


def answer_inventory_question(pregunta: str) -> str:
    if STOCK_MINIMO_PATTERN.search(pregunta):
        resultado = productos_bajo_stock_minimo()
        mensaje_vacio = "Ningún producto está actualmente por debajo de su stock mínimo."
        return "Productos con stock por debajo del mínimo:\n" + _formatear_resultados(
            resultado, COLUMNAS_PRODUCTO, mensaje_vacio=mensaje_vacio
        )

    if VENCIMIENTO_PATTERN.search(pregunta):
        match_dias = DIAS_PATTERN.search(pregunta)
        dias = int(match_dias.group(1)) if match_dias else 30
        resultado = productos_proximos_a_vencer(dias)
        columnas = ["SKU", "Descripción", "Categoría", "Fecha de Vencimiento"]
        mensaje_vacio = f"Ningún producto vence en los próximos {dias} días."
        return f"Productos próximos a vencer (≤ {dias} días):\n" + _formatear_resultados(
            resultado, columnas, limite=10, mensaje_vacio=mensaje_vacio
        )

    categoria = _extraer_categoria(pregunta)
    if categoria:
        resultado = productos_por_categoria(categoria)
        return f"Productos en la categoría '{categoria}':\n" + _formatear_resultados(resultado, COLUMNAS_PRODUCTO, limite=10)

    resultado = _buscar_por_tokens(pregunta)
    return _formatear_resultados(resultado, COLUMNAS_PRODUCTO)


if __name__ == "__main__":
    preguntas = [
        "¿Cuánto stock hay de arroz integral?",
        "¿Qué productos están bajo el stock mínimo?",
        "¿Qué productos de lácteos tenemos?",
        "¿Qué productos vencen en los próximos 60 días?",
        "¿Cuál es el precio del producto MER-005?",
    ]
    for p in preguntas:
        print(f"\nP: {p}")
        print(answer_inventory_question(p))
