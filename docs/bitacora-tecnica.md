# Bitácora técnica — Agente de IA para Documentos Internos

Registro de hallazgos, pruebas y decisiones tomadas durante el desarrollo del proyecto, organizado por bloque de trabajo. Complementa al README (que documenta la arquitectura final) con el detalle de *por qué* se llegó a cada decisión — importante para la trazabilidad del proyecto.

---

## Bloque 1 — Preparación y datos base

**Entorno de trabajo.** Se creó un entorno conda dedicado (`agente_rag`, Python 3.11) y se instaló Ollama localmente con los modelos `gemma2:2b` (generación) y, más adelante, `bge-m3` (embeddings).

**Hallazgo — AVG Antivirus bloqueaba la instalación.** La creación del entorno conda fallaba con un error de verificación SSL (`CondaSSLError`). Se diagnosticó que AVG Antivirus intercepta el tráfico HTTPS para escanearlo ("AVG Web/Mail Shield"), y su certificado raíz no estaba en el bundle de confianza (`certifi`) que usan conda y pip. Se resolvió exportando el certificado raíz de AVG desde el almacén de Windows y combinándolo con el bundle de certifi, sin desactivar el antivirus.

**Datos verificados.** Los 4 PDFs de origen (Reglamento Interno, Manual de Proveedores, Política de Atención al Cliente, FAQ) son de texto plano — 124 páginas en total, sin tablas embebidas como imágenes. El inventario XLSX contiene 200 filas × 18 columnas en 8 categorías.

---

## Bloque 2 — Agente RAG

**Hallazgo — `nomic-embed-text` fallaba en español conversacional.** Fernando validó localmente la cadena RAG con preguntas de ejemplo del propio proyecto. Ante "Acaba de sonar la alerta sísmica, ¿qué debo hacer ahora?", el retriever devolvía contenido irrelevante (prevención de pérdidas, seguridad de estacionamiento) en lugar de la sección 13.3 (Protocolo de Sismo), que sí existe en el documento. Se confirmó con `similarity_search` directo que una búsqueda por palabras clave sueltas ("alerta sísmica sismo") sí encontraba el chunk correcto, pero la frase conversacional completa no — apuntando a una debilidad semántica del modelo de embeddings en español, no a un problema de chunking.

**Decisión: cambiar a `bge-m3`** (embeddings multilingües, ~1.2 GB, compatible con el límite de 12 GB de OCI). Tras el cambio, las mismas preguntas recuperaron el contexto correcto. Se validaron 6 preguntas de prueba (una por cada categoría de ejemplo del proyecto) con resultados correctos.

**Construcción de `app/inventory.py` y `app/router.py`** para las consultas estructuradas sobre el inventario (pandas), separadas del RAG sobre los PDFs.

**Hallazgo — un solo endpoint `/chat` con detección automática no era confiable.** Fernando probó manualmente vía Swagger UI la pregunta "¿En qué pasillo se encuentra ubicado el arroz blanco Verde Valle?". La pregunta cayó, por descarte, en la cadena RAG de los PDFs (respuesta confusa), porque ni "pasillo" ni "ubicado" estaban en la lista de palabras clave del router (la columna real en el XLSX se llama "Ubicación"). Se concluyó que cualquier lista de keywords tiene ese mismo punto ciego de forma estructural.

**Decisión: separar en dos endpoints explícitos** — `/chat/documentos` (siempre RAG) y `/chat/inventario` (siempre pandas) — eliminando la detección automática. El usuario elige el modo desde la interfaz, no un heurístico. Se aprovechó para agregar la columna `Ubicación` a las respuestas de inventario, que faltaba.

---

## Bloque 3 — Interfaz UX/UI

**Decisión de infraestructura (imprevista).** A mitad del Bloque 3, Fernando fue notificado de que su cuenta OCI Free Tier sería suspendida el 30 de julio de 2026. Se evaluó como alternativa migrar a Streamlit Community Cloud y/o recursos gratuitos de AWS. Al revisar las limitaciones reales de esas alternativas (AWS Free Tier: solo 1 GB RAM y únicamente 12 meses para cuentas creadas después de julio de 2025, ya no permanente; Streamlit Community Cloud: 1 GB RAM, no soporta correr Ollama; Hugging Face Spaces: correr un Space con Docker requiere plan de pago), **Fernando decidió mantenerse en OCI**: consolidar sus 2 instancias `VM.Standard.A1.Flex` en 1 sola (2 OCPU/12 GB Always Free) y cambiar la cuenta a Pay-As-You-Go para evitar la suspensión del trial, permaneciendo dentro de los límites Always Free para no generar cargos. Esta decisión confirma sin cambios el plan original de despliegue del CLAUDE.md (una sola VM, un solo `docker-compose` con Ollama + app).

**Decisión de framework de UI: Streamlit.** Se aclaró una confusión inicial: Streamlit (la librería) no depende de Streamlit Community Cloud (el servicio de hosting) — corre como un contenedor más en el mismo `docker-compose`, 100% autoalojado en la VM de OCI. Su huella de memoria (~100-200 MB) es marginal frente a los varios GB que usa Ollama+Gemma.

**Nombre del asistente: Centy.** Definido por Fernando en este punto, según lo previsto por el CLAUDE.md.

**Construcción de `ui/app.py`**: chat con panel lateral de sugerencias (recomendado fuertemente por el CLAUDE.md para usuarios no técnicos) y selector explícito de modo (Documentos / Inventario), consistente con la decisión de los dos endpoints separados.

**Verificación visual.** Fernando probó la interfaz en el navegador y la calificó como "sobria y muy intuitiva".

---

## Hallazgos de calidad en las respuestas (pruebas de Fernando sobre el modo Documentos)

