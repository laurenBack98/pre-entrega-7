import json
import os
import fakeredis.aioredis as fake_redis
from dotenv import load_dotenv

load_dotenv()

# Instancia de Redis emulada en memoria para entorno de desarrollo local
redis_client = fake_redis.FakeRedis(decode_responses=True)


async def set_task_state(task_id: str, status: str, data: dict = None, expire_seconds: int = 3600):
    """Guarda o actualiza el estado de una tarea en Redis."""
    payload = {
        "task_id": task_id,
        "status": status,
        "data": data or {},
    }
    await redis_client.set(f"task:{task_id}", json.dumps(payload), ex=expire_seconds)


async def get_task_state(task_id: str) -> dict | None:
    """Recupera el estado de una tarea por su task_id."""
    raw = await redis_client.get(f"task:{task_id}")
    if not raw:
        return None
    return json.loads(raw)
