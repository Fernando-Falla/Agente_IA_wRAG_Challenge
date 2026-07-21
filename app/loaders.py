"""Carga de las dos fuentes de datos del agente: PDFs de politicas/procedimientos
(via LangChain + PyPDFLoader) y el inventario XLSX (via pandas, consulta estructurada)."""

from pathlib import Path

import pandas as pd
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

PDFS_DIR = Path(__file__).resolve().parent.parent / "data" / "pdfs"
INVENTARIO_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "inventario"
    / "inventario_de_supermercado_latam.xlsx"
)


def load_pdf_documents(pdfs_dir: Path = PDFS_DIR) -> list[Document]:
    """Carga todos los PDF de `pdfs_dir` y devuelve una lista de Document (uno por pagina)."""
    documents: list[Document] = []
    for pdf_path in sorted(pdfs_dir.glob("*.pdf")):
        loader = PyPDFLoader(str(pdf_path))
        documents.extend(loader.load())
    return documents


def load_inventory(path: Path = INVENTARIO_PATH) -> pd.DataFrame:
    """Carga el inventario XLSX como DataFrame para consultas estructuradas (no pasa por RAG)."""
    return pd.read_excel(path)


if __name__ == "__main__":
    docs = load_pdf_documents()
    print(f"PDFs cargados: {len(docs)} paginas totales")
    fuentes = sorted({Path(d.metadata["source"]).name for d in docs})
    for fuente in fuentes:
        paginas = sum(1 for d in docs if Path(d.metadata["source"]).name == fuente)
        print(f"  - {fuente}: {paginas} paginas")
    print(f"\nEjemplo de contenido (primera pagina de '{fuentes[0]}'):")
    print(docs[0].page_content[:300].strip(), "...")

    df = load_inventory()
    print(f"\nInventario cargado: {df.shape[0]} filas x {df.shape[1]} columnas")
    print("Columnas:", list(df.columns))
    print(f"Categorias: {df['Categoría'].nunique()} -> {sorted(df['Categoría'].unique())}")
    print(f"Productos con stock por debajo del minimo: {(df['Stock Actual'] < df['Stock Mínimo']).sum()}")
