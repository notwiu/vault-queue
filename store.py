"""
store.py — estado dos jobs no Redis.

Cada job é um hash Redis com TTL de 24h:
    HSET job:<id>  id <id>  status <status>  filename <nome>  ...

Por que Redis e não um banco SQL?
    Jobs de fila têm ciclo de vida curto (minutos a horas).
    Redis é ultrarrápido para leitura/escrita de campos pequenos
    e o TTL automático elimina lixo sem precisar de CRON de limpeza.
    Num sistema maior, jobs finalizados seriam arquivados em PostgreSQL.
"""

import os
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JOB_TTL   = 60 * 60 * 24  # 24 horas em segundos

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def _key(job_id: str) -> str:
    return f"job:{job_id}"


def save_job(job: dict) -> None:
    """Persiste um job novo no Redis com todos os campos de uma vez."""
    r = get_client()
    r.hset(_key(job["id"]), mapping=job)
    r.expire(_key(job["id"]), JOB_TTL)


def get_job(job_id: str) -> dict | None:
    """Retorna todos os campos do job ou None se não existir."""
    r = get_client()
    data = r.hgetall(_key(job_id))
    return data if data else None


def set_status(job_id: str, status: str) -> None:
    """Atualiza só o campo status do job (usado pelo worker nos transitions simples)."""
    r = get_client()
    r.hset(_key(job_id), "status", status)
    r.expire(_key(job_id), JOB_TTL)  # renova TTL a cada atualização


def update_job(job_id: str, fields: dict) -> None:
    """
    Atualiza múltiplos campos de um job de uma vez.
    Usado pelo worker ao finalizar para gravar checksum, storage_key, etc.

    Exemplo:
        update_job(job_id, {"status": "done", "checksum": "abc123", "storage_key": "u1/j1/data.gz"})
    """
    r = get_client()
    r.hset(_key(job_id), mapping=fields)
    r.expire(_key(job_id), JOB_TTL)
