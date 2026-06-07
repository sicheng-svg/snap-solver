"""
test_vlm.py —— 测试 VLM 识题 + 拍照搜题完整链路。

用法:
    uv run python test_vlm.py 你的题目图片.jpg
    (不传则默认读 test_question.jpg)

它会:读图片 -> 喂进 graph 的 image 字段 -> 跑完整流程
      -> 打印 识别出的题目、走过的节点、验证结果、最终教学输出。

这是测 VLM 最直接的方式(Studio 传不了二进制图片);
它模拟的正是将来"Go 网关把图片 bytes 塞进 state"那一步。
"""

import sys
from agent.graph import graph


def main():
    # 命令行第一个参数当图片路径,没传用默认
    image_path = sys.argv[1] if len(sys.argv) > 1 else "test_question.jpg"

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except FileNotFoundError:
        print(f"找不到图片:{image_path}")
        print("用法:uv run python test_vlm.py 你的题目图片.jpg")
        sys.exit(1)

    print(f"读入图片:{image_path}({len(image_bytes)} 字节)\n")
    print("=" * 60)
    print("开始跑 graph(拍照 → 识题 → 解题 → 验证 → 教学输出)...")
    print("=" * 60 + "\n")

    result = graph.invoke(
        {
            "image": image_bytes,
            "user_text": "",
            "messages": [],
            "trace": [],
        },
        {"configurable": {"thread_id": "vlm-test"}},
    )

    # ---- 分环节打印 ----
    print("【走过的节点】")
    print("  " + " → ".join(result.get("trace", [])) + "\n")

    print("【VLM 识别出的题目】")
    print("  " + (result.get("question_text") or "(空)") + "\n")

    print("【路由判定】")
    print(f"  intent={result.get('intent')}  question_type={result.get('question_type')}\n")

    print("【Solver 解答(原始)】")
    sol = result.get("solution") or "(空)"
    print("  " + sol[:300] + ("..." if len(sol) > 300 else "") + "\n")

    print("【工具验证结果】")
    print(f"  {result.get('verify_result')}\n")

    print("【复审】")
    print(f"  review_passed={result.get('review_passed')}  reason={result.get('review_reason')}\n")

    print("【配图】")
    diagram = result.get("diagram_svg") or ""
    if diagram.startswith("data:image"):
        print(f"  生成了函数图像(PNG base64,{len(diagram)} 字符)")
    elif diagram:
        print(f"  生成了表格/其他:\n{diagram[:200]}")
    else:
        print("  无配图")
    print()

    print("=" * 60)
    print("【最终教学输出 final_output】")
    print("=" * 60)
    print(result.get("final_output") or "(空)")


if __name__ == "__main__":
    main()