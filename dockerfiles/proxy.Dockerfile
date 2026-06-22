FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY dockerfiles/requirements/proxy.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src/ /app/src/
COPY config/ /app/config/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
  CMD python -c "import socket; s=socket.create_connection(('localhost',8080),2)" || exit 1

CMD ["mitmdump", "--listen-host", "0.0.0.0", "--listen-port", "8080", \
     "--mode", "regular", "--ssl-insecure", \
     "--set", "block_global=false", \
     "-s", "src/proxy/interceptor.py"]
