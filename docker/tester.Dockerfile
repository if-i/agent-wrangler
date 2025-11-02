FROM python:3.14-slim

# Инструменты для применения unified diff
RUN apt-get update && apt-get install -y --no-install-recommends git patch && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -e . uvicorn fastapi pytest

# Кладём демо‑проект внутрь контейнера — тестраннер копирует его в tmp
COPY agents_wrangler /app/agents_wrangler
COPY demo_app /app/demo_app

EXPOSE 7001
CMD ["uvicorn", "agents_wrangler.tester_service:app", "--host", "0.0.0.0", "--port", "7001"]
