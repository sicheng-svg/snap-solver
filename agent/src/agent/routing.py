"""
routing.py —— 所有【路由函数】集中地。

契约:读 state -> 返回去向字符串。不调 LLM、无副作用,纯粹轻量。

含:
  - route_by_intent      软分流后:解题 / 问概念
  - route_by_qtype       题型路由:计算题 -> verify;论述题 -> 直接 reviewer
  - route_after_review   验证循环核心:不过且没超限 -> 回 solver;通过/超限 -> 离开
  - route_by_diagram     配图判断:需要配图 -> draw;否则 -> 直接 teach_output
"""

from typing import Literal
from .state import SolveState
from .config import MAX_RETRY


def route_by_intent(state: SolveState) -> Literal["solver", "direct_answer"]:
    """软分流后:解题 -> solver;问概念 -> direct_answer。"""
    return "solver" if state.get("intent") == "solve" else "direct_answer"


def route_by_qtype(state: SolveState) -> Literal["verify", "reviewer"]:
    """题型路由:计算题 -> verify;论述题 -> 直接 reviewer。"""
    return "verify" if state.get("question_type") == "calc" else "reviewer"


def route_after_review(state: SolveState) -> Literal["retry", "draw", "teach_output"]:
    """验证循环 + 配图判断的合并决策:
    - 不通过且未超上限 -> retry(回 solver)
    - 通过 或 超上限降级 -> 再看 needs_diagram:需配图 -> draw,否则 -> teach_output
    """
    if state.get("review_passed") or state.get("retry_count", 0) >= MAX_RETRY:
        if state.get("needs_diagram"):
            return "draw"
        return "teach_output"
    return "retry"

def route_by_image(state: SolveState) -> Literal["recognize", "soft_route"]:
    """硬分流:有图片 -> VLM 识题;无图 -> 软分流。纯代码判断,不调 LLM。"""
    return "recognize" if state.get("image") is not None else "soft_route"


# def route_by_diagram(state: SolveState) -> Literal["draw", "teach_output"]:
#     """配图判断:解法需要配图/表 -> draw 生成;否则直接进教学输出。
#     needs_diagram 由 solver 顺带判断写入。"""
#     return "draw" if state.get("needs_diagram") else "teach_output"