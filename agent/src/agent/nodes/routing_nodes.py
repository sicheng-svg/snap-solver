"""
nodes/routing_nodes.py —— 需要"调 LLM 才能做"的分流节点。

  - soft_route_node:软分流。用 LLM【结构化输出】一次判定:
      intent(solve / ask)+ question_type(calc / essay)。

【intent 的本质区分】
  - solve:用户有【一道明确要解答的题】(作业/试卷/练习题),要一个完整答案。
    包括计算题(求/证/算)和论述题(简述/分析/比较某主题)。
  - ask:用户在【提问或聊天】—— 概念是什么、生活问题、推荐、闲聊等,
    不是要解一道题。direct_answer 是 agent 的通用对话出口,不限于答题领域。

  难点:论述题("简述TST原理")和概念提问("TST是什么")字面接近,
  容易都被判成 ask。关键信号是【句式与意图】:
    祈使句式的题目(简述/分析/证明/求…) → solve
    疑问/请求句式的提问(…是什么/为什么/推荐/怎么样) → ask
  用 few-shot 例子(含容易混的对照对)帮 LLM 学到这个边界。
"""

from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from ..state import SolveState
from ..llm import get_llm


class RouteResult(BaseModel):
    """软分流的结构化结果。"""

    intent: Literal["solve", "ask"] = Field(
        description=(
            "用户意图。"
            "solve=用户有一道明确要解答的题目(作业/试卷/练习),要完整答案,"
            "包括计算题和论述题;"
            "ask=用户在提问或聊天(问概念定义、生活问题、推荐、闲聊等),"
            "不是要解一道题。"
        )
    )
    question_type: Literal["calc", "essay"] = Field(
        default="essay",
        description=(
            "题目类型,仅当 intent=solve 时有意义。"
            "calc=可计算/可验证(求极限、解方程、求导积分等有确定数值答案);"
            "essay=论述/概念题(简述原理、比较区别、分析等无确定数值答案)。"
            "intent=ask 时填 essay 即可(不会被使用)。"
        )
    )


# few-shot:用对照例子(尤其容易混的论述题 vs 概念提问)帮 LLM 学边界
_SOFT_ROUTE_SYSTEM = SystemMessage(content=(
    "你是一个意图与题型分类器。判断用户输入的 intent 与 question_type。\n\n"
    "核心区分:用户是【有一道题要你解答】(solve),还是【在提问/聊天】(ask)。\n\n"
    "参考以下例子:\n"
    "- 「求 lim(x→0) sinx/x 的值」→ solve, calc(有一道计算题要解)\n"
    "- 「证明根号2是无理数」→ solve, essay(有一道证明题要解)\n"
    "- 「简述TST网络的工作原理」→ solve, essay(祈使句,是一道论述题)\n"
    "- 「分析冒泡排序的时间复杂度」→ solve, essay(是一道分析题)\n"
    "- 「比较S接线器和T接线器的区别」→ solve, essay(是一道比较论述题)\n"
    "- 「TST网络是什么意思」→ ask(疑问句,只是问概念,不是解题)\n"
    "- 「为什么数组随机访问是O(1)」→ ask(在问原理,不是要答一道题)\n"
    "- 「Python和Go哪个更适合做后端」→ ask(在征求看法/聊天)\n"
    "- 「推荐几本算法书」→ ask(请求推荐,与答题无关)\n"
    "- 「今天天气怎么样」→ ask(生活闲聊)\n\n"
    "注意「简述/分析/证明/比较/求…」这类祈使句式通常是题目(solve);"
    "「…是什么/为什么/怎么样/推荐…」这类疑问或请求句式通常是提问(ask)。"
))


def soft_route_node(state: SolveState) -> SolveState:
    """软分流节点:结构化输出一次判定 intent + question_type,并写好 question_text。"""
    trace = state.get("trace", []) + ["soft_route"]

    user_text = state.get("user_text", "")
    messages = [_SOFT_ROUTE_SYSTEM, HumanMessage(content=user_text)]

    llm = get_llm("router").with_structured_output(RouteResult, method="function_calling")
    result: RouteResult = llm.invoke(messages)

    return {
        "intent": result.intent,
        "question_type": result.question_type,
        "question_text": user_text,   # 纯文本场景:题目即 user_text(修 solver 读不到题的 bug)
        "trace": trace,
    }