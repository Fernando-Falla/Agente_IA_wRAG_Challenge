"""API del agente. Expone dos endpoints de chat separados: uno para politicas
(RAG sobre los PDFs) y otro para inventario (consulta estructurada con pandas).

NOTA: este archivo sigue siendo un scaffold provisional para probar la API en
localhost via Swagger UI (/docs). Se revisa/formaliza en el Bloque 3-4 cuando
se conecte la interfaz UX/UI.

Por que dos endpoints en vez de uno con deteccion automatica: un router por
palabras clave siempre tiene huecos (ej. una pregunta sobre en que pasillo
esta un producto no menciona "stock" ni "inventario" y termina cayendo, por
descarte, en la cadena RAG de los PDFs). Separar el modo a nivel de interfaz
(el usuario elige si pregunta sobre documentos o sobre inventario) elimina
esa ambiguedad de raiz.

Endpoints:
    GET  /health           -> chequeo simple de que la API esta arriba.
    POST /chat/documentos  -> recibe {"pregunta": str}, responde con la cadena
                              RAG (Chroma + Gemma via Ollama) sobre los PDFs
                              de politicas y procedimientos.
    POST /chat/inventario  -> recibe {"pregunta": str}, responde con consulta
                              estructurada sobre el inventario XLSX (pandas).
                              El texto de la pregunta solo se usa para elegir
                              que funcion de pandas llamar (categoria, stock
                              minimo, vencimiento, busqueda por texto); los
                              datos siempre vienen del DataFrame, nunca del LLM.
"""

import os

from fastapi import FastAPI
from pydantic import BaseModel

from app.chain import build_rag_chain
from app.router import answer_inventory_question

app = FastAPI(title="Agente IA - Mercado Central 24h")

_rag_chain = None


def get_chain():
    global _rag_chain
    if _rag_chain is None:
        _rag_chain = build_rag_chain()
    return _rag_chain


class Pregunta(BaseModel):
    pregunta: str


class Respuesta(BaseModel):
    respuesta: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat/documentos", response_model=Respuesta)
def chat_documentos(payload: Pregunta) -> Respuesta:
    """Preguntas sobre politicas y procedimientos (RAG sobre los PDFs)."""
    respuesta = get_chain().invoke(payload.pregunta)
    return Respuesta(respuesta=respuesta)


@app.post("/chat/inventario", response_model=Respuesta)
def chat_inventario(payload: Pregunta) -> Respuesta:
    """Preguntas sobre el inventario (consulta estructurada con pandas)."""
    return Respuesta(respuesta=answer_inventory_question(payload.pregunta))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("APP_PORT", "8000")), reload=True)
