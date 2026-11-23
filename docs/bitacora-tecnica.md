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

**Decisión de infraestructura (imprevista).** A mitad del Bloque 3, Fernando fue notificado de que su cuenta OCI Free Tier sería suspendida el 30 de julio de 2026. Se evaluó como alternativa migrar a Streamlit Community Cloud y/o recursos gratuitos de AWS. Al revisar las limitaciones reales de esas alternativas (AWS Free Tier: solo 1 GB RAM y únicamente 12 meses para cuentas creadas después de julio de 2025, ya no permanente; Streamlit Community Cloud: 1 GB RAM, no soporta correr Ollama; Hugging Face Spaces: correr un Space con Docker requiere plan de pago), **Fernando decidió mantenerse en OCI**: consolidar sus 2 instancias `VM.Standard.A1.Flex` en 1 sola (2 OCPU/12 GB Always Free) y cambiar la cuenta a Pay-As-You-Go para evitar la suspensión del trial, permaneciendo dentro de los límites Always Free para no generar cargos. Esta decisión mantiene sin cambios el plan original de despliegue (una sola VM, un solo `docker-compose` con Ollama + app).

**Decisión de framework de UI: Streamlit.** Se aclaró una confusión inicial: Streamlit (la librería) no depende de Streamlit Community Cloud (el servicio de hosting) — corre como un contenedor más en el mismo `docker-compose`, 100% autoalojado en la VM de OCI. Su huella de memoria (~100-200 MB) es marginal frente a los varios GB que usa Ollama+Gemma.

**Nombre del asistente: Centy.** Definido por Fernando en este punto.

**Construcción de `ui/app.py`**: chat con panel lateral de sugerencias (pensado para usuarios no técnicos) y selector explícito de modo (Documentos / Inventario), consistente con la decisión de los dos endpoints separados.

---

## Hallazgos de calidad en las respuestas (pruebas de Fernando sobre el modo Documentos)

Tras construir la interfaz, Fernando probó las preguntas sugeridas del panel y reportó tres respuestas problemáticas. Cada una se investigó a fondo inspeccionando directamente los chunks recuperados por el vector store (no solo la respuesta final del LLM), para distinguir problemas de *recuperación* de problemas de *generación*.

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

---

## Bloque 4 — Docker / Deploy

**Confirmación de infraestructura.** Fernando confirmó la consolidación de las 2 instancias `VM.Standard.A1.Flex` en 1 sola (2 OCPU/12 GB Always Free), cuenta en modo Pay-As-You-Go, y que el sistema operativo de la VM es **Oracle Linux 9** (no Ubuntu, que era la suposición inicial más común). Esto cambió los comandos de instalación de Docker (`dnf` en vez de `apt`) y añadió dos consideraciones que no aplicarían en Ubuntu:

- **`firewalld`**, activo por defecto en Oracle Linux, bloquea el puerto 8501 además de la Security List/NSG de la VCN — hay que abrirlo en ambas capas.
- **SELinux**, activo por defecto (enforcing), puede bloquear el bind mount de `data/` hacia el contenedor `app` si no se etiqueta correctamente. Se agregó la bandera `:z` al volumen en `docker/docker-compose.yml` (`../data:/app/data:z`) para que Docker relabele automáticamente el directorio.

**Arquitectura de despliegue: 4 servicios en un solo `docker-compose.yml`.** `ollama` (servidor, modelos en volumen nombrado), `ollama-init` (contenedor de una sola pasada que hace `ollama pull gemma2:2b` y `ollama pull bge-m3` contra el servidor, vía `OLLAMA_HOST`, y termina), `app` (FastAPI, con `data/` — PDFs, XLSX y el vector store Chroma — montado como volumen desde el host) y `ui` (Streamlit, expuesto públicamente en el 8501). El build de la imagen se hace en la propia VM (ARM64/aarch64), no de forma cruzada desde Windows.

