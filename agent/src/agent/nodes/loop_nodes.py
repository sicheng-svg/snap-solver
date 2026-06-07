"""
nodes/loop_nodes.py —— 循环辅助节点。

bump_retry:在"决定要重解"时把 retry_count +1。
  单独成节点的好处:计数只在真正重解时发生(由 route_after_review 路由到这里),
  逻辑清晰,不和 solver 的求解逻辑混在一起。
"""

from ..state import SolveState

from langgraph.config import get_stream_writer


def bump_retry_node(state: SolveState) -> SolveState:
    """重解前自增循环计数。"""
    retry = state.get("retry_count", 0) + 1
    trace = state.get("trace", []) + [f"bump_retry->{retry}"]

    # 推送重解提示(暴露自我纠错过程)
    writer = get_stream_writer()
    reason = state.get("review_reason") or "解答存在问题"
    writer({
        "type": "thinking",
        "stage": "retry",
        "content": f"发现问题:{reason}。正在第 {retry} 次重新求解…",
    })

    return {"retry_count": retry, "trace": trace}