from __future__ import annotations

import itertools

import httpx
import pytest
import respx

from agents_wrangler.orchestrator import (
    bridge_best_of_n,
    bridge_multi,
)

GOOD_DIFF = (
    "diff --git a/demo_app/app.py b/demo_app/app.py\n"
    "--- a/demo_app/app.py\n+++ b/demo_app/app.py\n@@\n-    return a - b\n+    return a + b\n"
)
BAD_DIFF = (
    "diff --git a/demo_app/app.py b/demo_app/app.py\n"
    "--- a/demo_app/app.py\n+++ b/demo_app/app.py\n@@\n-    return a - b\n+    return a - b - 1\n"
)

@pytest.fixture()
def endpoints() -> dict[str, str]:
    """Возвращает фиктивные URL сервисов для мокирования."""
    return {
        "plan": "http://codex-arch:7002",
        "build1": "http://codex-build-1:7002",
        "build2": "http://codex-build-2:7002",
        "build3": "http://codex-build-3:7002",
        "review": "http://codex-review:7002",
        "tester": "http://tester:7001",
    }

@respx.mock
@pytest.mark.parametrize("good_index", [0, 1, 2])
def test_best_of_n_picks_good(endpoints: dict[str, str], good_index: int) -> None:
    """Проверяет, что best-of-N выбирает кандидата с корректным патчем."""
    # Мокаем билд-эндпоинты
    build_urls = [endpoints["build1"], endpoints["build2"], endpoints["build3"]]
    for i, url in enumerate(build_urls):
        respx.post(f"{url}/codex/implement").mock(
            return_value=httpx.Response(200, json={"diff": GOOD_DIFF if i == good_index else BAD_DIFF, "stdout": "", "stderr": ""})
        )
    # Мокаем тестер: "зелено", если есть GOOD_DIFF
    def _testrun_response(request: httpx.Request) -> httpx.Response:
        body = request.json()
        diffs = "".join(body.get("diffs", []))
        failed = 0 if "return a + b" in diffs else 1
        return httpx.Response(200, json={"tests_total": 1, "tests_passed": 1 - failed, "tests_failed": failed, "return_code": 0 if failed == 0 else 1, "stdout": "", "stderr": ""})

    respx.post(f"{endpoints['tester']}/testrun").mock(side_effect=_testrun_response)

    with httpx.Client() as client:
        res = bridge_best_of_n(client, "Fix add()", build_urls, endpoints["tester"])
    assert res.winner_index == good_index
    assert res.candidate_tests[good_index].tests_failed == 0

@respx.mock
def test_multi_bridge_accepts_specialists(endpoints: dict[str, str]) -> None:
    """Проверяет, что мультиконвейер принимает полезные спец-диффы и проходит тесты."""
    # План с одним компонентом
    respx.post(f"{endpoints['plan']}/codex/plan").mock(
        return_value=httpx.Response(200, json={"components": [{"name": "fix_add_function", "target_files": ["demo_app/app.py"]}]})
    )
    # Билдеры: base (good, bad, bad)
    build_urls = [endpoints["build1"], endpoints["build2"], endpoints["build3"]]
    respx.post(f"{build_urls[0]}/codex/implement").mock(return_value=httpx.Response(200, json={"diff": GOOD_DIFF, "stdout": "", "stderr": ""}))
    respx.post(f"{build_urls[1]}/codex/implement").mock(return_value=httpx.Response(200, json={"diff": BAD_DIFF, "stdout": "", "stderr": ""}))
    respx.post(f"{build_urls[2]}/codex/implement").mock(return_value=httpx.Response(200, json={"diff": BAD_DIFF, "stdout": "", "stderr": ""}))
    # Специалисты: безвредный патч (новый файл)
    SPEC_DIFF = (
        "diff --git a/demo_app/_meta_spec.py b/demo_app/_meta_spec.py\n"
        "new file mode 100644\n--- /dev/null\n+++ b/demo_app/_meta_spec.py\n@@\n+META=1\n"
    )
    for url in build_urls:
        respx.post(f"{url}/codex/implement").mock(return_value=httpx.Response(200, json={"diff": SPEC_DIFF, "stdout": "", "stderr": ""}))

    # Тестер: зелено, если есть GOOD_DIFF; остальные диффы не ухудшают.
    def _testrun_response(request: httpx.Request) -> httpx.Response:
        body = request.json()
        diffs = "".join(body.get("diffs", []))
        failed = 0 if "return a + b" in diffs else 1
        return httpx.Response(200, json={"tests_total": 1, "tests_passed": 1 - failed, "tests_failed": failed, "return_code": 0 if failed == 0 else 1, "stdout": "", "stderr": ""})

    respx.post(f"{endpoints['tester']}/testrun").mock(side_effect=_testrun_response)

    # Ревью
    respx.post(f"{endpoints['review']}/codex/review").mock(return_value=httpx.Response(200, json={"score": 0.93, "rationale": "looks good"}))

    with httpx.Client() as client:
        out = bridge_multi(
            client=client,
            task="Fix add() to return a + b",
            plan_urls=[endpoints["plan"]],
            builder_urls=build_urls,
            review_urls=[endpoints["review"]],
            tester_url=endpoints["tester"],
            specialists_per_component=2,
        )

    assert out.final_tests.tests_failed == 0
    assert any("return a + b" in d for d in out.accepted_diffs)
    assert out.review.score > 0.5
