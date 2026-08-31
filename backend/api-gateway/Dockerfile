FROM python:3.11-slim

WORKDIR /app

# Build context is backend/ so both the service code and the shared/
# package it imports (via `from shared.x import y`) are available.
COPY api-gateway/requirements.txt ./api-gateway/requirements.txt
RUN pip install --no-cache-dir -r api-gateway/requirements.txt

COPY shared/ ./shared/
COPY api-gateway/ ./api-gateway/

WORKDIR /app/api-gateway

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
