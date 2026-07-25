# Guía de despliegue — OCI (Oracle Linux 9, VM.Standard.A1.Flex)

Guía para desplegar el agente completo (Ollama + API + interfaz Streamlit) en la instancia Ampere A1 consolidada (2 OCPU / 12 GB, Always Free), con la cuenta en modo Pay-As-You-Go.

Se asume que ya tienes: la VM aprovisionada y accesible por SSH, con IP pública asignada.

## 1. Instalar Docker en la VM (Oracle Linux 9)

Conéctate por SSH a la VM y ejecuta:

```bash
sudo dnf install -y dnf-utils
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

Cierra sesión y vuelve a entrar por SSH para que el grupo `docker` tome efecto (o usa `newgrp docker`). Verifica:

```bash
docker --version
docker compose version
```

Si `dnf config-manager` no se encuentra, instala primero `sudo dnf install -y dnf-plugins-core` y repite el comando `config-manager --add-repo`.

## 2. Clonar el repositorio

```bash
sudo dnf install -y git
git clone <URL_DE_TU_REPOSITORIO> agente-ia-rag
cd agente-ia-rag
```

## 3. Subir los archivos de datos reales

Los PDFs y el XLSX **no están en git** (ver `.gitignore`). Súbelos desde tu máquina local a la VM, por ejemplo con `scp`:

```bash
# Desde tu máquina local (Windows, en Git Bash o WSL):
scp "data/pdfs/"*.pdf  opc@<IP_PUBLICA_VM>:~/agente-ia-rag/data/pdfs/
scp "data/inventario/inventario_de_supermercado_latam.xlsx" opc@<IP_PUBLICA_VM>:~/agente-ia-rag/data/inventario/
```

Ajusta el usuario (`opc` es el default de las imágenes Oracle Linux de OCI) y la ruta según corresponda.

## 4. Construir y levantar los servicios

Todo se construye **en la propia VM** (arquitectura ARM64/aarch64) — no se hace build cruzado desde Windows.

```bash
cd ~/agente-ia-rag/docker
docker compose up -d --build
```

Esto levanta 4 servicios: `ollama`, `ollama-init` (descarga `gemma2:2b` y `bge-m3`, corre una vez y termina), `app` (FastAPI) y `ui` (Streamlit). La primera vez tardará varios minutos por la descarga de los modelos. Verifica el progreso:

```bash
docker compose logs -f ollama-init
```

## 5. Poblar el vector store (una sola vez, o cuando cambien los PDFs)

```bash
docker compose exec app python -m app.ingest
```

## 6. Abrir los puertos (dos capas distintas — ambas son necesarias)

**a) Security List / Network Security Group de la VCN** (en la consola de OCI): agrega una regla de ingreso para el puerto **8501** (TCP) desde `0.0.0.0/0` (o tu rango de IPs si prefieres restringirlo). El puerto 8000 (API) normalmente no necesita exponerse a internet — solo lo usa el contenedor `ui` internamente.

**b) `firewalld` en la propia VM** (Oracle Linux lo trae activo por defecto, es una capa aparte de la Security List):

```bash
sudo firewall-cmd --permanent --add-port=8501/tcp
sudo firewall-cmd --reload
```

## 7. Verificar acceso público

Desde tu navegador: `http://<IP_PUBLICA_VM>:8501`

## 8. Monitoreo de recursos

Antes de considerar agregar componentes adicionales (por ejemplo, un reranker), conviene observar el consumo real:

```bash
docker stats                # uso de CPU/RAM por contenedor, en vivo
free -h                     # memoria total/usada/disponible de la VM
docker compose logs ollama  # confirma que Ollama no está descargando/recargando modelos constantemente
```

## Comandos útiles

```bash
docker compose ps                 # estado de los servicios
docker compose logs -f app        # logs de la API en vivo
docker compose logs -f ui         # logs de Streamlit en vivo
docker compose restart app ui     # reiniciar solo backend/frontend (sin re-pull de modelos)
docker compose down               # detener todo (conserva los volumenes: modelos y chroma_db)
```
