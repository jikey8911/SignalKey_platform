# signaalKei_platform — Runbook (local dev)

## Prereqs
- Node.js + npm
- Python (with venv already created in `api/venv/`)

---

## 1 API (FastAPI) — port 8000

### PowerShell (Windows)
From repo root:

```powershell
cd api
.\venv\Scripts\Activate.ps1
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Quick check
- Swagger UI: http://localhost:8000/docs

---

## 2 Web (Vite) — port 3000

In another terminal:

```powershell
cd web
npm install
npm run dev
```

### Quick check
- Web: http://localhost:3000

---

## 3 Tests (API)

From `signaalKei_platform/api`:

### Stable (default)
Runs only the maintained deterministic tests (currently config/exchanges):

```powershell
cd api
.\venv\Scripts\python.exe -m pytest -q
```

### Legacy (explicit)
Runs legacy tests that are out of sync with the current codebase:

```powershell
cd api
.\venv\Scripts\python.exe -m pytest -q -m legacy
```

### Integration (explicit)
Runs integration/E2E tests that may require external services (Mongo, sockets, ccxt/telethon, etc.):

```powershell
cd api
.\venv\Scripts\python.exe -m pytest -q -m integration
```

### Run a specific file

```powershell
cd api
.\venv\Scripts\python.exe -m pytest -q tests\test_config_exchanges_endpoints.py
```

---

## Notes
- Start order: **API first** (activate venv + run uvicorn), then Web.
- Pytest default collection is intentionally limited to avoid importing historical tests with side effects.
- If the venv activation is blocked by policy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
