FROM python:3.11-slim

WORKDIR /app

# Build context is backend/ so both the service code and the shared/
# package it imports (via `from shared.x import y`) are available.
COPY reporting-service/requirements.txt ./reporting-service/requirements.txt
RUN pip install --no-cache-dir -r reporting-service/requirements.txt

COPY shared/ ./shared/
COPY reporting-service/ ./reporting-service/

WORKDIR /app/reporting-service

EXPOSE 8005

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
