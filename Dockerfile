# Voice agent image for LiveKit Cloud agent hosting (`lk agent create` / `lk agent deploy`
# run from the repository root, which is the build context). The API and website have their
# own Dockerfiles in backend/ and frontend/ (used by Render, see render.yaml).
#
# Follows https://docs.livekit.io/deploy/agents/builds/: glibc slim base, explicit WORKDIR,
# unprivileged user, fixed `start` command, no secrets in the image. LIVEKIT_URL,
# LIVEKIT_API_KEY and LIVEKIT_API_SECRET are injected by LiveKit Cloud at runtime; the
# agent's own settings (KIRA_API_URL, VOICE_WORKER_SECRET, VOICE_AGENT_NAME) are LiveKit
# Cloud secrets.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first for layer caching, then the code.
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install ".[voice]"

RUN useradd --create-home --uid 10001 agent
USER agent

CMD ["python", "-m", "app.voice.worker", "start"]
