"""
app.py — API HTTP do Vault Queue.

Responsabilidades:
  1. Receber o arquivo do cliente (upload multipart/form-data)
  2. Salvar no staging (MinIO) — sem processar nada
  3. Criar o registro do job no Redis  status = queued
  4. Publicar a task no Celery — retorna 202 imediatamente
  5. Deixar o worker fazer o trabalho pesado em segundo plano

Rotas:
  GET  /            → health check
  POST /jobs        → cria job + faz upload para staging, retorna 202 Accepted
  GET  /jobs/{id}   → consulta status atual do job

Por que 202 Accepted e não 200 OK?
  HTTP 202 significa "recebi, vou processar, mas ainda não terminei".
  É o código correto para operações assíncronas: o cliente sabe que
  o trabalho continua em segundo plano e deve consultar o status depois.
"""

from uuid import uuid4
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile

import store
import storage
from worker import process_backup


# ── Startup ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Executado uma vez quando o servidor sobe.
    Garante que os buckets existam no MinIO antes de qualquer requisição.
    """
    storage.ensure_buckets()
    yield


app = FastAPI(
    title="Vault Queue",
    description="Sistema de backup em nuvem com processamento assíncrono via fila.",
    version="0.2.0",
    lifespan=lifespan,
)


# ── Rotas ─────────────────────────────────────────────────────────────────────

@app.get("/")
def health():
    """Verifica se a API está no ar."""
    return {"status": "ok"}


@app.post("/jobs", status_code=202)
async def create_job(file: UploadFile = File(...)):
    """
    Cria um job de backup e enfileira o processamento.

    - Recebe um arquivo via multipart/form-data (campo: file)
    - Salva o arquivo no MinIO (bucket staging) como objeto temporário
    - Cria o registro do job no Redis com status = queued
    - Publica a task no Celery; o worker processa em segundo plano
    - Retorna 202 com o job_id para o cliente consultar depois

    Exemplo de uso com curl:
        curl -X POST http://localhost:8000/jobs -F "file=@foto.jpg"
    """
    job_id  = str(uuid4())
    content = await file.read()

    # 1. Salva no staging (MinIO) — retorna a object key
    staging_key = storage.upload_to_staging(job_id, content)

    # 2. Cria o registro no Redis
    job = {
        "id":          job_id,
        "status":      "queued",
        "filename":    file.filename or "unknown",
        "size_bytes":  str(len(content)),
        "staging_key": staging_key,
        "user_id":     "u_default",   # etapa 5: substituir por auth real
    }
    store.save_job(job)

    # 3. Enfileira o processamento — retorna imediatamente, worker age depois
    process_backup.delay(job_id)

    return {
        "id":       job_id,
        "status":   "queued",
        "filename": file.filename,
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """
    Consulta o status atual de um job.

    Estados possíveis:
      queued     → aguardando na fila
      processing → worker está processando agora
      done       → backup concluído com sucesso (checksum e storage_key disponíveis)
      failed     → erro após todas as tentativas de retry
    """
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
