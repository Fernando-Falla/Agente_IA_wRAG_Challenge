# Agente de IA para Documentos Internos

Agente de inteligencia artificial (RAG) que responde preguntas en lenguaje natural sobre documentos internos de una empresa (PDF), sin necesidad de abrirlos manualmente.

## Arquitectura

Pipeline del agente:

```
PDFs (data/pdfs/)  ──► PyPDFLoader ──► chunking (RecursiveCharacterTextSplitter,
                                        800 caract. / 150 de solape)
                                              │
                                              ▼
                                   Embeddings (Ollama: bge-m3)
                                              │
                                              ▼
                                     Vector store (Chroma)
                                              │
Pregunta del usuario ──► retriever (top-k) ──┤
                                              ▼
                          Prompt + contexto recuperado ──► Gemma (Ollama) ──► Respuesta

Inventario XLSX (data/inventario/) ──► pandas ──► consulta estructurada directa
                                                    (no pasa por el vector store)
```

- `app/loaders.py` — carga de PDFs (`PyPDFLoader`) e inventario (`pandas.read_excel`).
- `app/ingest.py` — chunking, generación de embeddings y persistencia en Chroma.
- `app/inventory.py` — consultas estructuradas sobre el inventario (búsqueda por producto/categoría, stock bajo mínimo, próximos a vencer).
- `app/chain.py` — cadena de recuperación + generación (RAG) sobre las políticas, usando Chroma como retriever y Gemma (vía Ollama) como generador.

### Decisiones técnicas relevantes

**Modelo de embeddings: `bge-m3` en vez de `nomic-embed-text`.**
Durante las pruebas locales del Bloque 2, `nomic-embed-text` (el candidato inicial, muy liviano) fallaba en recuperar el contexto correcto para preguntas conversacionales en español. Por ejemplo, ante "Acaba de sonar la alerta sísmica, ¿qué debo hacer ahora?", el retriever traía chunks sobre prevención de pérdidas o seguridad del estacionamiento en vez de la sección 13.3 (Protocolo de Sismo), que sí existe en el documento. Se confirmó con `similarity_search` directo que la búsqueda por palabras clave sueltas ("alerta sísmica sismo") sí encontraba el chunk correcto, pero la frase conversacional completa no — indicando una debilidad semántica del modelo en español, no un problema de chunking. Tras cambiar a `bge-m3` (embeddings multilingües, ~1.2 GB, sigue siendo apto para el límite de 12 GB de OCI), la misma pregunta recuperó el chunk correcto y la cadena completa respondió con precisión. Se repitieron 6 preguntas de prueba (una por cada categoría de ejemplo del proyecto) con resultados correctos.

## Stack

- **Lenguaje:** Python
- **Framework del agente:** LangChain
- **Lectura de documentos:** PyPDF (PDFs) + pandas (inventario XLSX, consulta estructurada)
- **Embeddings:** bge-m3 (vía Ollama)
- **Vector store:** Chroma
- **LLM:** Gemma (vía Ollama), dockerizado
- **Deploy:** Docker + OCI Compute (Always Free Ampere A1)

## Ejemplos de preguntas y respuestas

_(Se agregarán ejemplos reales una vez el agente esté funcionando)_

## Cómo ejecutar el proyecto

_(Instrucciones pendientes — local y en la nube)_

## Evidencia del deploy

_(Enlace o captura pendiente)_
