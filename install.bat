@echo off
REM NetEase Music MCP Server - Windows 安装脚本
REM ================================================

echo.
echo ========================================
echo   NetEase Music MCP Server Installer
echo ========================================
echo.

REM 检查 Python
echo [1/4] 检查 Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo.

REM 安装依赖
echo [2/4] 安装 Python 依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)
echo.

REM 获取安装路径
echo [3/4] 获取安装路径...
set INSTALL_PATH=%cd%
echo 安装路径: %INSTALL_PATH%
echo.

REM 生成配置
echo [4/4] 生成 Claude Desktop 配置...
set CONFIG_PATH=%APPDATA%\Claude\claude_desktop_config.json

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 接下来请按照以下步骤配置：
echo.
echo 1. 编辑 Claude Desktop 配置文件:
echo    %CONFIG_PATH%
echo.
echo 2. 添加以下配置:
echo.
echo {
echo   "mcpServers": {
echo     "netease-music": {
echo       "command": "python",
echo       "args": ["%INSTALL_PATH%\\mcp_server\\server.py"]
echo     }
echo   }
echo }
echo.
echo 3. 重启 Claude Desktop
echo.
echo ========================================
echo.

REM 询问是否打开配置文件
set /p OPEN_CONFIG="是否现在打开配置文件？(Y/N): "
if /i "%OPEN_CONFIG%"=="Y" (
    if exist "%CONFIG_PATH%" (
        notepad "%CONFIG_PATH%"
    ) else (
        echo.
        echo [提示] 配置文件不存在，请手动创建：
        echo %CONFIG_PATH%
        echo.
    )
)

echo.
echo 感谢使用！如有问题，请访问：
echo https://github.com/1mht/netease-cloud-music-mcp/issues
echo.
pause
