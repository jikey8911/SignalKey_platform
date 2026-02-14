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

## Notes
- Start order: **API first** (activate venv + run uvicorn), then Web.
- If the venv activation is blocked by policy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
