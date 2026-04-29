"""
ClarificationNode — generates structured correction options before the LLM acts.

Triggers when PlanningNode detects a "correction" intent AND the query has not
already been confirmed by the user (clarification_done flag not set).

Short-circuits the retrieval/reasoning/LLM pipeline by writing directly to
llm_output so the existing transport/client path receives a well-formed answer.
"""

from __future__ import annotations

from minder.graph.state import GraphState

_CORRECTION_KEYWORDS = frozenset(
    {
        "fix memory",
        "update memory",
        "wrong memory",
        "incorrect memory",
        "outdated memory",
        "sai memory",
        "fix skill",
        "update skill",
        "wrong skill",
        "outdated skill",
        "deprecate skill",
        "mark deprecated",
        "delete memory",
        "delete skill",
        "remove memory",
        "remove skill",
        "correct this",
        "sửa memory",
        "cập nhật skill",
        "xóa memory",
    }
)


class ClarificationNode:
    """Intercepts correction-intent queries and presents the user with choices."""

    def run(self, state: GraphState) -> GraphState:
        if state.metadata.get("clarification_done"):
            return state

        intent = state.plan.get("intent", "")
        if intent != "correction":
            return state

        options = self._build_options(state.query)
        state.metadata["clarification_options"] = options
        state.metadata["needs_clarification"] = True
        state.llm_output = {
            "text": self._format_options(state.query, options),
            "provider": "clarification",
            "model": "clarification_node",
            "runtime": "internal",
        }
        return state

    # ------------------------------------------------------------------

    def _build_options(self, query: str) -> list[dict[str, str]]:
        q = query.lower()
        options: list[dict[str, str]] = []

        if any(k in q for k in ("memory", "lưu", "nhớ")):
            options = [
                {
                    "id": "update_memory",
                    "label": "Sửa nội dung memory",
                    "description": (
                        "Cập nhật title, content, hoặc tags của memory hiện tại "
                        "bằng cách dùng minder_memory_update với memory_id."
                    ),
                    "tool_hint": "minder_memory_recall → minder_memory_update",
                },
                {
                    "id": "delete_and_recreate",
                    "label": "Xóa và tạo lại",
                    "description": (
                        "Xóa memory sai, sau đó tạo memory mới với nội dung đúng."
                    ),
                    "tool_hint": "minder_memory_recall → minder_memory_delete → minder_memory_store",
                },
                {
                    "id": "compact_memories",
                    "label": "Compact các memory trùng lặp",
                    "description": (
                        "Nếu có nhiều memory tương tự, gộp lại thành một entry chuẩn."
                    ),
                    "tool_hint": "minder_memory_list → minder_memory_compact",
                },
            ]
        elif any(k in q for k in ("skill", "kỹ năng")):
            options = [
                {
                    "id": "update_skill",
                    "label": "Cập nhật nội dung skill",
                    "description": (
                        "Sửa content, tags, quality_score của skill bằng minder_skill_update."
                    ),
                    "tool_hint": "minder_skill_list → minder_skill_update",
                },
                {
                    "id": "deprecate_skill",
                    "label": "Đánh dấu skill deprecated",
                    "description": (
                        "Skill không còn phù hợp — đánh dấu deprecated=True để "
                        "ẩn khỏi recall, nhưng vẫn giữ trong lịch sử."
                    ),
                    "tool_hint": "minder_skill_list → minder_skill_update(deprecated=True)",
                },
                {
                    "id": "delete_skill",
                    "label": "Xóa skill hoàn toàn",
                    "description": "Xóa skill khỏi catalog nếu không còn cần thiết.",
                    "tool_hint": "minder_skill_list → minder_skill_delete",
                },
            ]
        else:
            options = [
                {
                    "id": "update_memory",
                    "label": "Sửa memory liên quan",
                    "description": "Tìm và cập nhật memory có nội dung sai.",
                    "tool_hint": "minder_memory_recall → minder_memory_update",
                },
                {
                    "id": "update_skill",
                    "label": "Cập nhật skill liên quan",
                    "description": "Tìm và cập nhật skill không còn phù hợp.",
                    "tool_hint": "minder_skill_recall → minder_skill_update",
                },
                {
                    "id": "workflow_correction",
                    "label": "Điều chỉnh workflow state",
                    "description": "Nếu workflow đang ở bước sai, dùng minder_workflow_guard để kiểm tra.",
                    "tool_hint": "minder_workflow_step → minder_workflow_guard",
                },
            ]

        return options

    @staticmethod
    def _format_options(query: str, options: list[dict[str, str]]) -> str:
        lines = [
            f'Tôi hiểu bạn muốn thực hiện một thao tác sửa đổi liên quan đến: "{query}".',
            "",
            "Bạn muốn làm gì?",
            "",
        ]
        for i, opt in enumerate(options, 1):
            lines.append(f"{i}. **{opt['label']}**")
            lines.append(f"   {opt['description']}")
            lines.append(f"   ↳ Tool gợi ý: `{opt['tool_hint']}`")
            lines.append("")
        lines.append(
            "Hãy cho tôi biết bạn chọn phương án nào (hoặc mô tả cụ thể hơn), "
            "và tôi sẽ thực hiện ngay."
        )
        return "\n".join(lines)
