"""
nodes/recognize.py —— VLM 识题节点(有图路径)。

职责:图片 -> 识别出题目文本 + 顺带判定 intent/question_type。
  用多模态模型(硅基 Qwen-VL),一次调用既"看图出文字"又结构化输出题型。

  有图路径与无图路径对称:
    有图:hard_route → recognize(出 question_text + intent + question_type)→ 解题流程
    无图:hard_route → soft_route(同样出这三者)→ 解题流程
  两条各自备好"题目内容 + 路由信息",汇合到 solver。recognize 后【不再走 soft_route】。

多模态消息格式:HumanMessage 的 content 用列表,含 text 块 + image_url 块,
  图片以 base64 data-uri 传入(data:image/...;base64,...)。
"""

import base64
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from langgraph.config import get_stream_writer

from ..state import SolveState
from ..llm import get_llm


class RecognizeResult(BaseModel):
    """VLM 识题的结构化结果。"""

    question_text: str = Field(
        description="从图片中识别出的完整题目文本(含数学公式,用文字/LaTeX 转写)。若图中无题目,填空串。"
    )
    intent: Literal["solve", "ask"] = Field(
        description="solve=图中是一道要解答的题;ask=图中不是题目(如风景、无关内容),无法解题。"
    )
    question_type: Literal["calc", "essay"] = Field(
        default="essay",
        description="题型,仅 intent=solve 有意义。calc=可计算验证(求极限/解方程等);essay=论述/概念题。",
    )


_SYSTEM = SystemMessage(content=(
    "你是一个题目识别助手。请仔细看图,识别其中的题目内容(包括数学公式,用 LaTeX 或文字准确转写),"
    "并判断:这是不是一道要解答的题(intent),若是,是计算题还是论述题(question_type)。"
    "按结构化格式输出。"
))


def _to_data_uri(image: bytes) -> str:
    """把图片字节转成 base64 data-uri。默认按 PNG;实际类型不影响多数 VLM。"""
    b64 = base64.b64encode(image).decode("ascii")
    return f"data:image/png;base64,{b64}"


def recognize_node(state: SolveState) -> SolveState:
    """VLM 识题节点。读 image -> 写 question_text + intent + question_type。"""
    trace = state.get("trace", []) + ["recognize"]

    image = state.get("image")
    if not image:
        # 兜底:理论上硬分流保证有图才进来;万一没图,标记为无法识别,转 ask
        return {"intent": "ask", "question_text": "", "trace": trace}

    # 多模态消息:文字指令 + 图片
    user_msg = HumanMessage(content=[
        {"type": "text", "text": "请识别图中的题目并按要求输出。"},
        {"type": "image_url", "image_url": {"url": _to_data_uri(image)}},
    ])
    messages = [_SYSTEM, user_msg]

    llm = get_llm("vlm").with_structured_output(RecognizeResult)
    result: RecognizeResult = llm.invoke(messages)

    writer = get_stream_writer()
    writer({"type": "thinking", "stage": "recognize",
            "content": f"已识别题目:{result.question_text}"})

    return {
        "question_text": result.question_text,
        "intent": result.intent,
        "question_type": result.question_type,
        "trace": trace,
    }