FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY dockerfiles/requirements/dashboard_api.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src/ /app/src/
COPY config/ /app/config/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 9443

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
  CMD python -c "import httpx; c=httpx.Client(cert=('/app/certs/mtls/dashboard_api.crt','/app/certs/mtls/dashboard_api.key'),verify=False); c.get('https://localhost:9443/health')" || exit 1

CMD ["python", "-m", "src.dashboard.api.main"]