**No se pudo probar el build/arranque de Docker en esta máquina** (no hay Docker instalado localmente en el entorno de desarrollo de Fernando) — se validó la sintaxis del `docker-compose.yml` con un parser YAML, pero la prueba real de extremo a extremo (build, `ollama-init`, ingesta, acceso público) queda pendiente de ejecutar en la VM.

**Próximo paso acordado:** una vez arriba y funcionando en OCI, monitorear consumo real de recursos (`docker stats`, `free -h`) antes de decidir si hay margen para agregar un reranking con cross-encoder pequeño.

---

## Bloque 4 — Continuación: despliegue real en OCI

**Transferencia de archivos sin scp/ssh directo.** Fernando no logra usar `scp` desde su máquina local; su flujo de trabajo real es la consola web de OCI + el bucket de Object Storage ("el cubo") + **OCI Cloud Shell**, desde donde sí puede hacer `ssh opc@<IP>` hacia la VM (confirmado con el prompt `[opc@dps-vm1 ~]$`). La transferencia de los 4 PDFs y el XLSX se resolvió generando **Pre-Authenticated Requests (PAR)** para cada objeto del bucket desde la consola, y descargándolos directamente en la VM con `wget -O "<ruta_destino>" "<URL_PAR>"` — sin necesidad de `scp`, CLI local de OCI, ni credenciales adicionales en la VM.

**Instalación de Docker en Oracle Linux 9:** exitosa con la secuencia `dnf install -y dnf-utils` → `dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo` → `dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin`. Versión instalada: Docker 29.6.2 / Compose v5.3.1.

**`docker compose up -d --build` exitoso:** las 2 imágenes (`docker-app`, `docker-ui`) se construyeron en ~203s cada una; el pull de `ollama/ollama:latest` tomó ~579s; `ollama-init` (descarga de `gemma2:2b` + `bge-m3`) tomó ~489s. Los 4 servicios quedaron arriba sin errores.

**Ingesta ejecutada en la VM:** `docker compose exec app python -m app.ingest` produjo **302 chunks** — el mismo número exacto que en el entorno local con los mismos parámetros (`CHUNK_SIZE=1200`, `CHUNK_OVERLAP=200`), confirmando que los 4 PDFs subidos vía PAR llegaron completos y sin corrupción.

### Troubleshooting: la app no era accesible desde internet

Diagnóstico por descarte, de adentro hacia afuera:
1. `docker compose ps` — contenedores `Up`, puertos publicados correctamente (`0.0.0.0:8501->8501/tcp`).
2. `curl -I http://localhost:8501` desde la propia VM → `200 OK`. Esto confirmó que **la aplicación en sí funcionaba perfectamente**; el problema no era ni Docker ni Streamlit ni la API.
3. `docker compose logs ui` confirmó "External URL: http://158.247.123.37:8501" — Streamlit detectaba bien su propia IP pública.
4. `sudo firewall-cmd --list-ports` → `8501/tcp` ya estaba abierto.

Con los 4 puntos anteriores en verde, la única capa que quedaba sin verificar era la de red de OCI (Security List o Network Security Group de la VCN) — que es **independiente de `firewalld`** y bloquea el tráfico *antes* de que llegue siquiera a la VM. Tras agregar la regla de ingreso correspondiente (TCP, puerto destino 8501, origen `0.0.0.0/0`) en la consola de OCI, la aplicación quedó accesible públicamente. Lección para `docs/deploy.md`: siempre son **dos capas de firewall independientes** a revisar (Security List/NSG + `firewalld`), y un fallo silencioso (timeout, no "connection refused") apunta casi siempre a la capa de red de la nube, no al sistema operativo.

### Monitoreo de recursos

**En reposo** (`docker stats --no-stream` y `free -h`, sin preguntas activas):

| Contenedor | CPU | RAM |
|---|---|---|
| `ollama` | 0.00% | 88.7 MiB |
| `app` | 0.07% | 136.5 MiB |
| `ui` | 0.22% | 53.5 MiB |

`free -h`: 10 GiB totales, 1.4 GiB usados, **9.3 GiB disponibles**, swap (4 GiB) sin usar. El `ollama` en 88.7 MiB confirma que, tras el timeout de inactividad (`keep_alive` por defecto de 5 min), ningún modelo queda cargado en memoria.

