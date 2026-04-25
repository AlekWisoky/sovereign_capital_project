
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PYTHONPATH=/app/backend

WORKDIR /app/backend

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY victor_ai_bot ./victor_ai_bot
COPY config ./config
COPY data ./data
COPY scripts ./scripts
RUN chmod +x ./scripts/start-server.sh

EXPOSE 8000

CMD ["./scripts/start-server.sh"]
