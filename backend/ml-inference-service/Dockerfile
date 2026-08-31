FROM python:3.11-slim

WORKDIR /app

# Build context is backend/ so both the service code and the shared/
# package it imports (via `from shared.x import y`) are available.
COPY ml-inference-service/requirements.txt ./ml-inference-service/requirements.txt
RUN pip install --no-cache-dir -r ml-inference-service/requirements.txt

COPY shared/ ./shared/
COPY ml-inference-service/ ./ml-inference-service/

WORKDIR /app/ml-inference-service

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
