"""
store.py — estado dos jobs no Redis.

Cada job é um hash Redis: HSET job:<id> id <id> status <status>
TTL de 24h para não acumular lixo indefinidamente.
"""

import json
import os

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JOB_TTL = 60 * 60 * 24  # 24 horas em segundos

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def _key(job_id: str) -> str:
    return f"job:{job_id}"


def save_job(job: dict) -> None:
    """Persiste um job novo no Redis."""
    r = get_client()
    r.hset(_key(job["id"]), mapping=job)
    r.expire(_key(job["id"]), JOB_TTL)


def get_job(job_id: str) -> dict | None:
    """Retorna o job ou None se não existir."""
    r = get_client()
    data = r.hgetall(_key(job_id))
    return data if data else None


def set_status(job_id: str, status: str) -> None:
    """Atualiza só o campo status do job."""
    r = get_client()
    r.hset(_key(job_id), "status", status)
    r.expire(_key(job_id), JOB_TTL)  # renova TTL a cada atualização
