FROM python:3.11-slim

WORKDIR /app

# System deps for Presidio + PyThaiNLP + cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY config/versions.yaml /tmp/versions.yaml

# Install Python deps — versions pinned in versions.yaml, requirements.txt generated at build
COPY dockerfiles/requirements/orchestrator.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Download spaCy + PyThaiNLP models
RUN python -m spacy download en_core_web_sm || true
RUN python -c "import pythainlp; pythainlp.corpus.download('orchid_ud')" || true

COPY src/ /app/src/
COPY config/ /app/config/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8443
EXPOSE 9090

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
  CMD python -c "import httpx; c=httpx.Client(cert=('/app/certs/mtls/orchestrator.crt','/app/certs/mtls/orchestrator.key'),verify=False); c.get('https://localhost:8443/health')" || exit 1

CMD ["python", "-m", "src.orchestrator.main"]
