from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DEMO_APP_DIR = Path(__file__).resolve().parent.parent / "demo_app"
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
DEFAULT_MODEL = os.environ.get("CODEX_MODEL", "qwen2.5-coder:7b-instruct")

app = FastAPI(title="codex-runner", version="0.1.0")


class PatchRequest(BaseModel):
    """Запрос к локальному Codex: сформировать патч под задачу."""
    task: str = Field(..., description="Человеческое описание цели")
    model: str | None = Field(None, description="Имя модели для Codex в OSS-режиме (Ollama/vLLM)")


class PatchResponse(BaseModel):
    """Ответ с полученным unified diff и сырыми логами."""
    diff: str
    stdout: str
    stderr: str


def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    """Запускает команду в каталоге `cwd` с таймаутом, возвращает CompletedProcess."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def _ensure_repo(root: Path) -> None:
    """Инициализирует git-репозиторий с baseline-коммитом для расчёта diff."""
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _diff(root: Path) -> str:
    """Возвращает unified diff текущего состояния относительно baseline."""
    proc = subprocess.run(["git", "diff"], cwd=root, capture_output=True, text=True)
    return proc.stdout


@app.post("/codex/patch", response_model=PatchResponse)
def codex_patch(req: PatchRequest) -> PatchResponse:
    """
    Копирует demo-приложение, запускает `codex` в OSS-режиме над этой копией, затем возвращает unified diff.

    По умолчанию используется профиль с Ollama (`~/.codex/config.toml`), задающий локальный /v1.
    Это означает, что инференс выполняется локально; сеть не требуется.
    """
    work = Path(tempfile.mkdtemp(prefix="aw_codex_"))
    try:
        target = work / "demo_app"
        shutil.copytree(DEMO_APP_DIR, target)
        _ensure_repo(work)

        model = req.model or DEFAULT_MODEL
        # Неформатируемая, но строгая команда: codex изменяет файлы в каталоге.
        # Используем non-interactive режим через `exec`.
        proc = _run([CODEX_BIN, "--oss", "-m", model, "exec", req.task], cwd=target)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "codex exec failed")

        diff = _diff(work)
        if not diff.strip():
            raise RuntimeError("codex produced no changes")

        return PatchResponse(diff=diff, stdout=proc.stdout, stderr=proc.stderr)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        shutil.rmtree(work, ignore_errors=True)