Tras la verificación visual, Fernando probó las preguntas sugeridas del panel y reportó tres respuestas problemáticas. Cada una se investigó a fondo inspeccionando directamente los chunks recuperados por el vector store (no solo la respuesta final del LLM), para distinguir problemas de *recuperación* de problemas de *generación*.

### 1. "Un empleado ha faltado 3 veces sin justificación en el mes. ¿Qué sanción debo aplicar?"

- **Síntoma:** el agente respondía "suspensión temporal de 3 a 7 días" (columna *Reincidencia* de la tabla de sanciones), cuando lo correcto es "amonestación escrita con acta" (columna *Primera Vez*, ya que se trata de la primera vez que ocurre esta falta grave en particular).
- **Diagnóstico:** se confirmó que el retriever sí recupera el chunk con la tabla completa de sanciones (Primera Vez / Reincidencia / Reincidencia Grave). El problema no es de recuperación.
- **Causa raíz:** `PyPDFLoader` extrae las tablas del PDF como texto corrido, sin separadores de fila/columna. Un modelo de 2B parámetros tiene dificultad para reconstruir correctamente qué valor corresponde a qué combinación de fila y columna a partir de ese texto aplanado. Es una limitación de razonamiento del modelo frente a tablas mal estructuradas tras la extracción, no un problema del pipeline de recuperación.

### 2. "Vi a un cliente metiendo productos en su bolsa sin pagar. ¿Cuál es el protocolo?"

- **Síntoma:** la respuesta mezclaba el protocolo de robo con la idea de "aislar el producto en el anaquel", algo incoherente con el procedimiento real.
- **Diagnóstico:** entre los 4 chunks recuperados, 3 eran correctos (Reglamento Interno, secciones 11.2-11.5 sobre robo), pero el cuarto provenía de **otro documento** (Política de Atención al Cliente y Devoluciones, sección 6.2 "Protocolo de Retiro Inmediato de Góndola" — sobre productos dañados/no conformes, sin relación con robos).
- **Causa raíz:** colisión semántica entre dos documentos distintos que comparten vocabulario superficial ("protocolo", "producto", "retiro"). Se verificaron los scores de similitud de los 6 mejores resultados (0.84, 0.89, 0.92, 0.94, 0.95, 0.96): no hay un salto claro entre los chunks relevantes y el irrelevante, por lo que un umbral fijo de corte no sería una solución confiable de forma general. El modelo pequeño termina mezclando el contexto irrelevante en la respuesta en lugar de descartarlo.

### 3. "¿Cuál es la clasificación de proveedores?"

- **Síntoma:** la respuesta mencionaba las categorías A y C, omitiendo la B.
- **Diagnóstico:** se confirmó que el chunk con la descripción completa de la Categoría B existe en el vector store, pero ocupa el **puesto #9** por similitud (score 0.8291) — justo fuera de `k=4`, e incluso fuera de un `k=8` probado explícitamente.
- **Causa raíz:** la sección "5.1 Descripción de Categorías" (A, B y C) es compacta pero el `chunk_size` de 800 caracteres la fragmentó en varios chunks solapados. El chunk con el encabezado y la descripción completa de la Categoría B quedó, por azares de la segmentación, con una similitud menor a la de sus chunks vecinos (que contienen fragmentos de A y C), aunque tratan exactamente el mismo tema.

## Cambios decididos a partir de estos hallazgos

- **`CHUNK_SIZE` de 800 a 1200 caracteres** (`CHUNK_OVERLAP` de 150 a 200), para reducir la fragmentación de secciones/listas compactas como la de categorías de proveedores.
- **`k` del retriever de 4 a 6**, para mejorar el recall general.
- **Endurecimiento del system prompt**: instrucción explícita de ignorar fragmentos de contexto irrelevantes para la pregunta, no mezclar procedimientos de secciones o documentos distintos, y prestar especial cuidado al leer tablas con múltiples columnas.

## Resultado tras aplicar los cambios

Se reingestó el vector store (302 chunks, antes 433) y se volvieron a probar los 3 casos reportados más las 6 preguntas ya validadas del Bloque 2, para descartar regresiones.

- **Caso proveedores (Categoría B faltante): corregido.** La respuesta ahora incluye las 3 categorías completas.
- **Caso robo ("aislar el producto"): corregido.** La respuesta ya no mezcla el protocolo de robo con el de producto dañado; es coherente con el reglamento.
- **Caso de las 3 faltas: persiste.** El agente sigue respondiendo la sanción de *Reincidencia* en vez de *Primera Vez*, a pesar de que el chunk recuperado contiene la tabla completa y correcta, y a pesar del prompt endurecido. Se confirma que es una limitación de lectura de tablas del modelo (no de recuperación) que estas mitigaciones no alcanzan a resolver.
- Las 6 preguntas previamente validadas del Bloque 2 se mantuvieron correctas — sin regresiones.

**Limitación conocida que persiste.** La extracción de tablas de `PyPDFLoader` pierde la estructura de filas/columnas del PDF original. Un modelo de 2B parámetros puede tener dificultad para interpretar correctamente una tabla aplanada a texto, especialmente cuando debe distinguir entre columnas semánticamente parecidas (Primera Vez vs. Reincidencia). Una solución más robusta —reformatear las tablas explícitamente durante la ingesta usando una librería con detección de tablas (p. ej. `unstructured` o `pdfplumber`)— queda fuera de alcance por ahora y se documenta aquí como limitación conocida y candidata a un trabajo futuro, dado el compromiso del proyecto con modelos pequeños y cuantizados por la restricción de recursos de OCI. Como consecuencia práctica, se retiró la pregunta de las 3 faltas del panel de sugerencias de la interfaz (Bloque 3), dejando en su lugar la de "acta administrativa" (misma categoría de Gestión de Personal, validada de forma consistente).
