# agents-wrangler (Python)

Launcher and test service for a local "bridge between agents".

Use it together with the neighbouring repository **agents-wrangler-core** (Rust).

## Quick start

```bash
# place both repositories side by side:
# ~/work/agent-wrangler
# ~/work/agents-wrangler-core
cd ~/work/agent-wrangler
docker compose up --build
```

Submit a task:

```bash
aw submit --task "Fix add() to return a + b" --builders 3
# or using curl
curl -s -X POST http://localhost:8080/api/v1/bridge \
  -H "content-type: application/json" \
  -d '{"task":"Fix add() to return a + b","builders":3}' | jq .
```

Multiagent bridge:

```bash
aw submit-multi --task "Fix add() to return a + b" --builders 3 --reviewers 2 --specialists 2
```

### What the tester-service does

It accepts a unified diff, applies it to a copy of `demo_app`, runs pytest, and returns aggregated metrics.
