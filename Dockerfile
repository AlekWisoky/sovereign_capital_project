
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PYTHONPATH=/app/backend

WORKDIR /app

COPY backend/requirements.txt backend/requirements-dev.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
RUN chmod +x /app/backend/scripts/start-server.sh

EXPOSE 8000

CMD ["/app/backend/scripts/start-server.sh"]
