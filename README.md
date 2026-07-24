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
- `app/router.py` — dentro del modo inventario, decide qué función de `app/inventory.py` llamar (categoría, stock mínimo, vencimiento o búsqueda por texto) por coincidencia directa contra el propio catálogo.
- `app/main.py` — API (FastAPI). Scaffold de pruebas locales por ahora; se formaliza en el Bloque 3-4.

### Endpoints de la API

| Método | Ruta               | Descripción                                                                 |
|--------|---------------------|------------------------------------------------------------------------------|
| GET    | `/health`           | Chequeo de que la API está arriba.                                           |
| POST   | `/chat/documentos`  | Preguntas sobre políticas y procedimientos. `{"pregunta": str}` → cadena RAG (Chroma + Gemma). |
| POST   | `/chat/inventario`  | Preguntas sobre el inventario. `{"pregunta": str}` → consulta estructurada con pandas (nunca inventa cifras). |

Ambos devuelven `{"respuesta": str}`.

### Decisiones técnicas relevantes

**Modelo de embeddings: `bge-m3` en vez de `nomic-embed-text`.**
Durante las pruebas locales del Bloque 2, `nomic-embed-text` (el candidato inicial, muy liviano) fallaba en recuperar el contexto correcto para preguntas conversacionales en español. Por ejemplo, ante "Acaba de sonar la alerta sísmica, ¿qué debo hacer ahora?", el retriever traía chunks sobre prevención de pérdidas o seguridad del estacionamiento en vez de la sección 13.3 (Protocolo de Sismo), que sí existe en el documento. Se confirmó con `similarity_search` directo que la búsqueda por palabras clave sueltas ("alerta sísmica sismo") sí encontraba el chunk correcto, pero la frase conversacional completa no — indicando una debilidad semántica del modelo en español, no un problema de chunking. Tras cambiar a `bge-m3` (embeddings multilingües, ~1.2 GB, sigue siendo apto para el límite de 12 GB de OCI), la misma pregunta recuperó el chunk correcto y la cadena completa respondió con precisión. Se repitieron 6 preguntas de prueba (una por cada categoría de ejemplo del proyecto) con resultados correctos.

**Dos endpoints separados (`/chat/documentos` y `/chat/inventario`) en vez de uno con detección automática.**
La primera versión probada localmente tenía un único endpoint `/chat` que decidía con un router por palabras clave (`stock`, `inventario`, `precio`, etc.) si la pregunta era de inventario o de políticas. Al probarlo a mano, la pregunta "¿En qué pasillo se encuentra ubicado el arroz blanco Verde Valle?" cayó, por descarte, en la cadena RAG de los PDFs y respondió de forma confusa: ni "pasillo" ni "ubicado" estaban en la lista de palabras clave (la columna real se llama "Ubicación" en el XLSX). Cualquier lista de keywords tiene ese mismo punto ciego de forma estructural. Se decidió eliminar la detección automática y separar el modo a nivel de endpoint: la interfaz (Bloque 3) le pedirá al usuario elegir entre "preguntar sobre documentos" o "preguntar sobre inventario" — coherente con el diseño de panel lateral de sugerencias ya definido para la UX. El router por palabras clave se conservó, pero reducido a una tarea más acotada y fiable: una vez que ya se sabe que la pregunta es de inventario, decidir qué función de pandas llamar.

## Stack

- **Lenguaje:** Python
- **Framework del agente:** LangChain
- **Lectura de documentos:** PyPDF (PDFs) + pandas (inventario XLSX, consulta estructurada)
- **Embeddings:** bge-m3 (vía Ollama)
- **Vector store:** Chroma
- **LLM:** Gemma (vía Ollama), dockerizado
- **Deploy:** Docker + OCI Compute (Always Free Ampere A1)

## Ejemplos de preguntas y respuestas

Validado localmente contra `/chat/documentos` (gemma2:2b + bge-m3 + Chroma):

> **P:** ¿A qué hora debe estar terminado el surtido nocturno?
> **R:** El surtido nocturno debe completarse antes de las 05:30 hrs para dar tiempo a la revisión de apertura del turno matutino.

> **P:** Acaba de sonar la alerta sísmica, ¿qué debo hacer ahora?
> **R:** Al sonar la Alerta Sísmica de la CDMX, debes seguir estos pasos: evacuar a los clientes a las zonas de menor riesgo señalizadas, permanecer alejado de ventanas y estantes de producto pesado, y no correr hacia las salidas durante el movimiento — esperar a que el sismo termine.

> **P:** Un empleado ha faltado 3 veces sin justificación en el mes, ¿qué sanción aplico?
> **R:** De acuerdo con la política disciplinaria, se aplicará una amonestación escrita con acta (falta grave, primera vez).

> **P:** ¿Cuál es la capital de Francia? *(pregunta fuera de alcance)*
> **R:** Lo siento, pero mi conocimiento se basa en los documentos proporcionados. No tengo información sobre la capital de Francia. Te recomiendo consultar una fuente confiable.

Validado localmente contra `/chat/inventario` (consulta estructurada, sin LLM):

> **P:** ¿En qué pasillo se encuentra ubicado el arroz blanco Verde Valle?
> **R:** SKU: MER-001, Descripción: Arroz Blanco Tipo 1 5kg, Categoría: Abarrotes, Ubicación: Pasillo 1, Stock Actual: 150, Stock Mínimo: 50, Precio de Venta Unitario: 25.9

## Cómo ejecutar el proyecto

_(Instrucciones pendientes — local y en la nube)_

## Evidencia del deploy

_(Enlace o captura pendiente)_
