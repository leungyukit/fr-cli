@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: 凡人打字机 (fr-cli) Windows 安装脚本
:: ============================================================

title fr-cli 安装器
color 0F

echo.
echo  ============================================
echo     凡人打字机 (fr-cli) 安装器
echo  ============================================
echo.

set "SCRIPT_DIR=%~dp0"
set "WHEEL_FILE=%SCRIPT_DIR%fr_cli-2.1.0-py3-none-any.whl"

if not exist "%WHEEL_FILE%" (
    echo [错误] 未找到安装包: %WHEEL_FILE%
    pause
    exit /b 1
)

:: 检测 Python
echo [*] 正在检测 Python 环境...
set "PYTHON="
for %%P in (python python3 py) do (
    %%P -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)" 2>nul
    if !errorlevel! equ 0 (
        set "PYTHON=%%P"
        goto :found_python
    )
)

echo [错误] 未找到 Python 3.8+。
echo 请从 https://python.org 下载并安装 Python 3.8 或更高版本。
echo 安装时请务必勾选 "Add Python to PATH"。
pause
exit /b 1

:found_python
for /f "tokens=*" %%a in ('%PYTHON% --version 2^>^&1') do set "PYVER=%%a"
echo [OK] 检测到 %PYVER%

:: 创建虚拟环境
set "VENV_DIR=%SCRIPT_DIR%.venv"
echo.
echo [*] 步骤 1/3：创建虚拟环境...
%PYTHON% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [错误] 虚拟环境创建失败。
    pause
    exit /b 1
)

:: 安装
echo [*] 步骤 2/3：安装 fr-cli 及依赖...
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet "%WHEEL_FILE%"
if errorlevel 1 (
    echo [错误] 安装失败。
    pause
    exit /b 1
)

:: 创建启动器
echo [*] 步骤 3/3：创建启动器...
set "LAUNCHER=%SCRIPT_DIR%fr-cli.bat"
(
    echo @echo off
    echo call "%~dp0.venv\Scripts\activate.bat" ^>nul
    echo fr-cli %%*
) > "%LAUNCHER%"

:: 验证
echo.
echo [*] 验证安装...
if exist "%VENV_DIR%\Scripts\fr-cli.exe" (
    echo [OK] fr-cli 安装验证通过！
) else (
    if exist "%LAUNCHER%" (
        echo [OK] fr-cli 安装验证通过！
    ) else (
        echo [错误] 安装验证失败。
        pause
        exit /b 1
    )
)

:: 完成
echo.
echo  ============================================
echo     安装完成！
echo  ============================================
echo.
echo  使用方式:
echo     直接运行: %LAUNCHER%
echo.
echo  添加到全局 PATH (推荐):
echo     1. 打开 "系统属性 ^> 高级 ^> 环境变量"
echo     2. 编辑 Path 变量，添加:
echo        %SCRIPT_DIR%
echo     3. 新建命令提示符窗口，输入 fr-cli 即可使用
echo.
pause
