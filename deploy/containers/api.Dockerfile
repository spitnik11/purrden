FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY apps/api/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock

COPY apps/api /app
COPY apps/worker /app/apps/worker
COPY apps/scheduler /app/apps/scheduler
# Shared domain packages available for later ports
COPY packages/spawn-engine-py /packages/spawn-engine-py
COPY packages/domain-python /packages/domain-python
ENV PYTHONPATH=/app:/packages/spawn-engine-py:/packages/domain-python
RUN useradd --create-home --uid 10001 purrden
USER purrden

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

CMD ["uvicorn", "purrden_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
