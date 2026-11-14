FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
WORKDIR /app/backend
ENV MODEL_DIR=/app/models
RUN mkdir -p /app/models /app/data/synthetic && python scripts_train_and_seed.py --no-db
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
