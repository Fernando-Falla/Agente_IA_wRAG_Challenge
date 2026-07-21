"""Consultas estructuradas sobre el inventario XLSX via pandas.

Estas funciones no pasan por el vector store ni por el LLM: operan directamente
sobre el DataFrame, siguiendo la decision de arquitectura de mantener el
inventario como consulta estructurada separada del RAG sobre los PDFs.
"""

import pandas as pd

from app.loaders import load_inventory

_inventory_df: pd.DataFrame | None = None


def get_inventory() -> pd.DataFrame:
    """Devuelve el DataFrame del inventario, cacheado en memoria tras la primera carga."""
    global _inventory_df
    if _inventory_df is None:
        _inventory_df = load_inventory()
    return _inventory_df


def buscar_producto(nombre: str) -> pd.DataFrame:
    """Productos cuya descripcion contiene `nombre` (busqueda parcial, sin distinguir mayusculas)."""
    df = get_inventory()
    return df[df["Descripción"].str.contains(nombre, case=False, na=False)]


def productos_por_categoria(categoria: str) -> pd.DataFrame:
    """Productos cuya categoria contiene `categoria` (busqueda parcial)."""
    df = get_inventory()
    return df[df["Categoría"].str.contains(categoria, case=False, na=False)]


def productos_bajo_stock_minimo() -> pd.DataFrame:
    """Productos cuyo Stock Actual esta por debajo de su Stock Minimo definido."""
    df = get_inventory()
    return df[df["Stock Actual"] < df["Stock Mínimo"]]


def productos_proximos_a_vencer(dias: int = 30) -> pd.DataFrame:
    """Productos cuya Fecha de Vencimiento cae dentro de los proximos `dias` (o ya vencidos)."""
    df = get_inventory()
    fechas_vencimiento = pd.to_datetime(df["Fecha de Vencimiento"], errors="coerce")
    limite = pd.Timestamp.now().normalize() + pd.Timedelta(days=dias)
    return df[fechas_vencimiento <= limite]


if __name__ == "__main__":
    print("Categorias disponibles:", sorted(get_inventory()["Categoría"].unique()))
    print("\nProductos con 'arroz' en la descripcion:")
    print(buscar_producto("arroz")[["SKU", "Descripción", "Stock Actual", "Stock Mínimo"]])
    print(f"\nProductos bajo stock minimo: {len(productos_bajo_stock_minimo())}")
    print(f"Productos que vencen en los proximos 60 dias: {len(productos_proximos_a_vencer(60))}")
