from __future__ import annotations

import json
import sys
from typing import Any

import httpx
import typer

app = typer.Typer(help="CLI для общения с ядром Agent Wrangler.")


def _print_json(data: dict[str, Any]) -> None:
    """Красиво печатает JSON‑ответы."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


@app.command()
def submit(
    task: str = typer.Option(..., "--task", "-t", help="Человеческое описание задачи"),
    builders: int = typer.Option(3, "--builders", "-n", min=1, max=8, help="Число параллельных билдеров"),
    core_url: str = typer.Option("http://localhost:8080", "--core-url", help="Базовый URL ядра"),
) -> None:
    """Отправляет задачу в простой мост (best‑of‑N)."""
    payload = {"task": task, "builders": builders}
    with httpx.Client(timeout=60.0) as client:
        r = client.post(f"{core_url}/api/v1/bridge", json=payload)
        r.raise_for_status()
        _print_json(r.json())


@app.command("submit-multi")
def submit_multi(
    task: str = typer.Option(..., "--task", "-t", help="Описание цели"),
    builders: int = typer.Option(3, "--builders", "-n", min=1, max=8, help="Число билдеров"),
    reviewers: int = typer.Option(2, "--reviewers", "-k", min=0, max=8, help="Число ревьюеров"),
    specialists: int = typer.Option(2, "--specialists", "-s", min=0, max=8, help="Число специалистов на компонент"),
    core_url: str = typer.Option("http://localhost:8080", "--core-url", help="Базовый URL ядра"),
) -> None:
    """Отправляет задачу в мультиагентный мост: архитектор → билдеры → специалисты → финальный ревью."""
    payload = {
        "task": task,
        "builders": builders,
        "reviewers": reviewers,
        "specialists": specialists,
    }
    with httpx.Client(timeout=90.0) as client:
        r = client.post(f"{core_url}/api/v1/bridge/multi", json=payload)
        r.raise_for_status()
        _print_json(r.json())
