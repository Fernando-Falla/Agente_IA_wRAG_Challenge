"""Benchmark comparativo: Recuperacion directa (Bi-Encoder k=6) vs Two-Stage (k=15 -> Cross-Encoder -> k=6).

Mide tiempos de ejecucion, ranking de chunks y calidad de respuesta del LLM.
Requiere requirements-reranker.txt. Es una sola corrida: el tiempo de la primera
pregunta incluye la carga del modelo y los tiempos de generacion varian entre corridas.
"""

import os
import sys
import time
from pathlib import Path

# Asegurar que la raiz del proyecto este en el sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv

load_dotenv()

from app.ingest import load_vectorstore
from app.reranker import rerank_documents
from app.chain import PROMPT, format_docs
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser

PREGUNTAS_BENCHMARK = [
    {
        "id": "robo",
        "categoria": "Prevención de Pérdidas",
        "pregunta": "Vi a un cliente metiendo productos en su bolsa sin pagar. ¿Cuál es el protocolo?",
        "test_llm": True,
    },
    {
        "id": "sismo",
        "categoria": "Emergencias / Seguridad",
        "pregunta": "Acaba de sonar la alerta sísmica, ¿qué debo hacer ahora?",
        "test_llm": True,
    },
    {
        "id": "proveedores",
        "categoria": "Manual de Proveedores",
        "pregunta": "¿Cuál es la clasificación de proveedores?",
        "test_llm": True,
    },
    {
        "id": "surtido",
        "categoria": "Procedimientos Operativos",
        "pregunta": "¿A qué hora debe estar terminado el surtido nocturno?",
        "test_llm": False,
    },
    {
        "id": "peps",
        "categoria": "Operaciones / Calidad",
        "pregunta": "¿Cómo se debe aplicar el sistema PEPS en la sección de lácteos?",
        "test_llm": False,
    },
    {
        "id": "acta",
        "categoria": "Gestión de Personal",
        "pregunta": "¿Cuál es el proceso para levantar un acta administrativa?",
        "test_llm": False,
    },
    {
        "id": "faltas",
        "categoria": "Gestión de Personal (Tablas)",
        "pregunta": "Un empleado ha faltado 3 veces sin justificación en el mes. ¿Qué sanción debo aplicar?",
        "test_llm": False,
    },
]


def run_benchmark():
    print("=" * 80)
    print("INICIANDO BENCHMARK: BASELINE (Bi-Encoder k=6) vs TWO-STAGE RERANKING")
    print("=" * 80)

    print("\n[1/3] Cargando vector store Chroma...")
    vectorstore = load_vectorstore()
    print(f"Vector store cargado ({vectorstore._collection.count()} chunks totales).")

    print("\n[2/3] Configurando LLM (Ollama / gemma2:2b)...")
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "gemma2:2b")
    llm = ChatOllama(model=ollama_model, base_url=ollama_host, temperature=0.2)
    llm_chain = PROMPT | llm | StrOutputParser()

    print("\n[3/3] Ejecutando evaluaciones por pregunta...\n")

    resultados = []

    for item in PREGUNTAS_BENCHMARK:
        p_id = item["id"]
        pregunta = item["pregunta"]
        cat = item["categoria"]
        eval_llm = item.get("test_llm", False)

        print(f"\n>>> Evaluando [{cat}]: '{pregunta}'")

        # --- Baseline: Recuperación directa k=6 ---
        t0 = time.perf_counter()
        docs_baseline = vectorstore.similarity_search(pregunta, k=6)
        t_retrieval_baseline = time.perf_counter() - t0

        # --- Con Reranker: Recuperación amplia k=15 -> Cross-Encoder -> k=6 ---
        t0 = time.perf_counter()
        docs_candidates = vectorstore.similarity_search(pregunta, k=15)
        t_retrieval_candidates = time.perf_counter() - t0

        t0 = time.perf_counter()
        docs_reranked = rerank_documents(pregunta, docs_candidates, top_k=6)
        t_rerank = time.perf_counter() - t0

        # Comparar fuentes y chunks seleccionados
        fuentes_baseline = [Path(d.metadata.get("source", "")).name for d in docs_baseline]
        fuentes_reranked = [Path(d.metadata.get("source", "")).name for d in docs_reranked]

        # Verificar si hay chunks diferentes entre ambos conjuntos
        textos_baseline = {d.page_content[:60] for d in docs_baseline}
        textos_reranked = {d.page_content[:60] for d in docs_reranked}
        diferencias = len(textos_baseline.symmetric_difference(textos_reranked))
        sustituciones = diferencias // 2

        print(f"  - Tiempo retrieval baseline (k=6): {t_retrieval_baseline:.3f} s")
        print(f"  - Tiempo paso Reranker (15 -> 6):  {t_rerank:.3f} s")
        print(f"  - Chunks cambiados en Top 6:       {sustituciones} sustituciones")

        scores_str = ", ".join(f"{d.metadata.get('rerank_score', 0):.2f}" for d in docs_reranked)
        print(f"  - Scores del Cross-Encoder:        [{scores_str}]")

        # Fuentes
        print(f"  - Fuentes Baseline: {set(fuentes_baseline)}")
        print(f"  - Fuentes Reranked: {set(fuentes_reranked)}")

        resp_base = ""
        resp_rerank = ""
        t_llm_base = 0.0
        t_llm_rerank = 0.0

        if eval_llm:
            print("  - Generando respuestas con LLM (gemma2:2b)...")
            # Baseline
            ctx_base = format_docs(docs_baseline)
            t0 = time.perf_counter()
            resp_base = llm_chain.invoke({"context": ctx_base, "question": pregunta})
            t_llm_base = time.perf_counter() - t0

            # Reranked
            ctx_rerank = format_docs(docs_reranked)
            t0 = time.perf_counter()
            resp_rerank = llm_chain.invoke({"context": ctx_rerank, "question": pregunta})
            t_llm_rerank = time.perf_counter() - t0

            print(f"    * LLM Gen Time: Base {t_llm_base:.2f} s | Rerank {t_llm_rerank:.2f} s")
            print(f"    * Resp BASELINE: {resp_base.strip()[:180]}...")
            print(f"    * Resp RERANKED: {resp_rerank.strip()[:180]}...")

        resultados.append({
            "id": p_id,
            "pregunta": pregunta,
            "t_retrieval_baseline": t_retrieval_baseline,
            "t_retrieval_candidates": t_retrieval_candidates,
            "t_rerank": t_rerank,
            "t_llm_base": t_llm_base,
            "t_llm_rerank": t_llm_rerank,
            "sustituciones": sustituciones,
            "resp_base": resp_base.strip(),
            "resp_rerank": resp_rerank.strip(),
        })

    # Resumen final
    avg_rerank_time = sum(r["t_rerank"] for r in resultados) / len(resultados)
    total_sustituciones = sum(r["sustituciones"] for r in resultados)

    print("\n" + "=" * 80)
    print("RESUMEN GENERAL DEL BENCHMARK")
    print("=" * 80)
    print(f"Preguntas evaluadas:                   {len(resultados)}")
    print(f"Tiempo promedio del paso de Reranking: {avg_rerank_time:.3f} s")
    print(f"Total de chunks sustituidos en Top 6:  {total_sustituciones} cambios en {len(resultados)} preguntas")
    print("=" * 80)

    return resultados


if __name__ == "__main__":
    run_benchmark()
