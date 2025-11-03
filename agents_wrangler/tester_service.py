from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

app = FastAPI(title="agents-wrangler tester-service", version="0.2.0")

DEMO_APP_DIR = Path(__file__).resolve().parent.parent / "demo_app"


class TestRunRequest(BaseModel):
    """
    Запрос на тестовый прогон.

    Можно передать либо один unified diff через поле `diff`,
    либо список диффов `diffs` для последовательного применения.
    """
    diff: str | None = None
    diffs: list[str] | None = None

    @field_validator("diffs")
    @classmethod
    def at_least_one(cls, v: list[str] | None, info) -> list[str] | None:
        return v

    def normalized_diffs(self) -> list[str]:
        """Возвращает список диффов вне зависимости от того, что прислал клиент."""
        if self.diffs and len(self.diffs) > 0:
            return self.diffs
        if self.diff:
            return [self.diff]
        raise ValueError("either `diff` or `diffs` must be provided")


class TestRunResult(BaseModel):
    """Результат прогонов pytest: агрегированные метрики и логи."""
    tests_total: int
    tests_passed: int
    tests_failed: int
    return_code: int
    stdout: str
    stderr: str


def _parse_pytest_summary(stdout: str) -> tuple[int, int, int]:
    """Извлекает total/passed/failed из вывода pytest."""
    total = passed = failed = 0
    for line in stdout.splitlines():
        if " passed" in line or " failed" in line or " error" in line:
            parts = line.strip().split()
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


def run_tests_on_diffs(diffs: list[str]) -> TestRunResult:
    """
    Копирует demo_app во временную директорию, последовательно применяет все диффы
    (через git apply с fallback на patch), затем запускает pytest и возвращает метрики.
    """
    work = Path(tempfile.mkdtemp(prefix="aw_demo_"))
    try:
        target = work / "demo_app"
        shutil.copytree(DEMO_APP_DIR, target)
        subprocess.run(["git", "init"], cwd=work, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "add", "."], cwd=work, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=work, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for i, diff in enumerate(diffs):
            patch_path = work / f"patch_{i}.diff"
            patch_path.write_text(diff, encoding="utf-8")
            rc = subprocess.run(["git", "apply", str(patch_path)], cwd=work).returncode
            if rc != 0:
                rc = subprocess.run(["patch", "-p0", "-i", str(patch_path)], cwd=work).returncode
            if rc != 0:
                raise RuntimeError(f"unable to apply patch #{i}")
            # Фиксируем состояние, чтобы контекст следующих патчей был актуален
            subprocess.run(["git", "add", "-A"], cwd=work, check=True)
            subprocess.run(["git", "commit", "-m", f"apply patch {i}"], cwd=work, check=True)

        proc = subprocess.run(
            ["pytest", "-q"],
            cwd=target,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(target)},
            timeout=60,
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


@app.post("/testrun", response_model=TestRunResult)
def testrun(req: TestRunRequest) -> TestRunResult:
    """HTTP‑обёртка поверх `run_tests_on_diffs`."""
    try:
        return run_tests_on_diffs(req.normalized_diffs())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
