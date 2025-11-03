FROM python:3.13-slim

ARG CODEX_VERSION=0.53.0
WORKDIR /app

# Базовые утилиты: git/patch/curl для патчей и скачивания бинаря codex
RUN apt-get update && apt-get install -y --no-install-recommends git patch curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Устанавливаем Codex CLI (Linux x86_64 musl) из GitHub Releases
RUN curl -fsSL -o /tmp/codex.tar.gz \
      https://github.com/openai/codex/releases/download/${CODEX_VERSION}/codex-x86_64-unknown-linux-musl.tar.gz \
 && tar -xzf /tmp/codex.tar.gz -C /usr/local/bin \
 && mv /usr/local/bin/codex-x86_64-unknown-linux-musl /usr/local/bin/codex \
 && chmod +x /usr/local/bin/codex

# Конфиг Codex → указываем локальный провайдер Ollama (OpenAI-совместимый /v1)
RUN mkdir -p /root/.codex
RUN printf '%s\n' \
  'model = "qwen2.5-coder:7b-instruct"' \
  'model_provider = "ollama"' \
  '' \
  '[model_providers.ollama]' \
  'name = "Ollama"' \
  'base_url = "http://ollama:11434/v1"' \
  'wire_api = "chat"' \
  > /root/.codex/config.toml

# Python: сам сервис-обёртка
COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir fastapi uvicorn pydantic==2.* httpx pytest

COPY agents_wrangler /app/agents_wrangler
COPY demo_app /app/demo_app

EXPOSE 7002
CMD ["uvicorn", "agents_wrangler.codex_runner_service:app", "--host", "0.0.0.0", "--port", "7002"]
