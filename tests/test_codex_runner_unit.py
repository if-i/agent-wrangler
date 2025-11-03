from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from agents_wrangler.codex_runner_service import PatchRequest, codex_patch

CODEx_PRESENT = shutil.which("codex") is not None


@pytest.mark.skipif(not CODEx_PRESENT, reason="codex binary is not available in PATH")
def test_codex_patch_smoke() -> None:
    """Проверяет, что codex_runner_service способен вернуть непустой diff."""
    # Просим Codex исправить баг в demo_app (add должен складывать)
    req = PatchRequest(task="Fix add() to return a + b")
    resp = codex_patch(req)
    assert "diff --git" in resp.diff
    assert resp.diff.strip()


def test_patch_request_model_override() -> None:
    """Проверяет переопределение модели без вызова внешнего бинаря."""
    # Тест на dataclass-валидацию — без вызова codex
    req = PatchRequest(task="noop", model="qwen2.5-coder:7b-instruct")
    assert req.model == "qwen2.5-coder:7b-instruct"
