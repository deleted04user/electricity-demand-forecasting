FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# XGBoost's Linux wheels need the OpenMP runtime.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home app

COPY requirements-api.lock.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements-api.lock.txt

COPY backend/ ./backend/
COPY data/electricity_demand_2025.xlsx ./data/electricity_demand_2025.xlsx
COPY models/electricity_xgb_prediction_model.pkl models/metadata.json ./models/

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).read()"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
