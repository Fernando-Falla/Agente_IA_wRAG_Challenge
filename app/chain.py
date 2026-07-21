"""Cadena de recuperacion + generacion (RAG) sobre los PDFs de politicas y procedimientos,
usando Chroma como retriever y Gemma (via Ollama) como modelo generador.
"""

import os

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama

from app.ingest import load_vectorstore

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")

SYSTEM_PROMPT = (
    "Eres un asistente virtual para la empresa Mercado Central 24h. Tu objetivo es "
    "ayudar a resolver dudas sobre politicas, procedimientos y productos. Tus "
    "respuestas deben ser claras, concisas y estar basadas exclusivamente en la "
    "informacion de los documentos proporcionados. Si no sabes la respuesta, dilo "
    "amablemente y sugiere contactar al area de Recursos Humanos o Atencion al "
    "Cliente. No inventes informacion. Tu tono debe ser profesional y servicial."
)

PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "Documentos internos relevantes:\n{context}\n\nPregunta: {question}"),
    ]
)


def format_docs(docs) -> str:
    return "\n\n---\n\n".join(doc.page_content for doc in docs)


def build_rag_chain(k: int = 4):
    """Arma la cadena LCEL: retriever -> prompt -> LLM -> texto de respuesta."""
    vectorstore = load_vectorstore()
    retriever = vectorstore.as_retriever(search_kwargs={"k": k})
    llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_HOST, temperature=0.2)

    return (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
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
