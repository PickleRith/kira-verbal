# API and voice worker image. Build from the REPOSITORY ROOT (it needs data/lessons):
#   docker build -f backend/Dockerfile -t kira-verbal-api .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend

# Editable install keeps app/ at /srv/backend/app, so the code finds /srv/data/lessons.
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install -e ".[voice]"

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/start.sh ./
COPY data/lessons /srv/data/lessons

RUN useradd --create-home --uid 10001 app && chmod +x start.sh
USER app
EXPOSE 8000

# API: migrate, seed lessons (idempotent), serve. The voice worker overrides the command:
#   python -m app.voice.worker start
CMD ["./start.sh"]
