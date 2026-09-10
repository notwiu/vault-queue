# Vault Queue

Sistema de backup em nuvem com fila e processamento assíncrono.

Ainda no começo: este repositório só tem a estrutura Git e o ambiente Python. Sem API, fila ou worker por enquanto.

## Ambiente local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

No Git, o `.venv` não entra (está no `.gitignore`). Cada pessoa recria o ambiente na própria máquina.

## Como vamos evoluir

1. Repositório + venv (estamos aqui)
2. API mínima que cria um job
3. Fila + worker
4. Storage
