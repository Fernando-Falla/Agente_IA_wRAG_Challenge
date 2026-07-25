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

### Despliegue (Docker Compose)

4 contenedores en una sola VM (ver [`docker/docker-compose.yml`](docker/docker-compose.yml) y la guía completa en [`docs/deploy.md`](docs/deploy.md)):

- `ollama` — servidor Ollama (LLM + embeddings), modelos persistidos en volumen.
- `ollama-init` — corre una vez al iniciar, descarga `gemma2:2b` y `bge-m3`, y termina.
- `app` — API FastAPI (`/chat/documentos`, `/chat/inventario`), con `data/` montado como volumen (PDFs, XLSX y el vector store Chroma).
- `ui` — interfaz Streamlit, expuesta públicamente en el puerto 8501.

### Decisiones técnicas relevantes

**Modelo de embeddings: `bge-m3` en vez de `nomic-embed-text`.**
Durante las pruebas locales del Bloque 2, `nomic-embed-text` (el candidato inicial, muy liviano) fallaba en recuperar el contexto correcto para preguntas conversacionales en español. Por ejemplo, ante "Acaba de sonar la alerta sísmica, ¿qué debo hacer ahora?", el retriever traía chunks sobre prevención de pérdidas o seguridad del estacionamiento en vez de la sección 13.3 (Protocolo de Sismo), que sí existe en el documento. Se confirmó con `similarity_search` directo que la búsqueda por palabras clave sueltas ("alerta sísmica sismo") sí encontraba el chunk correcto, pero la frase conversacional completa no — indicando una debilidad semántica del modelo en español, no un problema de chunking. Tras cambiar a `bge-m3` (embeddings multilingües, ~1.2 GB, sigue siendo apto para el límite de 12 GB de OCI), la misma pregunta recuperó el chunk correcto y la cadena completa respondió con precisión. Se repitieron 6 preguntas de prueba (una por cada categoría de ejemplo del proyecto) con resultados correctos.

**Dos endpoints separados (`/chat/documentos` y `/chat/inventario`) en vez de uno con detección automática.**
La primera versión probada localmente tenía un único endpoint `/chat` que decidía con un router por palabras clave (`stock`, `inventario`, `precio`, etc.) si la pregunta era de inventario o de políticas. Al probarlo a mano, la pregunta "¿En qué pasillo se encuentra ubicado el arroz blanco Verde Valle?" cayó, por descarte, en la cadena RAG de los PDFs y respondió de forma confusa: ni "pasillo" ni "ubicado" estaban en la lista de palabras clave (la columna real se llama "Ubicación" en el XLSX). Cualquier lista de keywords tiene ese mismo punto ciego de forma estructural. Se decidió eliminar la detección automática y separar el modo a nivel de endpoint: la interfaz (Bloque 3) le pedirá al usuario elegir entre "preguntar sobre documentos" o "preguntar sobre inventario" — coherente con el diseño de panel lateral de sugerencias ya definido para la UX. El router por palabras clave se conservó, pero reducido a una tarea más acotada y fiable: una vez que ya se sabe que la pregunta es de inventario, decidir qué función de pandas llamar.

**Chunk size 1200/200, `k=6` y system prompt endurecido, tras probar la interfaz.**
Al probar la UI de Streamlit del Bloque 3 aparecieron tres respuestas problemáticas en el modo Documentos. Se investigó cada una inspeccionando directamente los chunks recuperados (no solo la respuesta final):

- *"¿Cuál es la clasificación de proveedores?"* omitía la Categoría B: el chunk con su descripción completa existía en el vector store pero rankeaba #9 por similitud, fuera incluso de un `k=8` de prueba — la sección compacta de categorías A/B/C quedaba fragmentada por el `chunk_size` de 800 caracteres.
- *"Vi a un cliente metiendo productos en su bolsa sin pagar..."* mezclaba el protocolo de robo con el de manejo de producto dañado: el retriever traía un chunk de otro documento (Política de Devoluciones) sin relación con robos, con un score de similitud muy cercano al de los chunks relevantes (sin salto claro que un umbral pudiera filtrar).
- *"Un empleado ha faltado 3 veces..."* respondía la sanción de Reincidencia en vez de Primera Vez, **a pesar de que el chunk recuperado contenía la tabla completa y correcta** — un problema de lectura del modelo, no de recuperación.

Se aplicaron tres mitigaciones: `CHUNK_SIZE` 800→1200 y `CHUNK_OVERLAP` 150→200 (mantiene juntas secciones/listas compactas como la de categorías de proveedores), `k` del retriever 4→6, y un system prompt más explícito sobre ignorar contexto irrelevante y prestar cuidado a filas/columnas de tablas. Al reingestar y volver a probar las 3 preguntas más las 6 ya validadas del Bloque 2 (sin regresiones), el caso de proveedores y el de robo quedaron corregidos. El caso de las 3 faltas **persiste**: `PyPDFLoader` extrae las tablas del PDF como texto corrido sin estructura de filas/columnas, y un modelo de 2B parámetros tiene dificultad real para asociar correctamente la fila y columna que corresponden — ni el prompt ni más contexto lo resuelven. Se documenta como limitación conocida (ver `docs/bitacora-tecnica.md`) y se retiró esa pregunta del panel de sugerencias del Bloque 3, dejando en su lugar la de "acta administrativa" (misma categoría de Gestión de Personal, validada de forma consistente).

