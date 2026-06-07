"""
nodes/preprocess.py —— 入口预处理节点(硬分流之前的公共必经点)。

目前放:
  - reset_turn_node:turn-level 状态重置。

============================================================
状态生命周期分层(决定 reset 清哪些)
============================================================
state 字段按生命周期分两大类:

【session-level】跨 turn 保留 —— reset 绝不碰:
  - user_id, session_id:身份/会话标识
  - messages:完整对话历史(有 add_messages reducer,且多轮对话靠它,清了就失忆)

【turn-level】每个 turn(用户每发一条消息)只属于本轮 —— 又细分两种:
  - 输入型:image, user_text。每 turn 由客户端传入新值,
    reset 是 turn 的第一个节点,此刻它们正是刚传进来的新输入,
    所以 reset【不碰】它们(清了反而丢输入,"重置"由外部传新值自然完成)。
  - 产物型:turn 内部各节点产生的中间/结果状态。
    存在 state 里会被 checkpointer 持久化,不清就污染下一题
    (如上一题 retry_count 残留 → 新题秒触发降级)。reset【全部清零】。

============================================================
为什么放最前(公共必经点)
============================================================
重置必须在【所有 turn 的公共必经点】—— 硬分流之前。若放在某条分支
(如软分流)上,走另一条分支(有图片 → VLM)的 turn 会绕过重置。
所以独立成入口节点,所有 turn 第一步都先经过它清场。

注:intent / question_type / question_text 虽然 soft_route 每 turn 会重写,
但仍重置 —— 以防将来某条分支(如 VLM 路径)不写其中某个字段而漏出上轮残留。
"求稳:产物型一律清",不依赖"反正会被覆盖"的假设。
"""

from ..state import SolveState


# turn-level【产物型】字段及其重置值。
# (session-level 的 user_id/session_id/messages 不在此列;
#  turn-level 输入型的 image/user_text 也不在此列——由客户端每 turn 传新值。)
_TURN_LEVEL_RESET = {
    # 路由标志(soft_route 等会重写,仍清以防分支绕过)
    "intent": None,
    "question_type": None,
    "question_text": "",
    "needs_diagram": False,

    # 上下文组装产物(每 turn 由记忆/窗口/拼装节点重算)
    "retrieved_memory": "",
    "llm_messages": [],

    # 解题数据流产物
    "solution": "",
    "verify_target": {},
    "verify_result": {},
    "review_passed": None,
    "review_reason": "",

    # 循环计数
    "retry_count": 0,

    # 配图与输出
    "diagram_svg": "",
    "diagram_spec": {},
    "final_output": "",

    # 调试
    "trace": [],   # 普通字段,直接覆盖为空;下一题路径从空开始
}


def reset_turn_node(state: SolveState) -> SolveState:
    """每个新 turn 的入口:重置 turn-level 产物型状态。

    不碰:session-level(user_id/session_id/messages)、
          turn-level 输入型(image/user_text,由客户端每 turn 传新值)。
    """
    out = dict(_TURN_LEVEL_RESET)
    # trace 直接重置为 ["reset_turn"]:既清空,又记录本节点已执行
    out["trace"] = ["reset_turn"]
    return out