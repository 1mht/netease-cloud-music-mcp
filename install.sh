#!/bin/bash
# NetEase Music MCP Server - Linux/macOS 安装脚本
# ================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "========================================"
echo "  NetEase Music MCP Server Installer"
echo "========================================"
echo ""

# 检查 Python
echo -e "${YELLOW}[1/4]${NC} 检查 Python..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[错误]${NC} 未找到 Python 3，请先安装 Python 3.8+"
    echo "macOS: brew install python3"
    echo "Ubuntu/Debian: sudo apt-get install python3"
    exit 1
fi
python3 --version
echo ""

# 安装依赖
echo -e "${YELLOW}[2/4]${NC} 安装 Python 依赖..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}[错误]${NC} 依赖安装失败"
    exit 1
fi
echo ""

# 获取安装路径
echo -e "${YELLOW}[3/4]${NC} 获取安装路径..."
INSTALL_PATH=$(pwd)
echo "安装路径: $INSTALL_PATH"
echo ""

# 检测操作系统并设置配置路径
echo -e "${YELLOW}[4/4]${NC} 检测配置路径..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    CONFIG_PATH="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
    OS_NAME="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    CONFIG_PATH="$HOME/.config/Claude/claude_desktop_config.json"
    OS_NAME="Linux"
else
    CONFIG_PATH="$HOME/.config/Claude/claude_desktop_config.json"
    OS_NAME="Unknown"
fi

echo ""
echo -e "${GREEN}========================================"
echo "  安装完成！"
echo "========================================${NC}"
echo ""
echo "接下来请按照以下步骤配置："
echo ""
echo "1. 编辑 Claude Desktop 配置文件:"
echo "   $CONFIG_PATH"
echo ""
echo "2. 添加以下配置:"
echo ""
echo "{"
echo "  \"mcpServers\": {"
echo "    \"netease-music\": {"
echo "      \"command\": \"python3\","
echo "      \"args\": [\"$INSTALL_PATH/mcp_server/server.py\"]"
echo "    }"
echo "  }"
echo "}"
echo ""
echo "3. 重启 Claude Desktop"
echo ""
echo "========================================"
echo ""

# 询问是否打开配置文件
read -p "是否现在打开配置文件？(y/n): " OPEN_CONFIG
if [[ "$OPEN_CONFIG" == "y" || "$OPEN_CONFIG" == "Y" ]]; then
    if [ -f "$CONFIG_PATH" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            open -t "$CONFIG_PATH"
        else
            ${EDITOR:-nano} "$CONFIG_PATH"
        fi
    else
        echo ""
        echo -e "${YELLOW}[提示]${NC} 配置文件不存在，请手动创建："
        echo "$CONFIG_PATH"
        echo ""

        # 询问是否自动创建
        read -p "是否自动创建配置文件？(y/n): " CREATE_CONFIG
        if [[ "$CREATE_CONFIG" == "y" || "$CREATE_CONFIG" == "Y" ]]; then
            mkdir -p "$(dirname "$CONFIG_PATH")"
            cat > "$CONFIG_PATH" << EOF
{
  "mcpServers": {
    "netease-music": {
      "command": "python3",
      "args": ["$INSTALL_PATH/mcp_server/server.py"]
    }
  }
}
EOF
            echo -e "${GREEN}[成功]${NC} 配置文件已创建！"
            echo ""
            if [[ "$OSTYPE" == "darwin"* ]]; then
                open -t "$CONFIG_PATH"
            else
                ${EDITOR:-nano} "$CONFIG_PATH"
            fi
        fi
    fi
fi

echo ""
echo "感谢使用！如有问题，请访问："
echo "https://github.com/1mht/netease-cloud-music-mcp/issues"
echo ""
