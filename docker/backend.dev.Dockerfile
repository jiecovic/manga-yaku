# docker/backend.dev.Dockerfile
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/backend-python

COPY backend-python /tmp/backend-python

RUN python -m venv /opt/venv \
    && python -m pip install --upgrade pip \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.9.1 torchvision==0.24.1 \
    && python -m pip install \
        fastapi==0.122.0 \
        httpx==0.28.1 \
        Jinja2==3.1.6 \
        json-repair==0.58.5 \
        manga-ocr==0.1.14 \
        openai==2.24.0 \
        openai-agents==0.10.4 \
        opencv-python==4.12.0.88 \
        pillow==12.0.0 \
        pydantic==2.12.4 \
        pgvector==0.4.1 \
        python-dotenv==1.2.1 \
        python-multipart==0.0.20 \
        PyYAML==6.0.3 \
        psycopg[binary]==3.2.10 \
        SQLAlchemy==2.0.43 \
        transformers==4.57.3 \
        ultralytics==8.4.13 \
        uvicorn==0.38.0 \
        pytest==8.4.2 \
        pytest-asyncio==1.2.0 \
    && python -m pip install -e /tmp/backend-python --no-deps

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8101", "--app-dir", "/workspace/backend-python", "--reload", "--reload-dir", "/workspace/backend-python/api", "--reload-dir", "/workspace/backend-python/core", "--reload-dir", "/workspace/backend-python/infra"]
