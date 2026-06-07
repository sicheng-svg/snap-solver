"""
nodes/review.py —— Reviewer 复审节点(两类题公共)。

职责:综合判断解答是否过关,产出 review_passed(+ 不通过原因)。
  - 它是循环的【唯一决策证据来源】:reviewer 判完,后面的条件边据 review_passed
    + retry_count 决定是否打回 solver。reviewer 本身不控制流向(那是路由函数的事)。
  - 与 verify 分工:verify 管"算得对不对"(机器、确定性),
    reviewer 管"讲得对不对"(语义、综合)。

处理两种输入情形:
  1. 计算题:带着 verify_result 三态(True/False/skipped)作为证据复审。
  2. 论述题:题型路由让它绕开了 verify,没有 verify_result,reviewer 纯语义判断
     (概念准不准、要点全不全、有没有答非所问)。

用结构化输出(DeepSeek: function_calling)产出 ReviewResult。
"""

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from ..state import SolveState
from ..llm import get_llm


class ReviewResult(BaseModel):
    """复审的结构化结论。"""

    review_passed: bool = Field(
        description="解答是否过关。推导逻辑严谨、答案正确、覆盖题目要求则 True;否则 False。"
    )
    reason: str = Field(
        default="",
        description="不通过的具体原因(哪一步错、漏了什么、概念有何问题)。通过时可留空。",
    )


_SYSTEM = (
    "你是一位严谨的复审老师,负责审查另一位老师给出的解答质量。"
    "你要独立判断解答是否过关,而不是盲目认可。"
    "审查维度:推导逻辑是否严谨、有无跳步或错误、答案是否正确、"
    "是否完整覆盖题目要求(论述题尤其看概念准确性与要点完整性)。"
    "如果提供了'工具验证结论',把它作为重要证据:验证通过则重点复核推导过程,"
    "验证失败则解答很可能有误,验证无法判定时你需独立判断。"
)


def _format_verify_evidence(state: SolveState) -> str:
    """把 verify_result 三态整理成给 reviewer 的证据文字。
    没有 verify_result(论述题绕开了 verify)则返回空,reviewer 纯语义判断。"""
    vr = state.get("verify_result")
    if not vr:
        return ""  # 论述题:无工具验证,reviewer 靠语义

    passed = vr.get("passed")
    msg = vr.get("msg", "")
    if passed is True:
        return f"\n\n【工具验证结论】通过。{msg}"
    if passed is False:
        return f"\n\n【工具验证结论】未通过!{msg}\n请重点核查此处。"
    # skipped / None
    return f"\n\n【工具验证结论】无法用工具判定({msg}),请你独立用推导逻辑判断。"


def reviewer_node(state: SolveState) -> SolveState:
    """Reviewer 复审节点。读 question_text + solution + verify_result,
    产出 review_passed(+ reason)。"""
    trace = state.get("trace", []) + ["reviewer"]

    question_text = state.get("question_text", "")
    solution = state.get("solution", "")
    evidence = _format_verify_evidence(state)

    user_content = (
        f"题目:\n{question_text}\n\n"
        f"待审查的解答:\n{solution}"
        f"{evidence}\n\n"
        "请判断这份解答是否过关。"
    )
    messages = [SystemMessage(content=_SYSTEM), HumanMessage(content=user_content)]

    llm = get_llm("reviewer").with_structured_output(ReviewResult, method="function_calling")
    result: ReviewResult = llm.invoke(messages)

    return {
        "review_passed": result.review_passed,
        # 不通过原因写进 verify_result 不合适(那是工具的),单独留在 state 供重解参考。
        # 复用 verify_result 的 msg 会污染语义,所以这里把复审原因并入一个独立通道:
        # 直接更新 review 相关信息。重解时 solver 的 _build_retry_hint 读 review_passed。
        "review_reason": result.reason,
        "trace": trace,
    }