**En el pico** (`docker stats --no-stream` repetido mientras Centy respondía una pregunta):

| Contenedor | CPU | RAM |
|---|---|---|
| `ollama` | **~198%** (los 2 OCPU casi al 100% cada uno) | **~3.86 GiB** |
| `app` | 0.10% | 137 MiB |
| `ui` | ~0.3% | 54 MiB |

**Conclusión clave:** en esta VM de 2 OCPU, **el CPU es el recurso limitante durante la generación, no la RAM**. Incluso en el pico, quedan ~5-6 GiB de RAM libres — pero ambos cores están saturados por Ollama mientras genera una respuesta. Esto reformula la pregunta original ("¿hay espacio para un reranker?"): en memoria sí, pero cualquier paso de cómputo adicional (como un reranker) se sumará en serie al tiempo de respuesta, porque no hay CPU ocioso que se solape con la generación.

### Experimento: latencia de un reranker con cross-encoder (local, pendiente de validar en la VM)

Se instaló `sentence-transformers` (trae PyTorch como dependencia — bastante más pesado que lo usado hasta ahora) y se probó `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (multilingüe, entrenado en mMARCO que incluye español, ~118 MB) en la máquina de desarrollo local (escritorio Windows con Intel Core i5-8400 y 24 GB de RAM, sin GPU dedicada), no en la VM.

Metodología: para 4 preguntas de prueba, se comparó (a) baseline: `similarity_search(k=6)` + generación, contra (b) con reranking: `similarity_search(k=15)` → cross-encoder → top 6 → generación (mismo `k` final, para que la comparación de la etapa de generación sea justa).

| Pregunta | Tiempo del paso de reranking |
|---|---|
| Clasificación de proveedores | 0.82s |
| Robo (redacción de la pregunta no registrada) | 0.73s |
| Surtido nocturno | 0.86s |
| Sismo | 0.90s |

El tiempo total de extremo a extremo varió mucho entre corridas (de -23s a +5s de diferencia), pero **eso es ruido de la generación de Gemma** (su tiempo de generación por sí solo varió entre 36s y 55s en las mismas pruebas, con o sin reranking) — no un efecto del reranker. El dato limpio y consistente es el paso de reranking en sí: **entre 0.7 y 0.9 segundos**, muy por debajo del umbral de 3-5s que Fernando definió como aceptable.

Como beneficio adicional no buscado: en 2 de las 4 preguntas (robo, sismo), la respuesta con reranking fue más completa y más fiel al documento que la respuesta base (incluyó pasos del procedimiento real que la respuesta base omitía). Fue una sola corrida por pregunta, con valoración manual, y no se guardaron los fragmentos candidatos ni la redacción exacta de cada pregunta.

**Nota de precaución:** esta prueba corrió en Windows/x86_64 con recursos de sobra. La VM del deploy es ARM64 y ya tiene el CPU saturado durante la generación (ver monitoreo arriba). El siguiente paso es repetir esta misma prueba directamente en la VM, de forma reversible (instalación efímera dentro del contenedor `app` en ejecución, sin modificar la imagen ni el `docker-compose.yml`, descartable con `docker compose restart app`), antes de decidir si se integra de forma permanente al pipeline del deploy.

---

## Cierre del deploy

El deploy en OCI estuvo activo desde julio hasta el **30 de agosto de 2026**. Después se canceló la cuenta de OCI y la aplicación quedó fuera de línea. Por eso **la prueba del reranker en la VM no se llegó a hacer** y el reranker no se integró al pipeline. La evidencia del deploy es la que queda en esta bitácora (instalación, ingesta de 302 chunks, troubleshooting de red y monitoreo con `docker stats`) y en el README.

---

## Bloque 5 — Reranker integrado y medido en local (noviembre de 2026)

**Contexto:** el proyecto se retomó en otro equipo (portátil), con Ollama y los modelos instalados de nuevo. Todo lo de este bloque es local; el reranker nunca corrió en OCI.

**Por qué un cross-encoder con `sentence-transformers`:** reordena en memoria los candidatos que ya devuelve Chroma, sin tocar el índice. Se consideró ColBERT (late interaction), pero no se probó: exigiría reemplazar ChromaDB por un índice por token y probablemente no cabría en una VM Always Free.

**Implementación:**
- `app/reranker.py`: `rerank_documents(query, documents, top_k)` con carga perezosa del modelo `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (~118 MB, multilingüe).
- `app/chain.py`: `ENABLE_RERANKER` (por defecto `false`), `RERANKER_INITIAL_K=15` y `RERANKER_TOP_K=6`.
- `sentence-transformers` (y con él PyTorch) va en `requirements-reranker.txt`, para que la imagen base no cargue con él cuando está desactivado.