**Se mantiene OCI (1 VM consolidada, Pay-As-You-Go) en vez de migrar a Streamlit Cloud/AWS.**
A mitad del Bloque 3, la cuenta OCI Free Tier recibió aviso de suspensión de su período de prueba. Se evaluó migrar a Streamlit Community Cloud y/o recursos gratuitos de AWS, pero ambas alternativas resultaron más limitadas de lo esperado para este proyecto: AWS Free Tier ya no ofrece EC2 permanente (solo 12 meses, 1 GB RAM, y solo para cuentas creadas antes de julio de 2025); Streamlit Community Cloud tiene 1 GB RAM y no soporta correr Ollama. Se decidió mantenerse en OCI: consolidar las 2 instancias `VM.Standard.A1.Flex` en 1 sola (2 OCPU/12 GB Always Free) y cambiar la cuenta a Pay-As-You-Go para evitar la suspensión del trial, permaneciendo dentro de los límites Always Free para no generar cargos. La VM corre Oracle Linux 9, lo que suma dos capas de firewall a considerar además de la Security List de OCI: `firewalld` (activo por defecto) y SELinux (requiere la bandera `:z` en el volumen de `data/` montado en Docker — ver `docker/docker-compose.yml`). Detalle completo en `docs/bitacora-tecnica.md` y `docs/deploy.md`.

## Stack

- **Lenguaje:** Python
- **Framework del agente:** LangChain
- **Lectura de documentos:** PyPDF (PDFs) + pandas (inventario XLSX, consulta estructurada)
- **Embeddings:** bge-m3 (vía Ollama)
- **Vector store:** Chroma
- **LLM:** Gemma (vía Ollama), dockerizado
- **API del agente:** FastAPI + uvicorn
- **Interfaz UX/UI:** Streamlit ("Centy") — chat con panel lateral de sugerencias
- **Deploy:** Docker Compose (Ollama + API + UI) en 1 VM Ampere A1 Always Free (OCI, Oracle Linux 9)

## Ejemplos de preguntas y respuestas

Validado localmente contra `/chat/documentos` (gemma2:2b + bge-m3 + Chroma):

> **P:** ¿A qué hora debe estar terminado el surtido nocturno?
> **R:** El surtido nocturno debe completarse antes de las 05:30 hrs para dar tiempo a la revisión de apertura del turno matutino.

> **P:** Acaba de sonar la alerta sísmica, ¿qué debo hacer ahora?
> **R:** Al sonar la Alerta Sísmica de la CDMX, debes seguir estos pasos: evacuar a los clientes a las zonas de menor riesgo señalizadas, permanecer alejado de ventanas y estantes de producto pesado, y no correr hacia las salidas durante el movimiento — esperar a que el sismo termine.

> **P:** ¿Cuál es el proceso para levantar un acta administrativa?
> **R:** El Supervisor de Área o Jefe de Turno detecta y documenta la falta, se notifica a Recursos Humanos, se cita al colaborador a una entrevista formal donde puede exponer su versión y presentar evidencia, y se elabora el acta (si se niega a firmar, se hace constar ante dos testigos y conserva plena validez).

> **P:** ¿Cuál es la clasificación de proveedores?
> **R:** Categoría A (Estratégicos, alto volumen y relación de largo plazo), Categoría B (Importantes, volumen medio y productos diferenciados) y Categoría C (Complementarios, menor impacto en el volumen total).

> **P:** ¿Cuál es la capital de Francia? *(pregunta fuera de alcance)*
> **R:** Lo siento, pero mi conocimiento se basa en los documentos proporcionados. No tengo información sobre la capital de Francia. Te recomiendo consultar una fuente confiable.

Validado localmente contra `/chat/inventario` (consulta estructurada, sin LLM):

> **P:** ¿En qué pasillo se encuentra ubicado el arroz blanco Verde Valle?
> **R:** SKU: MER-001, Descripción: Arroz Blanco Tipo 1 5kg, Categoría: Abarrotes, Ubicación: Pasillo 1, Stock Actual: 150, Stock Mínimo: 50, Precio de Venta Unitario: 25.9

## Cómo ejecutar el proyecto

### Local (desarrollo)

Requiere Python 3.11 (entorno conda/venv propio) y [Ollama](https://ollama.com) instalado, con los modelos descargados:

```bash
ollama pull gemma2:2b
ollama pull bge-m3
pip install -r requirements.txt
cp .env.example .env

python -m app.ingest          # construye el vector store (una vez, o cuando cambien los PDFs)

# Terminal 1 — API
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — interfaz
streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501
```

Abrir `http://127.0.0.1:8501`.

### En la nube (OCI, producción)

Todo el stack (Ollama + API + interfaz) corre dockerizado en una sola VM Ampere A1 Always Free. Ver la guía completa, con todos los comandos, en [`docs/deploy.md`](docs/deploy.md):

```bash
cd docker
docker compose up -d --build
docker compose exec app python -m app.ingest
```

## Evidencia del deploy

_(Enlace o captura pendiente)_
