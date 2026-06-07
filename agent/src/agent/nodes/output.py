"""
nodes/output.py —— 输出类节点。

  - direct_answer:问概念轻路径终点(已有)。
  - teach_output:解题路径终点。把 solver 的 solution 重写成【教学讲解】并交付。

teach_output 与 solver 的区别:
  solver 的 solution 是"解题过程"(解题导向,还掺着给验证用的考量);
  teach_output 再调一次 LLM,把它重写成"给学生看的循序渐进分步讲解"(教学导向)。
  两者定位不同,值得专门生成 —— 多一次调用换更好的教学质量。
"""

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from ..state import SolveState
from ..llm import get_llm
from langgraph.config import get_stream_writer


# ============================================================
# direct_answer:问概念轻路径
# ============================================================
_DIRECT_ANSWER_SYSTEM = SystemMessage(content=(
    "你是一位耐心的理工科老师。学生会问你一些概念性问题"
    "(比如某个原理是什么、两个概念有什么区别)。"
    "请用清晰、循序渐进的方式讲解,必要时举例,但不要长篇大论。"
))


def direct_answer_node(state: SolveState) -> SolveState:
    """直接问答节点(问概念轻路径)。"""
    trace = state.get("trace", []) + ["direct_answer"]

    llm_messages = state.get("llm_messages")
    if not llm_messages:
        user_text = state.get("user_text", "")
        llm_messages = [HumanMessage(content=user_text)]

    messages = [_DIRECT_ANSWER_SYSTEM] + llm_messages
    resp = get_llm("solver").invoke(messages)
    answer = resp.content

    new_history = []
    user_text = state.get("user_text", "")
    if user_text:
        new_history.append(HumanMessage(content=user_text))
    new_history.append(AIMessage(content=answer))

    return {"final_output": answer, "messages": new_history, "trace": trace}


# ============================================================
# teach_output:解题路径终点
# ============================================================
_TEACH_SYSTEM = SystemMessage(content=(
    "你是一位耐心的理工科老师,要把一份解题过程讲给学生听。"
    "请按两部分组织输出:\n\n"
    "## 解题思路\n"
    "用循序渐进的方式讲清这道题怎么想:关键在哪、为什么用这个方法、"
    "每一步的依据是什么。帮助学生理解,而不只是记住答案。\n\n"
    "## 解答过程\n"
    "给出可以直接写在试卷上的完整、规范的解答:步骤工整、推导完整、"
    "符号规范,最后明确写出答案。这部分要让学生能照着规范地誊写到卷子上。\n\n"
    "语言亲切清晰,不堆术语;但解答过程部分要严谨规范。"
))

# 降级提示:超上限仍未通过校验时,诚实告知
_DEGRADE_NOTICE = (
    "\n\n---\n"
    "⚠️ 提示:本题的自动校验未能完全通过,以下解答仅供参考,建议你再核对一遍关键步骤。"
)


def _is_degraded(state: SolveState) -> bool:
    """是否为"超上限降级"来的:复审明确未通过(review_passed 为 False)。
    通过是 True;论述题等未经复审改写的情况是 None —— 都不算降级。"""
    return state.get("review_passed") is False


def teach_output_node(state: SolveState) -> SolveState:
    """教学式输出节点(解题路径终点)。

    读:question_text、solution、(可选)diagram_svg、review_passed。
    写:final_output(教学讲解)、messages(追加本轮)。
    """
    trace = state.get("trace", []) + ["teach_output"]

    writer = get_stream_writer()
    if _is_degraded(state):
        writer({"type": "thinking", "stage": "teach_output",
                "content": "⚠️ 自动校验未完全通过,以下解答仅供参考,正在整理…"})
    else:
        writer({"type": "thinking", "stage": "teach_output", "content": "正在整理最终解答…"})

    question_text = state.get("question_text", "")
    solution = state.get("solution", "")

    # 调 LLM 把 solution 教学化重写
    user_content = (
        f"题目:\n{question_text}\n\n"
        f"解题过程(请据此改写成给学生的分步讲解):\n{solution}"
    )
    messages = [_TEACH_SYSTEM, HumanMessage(content=user_content)]
    resp = get_llm("solver").invoke(messages)
    teaching = resp.content

    # 附配图(若有)
    diagram = state.get("diagram_svg")
    if diagram:
        teaching = f"{teaching}\n\n[配图]\n{diagram}"

    # 降级提示
    if _is_degraded(state):
        teaching = teaching + _DEGRADE_NOTICE

    # 追加对话历史(维持多轮):本轮用户问题 + 最终讲解
    new_history = []
    user_text = state.get("user_text", "")
    if user_text:
        new_history.append(HumanMessage(content=user_text))
    new_history.append(AIMessage(content=teaching))

    return {"final_output": teaching, "messages": new_history, "trace": trace}