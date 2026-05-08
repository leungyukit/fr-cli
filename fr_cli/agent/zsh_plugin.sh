#!/bin/bash
# zsh-kimi-cli - Zsh 插件 for fr-cli
# 安装后，在 ~/.zshrc 中添加: plugins=(... kimi-cli)

# Ctrl-X 切换模式提示
_fr_cli_mode="agent"

_kimi_cli_toggle_mode() {
    if [ "$_fr_cli_mode" = "agent" ]; then
        _fr_cli_mode="shell"
        zle reset-prompt
    else
        _fr_cli_mode="agent"
        zle reset-prompt
    fi
}

# 创建 widget
zle -N kimi-cli-toggle-mode _kimi_cli_toggle_mode

# 绑定 Ctrl-X
bindkey '^X' kimi-cli-toggle-mode

# 模式提示符
FR_CLI_PS1="[🤖 Agent]"
FR_SHELL_PS1="[🐚 Shell]"

_prompt_fr_mode() {
    if [ "$_fr_cli_mode" = "agent" ]; then
        echo "$FR_CLI_PS1"
    else
        echo "$FR_SHELL_PS1"
    fi
}

# 显示模式信息
kimi-cli-info() {
    echo "fr-cli Zsh 集成"
    echo "  模式: $_fr_cli_mode"
    echo "  快捷键: Ctrl+X 切换模式"
}

# 快速启动 fr-cli
alias fr-start='fr'

# 帮助信息
kimi-cli-help() {
    cat << EOF
fr-cli Zsh 插件
================

快捷键:
  Ctrl-X   切换 Agent/Shell 模式

命令:
  kimi-cli-info    显示当前状态
  kimi-cli-help    显示此帮助

别名:
  fr-start    启动 fr-cli

EOF
}