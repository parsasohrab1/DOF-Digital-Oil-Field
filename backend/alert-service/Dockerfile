FROM python:3.11-slim

WORKDIR /app

# Build context is backend/ so both the service code and the shared/
# package it imports (via `from shared.x import y`) are available.
COPY alert-service/requirements.txt ./alert-service/requirements.txt
RUN pip install --no-cache-dir -r alert-service/requirements.txt

COPY shared/ ./shared/
COPY alert-service/ ./alert-service/

WORKDIR /app/alert-service

EXPOSE 8004

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
