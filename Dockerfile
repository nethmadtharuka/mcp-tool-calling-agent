# Pinned by digest so every rebuild starts from the exact same base image.
FROM python:3.13-slim@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN useradd --system --uid 10001 --no-create-home app

# Dependencies before code, so editing app/ doesn't reinstall packages.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Files stay owned by root and the app runs as a non-root user, so the
# app can't modify its own code. No secrets here: config comes from
# runtime env vars (see README "Docker").
COPY app/ ./app/
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

# uvicorn directly, not run.py (which uses reload=True, dev only).
# 0.0.0.0 is needed inside the container; the host publishes the port on
# 127.0.0.1 only.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
