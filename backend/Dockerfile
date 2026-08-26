# Backend Dockerfile - FastAPI + Hy-MT2-7B
FROM nvcr.io/nvidia/pytorch:25.09-py3

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    HF_HOME=/models/.cache/huggingface

WORKDIR /app

# Install dependencies from the Tsinghua PyPI mirror
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

# Copy backend code
COPY main.py .
COPY entrypoint.py .

EXPOSE 8000

# Keep one worker so the GPU model is loaded only once
CMD ["uvicorn", "entrypoint:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
