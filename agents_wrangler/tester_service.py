from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="agents-wrangler tester-service", version="0.1.0")

DEMO_APP_DIR = Path(__file__).resolve().parent.parent / "demo_app"


class TestRunRequest(BaseModel):
    """Запрос на тестовый прогоn: unified diff, который нужно применить к demo_app."""
    diff: str


class TestRunResult(BaseModel):
    """Результат тестов: агрегированные метрики и сырые логи pytest."""
    tests_total: int
    tests_passed: int
    tests_failed: int
    return_code: int
    stdout: str
    stderr: str


def run_tests_on_diff(diff: str) -> TestRunResult:
    """
    Копирует demo_app в временную директорию, применяет unified diff через git/patch,
    запускает pytest и возвращает агрегированные метрики.
    """
    work = Path(tempfile.mkdtemp(prefix="aw_demo_"))
    try:
        target = work / "demo_app"
        shutil.copytree(DEMO_APP_DIR, target)
        subprocess.run(["git", "init"], cwd=work, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "add", "."], cwd=work, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=work, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        patch_path = work / "patch.diff"
        patch_path.write_text(diff, encoding="utf-8")

        # Пытаемся через git apply, затем patch как fallback.
        apply_rc = subprocess.run(["git", "apply", "patch.diff"], cwd=work).returncode
        if apply_rc != 0:
            apply_rc = subprocess.run(["patch", "-p0", "-i", "patch.diff"], cwd=work).returncode
        if apply_rc != 0:
            raise RuntimeError("unable to apply patch")

        proc = subprocess.run(
            ["pytest", "-q"],
            cwd=target,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(target)},
            timeout=45,
        )
        total, passed, failed = _parse_pytest_summary(proc.stdout)
        return TestRunResult(
            tests_total=total,
            tests_passed=passed,
            tests_failed=failed,
            return_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _parse_pytest_summary(stdout: str) -> tuple[int, int, int]:
    """Извлекает сводку из вывода pytest в формате total/passed/failed."""
    total = passed = failed = 0
    for line in stdout.splitlines():
        if " passed" in line or " failed" in line or " error" in line:
            # Пример: "3 passed in 0.05s"
            parts = line.strip().split()
            # Суммируем по встречающимся ключам
            for i, tok in enumerate(parts):
                if tok.isdigit():
                    n = int(tok)
                    nxt = parts[i + 1] if i + 1 < len(parts) else ""
                    if nxt.startswith("passed"):
                        passed = n
                    if nxt.startswith("failed"):
                        failed = n
            total = max(total, passed + failed)
    return total, passed, failed


@app.post("/testrun", response_model=TestRunResult)
def testrun(req: TestRunRequest) -> TestRunResult:
    """HTTP‑обёртка над `run_tests_on_diff`: выполняет патч+pytest и возвращает метрики."""
    try:
        return run_tests_on_diff(req.diff)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
