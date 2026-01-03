# NetEase Cloud Music MCP

> 网易云音乐评论分析 MCP 工具

## 功能

- **情感分析** - 评论情感分类，支持内部自动采样
- **时间线分析** - 追踪评论区情绪随时间变化
- **歌曲对比** - 多维度 PK 对比两首歌的评论
- **关键词提取** - 词云生成、主题聚类
- **可视化** - 情感分布图、趋势图

## 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/1mht/netease-cloud-music-mcp.git
cd netease-cloud-music-mcp
pip install -r requirements.txt
```

### 2. 配置 MCP 客户端

本项目兼容所有支持 MCP 协议的客户端。

#### Claude Desktop

编辑配置文件（Windows: `%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "netease-music": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/netease-cloud-music-mcp"
    }
  }
}
```

#### Claude Code (CLI)

```bash
claude mcp add netease-music -- python -m mcp_server.server
```

### 3. 开始使用

```
你：搜索周杰伦的晴天
Claude：[展示搜索结果，等待你选择]

你：选第1首
Claude：[确认选择]

你：分析这首歌的评论情感
Claude：[返回情感分析结果]
```

## 工具列表

| 类别 | 工具 | 功能 |
|------|------|------|
| 搜索 | `search_songs_tool` | 搜索歌曲 |
| 搜索 | `confirm_song_selection_tool` | 确认选择 |
| 分析 | `analyze_sentiment_tool` | 情感分析 |
| 分析 | `analyze_sentiment_timeline_tool` | 情感时间线 |
| 分析 | `compare_songs_tool` | 歌曲 PK 对比 |
| 分析 | `extract_keywords_tool` | 关键词提取 |
| 分析 | `cluster_comments_tool` | 主题聚类 |
| 可视化 | `visualize_sentiment_tool` | 情感分布图 |
| 可视化 | `generate_wordcloud_tool` | 词云图 |

## 技术特点

- **内部自动采样** - 分析工具自动检测数据不足并触发采样
- **分层采样策略** - 热评 + 最新 + 历史 cursor 时间跳转
- **两步搜索架构** - 强制用户确认选择，避免 AI 自作主张

## 项目结构

```
netease-cloud-music-mcp/
├── mcp_server/              # MCP 服务器
│   ├── server.py            # 主入口
│   ├── tools/               # 工具模块
│   └── knowledge/           # 知识库
├── netease_cloud_music/     # 网易云 API
└── docs/                    # 文档
```

## License

MIT

## Author

1mht
