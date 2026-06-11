# snap-solver · 拍照搜题 AI Agent

> 上传一张题目照片或输入文字,AI 识题、求解、**用符号计算工具验证答案**、自我纠错,
> 最后以「解题思路 + 可誊写到试卷的规范解答」流式讲给你听。

**核心理念:用确定性工具兜住 LLM 的不确定性。**
不做题库检索 —— Solver 给出解答的同时产出"验证目标",由 SymPy 独立符号计算复核;
未通过则带着失败原因自动重解(evaluator-optimizer 循环),超限则诚实降级标注"仅供参考"。

---

## ✨ 功能

- 📷 **拍照解题**:上传题目照片,VLM(Qwen-VL)识别题目(含 LaTeX 公式转写)
- ✍️ **文字解题** / 💬 **概念问答**:意图分流,解题走验证管线,闲聊概念走轻路径
- ✅ **工具验证**:极限/求值/解方程/求导/积分 由 SymPy 独立验证,不靠 LLM 自检
- 🔁 **自我纠错**:验证/复审不过 → 带失败原因重解;超上限 → 降级输出并明确告知
- 📊 **按需配图**:解法需要时生成函数图像(matplotlib 固定安全代码)或真值表
- 🧠 **多轮对话**:追问"为什么这步这样"、"帮我解第二问"均可(滑动窗口 + checkpointer)
- ⚡ **全链路流式**:思考过程(识题/验证/重解/降级)+ 最终回答逐字,两段式体验
- 🧮 **公式渲染**:前端 KaTeX + Markdown,解答排版接近印刷质量

## 🏗 架构

```
React 前端 ──HTTP POST / SSE──▶ Go 网关(Gin) ──gRPC stream──▶ Python Agent(LangGraph)
   ▲  fetch+ReadableStream         协议转换 HTTP⟷gRPC            graph.astream 双流
   └────── 流式 SSE(thinking/token/done)◀──── SolveChunk ◀──────┘
```

**Python Agent(LangGraph)** —— 解题引擎:

```
reset_turn → 硬分流(有图?) ─┬ VLM识题 ┐
                             └ 软分流  ┘→ 上下文拼装 ─┬ direct_answer(概念/闲聊)
                                                     └ solver ─┬ SymPy验证 → reviewer ┐
                                                               └────────→ reviewer ┘
                                          retry(带失败原因)← 不过且未超限 ──┤
                                          通过/降级 →(需配图?)→ draw → teach_output
```

| 层 | 技术 | 职责 |
|---|---|---|
| 前端 | React + TS + Vite, KaTeX | 对话流 UI、传图、SSE 流式渲染、思考折叠、右侧导航 |
| 网关 | Go + Gin + gRPC client | HTTP/SSE ⟷ gRPC 协议转换、CORS、(预留鉴权/限流) |
| Agent | Python + LangGraph + gRPC server | 识题/求解/验证/复审/配图/教学输出、多轮、流式 |
| 契约 | Protocol Buffers | proto/solver.proto,单一真相源生成两侧代码 |
| 模型 | DeepSeek(文本)/ Qwen-VL(视觉)| 求解/复审/分流 / 图片识题 |
| 验证 | SymPy | 极限/求值/方程/导数/积分 符号验证(注册表模式) |

## 🚀 快速开始

### 环境
- Python 3.12 + [uv](https://docs.astral.sh/uv/) / Go 1.22+ / Node 18+
- API Key:DeepSeek、SiliconFlow(配置见 `agent/.env.example`)

### 启动(三个终端)
```bash
# ① Python Agent(gRPC :50051)
cd agent && uv sync && cp .env.example .env  # 填入你的 API Key
uv run python server.py

# ② Go 网关(HTTP :8080)
cd server && go run .

# ③ 前端(:5173)
cd web && npm install && npm run dev
```
浏览器打开 http://localhost:5173,输入题目或点 ➕ 上传题目照片。

### 开发调试
```bash
cd agent && uv run langgraph dev        # LangGraph Studio 可视化调试(热重载)
uv run python test_vlm.py 题目.jpg      # 命令行测拍照链路
cd server && go run ./cmd/solve "求 lim(x->0) sinx/x"   # 命令行测 gRPC 流式
```

### 重新生成 gRPC 代码(修改 proto 后)
```bash
# Python
cd agent && uv run python -m grpc_tools.protoc -I ../proto \
  --python_out=gen --grpc_python_out=gen --pyi_out=gen ../proto/solver.proto
# Go
cd server && protoc -I ../proto --go_out=gen --go_opt=paths=source_relative \
  --go-grpc_out=gen --go-grpc_opt=paths=source_relative ../proto/solver.proto
```

## 🔍 设计要点

- **验证不是自检**:Solver 输出平铺的结构化"验证目标"(表达式/变量/声称答案),
  verify 节点查注册表用 SymPy 独立计算比对 —— LLM 出意图,确定性代码执行。
  配图同理(只给"画什么",固定代码 sympy.sympify+matplotlib 渲染,不执行 LLM 代码)。
- **三态验证**:通过 / 未通过 / 无法验证(论述题等),复审节点综合证据做循环决策。
- **状态生命周期三层模型**:session 级(messages 等)/ turn 输入型 / turn 产物型,
  仅产物型在公共入口 reset,根治跨轮污染(详见 `agent/docs/state-lifecycle.md`)。
- **两段式流式**:custom 流(节点主动推思考:识题结果/验证结论/第N次重解/降级提示)
  + messages 流(仅输出节点的 AIMessageChunk 逐字),统一为 SolveChunk 经 gRPC→SSE。
- **多轮上下文**:滑动窗口按轮裁剪(不拆 Human/AI 对)+ 拼装(记忆预留+历史+当前问题),
  solver 仅在有真实历史时附带上下文(支持"解第二问"),独立题不受干扰。

## 📁 目录

```
snap-solver/
├── proto/solver.proto     # gRPC 契约(单一真相源)
├── agent/                 # Python LangGraph agent + gRPC server
│   ├── src/agent/         # state / graph / routing / nodes(11个节点)
│   ├── server.py          # gRPC 服务入口(流式)
│   └── gen/               # protoc 生成(Python)
├── server/                # Go 网关(Gin + gRPC client)
│   ├── main.go            # HTTP/SSE 入口
│   ├── cmd/               # 命令行测试工具(healthcheck / solve)
│   └── gen/               # protoc 生成(Go)
└── web/                   # React 前端(Vite + TS + KaTeX)
```

## 🗺 Roadmap(二期)
- [ ] 多会话:左侧会话列表、会话隔离与持久化(MySQL/Redis)
- [ ] 部署:Docker Compose 编排,VPS 上线
- [ ] RAG 旁路:用户自带电子书 → 异步索引 → 检索增强
- [ ] verify 升级:LLM tool calling 自主选择验证工具
- [ ] 长期记忆、鉴权/限流、Go internal 分层

## License
MIT

