from __future__ import annotations

import shutil
import pytest

from agents_wrangler.codex_runner_service import (
    PlanRequest, ImplementRequest, ReviewRequest,
    codex_plan, codex_implement, codex_review,
)

CODEx_PRESENT = shutil.which("codex") is not None


@pytest.mark.skipif(not CODEx_PRESENT, reason="codex binary is not available")
def test_codex_plan_smoke() -> None:
    """Проверяет, что Codex способен вернуть валидный план в JSON."""
    plan = codex_plan(PlanRequest(task="Fix add() to return a + b"))
    assert isinstance(plan.components, list)

@pytest.mark.skipif(not CODEx_PRESENT, reason="codex binary is not available")
def test_codex_implement_smoke() -> None:
    """Проверяет, что Codex способен вернуть непустой unified diff."""
    resp = codex_implement(ImplementRequest(task="Fix add() to return a + b"))
    assert "diff --git" in resp.diff

@pytest.mark.skipif(not CODEx_PRESENT, reason="codex binary is not available")
def test_codex_review_smoke() -> None:
    """Проверяет, что Codex способен вернуть JSON-оценку."""
    good = """\
diff --git a/demo_app/app.py b/demo_app/app.py
--- a/demo_app/app.py
+++ b/demo_app/app.py
@@
-    return a - b
+    return a + b
"""
    review = codex_review(ReviewRequest(task="Fix add()", diffs=[good]))
    assert 0.0 <= review.score <= 1.0
    assert isinstance(review.rationale, str)
