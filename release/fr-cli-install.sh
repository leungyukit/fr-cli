#!/bin/bash
# ============================================================
# 凡人打字机 (fr-cli) 跨平台安装脚本
# 支持 macOS / Linux
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WHEEL_FILE="$SCRIPT_DIR/fr_cli-2.1.0-py3-none-any.whl"

BOLD='\033[1m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
RESET='\033[0m'

print_header() {
    echo ""
    echo -e "${BOLD}╔══════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║     凡人打字机 (fr-cli) 安装器          ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
    echo ""
}

check_python() {
    local PYTHON_CMD=""
    for cmd in python3 python; do
        if command -v "$cmd" &> /dev/null; then
            local ver_ok
            ver_ok=$($cmd -c 'import sys; print(sys.version_info[:2] >= (3,8))' 2>/dev/null || echo "False")
            if [ "$ver_ok" = "True" ]; then
                PYTHON_CMD="$cmd"
                break
            fi
        fi
    done

    if [ -z "$PYTHON_CMD" ]; then
        echo -e "${RED}错误：未找到 Python 3.8+。${RESET}" >&2
        echo "请从 https://python.org 下载并安装 Python 3.8 或更高版本。" >&2
        exit 1
    fi

    local py_ver
    py_ver=$($PYTHON_CMD --version 2>&1)
    echo -e "✅ 检测到 ${GREEN}${py_ver}${RESET}" >&2
    echo "$PYTHON_CMD"
}

install_wheel() {
    local PYTHON="$1"
    local VENV_DIR="$SCRIPT_DIR/.venv"

    echo ""
    echo -e "${YELLOW}📦 步骤 1/3：创建虚拟环境...${RESET}"
    "$PYTHON" -m venv "$VENV_DIR"

    echo -e "${YELLOW}📦 步骤 2/3：安装 fr-cli 及依赖...${RESET}"
    source "$VENV_DIR/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet "$WHEEL_FILE"

    echo -e "${YELLOW}📦 步骤 3/3：创建启动器...${RESET}"
    cat > "$SCRIPT_DIR/fr-cli" << 'LAUNCHER'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
exec fr-cli "$@"
LAUNCHER
    chmod +x "$SCRIPT_DIR/fr-cli"
}

verify_install() {
    echo ""
    echo -e "${YELLOW}🔍 验证安装...${RESET}"
    if "$SCRIPT_DIR/fr-cli" --help &> /dev/null; then
        echo -e "${GREEN}✅ fr-cli 安装验证通过！${RESET}"
    else
        # 交互式程序没有 --help，直接检查入口是否存在
        if [ -f "$SCRIPT_DIR/.venv/bin/fr-cli" ]; then
            echo -e "${GREEN}✅ fr-cli 安装验证通过！${RESET}"
        else
            echo -e "${RED}❌ 安装验证失败，请检查错误信息。${RESET}"
            exit 1
        fi
    fi
}

print_footer() {
    echo ""
    echo -e "${GREEN}${BOLD}🎉 安装完成！${RESET}"
    echo ""
    echo -e "${BOLD}使用方式：${RESET}"
    echo "  直接运行：$SCRIPT_DIR/fr-cli"
    echo ""
    echo -e "${BOLD}添加到全局 PATH（推荐）：${RESET}"
    echo "  ${YELLOW}export PATH=\"$SCRIPT_DIR:\$PATH\"${RESET}"
    echo ""
    echo -e "添加到 ~/.bashrc 或 ~/.zshrc 可永久生效。"
    echo ""
}

# ============ 主流程 ============
print_header

if [ ! -f "$WHEEL_FILE" ]; then
    echo -e "${RED}错误：未找到安装包 ${WHEEL_FILE}${RESET}"
    exit 1
fi

PYTHON=$(check_python)
install_wheel "$PYTHON"
verify_install
print_footer
