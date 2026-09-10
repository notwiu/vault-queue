# Vault Queue

Sistema de backup em nuvem com fila e processamento assíncrono.

## Ambiente local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

No Git, o `.venv` não entra (está no `.gitignore`). Cada pessoa recria o ambiente na própria máquina.

## Rodar a API

Com o venv ativo:

```powershell
uvicorn app:app --reload
```

Abra http://127.0.0.1:8000 — deve aparecer `{"status":"ok"}`.

## Como vamos evoluir

1. Repositório + venv
2. API mínima que responde ok (estamos aqui)
3. Criar um job
4. Fila + worker
5. Storage
