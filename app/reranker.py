"""Modulo de Reranking usando un Cross-Encoder (sentence-transformers).

Implementa la segunda etapa de recuperacion (Two-Stage Retrieval):
1ra etapa (Bi-Encoder): ChromaDB recupera N candidatos con bge-m3.
2da etapa (Cross-Encoder): Este modulo evalua los pares (query, texto)
cruzados con atencion completa para reordenar por relevancia semantica fina
y quedarse con los top K.
"""

import os
from typing import Any
from langchain_core.documents import Document

DEFAULT_RERANKER_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

_cross_encoder_model: Any = None
_loaded_model_name: str | None = None


def get_cross_encoder(model_name: str | None = None):
    """Carga de forma perezosa (lazy loading) y cachea la instancia del CrossEncoder."""
    global _cross_encoder_model, _loaded_model_name
    target_model = model_name or os.getenv("RERANKER_MODEL", DEFAULT_RERANKER_MODEL)

    if _cross_encoder_model is None or _loaded_model_name != target_model:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers no esta instalado. Instalalo con: "
                "pip install -r requirements-reranker.txt"
            ) from exc

        _cross_encoder_model = CrossEncoder(target_model)
        _loaded_model_name = target_model

    return _cross_encoder_model


def rerank_documents(
    query: str,
    documents: list[Document],
    top_k: int = 6,
    model_name: str | None = None,
) -> list[Document]:
    """Reordena una lista de documentos candidatos evaluando su relevancia frente a la query.

    Args:
        query: Pregunta del usuario.
        documents: Documentos candidatos recuperados por el vector store.
        top_k: Numero maximo de documentos a devolver tras el reordenamiento.
        model_name: Nombre o ruta del modelo CrossEncoder (opcional).

    Returns:
        Lista de documentos ordenados descendentemente por score del CrossEncoder,
        con el puntaje guardado en `doc.metadata['rerank_score']`.
    """
    if not documents:
        return []

    # Si hay menos documentos que top_k y solo hay 1, no hace falta reordenar
    if len(documents) <= 1:
        return documents

    model = get_cross_encoder(model_name)
    pairs = [[query, doc.page_content] for doc in documents]
    scores = model.predict(pairs)

    # Asociar documento con su score
    scored_docs: list[tuple[float, Document]] = []
    for doc, score in zip(documents, scores):
        doc_copy = Document(
            page_content=doc.page_content,
            metadata=dict(doc.metadata),
        )
        doc_copy.metadata["rerank_score"] = float(score)
        scored_docs.append((float(score), doc_copy))

    # Ordenar descendente por score
    scored_docs.sort(key=lambda x: x[0], reverse=True)

    return [doc for _, doc in scored_docs[:top_k]]
