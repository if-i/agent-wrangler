from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="codex-runner", version="0.2.0")

DEMO_APP_DIR = Path(__file__).resolve().parent.parent / "demo_app"
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
DEFAULT_MODEL = os.environ.get("CODEX_MODEL", "qwen2.5-coder:7b-instruct")


class Plan(BaseModel):
    """План работ от архитектора."""
    components: list[dict]


class Review(BaseModel):
    """Финальная оценка результата."""
    score: float
    rationale: str


class PlanRequest(BaseModel):
    """Запрос на планирование архитектуры задачи."""
    task: str = Field(..., description="Описание цели")
    model: str | None = None


class ImplementRequest(BaseModel):
    """Запрос на реализацию патча для задачи."""
    task: str = Field(..., description="Описание цели")
    model: str | None = None


class ReviewRequest(BaseModel):
    """Запрос на финальный ревью набора патчей."""
    task: str = Field(..., description="Описание цели")
    diffs: list[str] = Field(..., description="Список unified diff")
    model: str | None = None


class PatchResponse(BaseModel):
    """Единичный unified diff и логи запуска Codex."""
    diff: str
    stdout: str
    stderr: str


def _run(cmd: list[str], cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    """Запускает команду в каталоге `cwd` с таймаутом, возвращает CompletedProcess."""
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def _ensure_repo(root: Path) -> None:
    """Инициализирует git-репозиторий с baseline-коммитом для последующих diff."""
    subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _json_from_text(text: str) -> dict:
    """Пытается извлечь JSON-объект из произвольного текста stdout Codex."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in Codex output")
    return json.loads(text[start:end + 1])


def _diff(root: Path) -> str:
    """Возвращает unified diff текущего состояния относительно baseline."""
    proc = subprocess.run(["git", "diff"], cwd=root, capture_output=True, text=True)
    return proc.stdout


@app.post("/codex/plan", response_model=Plan)
def codex_plan(req: PlanRequest) -> Plan:
    """
    Просит локальный Codex сформировать JSON-план задачи.
    Ожидается строгое JSON-представление: {"components":[{"name":"...","target_files":["..."]}, ...]}.
    """
    work = Path(tempfile.mkdtemp(prefix="aw_codex_plan_"))
    try:
        target = work / "demo_app"
        shutil.copytree(DEMO_APP_DIR, target)
        model = req.model or DEFAULT_MODEL
        prompt = (
            "ROLE: Software Architect\n"
            "Output STRICT JSON: {\"components\":[{\"name\":\"...\",\"target_files\":[\"...\"]}]}\n"
            f"Goal:\n{req.task}\n"
        )
        proc = _run([CODEX_BIN, "--oss", "-m", model, "exec", prompt], cwd=target)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "codex exec failed")
        data = _json_from_text(proc.stdout)
        return Plan(components=data.get("components", []))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        shutil.rmtree(work, ignore_errors=True)


@app.post("/codex/implement", response_model=PatchResponse)
def codex_implement(req: ImplementRequest) -> PatchResponse:
    """
    Просит локальный Codex внести правки в копию demo-приложения и возвращает unified diff.
    Используется неинтерактивный режим `codex exec`.
    """
    work = Path(tempfile.mkdtemp(prefix="aw_codex_impl_"))
    try:
        target = work / "demo_app"
        shutil.copytree(DEMO_APP_DIR, target)
        _ensure_repo(work)
        model = req.model or DEFAULT_MODEL
        prompt = (
            "ROLE: Senior Implementer\n"
            "Edit files to achieve the goal and keep changes minimal.\n"
            f"Goal:\n{req.task}\n"
        )
        proc = _run([CODEX_BIN, "--oss", "-m", model, "exec", prompt], cwd=target)
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


@app.post("/codex/review", response_model=Review)
def codex_review(req: ReviewRequest) -> Review:
    """
    Просит локальный Codex дать короткий JSON-вердикт по набору патчей.
    Ожидается строгое JSON-представление: {"score": 0..1, "rationale": "..."}.
    """
    work = Path(tempfile.mkdtemp(prefix="aw_codex_review_"))
    try:
        target = work / "demo_app"
        shutil.copytree(DEMO_APP_DIR, target)
        model = req.model or DEFAULT_MODEL
        patches = "\n---\n".join(req.diffs)
        prompt = (
            "ROLE: Senior Reviewer\n"
            "Assess the proposed patches and return STRICT JSON {\"score\": <0..1>, \"rationale\": \"...\"}.\n"
            f"Goal:\n{req.task}\nPatches:\n{patches}\n"
        )
        proc = _run([CODEX_BIN, "--oss", "-m", model, "exec", prompt], cwd=target)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "codex exec failed")
        data = _json_from_text(proc.stdout)
        return Review(score=float(data.get("score", 0.5)), rationale=str(data.get("rationale", "n/a")))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        shutil.rmtree(work, ignore_errors=True)