**Benchmark (`scripts/benchmark_reranker.py`; 7 preguntas, corrida 1 - 22 nov 2026):**

| Pregunta | Paso de reranking (15 → 6) | Fragmentos cambiados en el top 6 |
|---|---|---|
| robo | 15,38 s (incluye la carga del modelo) | 2 |
| sismo | 2,83 s | 1 |
| proveedores | 2,43 s | 2 |
| surtido | 2,30 s | 2 |
| peps | 2,37 s | 3 |
| acta | 3,26 s | 2 |
| faltas | 3,03 s | 3 |

- Paso de reranking en caliente (corrida 1): 2,3–3,3 s (~2,7 s de media); 15 fragmentos cambiados en total.
- Los tiempos de generación de Gemma variaron mucho entre corridas (como ya se vio en julio) y no se usan para sacar conclusiones.
- **Hallazgo:** en *"Vi a un cliente metiendo productos en su bolsa sin pagar. ¿Cuál es el protocolo?"*, abrir el pool a 15 candidatos trajo un fragmento de la Política de Atención al Cliente sobre retiro de producto dañado. El cross-encoder le dio el score más alto (−1,08) y bajó el protocolo de robo al 4.º puesto (−2,63). Con ese contexto, `gemma2:2b` respondió con el procedimiento de producto dañado ("aislar el producto en cuarentena"). Sin reranker (`k=6`), la respuesta fue correcta.

### Repetición de la prueba y benchmarking empírico (23 nov 2026)

Se volvió a ejecutar `scripts/benchmark_reranker.py` en el mismo entorno portátil para contrastar las mediciones:

| Pregunta | Paso de reranking (15 → 6) | Fragmentos cambiados en el top 6 | Scores Cross-Encoder |
|---|---|---|---|
| robo | 20,61 s (incluye carga lazy del modelo) | 2 | `[-1.08, -2.12, -2.33, -2.63, -3.95, -4.90]` |
| sismo | 2,25 s | 1 | `[-0.71, -5.29, -5.44, -5.67, -6.10, -6.74]` |
| proveedores | 2,14 s | 2 | `[3.50, 2.37, -0.67, -1.72, -2.22, -2.76]` |
| surtido | 1,76 s | 2 | `[-0.99, -1.99, -2.77, -2.97, -3.81, -4.53]` |
| peps | 1,91 s | 3 | `[1.45, -0.01, -3.22, -3.29, -3.41, -3.83]` |
| acta | 2,28 s | 2 | `[-2.34, -2.51, -5.12, -5.23, -5.26, -5.49]` |
| faltas | 2,05 s | 3 | `[-1.63, -3.65, -3.73, -4.12, -4.22, -5.20]` |

- **Paso de reranking en caliente:** 1,76–2,28 s (**~2,06 s de media** en caliente).
- **Consistencia cualitativa:** se repitieron exactamente las mismas sustituciones de chunks (15 en total) y los mismos scores, de modo que el fragmento equivocado vuelve a quedar primero en la pregunta de robo.

### Diferencia entre julio y noviembre

**1. Latencia: el paso de reranking pasó de ~0,8 s a ~2,1 s en caliente.**

