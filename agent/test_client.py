"""
test_client.py —— Python gRPC 测试客户端。

连上本地 agent gRPC server(50051),发一个 SolveRequest,
实时打印流式返回的 SolveChunk:
  - thinking:思考过程(识题/验证/重解/降级…),显示成 [思考] 行
  - token:最终回答,逐字拼出来(模拟前端打字机效果)
  - done:结束
  - error:错误

用法:
    # 先在另一个终端 uv run python server.py 起服务
    uv run python test_client.py "求 lim(x->0) sinx/x 的值"      # 文本解题
    uv run python test_client.py --image question.jpg            # 拍照解题
    uv run python test_client.py                                  # 用默认文本
"""

import sys
import asyncio
import grpc

from gen import solver_pb2, solver_pb2_grpc


async def run(user_text: str = "", image_path: str = "", session_id: str = "test-session"):
    # 连接 server(明文,本地)
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = solver_pb2_grpc.SolverAgentStub(channel)

        # 读图片(如果指定了)
        image_bytes = b""
        if image_path:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            print(f"[输入] 图片:{image_path}({len(image_bytes)} 字节)")
        if user_text:
            print(f"[输入] 文本:{user_text}")
        print("=" * 60)

        request = solver_pb2.SolveRequest(
            image=image_bytes,
            user_text=user_text,
            session_id=session_id,
            user_id="test-user",
        )

        # 流式接收
        answer_buffer = []          # 拼最终回答
        answer_started = False

        async for chunk in stub.Solve(request):
            if chunk.type == "thinking":
                print(f"[思考·{chunk.stage}] {chunk.content}")
            elif chunk.type == "token":
                if not answer_started:
                    print("\n" + "=" * 60)
                    print("【最终回答】")
                    answer_started = True
                # 逐字打印(打字机效果),不换行
                print(chunk.content, end="", flush=True)
                answer_buffer.append(chunk.content)
            elif chunk.type == "done":
                print("\n" + "=" * 60)
                print("[完成]")
            elif chunk.type == "error":
                print(f"\n[错误] {chunk.content}")

        # 也可以拿到完整回答
        # full_answer = "".join(answer_buffer)


def main():
    args = sys.argv[1:]
    image_path = ""
    user_text = ""

    if "--image" in args:
        idx = args.index("--image")
        image_path = args[idx + 1] if idx + 1 < len(args) else "question.jpg"
    elif args:
        user_text = args[0]
    else:
        user_text = "求 lim(x->0) sinx/x 的值"   # 默认

    asyncio.run(run(user_text=user_text, image_path=image_path))


if __name__ == "__main__":
    main()