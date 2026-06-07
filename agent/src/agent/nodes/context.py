"""
nodes/context.py —— 上下文组装。

  - sliding_window(工具函数):把完整历史 messages 按轮数裁剪到最近 N 轮。
    纯数据变换,不调外部、无副作用 -> 做成工具函数,而非独立节点。
  - assemble_context_node(节点):上下文拼装。组装出 llm_messages =
    (裁剪后的历史) + (长期记忆,一期预留)。放在分流之后、solver/direct_answer 之前
    的公共位置,两类节点都能拿到对话历史(支持多轮追问)。

llm_messages 是 messages 的【派生子集】,每次重算覆盖(不持久化);
messages 才是完整历史(持久化)。滑动窗口裁的是派生版,不动 messages。
"""

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from mypy.state import state

from ..state import SolveState
from ..config import WINDOW_MAX_TURNS


def sliding_window(messages: list[BaseMessage], max_turns: int) -> list[BaseMessage]:
    """按轮数裁剪历史,保留最近 max_turns 轮。

    一"轮"= 一条 Human + 其后的 AI 回复。裁剪时从末尾往前数,
    保证不把一对 Human/AI 拆散,也不会以 AI 开头(那样上下文不完整)。
    """
    if not messages or max_turns <= 0:
        return []

    # 从后往前数 Human 消息,数到第 max_turns 个 Human,从那里截断
    human_count = 0
    cut_index = 0
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            human_count += 1
            if human_count == max_turns:
                cut_index = i
                break
    else:
        # Human 数不足 max_turns 个,保留全部
        cut_index = 0

    return messages[cut_index:]


def assemble_context_node(state: SolveState) -> SolveState:
    """上下文拼装节点:产出 llm_messages = 裁剪历史 + 长期记忆(预留)。"""
    trace = state.get("trace", []) + ["assemble_context"]

    # 1. 裁剪历史
    history = state.get("messages", [])
    windowed = sliding_window(history, WINDOW_MAX_TURNS)

    # 2. 长期记忆(一期预留:retrieved_memory 目前为空,有了就拼成 SystemMessage 放最前)
    llm_messages: list[BaseMessage] = []
    memory = state.get("retrieved_memory")
    if memory:
        llm_messages.append(SystemMessage(content=f"关于该用户的背景信息:{memory}"))

    # 3. 拼上裁剪后的历史
    llm_messages.extend(windowed)

    # 4. 追加本轮当前问题(关键:llm_messages 要含当前输入,否则 LLM 看不到新问题)
    current = state.get("question_text") or state.get("user_text") or ""
    if current:
        llm_messages.append(HumanMessage(content=current))

    return {"llm_messages": llm_messages, "trace": trace}