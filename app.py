from uuid import uuid4

from fastapi import FastAPI, HTTPException

import store
from worker import process_backup

app = FastAPI(title="Vault Queue")


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/jobs", status_code=202)
def create_job():
    """
    Cria um job de backup e o enfileira para processamento assíncrono.
    Retorna 202 Accepted — o trabalho ainda não terminou.
    """
    job_id = str(uuid4())
    job = {"id": job_id, "status": "queued"}

    # 1. Persiste no Redis antes de enfileirar
    store.save_job(job)

    # 2. Envia para a fila — retorna imediatamente, worker processa em paralelo
    process_backup.delay(job_id)

    return job


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Consulta o status atual de um job."""
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
