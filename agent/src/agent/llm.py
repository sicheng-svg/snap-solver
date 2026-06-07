"""
llm.py —— LLM 客户端工厂(基础设施,不是图节点,所以放在 agent/ 下与 graph.py 同级)。

核心职责:
  把"创建配好的模型客户端"这件事收口到 get_llm(role) 一个函数。
  节点只说"我要 solver 的模型",不关心背后是 DeepSeek 还是硅基、key 从哪来 ——
  平台差异、key、base_url、temperature、模型名,全在这里按 role 装配好。

两个设计点:
  1. 按 role 路由平台:solver/reviewer/router -> DeepSeek;vlm -> 硅基流动。
  2. callback 挂载点:所有客户端统一挂上 TokenUsageHandler,
     于是每次模型调用自动被埋点(打印 token 用量)。将来要做精细成本统计
     (写库、按节点归因),只改这个 handler,节点代码一行不动 —— 这就是 hook 思想。
"""

from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler

from . import config


Role = Literal["solver", "reviewer", "router", "vlm"]


# ============================================================
# Callback:模型调用生命周期的 hook
# ============================================================
class TokenUsageHandler(BaseCallbackHandler):
    """在每次 LLM 调用结束时触发,记录 token 用量。
    一期只打印;将来可在这里累加到数据库、按 role 归因成本、接 Langfuse 等 ——
    节点无感知,这是统一加切面的入口。"""

    def on_llm_end(self, response, **kwargs) -> None:
        # 不同平台返回的 usage 字段位置可能不同,稳妥地兜底取
        usage = {}
        try:
            usage = (response.llm_output or {}).get("token_usage", {}) or {}
        except Exception:
            pass
        if usage:
            print(
                f"[token] prompt={usage.get('prompt_tokens', '?')} "
                f"completion={usage.get('completion_tokens', '?')} "
                f"total={usage.get('total_tokens', '?')}"
            )


# 全局共用一个 handler 实例即可(无状态)
_token_handler = TokenUsageHandler()

# ============================================================
# 平台连接信息(按平台,key/base_url 只写一次)
# ============================================================
PLATFORMS = {
    "deepseek": {
        "api_key": config.DEEPSEEK_API_KEY,
        "base_url": config.DEEPSEEK_BASE_URL,
    },
    "siliconflow": {
        "api_key": config.SILICONFLOW_API_KEY,
        "base_url": config.SILICONFLOW_BASE_URL,
    },
}

# ============================================================
# role -> 配置(新增 role 只改这里)
# ============================================================
ROLE_CONFIG = {
    "solver":   {"platform": "deepseek",    "model": config.MODEL_SOLVER,   "temperature": config.TEMPERATURE_SOLVER},
    "reviewer": {"platform": "deepseek",    "model": config.MODEL_REVIEWER, "temperature": config.TEMPERATURE_REVIEWER},
    "router":   {"platform": "deepseek",    "model": config.MODEL_ROUTER,   "temperature": config.TEMPERATURE_ROUTER},
    "vlm":      {"platform": "siliconflow", "model": config.MODEL_VLM,       "temperature": 0.0},
}


# ============================================================
# 对外唯一入口
# ============================================================
def get_llm(role: Role) -> ChatOpenAI:
    if role not in ROLE_CONFIG:
        raise ValueError(f"未知的 role: {role!r},应为 {'/'.join(ROLE_CONFIG)} 之一")

    rc = ROLE_CONFIG[role]
    platform = PLATFORMS[rc["platform"]]   # role 指向哪个平台,就取那组 key/url

    return ChatOpenAI(
        model=rc["model"],
        api_key=platform["api_key"],
        base_url=platform["base_url"],
        temperature=rc["temperature"],
        max_tokens=config.MAX_TOKENS,
        callbacks=[_token_handler],
        timeout=60,
        max_retries=2,
    )