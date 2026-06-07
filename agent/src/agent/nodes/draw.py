"""
nodes/draw.py —— 配图节点。

根据 solver 产出的 diagram_spec 生成图/表:
  - function_plot:用【固定的安全代码】(sympy 解析表达式 + numpy 取点 + matplotlib 画),
    出 PNG,转 base64 内嵌。全程【不执行 LLM 生成的代码】—— solver 只给"画什么"
    (表达式+范围),不给"画图代码",安全风险被消除(同 verify 节点思路)。
  - truth_table:solver 解题时已算好真值表并以 Markdown 给出,直接采用,无需画。
  - none / 无法生成:返回空,不阻塞流程。

产物写入 diagram_svg(沿用该字段名;函数图像存 base64 data-uri,真值表存 Markdown)。
"""

import io
import base64

import matplotlib
matplotlib.use("Agg")   # 无界面后端,服务器环境必需
import matplotlib.pyplot as plt
import numpy as np
import sympy

from langgraph.config import get_stream_writer

from ..state import SolveState


def _render_function_plot(spec: dict) -> str:
    """用固定安全代码画函数图像,返回 PNG 的 base64 data-uri。失败返回空串。
    只接受表达式和范围,用 sympy 解析(不 eval/exec 任意代码)。"""
    expr_str = spec.get("plot_expression")
    var_str = spec.get("plot_var") or "x"
    range_str = spec.get("plot_range") or "-10,10"
    if not expr_str:
        return ""

    try:
        var = sympy.Symbol(var_str)
        expr = sympy.sympify(expr_str)                  # 安全解析,非 eval
        f = sympy.lambdify(var, expr, modules=["numpy"])

        lo, hi = (float(x) for x in range_str.split(","))
        xs = np.linspace(lo, hi, 400)
        with np.errstate(all="ignore"):                 # 容忍除零/定义域外的点
            ys = f(xs)
        ys = np.array(ys, dtype=float)
        ys[~np.isfinite(ys)] = np.nan                   # 把 inf/nan 处断开,不画错线

        fig, ax = plt.subplots(figsize=(5, 3.2), dpi=120)
        ax.plot(xs, ys, color="#185FA5", linewidth=1.6)
        ax.axhline(0, color="#888780", linewidth=0.6)
        ax.axvline(0, color="#888780", linewidth=0.6)
        ax.set_title(f"y = {expr_str}")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)                                  # 必须关闭,否则内存泄漏
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        # 画图失败不阻塞主流程,返回空(teach_output 会当作无配图)
        return ""


def draw_node(state: SolveState) -> SolveState:
    """配图节点。读 diagram_spec -> 生成图/表 -> 写 diagram_svg。"""
    trace = state.get("trace", []) + ["draw"]
    get_stream_writer()({"type": "thinking", "stage": "draw", "content": "正在生成配图/表…"})
    spec = state.get("diagram_spec") or {}
    dtype = spec.get("diagram_type", "none")

    diagram = ""
    if dtype == "function_plot":
        diagram = _render_function_plot(spec)
    elif dtype == "truth_table":
        # solver 已给出 Markdown 真值表,直接用
        diagram = spec.get("table_markdown") or ""
    # none 或失败:diagram 保持 ""

    return {"diagram_svg": diagram, "trace": trace}