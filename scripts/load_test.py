import argparse
import asyncio
import math
import time

import httpx


TERMINAL_STATUSES = {"COMPLETED", "FAILED", "AWAITING_APPROVAL"}


async def run_task(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    base_url: str,
    query: str,
    poll_interval: float,
    timeout: float,
) -> dict:
    async with semaphore:
        started = time.perf_counter()
        response = await client.post(
            f"{base_url}/tasks",
            json={"query": query},
        )
        response.raise_for_status()
        task_id = response.json()["task_id"]
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            status_response = await client.get(f"{base_url}/tasks/{task_id}")
            status_response.raise_for_status()
            task_data = status_response.json()
            task_status = task_data.get("status")
            if task_status in TERMINAL_STATUSES:
                return {
                    "task_id": task_id,
                    "status": task_status,
                    "elapsed_seconds": time.perf_counter() - started,
                    "data": task_data.get("data", {}),
                }
            await asyncio.sleep(poll_interval)

        return {
            "task_id": task_id,
            "status": "TIMEOUT",
            "elapsed_seconds": time.perf_counter() - started,
            "data": {},
        }


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Envía tareas concurrentes a la API y mide latencia end-to-end."
    )
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--query", required=True)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    if args.requests < 1 or args.concurrency < 1:
        parser.error("--requests y --concurrency deben ser mayores que cero")
    if args.poll_interval <= 0 or args.timeout <= 0:
        parser.error("--poll-interval y --timeout deben ser mayores que cero")

    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(timeout=30.0) as client:
        results = await asyncio.gather(
            *(
                run_task(
                    client,
                    semaphore,
                    args.url.rstrip("/"),
                    args.query,
                    args.poll_interval,
                    args.timeout,
                )
                for _ in range(args.requests)
            ),
            return_exceptions=True,
        )

    failures = [result for result in results if isinstance(result, Exception)]
    completed = [result for result in results if isinstance(result, dict)]
    unsuccessful = [
        result
        for result in completed
        if result["status"] in {"FAILED", "TIMEOUT"}
    ]
    total_tokens = {}
    for failure in failures:
        print(f"ERROR: {failure}")
    for result in completed:
        print(
            f"{result['task_id']} {result['status']} "
            f"{result['elapsed_seconds']:.2f}s"
        )
        token_usage = result["data"].get("token_usage", {})
        if token_usage:
            print(f"  Tokens por modelo: {token_usage}")
            for model, counts in token_usage.items():
                model_totals = total_tokens.setdefault(model, {})
                for name, count in counts.items():
                    if isinstance(count, (int, float)):
                        model_totals[name] = model_totals.get(name, 0) + count

    latencies = [result["elapsed_seconds"] for result in completed]
    if latencies:
        print(f"Completadas/observadas: {len(completed)}/{args.requests}")
        print(f"Latencia media end-to-end: {sum(latencies) / len(latencies):.2f}s")
        print(f"Latencia p95 end-to-end: {percentile(latencies, 0.95):.2f}s")
    if total_tokens:
        print(f"Tokens acumulados por modelo: {total_tokens}")
    if failures or unsuccessful or len(completed) != args.requests:
        raise SystemExit(1)

    print(
        "Las trazas LangSmith se pueden localizar por metadata.task_id "
        "y el proyecto configurado en LANGSMITH_PROJECT. Ollama local no "
        "tiene costo de API; LangSmith solo estima costos si hay tarifas "
        "configuradas para el modelo."
    )


if __name__ == "__main__":
    asyncio.run(main())
