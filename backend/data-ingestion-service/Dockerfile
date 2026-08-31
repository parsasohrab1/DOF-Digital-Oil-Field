FROM python:3.11-slim

WORKDIR /app

# Build context is backend/ so both the service code and the shared/
# package it imports (via `from shared.x import y`) are available.
COPY data-ingestion-service/requirements.txt ./data-ingestion-service/requirements.txt
RUN pip install --no-cache-dir -r data-ingestion-service/requirements.txt

COPY shared/ ./shared/
COPY data-ingestion-service/ ./data-ingestion-service/

WORKDIR /app/data-ingestion-service

EXPOSE 8002

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
