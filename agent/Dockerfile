# agent/Dockerfile —— Python LangGraph gRPC 服务
FROM python:3.12-slim

# 装 uv(快速 Python 包管理)
RUN pip install --no-cache-dir uv

WORKDIR /app

# 先拷依赖清单,利用 Docker 层缓存(依赖没变就不重装)
COPY pyproject.toml uv.lock* ./

# 配 uv 的国内源(uv sync 用),再装依赖
ENV UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project

COPY . .
# gRPC 端口(仅容器内网暴露,不 -p 到宿主)
EXPOSE 50051

CMD ["uv", "run", "python", "server.py"]