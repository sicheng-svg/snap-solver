"""
server.py —— Python agent 的 gRPC server 入口。

职责:把 LangGraph 的 graph 包成一个 gRPC 服务,供 Go 业务层调用。
  实现 proto(solver.proto)里定义的 SolverAgent 服务的两个方法:
    - Solve(server-streaming):跑 graph,把流式输出转成 SolveChunk 一段段 yield 给客户端。
    - HealthCheck(unary):返回存活状态。

【两段式流式】用 graph.astream(stream_mode=["custom","messages"]):
  - custom 流:各节点用 get_stream_writer 推的 thinking dict -> SolveChunk(type=thinking)
  - messages 流:LLM 的 token;只取 teach_output / direct_answer 节点的 ->
                 SolveChunk(type=token)。其余节点(solver/reviewer 等)的 token 是中间
                 思考,不作为最终回答输出。
  - 结束 -> SolveChunk(type=done);异常 -> SolveChunk(type=error)。

astream 多 stream_mode 时,每个产出是 (mode, data) 元组,据此区分两种流。
用 grpc.aio(异步 server),与 astream 的异步天然契合。
"""

import asyncio
import grpc
from grpc import aio

# 生成的 gRPC 代码(由 proto 编译而来)
from gen import solver_pb2, solver_pb2_grpc

# 你的 LangGraph 图
import os
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from agent.graph import build_graph


# 最终回答的 token 只取这两个节点(它们是面向用户的输出节点)
_OUTPUT_NODES = {"teach_output", "direct_answer"}

PG_URI = os.getenv(
    "CHECKPOINT_PG_URI",
    "postgresql://postgres:snap123456@127.0.0.1:5434/snap_checkpoint",
)


class SolverAgentServicer(solver_pb2_grpc.SolverAgentServicer):
    """实现 proto 定义的 SolverAgent 服务。"""
    def __init__(self, graph):           # 改:graph 由外部传入
        self.graph = graph

    async def Solve(self, request, context):
        """流式解题。yield 出一个个 SolveChunk。

        request: SolveRequest(image / user_text / session_id / user_id)
        每个 yield 的 SolveChunk 会被 gRPC 流式发给客户端(Go)。
        """
        # 1. 组装 graph 的输入 state
        input_state = {
            "image": request.image if request.image else None,
            "user_text": request.user_text or "",
            "user_id": request.user_id or "",
            "session_id": request.session_id or "",
            "messages": [],
            "trace": [],
        }
        # checkpointer 用 session_id 作 thread_id 维持多轮
        config = {"configurable": {"thread_id": request.session_id or "default"}}

        try:
            # 2. 跑 graph,混合流(custom + messages)
            async for mode, data in self.graph.astream(
                input_state, config, stream_mode=["custom", "messages"]
            ):
                if mode == "custom":
                    # 节点推的 thinking dict
                    yield solver_pb2.SolveChunk(
                        type=data.get("type", "thinking"),
                        stage=data.get("stage", ""),
                        content=data.get("content", ""),
                    )
                elif mode == "messages":
                    # (message_chunk, metadata) —— 只取输出节点的【流式增量】token
                    message_chunk, metadata = data
                    node = metadata.get("langgraph_node", "")
                    token = getattr(message_chunk, "content", "")
                    # AIMessageChunk = 流式增量(逐字);AIMessage = 节点结束时 append 进
                    # messages 的完整消息。后者会和 token 重复,必须过滤掉。
                    # 注意:AIMessageChunk 是 AIMessage 的子类,不能用 isinstance 判断,
                    # 必须用 type().__name__ 精确匹配。
                    is_chunk = type(message_chunk).__name__ == "AIMessageChunk"
                    if node in _OUTPUT_NODES and token and is_chunk:
                        yield solver_pb2.SolveChunk(
                            type="token", stage=node, content=token
                        )

            # 3. 正常结束
            yield solver_pb2.SolveChunk(type="done", stage="", content="")

        except Exception as e:
            # 异常也通过流告诉客户端(而不是直接断开)
            yield solver_pb2.SolveChunk(type="error", stage="", content=str(e))

    async def HealthCheck(self, request, context):
        """健康检查。"""
        return solver_pb2.HealthReply(status="ok")


async def serve():
    # async with 包住整个服务生命周期:连接池随服务启停
    async with AsyncPostgresSaver.from_conn_string(PG_URI) as checkpointer:
        await checkpointer.setup()        # 首次运行建 checkpoint 相关表(幂等,每次调也无妨)
        graph = build_graph(checkpointer=checkpointer)

        server = grpc.aio.server()
        solver_pb2_grpc.add_SolverAgentServicer_to_server(
            SolverAgentServicer(graph), server
        )
        server.add_insecure_port("[::]:50051")
        await server.start()
        print("gRPC server 已启动,监听 [::]:50051(checkpointer: PostgreSQL)")
        await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())