FROM python:3.11-slim

WORKDIR /app

# Build context is backend/ so both the service code and the shared/
# package it imports (via `from shared.x import y`) are available.
COPY command-control-service/requirements.txt ./command-control-service/requirements.txt
RUN pip install --no-cache-dir -r command-control-service/requirements.txt

COPY shared/ ./shared/
COPY command-control-service/ ./command-control-service/

WORKDIR /app/command-control-service

EXPOSE 8006

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8006"]