| Pregunta | Julio (escritorio) | Noviembre, repetición (portátil) | Factor |
|---|---|---|---|
| proveedores | 0,82 s | 2,14 s | ~2,6x |
| surtido | 0,86 s | 1,76 s | ~2,0x |
| sismo | 0,90 s | 2,25 s | ~2,5x |
| robo | 0,73 s | sin dato en caliente (fue la primera pregunta y absorbió la carga del modelo) | — |

- **Equipos distintos.** Julio: escritorio con Intel Core i5-8400 (6 núcleos, CPU de escritorio de 65 W), 24 GB de RAM y gráficos integrados. Noviembre: portátil con Intel Core i5-1035G1 (4 núcleos / 8 hilos, base de 1,0 GHz, CPU móvil de 15 W). En ambos casos la inferencia corrió solo en CPU (en noviembre, `torch.cuda.is_available() = False`).
- **Software distinto.** Julio: Python 3.11 en un entorno conda. Noviembre: Python 3.13.9 con `torch==2.15.0+cpu`. La versión de PyTorch de julio no quedó registrada.
- **Arranque en frío.** En noviembre la pregunta de robo se ejecutó primero y su tiempo incluye la carga del modelo (15,38 s en la corrida 1; 20,61 s en la repetición). No es un problema de esa pregunta.
- **Conclusión:** la causa más probable de la diferencia (~2,5x) es el cambio de CPU de escritorio a CPU móvil de bajo consumo. No se puede aislar del cambio de Python y PyTorch, porque no se repitió la prueba en el escritorio.

**2. Resultado en robo: en julio el reranker mejoró la respuesta; en noviembre la empeoró.**

- En noviembre la causa está medida: con 15 candidatos entra el fragmento de retiro de producto dañado (Política de Atención al Cliente), el cross-encoder le da el score más alto (−1,08) y baja el de robo al 4.º puesto (−2,63). `gemma2:2b` respondió de forma coherente con ese contexto, que era el equivocado. Es el mismo cruce entre documentos ya visto en los hallazgos del modo Documentos.
- En julio no se guardaron ni la redacción exacta de la pregunta ni los candidatos, y la valoración fue manual y de una sola corrida. **La diferencia de resultado no se puede reconstruir.** Las hipótesis (otra redacción, un vector store reingestado en otro equipo) no están verificadas.
- Lección: el benchmark de noviembre guarda las preguntas, los candidatos y los scores, y es reproducible (la repetición dio los mismos 15 cambios y los mismos scores).

### Evaluación del reranker

**En el estado actual del proyecto no aporta:**
- Empeora la pregunta de robo (ver arriba); sin reranker (`k=6`) la respuesta es correcta.
- Suma ~2,1–2,7 s en caliente por consulta, más ~15–20 s de arranque en frío, en una arquitectura donde el CPU ya es el recurso limitante.
- El corpus es pequeño (4 documentos, 302 chunks) y `bge-m3` con `k=6` responde bien las preguntas validadas.

**Condiciones para reactivarlo (no probadas):**
1. Filtrar antes por documento o metadatos (`where={"source": ...}` en Chroma), para evitar el cruce entre documentos.
2. Reducir los candidatos de 15 a 8–10. Por el número de pares, la latencia debería bajar en proporción; no se midió.
3. Exportar el cross-encoder a ONNX cuantizado para bajar la latencia en CPU y quitar PyTorch de la imagen; no se midió.

**Mejoras con más retorno, en orden:**
- Extracción estructurada de tablas en la ingesta (`pdfplumber` o `unstructured`), para la confusión entre *Primera Vez* y *Reincidencia* en la tabla de sanciones.
- Filtro por documento o enrutamiento de la consulta, con costo de cómputo bajo.
- Búsqueda híbrida (BM25 + densa, fusión RRF), para consultas con números de artículo o términos exactos.

**Decisión final:** el reranker queda integrado en el repositorio y desactivado por defecto (`ENABLE_RERANKER=false`). La configuración base (`k=6`, `CHUNK_SIZE=1200`) es más rápida y, en estas pruebas, más precisa.