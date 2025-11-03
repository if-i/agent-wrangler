from __future__ import annotations

import json
import textwrap
from typing import Iterable

import httpx
import streamlit as st

from agents_wrangler.orchestrator import (
    bridge_best_of_n,
    bridge_multi,
    codex_plan,
    codex_review,
    codex_implement,
    tester_run,
)


def _parse_urls(s: str) -> list[str]:
    """Разбирает список URL по строкам, игнорируя пустые строки и пробелы."""
    return [u.strip() for u in s.splitlines() if u.strip()]


def _show_diff(title: str, diff: str) -> None:
    """Показывает unified diff в виде кода."""
    st.markdown(f"**{title}**")
    st.code(diff, language="diff")


def main() -> None:
    """Streamlit‑UI для локального запуска мостов с несколькими инстансами Codex."""
    st.set_page_config(page_title="Agent Wrangler — Codex Orchestrator", layout="wide")
    st.title("Agent Wrangler — Codex Orchestrator (Local)")

    with st.sidebar:
        st.header("Endpoints")
        default_plan = "http://localhost:7003"
        default_builders = textwrap.dedent(
            """
            http://localhost:7002
            http://localhost:7004
            http://localhost:7005
            """
        ).strip()
        default_review = "http://localhost:7006"
        default_tester = "http://localhost:7001"

        plan_urls = _parse_urls(st.text_area("Codex Architect URL(s)", value=default_plan, height=80))
        builder_urls = _parse_urls(st.text_area("Codex Builder URL(s)", value=default_builders, height=120))
        review_urls = _parse_urls(st.text_area("Codex Reviewer URL(s)", value=default_review, height=80))
        tester_url = st.text_input("Tester URL", value=default_tester)

        st.header("Parameters")
        task = st.text_area("Task", value="Fix add() to return a + b", height=100)
        builders = st.number_input("Builders (for base best-of-N)", min_value=1, max_value=32, value=min(3, max(1, len(builder_urls))))
        specialists = st.number_input("Specialists per component", min_value=0, max_value=8, value=2)

    col1, col2 = st.columns(2)

    if col1.button("Run best-of‑N (Builders only)", use_container_width=True):
        with st.spinner("Running best-of‑N..."):
            with httpx.Client() as client:
                chosen_urls = builder_urls[: int(builders)] if builder_urls else []
                result = bridge_best_of_n(client, task, chosen_urls, tester_url)
        st.subheader("Best‑of‑N Result")
        for i, (d, tr) in enumerate(zip(result.candidate_diffs, result.candidate_tests)):
            mark = "✅" if i == result.winner_index and tr.tests_failed == 0 else ("⚠️" if tr.tests_failed == 0 else "❌")
            st.markdown(f"{mark} **Candidate #{i}** — passed: {tr.tests_passed}, failed: {tr.tests_failed}")
            _show_diff(f"Candidate #{i} diff", d)
        st.success(f"Winner: Candidate #{result.winner_index}")

    if col2.button("Run Multi‑Agent Pipeline", type="primary", use_container_width=True):
        if not plan_urls or not builder_urls or not review_urls:
            st.error("Provide at least one URL for each role (architect, builders, reviewer).")
        else:
            with st.spinner("Running multi‑agent pipeline..."):
                with httpx.Client() as client:
                    res = bridge_multi(
                        client=client,
                        task=task,
                        plan_urls=plan_urls,
                        builder_urls=builder_urls[: int(builders)] if builder_urls else [],
                        review_urls=review_urls,
                        tester_url=tester_url,
                        specialists_per_component=int(specialists),
                    )
            st.subheader("Plan")
            st.json(res.plan.model_dump())

            st.subheader("Base Best‑of‑N")
            for i, (d, tr) in enumerate(zip(res.base.candidate_diffs, res.base.candidate_tests)):
                mark = "✅" if i == res.base.winner_index and tr.tests_failed == 0 else ("⚠️" if tr.tests_failed == 0 else "❌")
                st.markdown(f"{mark} **Candidate #{i}** — passed: {tr.tests_passed}, failed: {tr.tests_failed}")
                _show_diff(f"Candidate #{i} diff", d)
            st.success(f"Base winner: Candidate #{res.base.winner_index}")

            st.subheader("Accepted Diffs (after specialists)")
            for i, d in enumerate(res.accepted_diffs):
                _show_diff(f"Accepted #{i}", d)

            st.subheader("Final Tests")
            st.json(res.final_tests.model_dump())

            st.subheader("Final Review")
            st.json(res.review.model_dump())


if __name__ == "__main__":
    main()
