"""
worker.py — Celery app e task de backup com processamento real.

Para rodar o worker:
    celery -A worker worker --loglevel=info

O que a task faz (etapa 4):
  1. Verifica idempotência — se já "done", ignora e dá ack
  2. Marca o job como "processing"
  3. Baixa o arquivo bruto do staging (MinIO)
  4. Calcula SHA-256 do conteúdo original
  5. Comprime com gzip
  6. Faz upload do .gz para o bucket backups
  7. Grava checksum e storage_key no Redis
  8. Apaga o arquivo do staging (só depois de confirmar o upload)
  9. Marca o job como "done"

Idempotência (por que é obrigatório):
  A fila pode entregar a mesma mensagem duas vezes (ex: o worker travou
  depois do upload mas antes do ack). Sem verificação, teríamos dois
  backups do mesmo job pagando storage duas vezes.
  A checagem job.status == "done" resolve isso: o segundo worker vê
  que já foi processado e para sem fazer nada.

Retry automático:
  max_retries=3 com default_retry_delay=10s.
  Em produção use backoff exponencial: 10s, 50s, 250s.
  Após 3 falhas o job fica como "failed" para inspeção.
"""

import gzip
import hashlib
import os

from celery import Celery

import store
import storage

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
    Processa um job de backup completo.

    bind=True           → self disponível para self.retry() e self.request.id
    max_retries=3       → tenta mais 3 vezes em caso de falha
    default_retry_delay → aguarda 10s entre tentativas
    """
    job = store.get_job(job_id)
    if job is None:
        # Job não existe — não há o que processar (pode ter expirado o TTL)
        return {"error": "job not found"}

    # ── Idempotência: nunca processa o mesmo job duas vezes ───────────────────
    if job.get("status") == "done":
        return {"job_id": job_id, "result": "already done, skipping"}

    if job.get("status") == "processing":
        # Outro worker já pegou — este para aqui sem re-enfileirar
        return {"job_id": job_id, "result": "already processing, skipping"}

    try:
        # ── 1. Marca como em andamento ────────────────────────────────────────
        store.set_status(job_id, "processing")
        storage.ensure_buckets()

        # ── 2. Baixa o arquivo bruto do staging ───────────────────────────────
        staging_key = job["staging_key"]
        raw_bytes   = storage.download_from_staging(staging_key)

        # ── 3. Calcula SHA-256 do conteúdo original ───────────────────────────
        #       Feito ANTES da compressão para ter o hash do arquivo real.
        checksum = hashlib.sha256(raw_bytes).hexdigest()

        # ── 4. Comprime com gzip ──────────────────────────────────────────────
        #       compresslevel=6 é o padrão do gzip: bom equilíbrio speed/ratio.
        compressed = gzip.compress(raw_bytes, compresslevel=6)

        # ── 5. Faz upload do backup final para o bucket definitivo ────────────
        user_id     = job.get("user_id", "u_default")
        storage_key = storage.upload_to_backups(job_id, user_id, compressed)

        # ── 6. Atualiza o registro no Redis com todos os metadados ────────────
        store.update_job(job_id, {
            "status":          "done",
            "checksum_sha256": checksum,
            "storage_key":     storage_key,
            "size_original":   str(len(raw_bytes)),
            "size_compressed": str(len(compressed)),
        })

        # ── 7. Remove o staging APÓS confirmar o upload definitivo ────────────
        #       Nunca apague antes — se o upload falhar e o staging sumir,
        #       o arquivo se perde para sempre.
        storage.delete_staging(staging_key)

        return {
            "job_id":          job_id,
            "checksum_sha256": checksum,
            "storage_key":     storage_key,
            "result":          "ok",
        }

    except Exception as exc:
        store.set_status(job_id, "failed")
        # Celery vai retentar automaticamente até max_retries
        raise self.retry(exc=exc)
