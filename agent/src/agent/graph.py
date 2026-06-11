"""
graph.py —— 图的组装中心。

当前进度:解题路径接入配图判断。

  START → reset_turn → soft_route ─(intent)─┬ direct_answer ─────────────────────────────→ END
                                            └ solver →(qtype)─┬ verify → reviewer ┐
                                                               └─────────→ reviewer ┘
                                                                                │
                                                           (route_after_review)──┤
                                               retry → bump_retry → solver(循环) │
                                                          pass →(needs_diagram?)─┬ draw → teach_output → END
                                                                                  └────→ teach_output → END

  - 计算题:solver → verify → reviewer;论述题:solver → reviewer。
  - 验证循环:不过且没超限 → 回 solver;通过/降级 → 配图判断。
  - 配图判断:solver 判定 needs_diagram → 需要走 draw(函数图像/真值表),否则直接 teach。
  - teach_output:教学化重写为最终交付(含配图,若有)。
  - 问概念:direct_answer → END。

入口文件用绝对导入(langgraph dev 按路径加载)。
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agent.state import SolveState
from agent.routing import (
    route_by_intent, route_by_qtype, route_after_review, route_by_image
)
from agent.nodes.recognize import recognize_node
from agent.nodes.preprocess import reset_turn_node
from agent.nodes.routing_nodes import soft_route_node
from agent.nodes.solve import solver_node
from agent.nodes.verify import verify_node
from agent.nodes.review import reviewer_node
from agent.nodes.loop_nodes import bump_retry_node
from agent.nodes.draw import draw_node
from agent.nodes.output import direct_answer_node, teach_output_node
from agent.nodes.context import assemble_context_node


def build_graph(checkpointer=None):
    g = StateGraph(SolveState)

    g.add_node("reset_turn", reset_turn_node)
    g.add_node("recognize", recognize_node)
    g.add_node("soft_route", soft_route_node)
    g.add_node("assemble_context", assemble_context_node)
    g.add_node("solver", solver_node)
    g.add_node("verify", verify_node)
    g.add_node("reviewer", reviewer_node)
    g.add_node("bump_retry", bump_retry_node)
    g.add_node("draw", draw_node)
    g.add_node("teach_output", teach_output_node)
    g.add_node("direct_answer", direct_answer_node)

    g.add_edge(START, "reset_turn")
    # 硬分流，区分有图无图，是否调用vlm
    g.add_conditional_edges("reset_turn", route_by_image, {
        "recognize": "recognize",
        "soft_route": "soft_route",
    })

    # g.add_conditional_edges("recognize", route_by_intent, {
    #     "solver": "solver",
    #     "direct_answer": "direct_answer",
    # })

    # g.add_conditional_edges("soft_route", route_by_intent, {
    #     "solver": "solver",
    #     "direct_answer": "direct_answer",
    # })
    g.add_edge("recognize", "assemble_context")
    g.add_edge("soft_route", "assemble_context")

    g.add_conditional_edges("assemble_context", route_by_intent, {
        "solver": "solver",
        "direct_answer": "direct_answer",
    })

    g.add_conditional_edges("solver", route_by_qtype, {
        "verify": "verify",
        "reviewer": "reviewer",
    })
    g.add_edge("verify", "reviewer")

    # 验证循环:通过/降级 -> 配图判断(不再直接到 teach)
    g.add_conditional_edges("reviewer", route_after_review, {
        "retry": "bump_retry",
        "draw": "draw",
        "teach_output": "teach_output",
    })
    g.add_edge("bump_retry", "solver")

    g.add_edge("draw", "teach_output")

    # 终点
    g.add_edge("teach_output", END)
    g.add_edge("direct_answer", END)

    return g.compile(checkpointer=checkpointer)


graph = build_graph()