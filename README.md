# agents-wrangler (Python)

Запускалка и тест‑сервис для локального «моста между агентами».  
Используй в паре с соседним репозиторием **agents-wrangler-core** (Rust).

## Быстрый старт
```bash
# расположи оба репозитория рядом:
# ~/work/agents-wrangler
# ~/work/agents-wrangler-core
docker compose up --build
```

Отправить задачу:
```bash
aw submit --task "Fix add() to return a + b" --builders 3
# или через curl
curl -s -X POST http://localhost:8080/api/v1/bridge \
  -H "content-type: application/json" \
  -d '{"task":"Fix add() to return a + b","builders":3}' | jq .
```

Что делает tester-service

Принимает unified diff → применяет к копии demo_app → запускает pytest → возвращает метрики.
