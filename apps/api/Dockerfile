FROM python:3.13.7-slim

ARG EMBEDDING_MODEL=intfloat/multilingual-e5-small

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 appuser && mkdir -p "$HF_HOME" && chown -R appuser:appuser /app
USER appuser

# Bake the encoder into the image so workers don't download it on every restart.
RUN python -c "import sys; from sentence_transformers import SentenceTransformer; SentenceTransformer(sys.argv[1])" "$EMBEDDING_MODEL"

COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser scripts ./scripts

EXPOSE 8000

CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
