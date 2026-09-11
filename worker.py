"""
worker.py — Celery app e tasks de backup.

Para rodar o worker:
    celery -A worker worker --loglevel=info

O broker (fila de entrada) e o backend (resultado das tasks) apontam
para o mesmo Redis por simplicidade. Em produção pode separar.
"""

import os
import time

from celery import Celery

import store

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "vault_queue",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_backup(self, job_id: str) -> dict:
    """
    Task principal: simula o processamento de um backup.

    bind=True     → self disponível para retry e metadados da task
    max_retries=3 → tenta até 3 vezes em caso de falha
    """
    try:
        store.set_status(job_id, "processing")

        # -----------------------------------------------------------
        # Aqui vai a lógica real de backup (etapa 5: upload para S3).
        # Por enquanto simulamos com um sleep.
        # -----------------------------------------------------------
        time.sleep(3)  # simula trabalho pesado

        store.set_status(job_id, "done")
        return {"job_id": job_id, "result": "ok"}

    except Exception as exc:
        store.set_status(job_id, "failed")
        # Celery vai retentar automaticamente até max_retries
        raise self.retry(exc=exc)
