"""
SolveState —— 解题 agent 这张图的脊椎。

所有节点的输入输出都基于这个共享状态。字段按"职责"分组,
每个字段都标注了【谁写】【谁读】,方便后面逐个实现节点时对照。

两个关键设计点:
  1. messages 用 add_messages reducer:节点返回新消息时自动【追加】到历史,
     而不是覆盖 —— 这是"完整历史只增不减"的保证,也是多轮对话的基础。
  2. llm_messages 不用 reducer:它是每次由上下文组装节点从 messages
     【派生重算】的"本次待发送精简版",所以是普通字段,每次被覆盖。

  注:total=False 让所有字段可选,因为节点是逐个填充的,
  流程早期很多字段还没有值。
"""

from typing import TypedDict, Optional, Literal, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class SolveState(TypedDict, total=False):

   # ===== 身份与会话 =====
   # user_id: 记忆提取节点靠它去外部存储查这个用户的长期记忆
   # session_id: checkpointer 靠它(作为 thread_id)区分不同对话线程
   user_id: str
   session_id: str

   # ===== 原始输入 =====
   # 【写】客户端入参   【读】噪声去除、入口硬分流
   image: Optional[bytes]          # 用户上传的图片,无图时为 None
   user_text: str                  # 用户输入的原始文本

   # ===== 消息 =====
   # messages: 完整对话历史。用 add_messages reducer —— 节点返回消息时
   #           自动追加而非覆盖。靠 checkpointer 持久化,支撑多轮对话。
   #   【写】各 LLM 节点(把本轮问答追加进来)   【读】上下文组装
   messages: Annotated[list[BaseMessage], add_messages]

   # llm_messages: 本次真正发给 LLM 的消息 = 滑动窗口裁剪 + 长期记忆拼装后的结果。
   #               它是 messages 的派生子集,不持久化,每次重算被覆盖。
   #   【写】上下文拼装节点   【读】Solver / Reviewer / 直接问答等调 LLM 的节点
   llm_messages: list[BaseMessage]

   # ===== 路由标志位(存在的唯一目的:给条件边读,决定下一步去哪)=====
   intent: Literal["solve", "ask"]            # 软分流:解题 / 问概念
   question_type: Literal["calc", "essay"]    # 题型:计算题 / 论述题
   needs_diagram: bool                         # 是否需要配图
   review_passed: bool                         # Reviewer 是否通过,决定是否循环
   retry_count: int                            # 重解循环计数,控制上限防死循环

   # ===== 个性化 =====
   # 这次实际捞出来、要拼进上下文的那一小份记忆(不是全部记忆,全量在外部库)
   #   【写】长期记忆提取节点   【读】上下文拼装节点
   retrieved_memory: str

   # ===== 解题数据流(在流程里实质流动的内容)=====
   question_text: str              # 题目文本,VLM 识题 或 文本预处理 产出
   solution: str                   # Solver 的解答,可能被 Reviewer 打回重填
   verify_target: dict             # Solver 产出的结构化验证目标,verify 节点读取
   verify_result: dict             # 工具验证结果,如 {"passed": bool, "msg": str}
   review_reason: str              # Reviewer 不通过的原因,重解时参考
   diagram_svg: str                # 绘图节点产物
   diagram_spec: dict              # Solver 产出的配图目标,draw 节点据此生成

   # ===== 输出 =====
   final_output: str               # 交付给用户的最终内容

   # ===== 调试 / 可观测性 =====
   # 记录走过的节点路径,一期用来验证流转,后续可接 LangSmith/Langfuse
   trace: list[str]