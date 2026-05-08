# ================================================================
# 凡人打字机 (fr-cli) —— Docker 镜像
# 基于 Python 3.13 Slim，预装全部可选依赖
# ================================================================

FROM python:3.13-slim

LABEL maintainer="fr-cli"
LABEL description="凡人打字机 - 基于智谱AI的交互式终端工具"

# 避免交互式配置提示
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装系统依赖（部分 Python 包需要编译工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 先复制构建文件，利用 Docker 层缓存
COPY pyproject.toml README.md MANIFEST.in ./
COPY fr_cli/ ./fr_cli/

# 安装 fr-cli 及全部可选依赖
RUN pip install --no-cache-dir -e ".[all]"

# 创建配置目录（运行时通过卷挂载持久化）
RUN mkdir -p /root/.zhipu_cli_history \
    /root/.zhipu_cli_plugins \
    /root/.fr_cli_agents \
    /root/.fr_cli_master \
    /root/.fr_cli_sessions \
    /app/workspace

# 默认工作目录
WORKDIR /app/workspace

# 交互式终端需要标准输入
ENTRYPOINT ["fr-cli"]
