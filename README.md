# agents-wrangler (Python)

Launcher and test service for a local "bridge between agents".

Use it together with the neighbouring repository **agents-wrangler-core** (Rust).

## Getting Started (Docker Compose)

> Clone two repos side by side:
>
> ```
> ~/work/agent-wrangler        # Python (this repo)
> ~/work/agents-wrangler-core  # Rust core
> ```

### 1) Build & run services

```bash
docker compose up --build
# core -> http://localhost:8080
# tester -> http://localhost:7001
```

### 2) Install CLI (host)

```bash
# choose one:
pipx install -e .
# or
python -m venv .venv && source .venv/bin/activate && pip install -e .
```

### 3) Send a task (best-of-N bridge)

```bash
aw submit --task "Fix add() to return a + b" --builders 3
# or via curl
curl -s -X POST http://localhost:8080/api/v1/bridge \
  -H "content-type: application/json" \
  -d '{"task":"Fix add() to return a + b","builders":3}' | jq .
```

### 4) (Optional) Real LLM backend

Set envs in compose.yaml:

```yaml
services:
  core:
    environment:
      USE_MOCK_LLM: "0"
      OPENAI_API_KEY: "<your key>"
      OPENAI_BASE_URL: "https://api.openai.com"
      OPENAI_MODEL: "gpt-4o-mini"
```

### 5) (Optional) Multi-agent pipeline

```bash
aw submit-multi --task "Fix add() to return a + b" --builders 3 --reviewers 2 --specialists 2
```

### 6) Tests

```bash
pytest -q
# and for the Rust core:
# cd ../agents-wrangler-core && cargo test
```
