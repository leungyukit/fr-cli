# 凡人打字机 (fr-cli) 安装指南

## 📦 快速安装

### 方式一：双击运行安装程序（推荐）

| 平台 | 文件 | 操作 |
|------|------|------|
| **macOS** | `fr-cli-installer` | 右键 → 打开，按提示完成安装 |
| **Windows** | `fr-cli-installer.exe` | 双击运行，按提示完成安装 |

> 安装程序会自动检测 Python、创建虚拟环境、安装依赖、生成 `fr-cli` 启动器。

### 方式二：命令行安装（高级用户）

```bash
# macOS / Linux
chmod +x fr-cli-install
./fr-cli-install

# Windows
python fr-cli-install
```

## 🚀 使用

安装完成后，在 release 目录下会生成 `fr-cli` 启动器：

```bash
# 直接运行
./fr-cli

# 添加到 PATH 后全局使用（推荐）
export PATH="$(pwd):$PATH"
fr-cli
```

## 📝 快速上手

```bash
fr-cli

# 与 AI 对话，描述需求即可自动调用工具
>>> 搜索 Python 最新特性并保存到文件
🧙 仙人 【调用：search_web({"query": "Python 最新特性"})】
🧙 仙人 【调用：write_file({"path": "python_news.md", "content": "..."})】

# 启动 Agent HTTP API 服务（供外部系统调用）
>>> /agent_server start 8080

# 调用本机应用
>>> /open /Users/me/report.pdf
>>> /launch chrome https://github.com
>>> /launch 微信
>>> /apps

# 用户直接命令
>>> /ls
>>> /cat python_news.md
>>> /save mysession
>>> /exit
```

## 📋 环境要求

- **Python 3.8+**（安装程序会自动检测，未安装会提示下载）
- 安装时自动创建虚拟环境，**不需要管理员权限**

## 🛠️ 手动安装（已有 Python 环境）

```bash
pip install fr_cli-2.1.0-py3-none-any.whl
fr-cli
```

## 🗑️ 卸载

直接删除 release 目录即可，所有文件（含虚拟环境）都在该目录内。

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `fr-cli-installer` | **macOS 可执行安装程序**（已内嵌安装包，双击运行） |
| `fr-cli-installer.exe` | **Windows 可执行安装程序**（已内嵌安装包，双击运行） |
| `fr-cli-install` | 跨平台 Python 安装脚本（命令行备用） |
| `fr-cli-install.sh` | macOS / Linux 安装脚本（备用） |
| `fr-cli-install.bat` | Windows 安装脚本（备用） |
| `fr_cli-2.1.0-py3-none-any.whl` | 程序安装包 |

## ❓ 常见问题

**Q: macOS 提示 "无法打开，因为无法验证开发者"？**
A: 右键点击 `fr-cli-installer`，选择 "打开"，然后在弹出的对话框中再次点击 "打开"。

**Q: 安装后输入 fr-cli 提示命令不存在？**
A: 
- macOS/Linux: 将 release 目录添加到 PATH，或使用完整路径 `./fr-cli` 运行
- Windows: 打开新的命令提示符窗口再试，或双击 `fr-cli.bat` 运行

**Q: 需要联网吗？**
A: 安装时需要联网下载 `zhipuai` 等依赖。运行时需要联网调用智谱 AI API。
