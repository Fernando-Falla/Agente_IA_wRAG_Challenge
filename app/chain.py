"""Cadena de recuperacion + generacion (RAG) sobre los PDFs de politicas y procedimientos,
usando Chroma como retriever, reordenamiento opcional con Cross-Encoder y Gemma (via Ollama) como modelo generador.
"""

import os

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama

from app.ingest import load_vectorstore
from app.reranker import rerank_documents

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")
ENABLE_RERANKER = os.getenv("ENABLE_RERANKER", "false").lower() in ("true", "1", "yes")
RERANKER_INITIAL_K = int(os.getenv("RERANKER_INITIAL_K", "15"))
RERANKER_TOP_K = int(os.getenv("RERANKER_TOP_K", "6"))

SYSTEM_PROMPT = (
    "Te llamas Centy y eres el asistente virtual de la empresa Mercado Central 24h. "
    "Tu objetivo es ayudar a resolver dudas sobre politicas, procedimientos y "
    "productos. Tus "
    "respuestas deben ser claras, concisas y estar basadas exclusivamente en la "
    "informacion de los documentos proporcionados. Si no sabes la respuesta, dilo "
    "amablemente y sugiere contactar al area de Recursos Humanos o Atencion al "
    "Cliente. No inventes informacion. Tu tono debe ser profesional y servicial.\n\n"
    "Los documentos internos que recibes como contexto vienen recuperados "
    "automaticamente y pueden incluir fragmentos de secciones o documentos que NO "
    "tienen relacion con la pregunta: ignora por completo cualquier fragmento que no "
    "aplique directamente, y nunca mezcles procedimientos de situaciones distintas "
    "(por ejemplo, no combines el protocolo de robo con el de manejo de producto "
    "danado). Si el contexto incluye una tabla con varias columnas (por ejemplo "
    "Primera Vez / Reincidencia / Reincidencia Grave), identifica con cuidado a que "
    "fila y columna corresponde la situacion descrita antes de responder."
)

PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "Documentos internos relevantes:\n{context}\n\nPregunta: {question}"),
    ]
)


def format_docs(docs) -> str:
    return "\n\n---\n\n".join(doc.page_content for doc in docs)


def build_rag_chain(k: int = 6, use_reranker: bool | None = None):
    """Arma la cadena LCEL: retriever (con o sin reranker) -> prompt -> LLM -> texto de respuesta.

    Sin reranker se recuperan `k` fragmentos. Con reranker se recuperan RERANKER_INITIAL_K
    candidatos y se pasan RERANKER_TOP_K al LLM.
    """
    vectorstore = load_vectorstore()
    apply_reranker = ENABLE_RERANKER if use_reranker is None else use_reranker

    if apply_reranker:
        def context_retriever(query: str) -> str:
            candidates = vectorstore.similarity_search(query, k=RERANKER_INITIAL_K)
            ranked_docs = rerank_documents(query, candidates, top_k=RERANKER_TOP_K)
            return format_docs(ranked_docs)

        context_runnable = context_retriever
    else:
        retriever = vectorstore.as_retriever(search_kwargs={"k": k})
        context_runnable = retriever | format_docs

    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_HOST, temperature=0.2)

    return (
        {"context": context_runnable, "question": RunnablePassthrough()}
        | PROMPT
        | llm
        | StrOutputParser()
    )


if __name__ == "__main__":
    chain = build_rag_chain()
    preguntas_de_prueba = [
        "¿A qué hora debe estar terminado el surtido nocturno?",
        "¿Cómo se debe aplicar el sistema PEPS en la sección de lácteos?",
        "Acaba de sonar la alerta sísmica, ¿qué debo hacer ahora?",
        "¿Cuál es el proceso para levantar un acta administrativa?",
    ]
    for pregunta in preguntas_de_prueba:
        print(f"\nP: {pregunta}")
        print(f"R: {chain.invoke(pregunta)}")
