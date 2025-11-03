from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Iterable

import httpx
from pydantic import BaseModel


class Plan(BaseModel):
    """JSON-план архитектора Codex."""
    components: list[dict]


class Review(BaseModel):
    """Итоговая оценка ревью Codex."""
    score: float
    rationale: str


class PatchResponse(BaseModel):
    """Единичный unified diff от Codex."""
    diff: str
    stdout: str
    stderr: str


class TestRunResult(BaseModel):
    """Результат тестов tester-service."""
    tests_total: int
    tests_passed: int
    tests_failed: int
    return_code: int
    stdout: str
    stderr: str


@dataclass
class BestOfNResult:
    """Результат best-of-N: кандидаты, их метрики и победитель."""
    candidate_diffs: list[str]
    candidate_tests: list[TestRunResult]
    winner_index: int


@dataclass
class MultiBridgeResult:
    """Результат мультиагентного конвейера."""
    plan: Plan
    base: BestOfNResult
    accepted_diffs: list[str]
    final_tests: TestRunResult
    review: Review


def _post_json(client: httpx.Client, url: str, payload: dict) -> dict:
    """Выполняет POST JSON и возвращает JSON-ответ как словарь."""
    r = client.post(url, json=payload, timeout=60.0)
    r.raise_for_status()
    return r.json()


def codex_plan(client: httpx.Client, codex_url: str, task: str) -> Plan:
    """Вызывает архитектора Codex и возвращает план работ."""
    data = _post_json(client, f"{codex_url.rstrip('/')}/codex/plan", {"task": task})
    return Plan.model_validate(data)


def codex_implement(client: httpx.Client, codex_url: str, task: str) -> PatchResponse:
    """Просит билдера Codex сгенерировать unified diff под задачу."""
    data = _post_json(client, f"{codex_url.rstrip('/')}/codex/implement", {"task": task})
    return PatchResponse.model_validate(data)


def codex_review(client: httpx.Client, codex_url: str, task: str, diffs: list[str]) -> Review:
    """Просит ревью Codex оценить набор диффов."""
    data = _post_json(client, f"{codex_url.rstrip('/')}/codex/review", {"task": task, "diffs": diffs})
    return Review.model_validate(data)


def tester_run(client: httpx.Client, tester_url: str, diffs: list[str]) -> TestRunResult:
    """Запускает pytest над копией демо-проекта, последовательно применяя диффы."""
    data = _post_json(client, f"{tester_url.rstrip('/')}/testrun", {"diffs": diffs})
    return TestRunResult.model_validate(data)


def bridge_best_of_n(
    client: httpx.Client,
    task: str,
    builder_urls: list[str],
    tester_url: str,
) -> BestOfNResult:
    """
    Параллельно запрашивает билдеров Codex, тестирует каждый diff и выбирает лучший по метрикам.
    Правило выбора: минимальные failures, при равенстве — максимальные passed.
    """
    diffs: list[str] = []
    for i, url in enumerate(builder_urls):
        resp = codex_implement(client, url, task)
        diffs.append(resp.diff)

    results: list[TestRunResult] = []
    winner_idx = 0
    best: TestRunResult | None = None
    for i, d in enumerate(diffs):
        tr = tester_run(client, tester_url, [d])
        results.append(tr)
        better = best is None or tr.tests_failed < best.tests_failed or (
            tr.tests_failed == best.tests_failed and tr.tests_passed > best.tests_passed
        )
        if better:
            best = tr
            winner_idx = i

    return BestOfNResult(candidate_diffs=diffs, candidate_tests=results, winner_index=winner_idx)


def bridge_multi(
    client: httpx.Client,
    task: str,
    plan_urls: list[str],
    builder_urls: list[str],
    review_urls: list[str],
    tester_url: str,
    specialists_per_component: int,
) -> MultiBridgeResult:
    """
    Мультиагентный конвейер: архитектор → билдеры → специалисты → финальный ревью.
    Специалисты добавляются жадно: дифф включается только если метрики не ухудшаются.
    """
    plan = codex_plan(client, plan_urls[0], task)

    base = bridge_best_of_n(client, task, builder_urls, tester_url)
    accepted = [base.candidate_diffs[base.winner_index]]
    current = tester_run(client, tester_url, accepted)

    if specialists_per_component > 0:
        for comp in plan.components:
            for s in range(specialists_per_component):
                prompt = (
                    f"Implement specialized improvements for component '{comp.get('name','?')}', "
                    f"focus files: {', '.join(comp.get('target_files', [])) or 'any'}."
                )
                spec_url = builder_urls[(len(accepted) + s) % len(builder_urls)]
                patch = codex_implement(client, spec_url, prompt).diff
                trial = accepted + [patch]
                tr = tester_run(client, tester_url, trial)
                better = tr.tests_failed < current.tests_failed or (
                    tr.tests_failed == current.tests_failed and tr.tests_passed >= current.tests_passed
                )
                if better:
                    accepted.append(patch)
                    current = tr

    review = codex_review(client, review_urls[0], task, accepted)
    return MultiBridgeResult(plan=plan, base=base, accepted_diffs=accepted, final_tests=current, review=review)
