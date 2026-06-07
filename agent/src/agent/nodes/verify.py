"""
nodes/verify.py —— 工具验证节点(SymPy,注册表模式)。

职责:拿 Solver 产出的结构化 verify_target,用 SymPy【独立】算一遍,
      和模型声称的 claimed_answer 对比,产出三态 verify_result。
  - 三态:passed=True(验证通过)/ False(验证失败,有错误详情)/
          None+skipped(无法验证:论述题 或 SymPy 解析不了 -> 交 reviewer 语义兜底)。
  - 它【不直接控制循环】:只产出 verify_result 作为证据,交 reviewer 综合判断。
  - 与 reviewer 分工:verify 管"算得对不对",reviewer 管"讲得对不对"。

【注册表模式】每种验证 = 一个 _verify_xxx 函数 + 在 VERIFIERS 里注册一行。
  新增验证类型(如矩阵、数值积分)只需加函数 + 注册,主逻辑不动(开闭原则)。
  这是当前方案与"LLM tool calling 自主选型"之间的中间形态:工具少时够用且稳,
  工具变多后可再升级为 tool calling。

安全:只用 sympify 解析数学表达式,不 exec 任意代码(沙箱留作二期扩展)。
"""

import sympy

from ..state import SolveState


# ============================================================
# 公共工具
# ============================================================
def _sym(name: str | None):
    """取主变量符号,默认 x。"""
    return sympy.Symbol(name) if name else sympy.Symbol("x")


def _parse_point(point_str: str | None):
    """解析极限趋近点,支持无穷。"""
    if point_str in ("oo", "inf", "infinity", "+oo"):
        return sympy.oo
    if point_str in ("-oo", "-inf"):
        return -sympy.oo
    return sympy.sympify(point_str)


def _compare(computed, claimed_str: str | None) -> dict:
    """把 SymPy 算出的 computed 与模型声称的 claimed 对比,返回三态结果。
    这是各验证器复用的对比逻辑(符号等价判断,处理 1/2 vs 0.5、解集等)。"""
    if claimed_str is None:
        return {"passed": None, "skipped": True,
                "msg": f"模型未给出 claimed_answer,SymPy 算得 {computed}",
                "computed": str(computed)}

    claimed = sympy.sympify(claimed_str)
    try:
        if isinstance(computed, list):  # 解方程:按集合比较解
            claimed_list = claimed if isinstance(claimed, (list, tuple)) else [claimed]
            equal = set(map(sympy.sympify, claimed_list)) == set(computed)
        else:
            equal = sympy.simplify(computed - claimed) == 0
    except Exception:
        equal = (computed == claimed)

    if equal:
        return {"passed": True, "msg": f"SymPy 验证通过(算得 {computed})", "computed": str(computed)}
    return {"passed": False,
            "msg": f"答案不一致:模型声称 {claimed_str},但 SymPy 算得 {computed}",
            "computed": str(computed)}


# ============================================================
# 各验证器:只负责"算出 computed",对比交给 _compare
# ============================================================
def _verify_limit(t: dict) -> dict:
    expr = sympy.sympify(t["expression"])
    computed = sympy.limit(expr, _sym(t.get("variable")), _parse_point(t.get("point")))
    return _compare(computed, t.get("claimed_answer"))


def _verify_derivative(t: dict) -> dict:
    expr = sympy.sympify(t["expression"])
    computed = sympy.diff(expr, _sym(t.get("variable")))
    return _compare(computed, t.get("claimed_answer"))


def _verify_integral(t: dict) -> dict:
    expr = sympy.sympify(t["expression"])
    computed = sympy.integrate(expr, _sym(t.get("variable")))
    return _compare(computed, t.get("claimed_answer"))


def _verify_solve_equation(t: dict) -> dict:
    expr = sympy.sympify(t["expression"])
    computed = sympy.solve(expr, _sym(t.get("variable")))
    return _compare(computed, t.get("claimed_answer"))


def _verify_evaluate(t: dict) -> dict:
    expr = sympy.sympify(t["expression"])
    computed = sympy.simplify(expr)
    return _compare(computed, t.get("claimed_answer"))


# ============================================================
# 注册表:verify_type -> 验证器函数
#   新增验证类型只需在这里加一行 + 上面写一个 _verify_xxx
# ============================================================
VERIFIERS = {
    "limit": _verify_limit,
    "derivative": _verify_derivative,
    "integral": _verify_integral,
    "solve_equation": _verify_solve_equation,
    "evaluate": _verify_evaluate,
}


# ============================================================
# 分发 + 节点
# ============================================================
def _verify_with_sympy(target: dict) -> dict:
    """查注册表分发到对应验证器。任何异常都降级为 skipped(无法验证),
    绝不崩、也绝不武断判失败(避免 SymPy 局限误伤正确解答)。"""
    vtype = target.get("verify_type")

    if vtype == "none" or not vtype:
        return {"passed": None, "skipped": True, "msg": "无可验证目标,跳过工具验证"}

    verifier = VERIFIERS.get(vtype)
    if verifier is None:
        return {"passed": None, "skipped": True, "msg": f"未知验证类型 {vtype},跳过"}

    try:
        return verifier(target)
    except Exception as e:
        return {"passed": None, "skipped": True,
                "msg": f"SymPy 无法验证(原因:{e}),交由复审判断"}


def verify_node(state: SolveState) -> SolveState:
    """工具验证节点。读 verify_target -> 查注册表用 SymPy 计算 -> 写 verify_result。"""
    trace = state.get("trace", []) + ["verify"]
    target = state.get("verify_target") or {"verify_type": "none"}
    result = _verify_with_sympy(target)
    return {"verify_result": result, "trace": trace}