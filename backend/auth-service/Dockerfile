FROM python:3.11-slim

WORKDIR /app

# Build context is backend/ so both the service code and the shared/
# package it imports (via `from shared.x import y`) are available.
COPY auth-service/requirements.txt ./auth-service/requirements.txt
RUN pip install --no-cache-dir -r auth-service/requirements.txt

COPY shared/ ./shared/
COPY auth-service/ ./auth-service/

WORKDIR /app/auth-service

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
