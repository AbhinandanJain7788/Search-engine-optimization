# Claude SEO frontend deploy image
# Uses the official Playwright Python image (Chromium + system deps pre-baked).
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium ships with this base image at /ms-playwright/.
# (We skip `playwright install` because it's already present.)

COPY app.py audit_runner.py commands.py ./
COPY static/ ./static/

# Where finished audit artifacts land. Ephemeral on Railway/Fly,
# survives restarts only if you mount a volume here.
RUN mkdir -p /app/runs

EXPOSE 7860

# Railway/Fly/Render all set $PORT. Default to 7860 locally.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860} --log-level info"]
