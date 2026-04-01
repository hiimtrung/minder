from __future__ import annotations

from pathlib import Path
from typing import cast

from minder.graph.state import GraphState


class RetrieverNode:
    def __init__(self, top_k: int = 5) -> None:
        self._top_k = top_k

    def run(self, state: GraphState) -> GraphState:
        repo_path = Path(state.repo_path or ".")
        query_terms = {term for term in state.query.lower().split() if len(term) > 2}
        candidates: list[dict[str, object]] = []
        if repo_path.exists():
            for path in repo_path.rglob("*"):
                if not path.is_file():
                    continue
                if any(part.startswith(".") and part != ".minder" for part in path.parts):
                    continue
                if path.suffix not in {".py", ".md", ".txt", ".json"}:
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                lowered = content.lower()
                score = sum(lowered.count(term) for term in query_terms)
                if score == 0 and query_terms:
                    continue
                candidates.append(
                    {
                        "title": path.name,
                        "path": str(path),
                        "content": content,
                        "score": float(score),
                        "doc_type": "code" if path.suffix == ".py" else "markdown",
                    }
                )
        ranked = sorted(
            candidates,
            key=lambda item: cast(float, item["score"]),
            reverse=True,
        )
        state.retrieved_docs = ranked[: self._top_k]
        state.reranked_docs = list(state.retrieved_docs)
        return state
