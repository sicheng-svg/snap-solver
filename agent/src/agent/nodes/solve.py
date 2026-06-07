"""
nodes/solve.py —— Solver 求解节点。

职责:拿题目 + 题型 -> 调 LLM 求解 -> 产出 solution + 验证目标 + 配图判断。
  - 验证目标(verify_*):计算题填,供 SymPy 独立验证。论述题 verify_type=none。
  - 配图判断(diagram_*):由 solver 顺带判断"解法是否需要图/表"。
  - 不写 final_output(交付留给 teach_output)。
  - 重解接口:被打回时带上一轮解答 + 失败原因。
  - 多轮上下文:有对话历史时作为【参考上下文】拼进 prompt,以便处理
    "帮我解第二问/剩下几道"这类依赖原题上文的求解。独立新题则不拼,避免干扰。

【字段平铺】DeepSeek function_calling 对嵌套 Pydantic 支持不稳,字段平铺。
【配图安全】solver 只产出"画什么",draw 用固定代码生成,不跑 LLM 代码。
"""

from os import write
from typing import Literal, Optional
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from pydantic import BaseModel, Field

from langgraph.config import get_stream_writer

from ..state import SolveState
from ..llm import get_llm


class SolveOutput(BaseModel):
    """Solver 的结构化输出:解答 + 验证目标 + 配图判断(全平铺)。"""

    solution: str = Field(description="完整的分步解答文本。")

    verify_type: Literal[
        "limit", "evaluate", "solve_equation", "derivative", "integral", "none"
    ] = Field(
        description=(
            "验证类型。limit/evaluate/solve_equation/derivative/integral 对应可符号验证的计算;"
            "none=无法符号验证(论述题等)。"
        )
    )
    expression: Optional[str] = Field(default=None, description="待验证表达式(SymPy 语法),none 时留空。")
    variable: Optional[str] = Field(default=None, description="主变量名,如 'x'。")
    point: Optional[str] = Field(default=None, description="极限趋近点,如 '0'、'oo'。仅 limit。")
    claimed_answer: Optional[str] = Field(default=None, description="你的最终答案(SymPy 可解析形式)。")

    needs_diagram: bool = Field(
        default=False,
        description="本题的【解法】是否需要图或表才能讲清(题目要求画图、或解法离不开图表如真值表)。不是遇题就画。",
    )
    diagram_type: Literal["function_plot", "truth_table", "none"] = Field(
        default="none",
        description="配图类型。function_plot=函数图像;truth_table=真值表;none=不需要。",
    )
    plot_expression: Optional[str] = Field(default=None, description="仅 function_plot:函数表达式(SymPy 语法)。")
    plot_var: Optional[str] = Field(default=None, description="仅 function_plot:自变量。")
    plot_range: Optional[str] = Field(default=None, description="仅 function_plot:区间,格式 '下限,上限'。")
    table_markdown: Optional[str] = Field(default=None, description="仅 truth_table:Markdown 真值表。")


_SYSTEM_CALC = (
    "你是一位严谨的理工科老师,正在解一道【计算题】。"
    "请一步步推导写进 solution,明确给出最终答案。"
    "填写验证字段(verify_type/expression/variable/point/claimed_answer)以便符号验证。"
    "判断本题解法是否需要配图/表:若题目要求画函数图像,设 needs_diagram=True、"
    "diagram_type=function_plot,并填 plot_expression/plot_var/plot_range;"
    "若解法需要真值表,设 diagram_type=truth_table 并填 table_markdown;否则 none。"
)

_SYSTEM_ESSAY = (
    "你是一位严谨的理工科老师,正在解一道【论述/概念题】。"
    "条理清晰地作答写进 solution,覆盖关键概念与要点。verify_type 填 none。"
    "判断是否需要配图/表并相应设置 needs_diagram/diagram_type。"
)


def _build_system(question_type: str) -> SystemMessage:
    return SystemMessage(content=_SYSTEM_CALC if question_type == "calc" else _SYSTEM_ESSAY)


def _build_retry_hint(state: SolveState) -> str:
    prev_solution = state.get("solution")
    verify = state.get("verify_result") or {}
    review_passed = state.get("review_passed")
    review_reason = state.get("review_reason")

    if not prev_solution:
        return ""

    reasons = []
    if verify.get("passed") is False:
        reasons.append(f"工具验证未通过:{verify.get('msg', '(无详情)')}")
    if review_passed is False:
        reasons.append(
            f"复审认为解答存在问题:{review_reason}" if review_reason else "复审认为解答存在问题"
        )
    if not reasons:
        return ""

    return (
        "\n\n【这是重新求解】你上一次的解答如下:\n"
        f"{prev_solution}\n\n"
        "但存在以下问题:\n- " + "\n- ".join(reasons) +
        "\n请针对这些问题改进,重新给出正确的解答与各字段。"
    )


def _build_history_context(llm_messages: list[BaseMessage]) -> str:
    """把对话历史格式化成干净文本(供 solver 参考"第二问/原题上文")。
    - 过滤掉记忆 SystemMessage(那不是对话);
    - 排除末尾那条 Human(assemble 拼进去的"当前问题",solver 用 question_text 更准,避免重复);
    - 无可用历史则返回空串(独立新题不拼上下文,避免干扰)。
    """
    if not llm_messages:
        return ""

    history = [m for m in llm_messages if not isinstance(m, SystemMessage)]
    if history and isinstance(history[-1], HumanMessage):
        history = history[:-1]   # 去掉末尾的当前问题
    if not history:
        return ""

    lines = []
    for m in history:
        role = "学生" if isinstance(m, HumanMessage) else "老师"
        lines.append(f"{role}:{m.content}")
    return "\n".join(lines)


def solver_node(state: SolveState) -> SolveState:
    """Solver 求解节点。写:solution、verify_target、配图相关字段。不写 final_output。"""
    trace = state.get("trace", []) + ["solver"]
    writer = get_stream_writer()
    writer({"type": "thinking", "stage": "solve", "content": "正在求解…"})

    question_text = state.get("question_text", "")
    question_type = state.get("question_type", "essay")
    llm_messages = state.get("llm_messages", [])

    system = _build_system(question_type)
    retry_hint = _build_retry_hint(state)
    history_ctx = _build_history_context(llm_messages)

    if history_ctx:
        # 有历史:作为参考上下文放在前,再给出当前要解的题
        user_content = (
            "以下是之前的对话(可能含本题原文或相关上下文,仅供参考):\n"
            f"{history_ctx}\n\n"
            f"现在请解答以下题目:\n{question_text}{retry_hint}"
        )
    else:
        # 独立新题:只给当前题,不拼无关历史
        user_content = f"题目:\n{question_text}{retry_hint}"

    messages = [system, HumanMessage(content=user_content)]

    llm = get_llm("solver").with_structured_output(SolveOutput, method="function_calling")
    result: SolveOutput = llm.invoke(messages)

    verify_target = {
        "verify_type": result.verify_type,
        "expression": result.expression,
        "variable": result.variable,
        "point": result.point,
        "claimed_answer": result.claimed_answer,
    }
    diagram_spec = {
        "diagram_type": result.diagram_type,
        "plot_expression": result.plot_expression,
        "plot_var": result.plot_var,
        "plot_range": result.plot_range,
        "table_markdown": result.table_markdown,
    }

    writer({"type": "thinking", "stage": "solve", "content": "求解完成,正在准备验证和配图信息…"})

    return {
        "solution": result.solution,
        "verify_target": verify_target,
        "needs_diagram": result.needs_diagram,
        "diagram_spec": diagram_spec,
        "trace": trace,
    }