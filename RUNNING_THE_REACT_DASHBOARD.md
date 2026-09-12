# Running the local React + FastAPI demo

Use Python 3.12 or 3.13 and Node.js 22.12+ with npm. The existing `.venv` is machine-specific (it references another user's Python); leave it untouched. From PowerShell:

```powershell
cd C:\Users\oussa\OneDrive\Desktop\electricity-project-2
python -m venv .venv-local
.\.venv-local\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

Alternatively, after activation, `cd backend` and run `python -m uvicorn main:app --reload --port 8000`. Both resolve artifacts relative to source files. Health: http://localhost:8000/api/health; interactive API contract: http://localhost:8000/docs. Missing/corrupt artifacts fail startup explicitly.

In a second PowerShell terminal:

```powershell
cd C:\Users\oussa\OneDrive\Desktop\electricity-project-2\frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

Open http://localhost:5173. Set `VITE_API_BASE_URL` in frontend/.env before starting/building Vite. Set `$env:CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"` before starting the backend to override permitted browser origins. No external services are needed.

From the project root with the new environment activated:

```powershell
python -m pytest backend/tests -q
python -m backend.modeling --train
python -m backend.evaluate
python -m backend.evaluate --manifest
python -m streamlit run dashboard.py
```

Run the training command only for an intentional bounded retraining pass; it preserves a candidate and promotes it only after a better 2024 WAPE or RMSE. The final command starts the optional legacy Streamlit UI. In frontend, verification commands are `npm run build` and `npm exec vitest run`.

`GET /api/forecast?date=2024-12-31&hour=12` is historical comparison. `POST /api/forecast/future` accepts JSON such as `{"start":"2025-01-01T00:00:00","horizon":24}`. Start must equal `/api/meta`'s `future_start` (the hour after packaged history, timezone-naive); horizon is an integer 1–168. Optional `temperature` and `humidity` arrays must both contain exactly horizon finite numbers; humidity is 0–100%. Omitted weather uses historical month/hour means, with hour means as fallback, never a real weather forecast. This recursive mode is experimental: predictions feed subsequent lag/rolling inputs and errors accumulate. Missing historical demand is forward-filled for feature history only; missing actual targets remain excluded from scoring.
