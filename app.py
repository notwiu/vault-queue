from uuid import uuid4

from fastapi import FastAPI, HTTPException

app = FastAPI(title="Vault Queue")

jobs = {}


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/jobs")
def create_job():
    job_id = str(uuid4())
    job = {"id": job_id, "status": "queued"}
    jobs[job_id] = job
    return job


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
