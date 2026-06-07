"""
config.py —— 集中管理代码逻辑常量(调参用的旋钮)。

与 .env 的分工:
  - config.py 放【逻辑常量】:循环上限、窗口大小、用哪个模型、temperature 等。
    这些相对固定、不敏感,换它们等于改代码行为。
  - .env 放【环境配置】:API key、base_url。随部署环境变、且敏感,绝不写死在代码里。
  config.py 从 .env 读取敏感值(下面的 API_KEY / BASE_URL),而不是硬编码。
"""

import os
from dotenv import load_dotenv

load_dotenv()   # 模块导入时就加载 .env,确保下面的 os.getenv 能读到


# ============================================================
# 循环控制
# ============================================================
# Reviewer 打回 Solver 重解的最大轮数。超过则降级输出(带"未通过校验"提示),
# 不再无限重试 —— 这是防死循环的命门。
MAX_RETRY: int = 2


# ============================================================
# 滑动窗口(上下文管理)
# ============================================================
# 一期按"轮数"裁剪历史:只保留最近 N 轮对话喂给 LLM。
# 简单粗暴但够用;二期可升级为按 token 数裁剪(更精确)。
WINDOW_MAX_TURNS: int = 6


# ============================================================
# 模型档位
# ============================================================
# 不同节点用不同档位的模型:贵的留给难任务,便宜的做简单分类。
# 这是"按需调用、分层降级"的成本控制 —— 面试可讲的点。
MODEL_SOLVER: str = os.getenv("MODEL_SOLVER", "deepseek-chat")    # 求解:主力模型
MODEL_REVIEWER: str = os.getenv("MODEL_REVIEWER", "deepseek-chat")  # 复审:可同档或更强
MODEL_ROUTER: str = os.getenv("MODEL_ROUTER", "deepseek-chat")    # 软分流:最便宜即可
MODEL_VLM: str = os.getenv("MODEL_VLM", "Qwen/Qwen3-VL-8B-Instruct")           # VLM 识题:多模态模型


# ============================================================
# 模型调用参数
# ============================================================
# 解题要稳定、可复现,temperature 调低;复审同理要严谨。
TEMPERATURE_SOLVER: float = 0.2
TEMPERATURE_REVIEWER: float = 0.0
TEMPERATURE_ROUTER: float = 0.0   # 分类任务,要确定性

# 单次生成的最大 token,防止跑飞
MAX_TOKENS: int = 2048


# ============================================================
# 敏感值:从 .env 读取(.env.example 里列出需要哪些,实际值填在 .env)
# ============================================================
# DeepSeek:文本模型(Solver / Reviewer / 软分流共用)
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# 硅基流动:视觉模型(识题)
SILICONFLOW_API_KEY: str = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL: str = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")


def assert_env_ready() -> None:
    missing = [name for name, val in [
        ("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY),
        ("SILICONFLOW_API_KEY", SILICONFLOW_API_KEY),
    ] if not val]
    if missing:
        raise RuntimeError(f"缺少环境变量: {', '.join(missing)} —— 请在 .env 中配置")