# syntax=docker/dockerfile:1

# Stage 1: install dependencies into a virtualenv.
FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

# Stage 2: runtime image with only the virtualenv and the package.
FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN useradd --create-home --uid 10001 app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app sea_route ./sea_route

USER app
EXPOSE 5018

# /health stays open even when SEA_ROUTE_TOKEN is set. No curl in the image, so use Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5018/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "sea_route.app:app", "--host", "0.0.0.0", "--port", "5018"]
