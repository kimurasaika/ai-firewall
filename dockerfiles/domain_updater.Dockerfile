FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY dockerfiles/requirements/domain_updater.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src/ /app/src/
COPY config/ /app/config/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-c", "import asyncio; from src.domain_updater.updater import DomainUpdaterService; s=DomainUpdaterService(); s.start(); asyncio.get_event_loop().run_forever()"]
