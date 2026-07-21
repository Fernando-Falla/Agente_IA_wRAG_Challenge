"""Chunking, embeddings (Ollama) y persistencia en Chroma del contenido de los PDFs.

El inventario XLSX no pasa por aqui: se consulta directamente con pandas (ver
`app.inventory`), conforme a la decision de arquitectura del proyecto.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.loaders import load_pdf_documents

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_PERSIST_DIR = BASE_DIR / os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "bge-m3")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
COLLECTION_NAME = "politicas_mercado_central"


def get_embeddings() -> OllamaEmbeddings:
    return OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_HOST)


def build_vectorstore(persist_directory: Path = CHROMA_PERSIST_DIR) -> Chroma:
    """Carga los PDFs, los divide en chunks y persiste sus embeddings en Chroma."""
    documents = load_pdf_documents()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)

    return Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        persist_directory=str(persist_directory),
        collection_name=COLLECTION_NAME,
    )


def load_vectorstore(persist_directory: Path = CHROMA_PERSIST_DIR) -> Chroma:
    """Abre el vector store ya persistido, sin volver a generar embeddings."""
    return Chroma(
        embedding_function=get_embeddings(),
        persist_directory=str(persist_directory),
        collection_name=COLLECTION_NAME,
    )


if __name__ == "__main__":
    vectorstore = build_vectorstore()
    total_chunks = vectorstore._collection.count()
    print(f"Vector store creado en '{CHROMA_PERSIST_DIR}' con {total_chunks} chunks.")
