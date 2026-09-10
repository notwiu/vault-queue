from fastapi import FastAPI

app = FastAPI(title="Vault Queue")


@app.get("/")
def health():
    return {"status": "ok"}
