"""
storage.py — camada de abstração para o MinIO (ou S3 real em produção).

Por que isso existe?
    O worker e a API não sabem se estão falando com MinIO local ou AWS S3.
    Toda a configuração fica aqui. Para trocar para S3 de verdade, basta
    mudar as variáveis de ambiente — o restante do código não muda.

Variáveis de ambiente:
    STORAGE_ENDPOINT         URL do MinIO  (default: http://localhost:9000)
    STORAGE_KEY              Access key    (default: minioadmin)
    STORAGE_SECRET           Secret key    (default: minioadmin)
    STORAGE_BUCKET_STAGING   Bucket bruto  (default: staging)
    STORAGE_BUCKET_BACKUPS   Bucket final  (default: backups)

Buckets:
    staging/  → arquivo bruto, gravado pela API ao receber o upload
    backups/  → arquivo comprimido + processado, gravado pelo worker
"""

import os
import boto3
from botocore.client import Config

# ── Configuração ──────────────────────────────────────────────────────────────

ENDPOINT       = os.getenv("STORAGE_ENDPOINT",       "http://localhost:9000")
KEY            = os.getenv("STORAGE_KEY",             "minioadmin")
SECRET         = os.getenv("STORAGE_SECRET",          "minioadmin")
BUCKET_STAGING = os.getenv("STORAGE_BUCKET_STAGING",  "staging")
BUCKET_BACKUPS = os.getenv("STORAGE_BUCKET_BACKUPS",  "backups")

# ── Cliente boto3 (singleton lazy) ────────────────────────────────────────────

_s3 = None

def _client():
    """Retorna (e cria, se necessário) o cliente boto3 apontando para o MinIO."""
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            "s3",
            endpoint_url=ENDPOINT,
            aws_access_key_id=KEY,
            aws_secret_access_key=SECRET,
            # path_style é obrigatório no MinIO — não usa virtual-hosted buckets
            config=Config(signature_version="s3v4"),
        )
    return _s3


# ── Inicialização dos buckets ─────────────────────────────────────────────────

def ensure_buckets() -> None:
    """
    Cria os buckets se não existirem.
    Chamado no startup da API e do worker para garantir que o MinIO está pronto.
    Seguro chamar múltiplas vezes (idempotente).
    """
    s3 = _client()
    existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
    for bucket in (BUCKET_STAGING, BUCKET_BACKUPS):
        if bucket not in existing:
            s3.create_bucket(Bucket=bucket)


# ── Upload: API → staging ─────────────────────────────────────────────────────

def upload_to_staging(job_id: str, data: bytes) -> str:
    """
    Salva o arquivo bruto no bucket de staging.

    A API chama isso ao receber o upload do cliente.
    Retorna a object key no formato  <job_id>/raw
    O worker baixa o arquivo por essa mesma key.
    """
    key = f"{job_id}/raw"
    _client().put_object(Bucket=BUCKET_STAGING, Key=key, Body=data)
    return key


# ── Download: worker ← staging ────────────────────────────────────────────────

def download_from_staging(staging_key: str) -> bytes:
    """
    Baixa o arquivo bruto do staging.
    staging_key é o valor retornado por upload_to_staging.
    """
    response = _client().get_object(Bucket=BUCKET_STAGING, Key=staging_key)
    return response["Body"].read()


# ── Upload: worker → backups ──────────────────────────────────────────────────

def upload_to_backups(job_id: str, user_id: str, data: bytes) -> str:
    """
    Salva o backup processado (comprimido) no bucket definitivo.

    Estrutura da key:  <user_id>/<job_id>/data.gz
    Usar user_id na key facilita políticas de acesso por usuário no S3 real.
    Retorna a object key gravada.
    """
    key = f"{user_id}/{job_id}/data.gz"
    _client().put_object(Bucket=BUCKET_BACKUPS, Key=key, Body=data)
    return key


# ── Limpeza do staging ────────────────────────────────────────────────────────

def delete_staging(staging_key: str) -> None:
    """
    Remove o arquivo bruto do staging após o backup definitivo ser confirmado.
    Só chame DEPOIS de upload_to_backups ter retornado com sucesso — nunca antes.
    """
    _client().delete_object(Bucket=BUCKET_STAGING, Key=staging_key)
