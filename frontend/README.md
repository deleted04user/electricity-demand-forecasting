# Electricity demand dashboard

React/Vite dashboard for the repository's FastAPI service. It provides demand summaries, seasonal analysis, model diagnostics, historical comparisons, and experimental recursive forecasts. The bundled data is synthetic; see the [project README](../README.md) for model scope and limitations.

## Development

Use Node.js 24.15+ (24.x LTS) and npm. Start the backend on port 8000 using the [running guide](../RUNNING_THE_REACT_DASHBOARD.md), then run from this directory:

```bash
npm ci
npm run dev
```

Open [localhost:5173](http://localhost:5173). Vite forwards `/api` to `http://127.0.0.1:8000`. Same-origin requests also work in the Docker deployment, where nginx forwards `/api` to FastAPI.

To call another API origin, copy `.env.example` to `.env`, set `VITE_API_BASE_URL` (for example `http://localhost:9000`), and restart Vite. The value is embedded into the browser bundle at build time, so it is public and must not contain credentials. Configure the backend's `CORS_ORIGINS` for the dashboard's browser origin when using a separate API origin. Leaving the value blank uses the same-origin `/api` route.

## Checks and production build

```bash
npm run check
```

This runs Oxlint, Vitest component tests, and the Vite production build. Individual commands are `npm run lint`, `npm test`, and `npm run build`. Tests use Testing Library and jsdom. Build output is written to `dist/`.

`npm run preview` serves the build for local inspection. For deployment, use the repository's [Docker Compose setup](../docker-compose.yml), or serve `dist/` with an `/api` reverse proxy. If using a separate API origin, set `VITE_API_BASE_URL` before building.

Use `npm ci` to install exactly the committed lock file. Commit `package-lock.json` together with intentional dependency changes; run the complete check after updating it.

## Browser integration

Start the repository's Docker Compose stack, then run from this directory:

```bash
npx playwright install --with-deps --only-shell chromium
npm run test:e2e
```

The default `E2E_BASE_URL` is `http://127.0.0.1:8080`. These Chromium tests check the real dashboard, historical hour changes, recursive forecast rows, and recovery after a controlled API failure. CI runs them against nginx and FastAPI containers and uploads an HTML report plus failure traces. Vitest continues to run only the component/API-client unit tests.
