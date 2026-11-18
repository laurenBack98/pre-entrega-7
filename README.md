# Rapanui Multi-Agent Production API

API asíncrona con FastAPI que coordina agentes de investigación y análisis usando LangGraph. El proyecto integra búsqueda híbrida con Pinecone y Ollama, aprobación humana (HITL), trazas opcionales en LangSmith y una utilidad para medir concurrencia y latencia.

## Requisitos previos

- Windows, macOS o Linux.
- Python 3.10 o superior (el proyecto fue ejecutado con Python 3.12).
- [Ollama](https://ollama.com/) instalado y en ejecución.
- Una cuenta e índice de Pinecone.
- Una clave de LangSmith si se desean consultar trazas.

Descarga los modelos que usa el proyecto en Ollama:

```powershell
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

## Instalación

Desde la carpeta del proyecto, crea y activa un entorno virtual:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Crea tu archivo `.env` a partir del ejemplo:

```powershell
Copy-Item .env.example .env
```

Completa en `.env` `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` y `LANGSMITH_API_KEY` con tus propios valores. No publiques ni compartas ese archivo. LangSmith es opcional; sin una clave válida no se podrán enviar trazas al proyecto.

Al iniciar la aplicación, se crea el índice de Pinecone si no existe y se cargan los documentos base. Ollama debe estar activo y Pinecone debe ser accesible.

## Iniciar la API

```powershell
python -m uvicorn main:app --reload
```

La API queda disponible en `http://127.0.0.1:8000`. La documentación interactiva de FastAPI está en `http://127.0.0.1:8000/docs`.

## Endpoints

### Crear una tarea

`POST /tasks`

```json
{
  "query": "¿Qué beneficios laborales se mencionan?"
}
```

Responde `202 Accepted` con un `task_id` y estado inicial `PENDING`. El grafo se ejecuta en segundo plano.

### Consultar el estado

`GET /tasks/{task_id}`

Los estados de la tarea son `PENDING`, `RUNNING`, `AWAITING_APPROVAL`, `COMPLETED` o `FAILED`. Cuando corresponde, la respuesta incluye resultados de los agentes y uso de tokens.

### Aprobar o rechazar una tarea pausada

`POST /tasks/{task_id}/approve`

Solo se acepta si la tarea está en `AWAITING_APPROVAL`.

```json
{
  "aprobado": true,
  "comentario": "Presupuesto aprobado"
}
```

`comentario` es opcional. El grafo se reanuda con la decisión recibida.

## Estado y persistencia actuales

En la configuración actual, `redis_client.py` usa `fakeredis` en memoria para los estados de las tareas. Los estados expiran después de una hora y se pierden cuando el proceso de la API termina. Aunque el repositorio incluye `docker-compose.yml` con un servicio Redis, la aplicación todavía no se conecta a ese servicio.

El checkpoint de LangGraph también usa `MemorySaver`. Por lo tanto, una tarea pausada para aprobación no sobrevive al reinicio del proceso. Para producción o varios workers, ambos almacenamientos deben reemplazarse por implementaciones persistentes y compartidas.

## LangSmith y observabilidad

El ejemplo activa `LANGSMITH_TRACING` y configura `LANGSMITH_PROJECT`. El código agrega `task_id` como metadata a las trazas y expone el uso de tokens que reporta LangChain en los datos de la tarea. Usa la metadata `task_id` para localizar una ejecución en el proyecto configurado.

Los modelos de chat y embeddings se ejecutan localmente con Ollama. El conteo de tokens depende de la metadata que devuelva el modelo; LangSmith no calcula un costo de API para inferencia local ni estima el costo de hardware o electricidad.

## Prueba de concurrencia

Con la API en ejecución, abre otra terminal en la carpeta del proyecto y ejecuta:

```powershell
python scripts\load_test.py --requests 5 --concurrency 5 --query "¿Qué beneficios laborales se mencionan?"
```

El script crea cinco tareas concurrentes, consulta su estado hasta que sea terminal o expire el timeout e informa latencia end-to-end media y p95. También muestra los tokens reportados. `AWAITING_APPROVAL` se considera estado terminal para esta medición; la prueba no envía aprobaciones automáticamente.

Se pueden ajustar el número de solicitudes y el paralelismo, por ejemplo:

```powershell
python scripts\load_test.py --requests 10 --concurrency 5 --query "Calcula el costo mensual para 20 empleados"
```

## Estructura principal

```text
.
├── agents/
│   ├── analyst_agent.py     # Análisis y cálculos
│   ├── research_agent.py    # Investigación documental
│   └── supervisor.py        # Enrutamiento entre agentes
├── scripts/
│   └── load_test.py         # Prueba concurrente y métricas
├── graph.py                 # Grafo LangGraph y flujo HITL
├── ingesta.py               # Carga de documentos a Pinecone
├── main.py                  # API FastAPI y endpoints de tareas
├── redis_client.py          # Estado de tareas con fakeredis
├── retriver.py               # Recuperador híbrido
├── state.py                  # Estado compartido del grafo
└── tools.py                  # Herramientas de búsqueda y cálculo
```
