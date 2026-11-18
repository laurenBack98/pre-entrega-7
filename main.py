import uuid
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from graph import create_production_graph
from redis_client import set_task_state, get_task_state

app = FastAPI(
    title="Rapanui Multi-Agent Production API",
    version="1.0.0",
    description="API asíncrona de producción con observabilidad y Human-in-the-Loop",
)

# Checkpointer en memoria. 
# Nota: Si el grafo corre en múltiples workers o procesos independientes, 
# se recomienda sustituir MemorySaver por AsyncRedisSaver o PostgresSaver.
checkpointer = MemorySaver()
multi_agent_graph = create_production_graph(checkpointer=checkpointer)


def merge_token_usage(*usage_maps: dict) -> dict:
    merged = {}
    for usage_map in usage_maps:
        for model, counts in usage_map.items():
            model_counts = merged.setdefault(model, {})
            for name, count in counts.items():
                if isinstance(count, (int, float)):
                    model_counts[name] = model_counts.get(name, 0) + count
    return merged


# --- Modelos Pydantic ---
class TaskCreateRequest(BaseModel):
    query: str


class TaskCreateResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskApprovalRequest(BaseModel):
    aprobado: bool
    comentario: Optional[str] = "Aprobado por el responsable de RRHH / Finanzas"


# --- Worker Asíncrono en Background ---
async def execute_graph_task(task_id: str, query: str):
    """Ejecuta el grafo en segundo plano sin bloquear la API."""
    await set_task_state(task_id, "RUNNING")
    usage_callback = UsageMetadataCallbackHandler()
    config = {
        "configurable": {"thread_id": task_id},
        "metadata": {"task_id": task_id},
        "tags": ["rapanui-production"],
        "callbacks": [usage_callback],
    }
    inputs = {
        "messages": [HumanMessage(content=query)],
        "step_count": 0,
        "requiere_aprobacion": False,
    }

    try:
        resultado = await multi_agent_graph.ainvoke(inputs, config=config)

        # Consulta asíncrona del estado del grafo
        estado_grafo = await multi_agent_graph.aget_state(config)

        # Si el grafo quedó en pausa esperando validación humana
        if estado_grafo.next and "human_approval" in estado_grafo.next:
            await set_task_state(
                task_id,
                "AWAITING_APPROVAL",
                data={
                    "datos_analisis": resultado.get("datos_analisis"),
                    "mensaje": "La tarea requiere validación humana para autorizar el presupuesto.",
                    "token_usage": usage_callback.usage_metadata,
                },
            )
            return

        # Tarea completada con éxito
        ultimo_mensaje = resultado["messages"][-1].content if resultado.get("messages") else ""
        await set_task_state(
            task_id,
            "COMPLETED",
            data={
                "respuesta": ultimo_mensaje,
                "datos_investigacion": resultado.get("datos_investigacion"),
                "datos_analisis": resultado.get("datos_analisis"),
                "token_usage": usage_callback.usage_metadata,
            },
        )
    except Exception as e:
        await set_task_state(
            task_id,
            "FAILED",
            data={
                "error": str(e),
                "token_usage": usage_callback.usage_metadata,
            },
        )


# --- Endpoints REST ---
@app.post("/tasks", response_model=TaskCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(req: TaskCreateRequest, background_tasks: BackgroundTasks):
    """Encola una consulta para ser procesada por el orquestador multi-agente."""
    task_id = str(uuid.uuid4())
    await set_task_state(task_id, "PENDING")
    background_tasks.add_task(execute_graph_task, task_id, req.query)
    return {
        "task_id": task_id,
        "status": "PENDING",
        "message": "Tarea encolada con éxito.",
    }


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Consulta el estado actual y el resultado de la tarea."""
    task_data = await get_task_state(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return task_data


@app.post("/tasks/{task_id}/approve")
async def approve_task(task_id: str, req: TaskApprovalRequest, background_tasks: BackgroundTasks):
    """Reanuda un hilo pausado tras la aprobación humana (HITL)."""
    task_data = await get_task_state(task_id)
    if not task_data or task_data.get("status") != "AWAITING_APPROVAL":
        raise HTTPException(status_code=400, detail="La tarea no está esperando aprobación.")

    previous_usage = (task_data.get("data") or {}).get("token_usage", {})

    async def resume_graph():
        usage_callback = UsageMetadataCallbackHandler()
        config = {
            "configurable": {"thread_id": task_id},
            "metadata": {"task_id": task_id},
            "tags": ["rapanui-production"],
            "callbacks": [usage_callback],
        }
        await set_task_state(task_id, "RUNNING")
        try:
            # Reanudamos pasando el Command con la decisión humana
            resultado = await multi_agent_graph.ainvoke(
                Command(resume={"aprobado": req.aprobado, "comentario": req.comentario}),
                config=config,
            )
            ultimo_mensaje = resultado["messages"][-1].content if resultado.get("messages") else ""
            await set_task_state(
                task_id,
                "COMPLETED",
                data={
                    "respuesta": ultimo_mensaje,
                    "aprobado_por_humano": req.aprobado,
                    "comentario_humano": req.comentario,
                    "token_usage": merge_token_usage(
                        previous_usage,
                        usage_callback.usage_metadata,
                    ),
                },
            )
        except Exception as e:
            await set_task_state(
                task_id,
                "FAILED",
                data={
                    "error": str(e),
                    "token_usage": merge_token_usage(
                        previous_usage,
                        usage_callback.usage_metadata,
                    ),
                },
            )

    background_tasks.add_task(resume_graph)
    return {"message": "Aprobación recibida. Reanudando ejecución de la tarea."}
