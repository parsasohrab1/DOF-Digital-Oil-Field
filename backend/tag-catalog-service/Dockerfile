FROM python:3.11-slim

WORKDIR /app

# Build context is backend/ so both the service code and the shared/
# package it imports (via `from shared.x import y`) are available.
COPY tag-catalog-service/requirements.txt ./tag-catalog-service/requirements.txt
RUN pip install --no-cache-dir -r tag-catalog-service/requirements.txt

COPY shared/ ./shared/
COPY tag-catalog-service/ ./tag-catalog-service/

WORKDIR /app/tag-catalog-service

EXPOSE 8007

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8007"]
