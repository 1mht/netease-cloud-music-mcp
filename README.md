# 🎵 NetEase Music MCP Server

> 让 Claude 帮你分析网易云音乐评论区

一句话让 AI 读懂几十万条评论背后的故事。

## ✨ 能做什么

```
你：帮我分析《晴天》的评论区

Claude：
📊 数据概览：采样 600 条评论，覆盖 2003-2024 年

🎯 核心发现：
1. 这是一个「青春回忆型」评论区，关键词：青春、回忆、那年、十七岁
2. 情感以怀旧为主，大量"感伤式金句"被高赞
3. TOP10 评论占据 43% 点赞，评论区由少数金句主导

💬 代表性评论：
> "那年我们十七岁，现在我们已经三十岁了" —— 12.5万赞
```

## 🚀 快速开始

### 1. 安装

```bash
git clone https://github.com/1mht/netease-cloud-music-mcp.git
cd netease-cloud-music-mcp
pip install -r requirements.txt
```

### 2. 配置 Claude Desktop

编辑 `claude_desktop_config.json`（Windows: `%APPDATA%\Claude\`）:

```json
{
  "mcpServers": {
    "netease-music": {
      "command": "python",
      "args": ["你的路径/mcp_server/server.py"]
    }
  }
}
```

### 3. 开始使用

重启 Claude Desktop，然后直接对话：

- "帮我分析《XXX》的评论区"
- "搜索歌曲 晴天"
- "对比《晴天》和《七里香》的评论区"

## 🎯 特色功能

| 功能 | 说明 |
|------|------|
| **智能采样** | 1分钟内从几十万评论中提取代表性样本 |
| **六维度分析** | 情感、内容、时间、结构、社交、语言 |
| **算法纠偏** | AI 阅读原文，修正情感分析误判 |
| **透明可信** | 告诉你数据来源和局限，不做黑盒 |

## 📖 工作原理

```
200万条评论 → 智能采样 1000条 → 六维度量化 → AI 验证 → 生成报告
                  ↑
            热评 + 最新 + 历史（cursor时间跳转）
```

**为什么不全量爬取？**
- 太慢（要几小时）
- 没必要（1000条足够发现模式）
- 更诚实（告诉 AI 这是采样，而不是假装完整）

## 🛠 技术栈

- MCP Server: [FastMCP](https://github.com/jlowin/fastmcp)
- NLP: jieba + SnowNLP
- 数据库: SQLite
- API: 网易云音乐 weapi

## 📝 License

MIT

---

**问题反馈**: [Issues](https://github.com/1mht/netease-cloud-music-mcp/issues)
