# Vault Queue

Sistema de backup em nuvem com fila e processamento assíncrono.

A API aceita o arquivo, enfileira um job e responde em milissegundos.
Workers em segundo plano fazem checksum, compressão e upload para o storage.

## Arquitetura

```
Cliente
  │  POST /jobs  (arquivo)
  ▼
API (FastAPI)
  │  1. salva no MinIO  → bucket: staging
  │  2. cria job no Redis  status = queued
  │  3. publica na fila (Celery/Redis)
  ▼
Fila (Redis)
  │  worker consome
  ▼
Worker (Celery)
  │  4. baixa do staging
  │  5. SHA-256 do original
  │  6. comprime com gzip
  │  7. upload → bucket: backups
  │  8. atualiza Redis  status = done
  │  9. apaga staging
  ▼
MinIO (backups/<user_id>/<job_id>/data.gz)
```

## Pré-requisitos

- Python 3.11+
- Docker e Docker Compose

## Ambiente local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Subir a infraestrutura (Redis + MinIO)

```bash
docker compose up -d
```

| Serviço | URL                                          | Credenciais          |
|---------|----------------------------------------------|----------------------|
| MinIO API (S3) | http://localhost:9000              | —                    |
| MinIO Console  | http://localhost:9001              | minioadmin/minioadmin|
| Redis          | localhost:6379                     | —                    |

## Rodar a API

```bash
uvicorn app:app --reload
```

Acesse a documentação interativa: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Rodar o worker

Em outro terminal (com o venv ativo):

```bash
celery -A worker worker --loglevel=info
```

## Testar

### 1. Enviar um arquivo para backup

```bash
curl -X POST http://localhost:8000/jobs -F "file=@qualquer_arquivo.txt"
```

Resposta (202 Accepted):
```json
{"id": "bck_abc123", "status": "queued", "filename": "qualquer_arquivo.txt"}
```

### 2. Consultar o status

```bash
curl http://localhost:8000/jobs/bck_abc123
```

Resposta após o worker processar:
```json
{
  "id": "bck_abc123",
  "status": "done",
  "filename": "qualquer_arquivo.txt",
  "checksum_sha256": "e3b0c44298...",
  "storage_key": "u_default/bck_abc123/data.gz",
  "size_original": "1024",
  "size_compressed": "312"
}
```

### 3. Ver o arquivo no MinIO

Abra [http://localhost:9001](http://localhost:9001), entre com `minioadmin`/`minioadmin`.
- Bucket `staging` → arquivo bruto (apagado após o worker terminar)
- Bucket `backups` → backup final comprimido

## Estrutura de arquivos

```
vault-queue/
├── app.py            # API HTTP (FastAPI) — recebe upload, enfileira job
├── worker.py         # Worker Celery — checksum, gzip, upload MinIO
├── store.py          # Acesso ao Redis — estado dos jobs
├── storage.py        # Acesso ao MinIO/S3 — upload/download/delete
├── docker-compose.yml# Redis + MinIO
└── requirements.txt
```

## Variáveis de ambiente

| Variável                 | Default                    | Descrição                    |
|--------------------------|----------------------------|------------------------------|
| `REDIS_URL`              | redis://localhost:6379/0   | Broker e backend do Celery   |
| `STORAGE_ENDPOINT`       | http://localhost:9000      | URL do MinIO ou S3           |
| `STORAGE_KEY`            | minioadmin                 | Access key                   |
| `STORAGE_SECRET`         | minioadmin                 | Secret key                   |
| `STORAGE_BUCKET_STAGING` | staging                    | Bucket temporário            |
| `STORAGE_BUCKET_BACKUPS` | backups                    | Bucket definitivo            |

Para apontar para AWS S3 real, defina `STORAGE_ENDPOINT` como vazio e passe credenciais AWS normais — o código do `storage.py` não muda.

## Roadmap

| Etapa | Status | Descrição |
|-------|--------|-----------|
| 1 | ✅ | Job síncrono falso (responde ok) |
| 2 | ✅ | Status no Redis |
| 3 | ✅ | Fila Celery + worker vazio |
| 4 | ✅ | Upload real + checksum + gzip + MinIO |
| 5 | ⬜ | Upload direto via presigned URL (arquivos grandes) |
| 6 | ⬜ | Auth real, DLQ, idempotência por hash, limites de quota |
| 7 | ⬜ | Métricas, alertas, lifecycle no bucket |
