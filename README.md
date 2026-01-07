# NetEase Cloud Music MCP Server

基于 MCP 协议的网易云音乐评论区分析工具。

## 核心问题

> **如何让 AI 理解一个有几十万条评论的评论区？**

传统做法是全量爬取 + 统计分析，但：
- 热门歌曲几十万评论，全爬要数小时
- 统计结果 AI 看不懂，无法验证
- 情感算法经常误判（"我恨这首歌让我哭" 被判负面）

## 解决方案

**不追求"大而全"，而是"少而精"**——用有限样本让 AI 做可靠推断。

### 1. 智能采样

固定结构：**热评(15) + 最新(offset) + 历史(cursor)**

| 级别 | 数量 | 场景 |
|------|------|------|
| quick | 200 | 快速预览 |
| standard | 600 | 日常分析 |
| deep | 1000 | 深度研究 |

根据歌曲年龄自动调整比例：新歌侧重最新评论，老歌侧重历史覆盖。

### 2. 分层加载

```
Layer 0: 数据概览 → 有多少评论、覆盖几年
Layer 1: 六维度信号 → 情感、主题、趋势（量化指标）
Layer 2: 验证样本 → 锚点+对比样本（供 AI 验证）
Layer 3: 原始评论 → 按需筛选
```

AI 按需加载，不一次性获取所有数据。

### 3. 强制流程

数据量 <100 条时阻断分析，要求先采样。防止 AI 跳过关键步骤。

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 配置 Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "netease-music": {
      "command": "python",
      "args": ["path/to/mcp_server/server.py"]
    }
  }
}
```

### 使用

```
"帮我分析《晴天》的评论区"
```

## 工具列表

| 工具 | 功能 |
|------|------|
| `search_songs_tool` | 搜索 |
| `confirm_song_selection_tool` | 确认 |
| `add_song_to_database` | 入库 |
| `sample_comments_tool` | 采样 |
| `get_analysis_overview_tool` | Layer 0 |
| `get_analysis_signals_tool` | Layer 1 |
| `get_analysis_samples_tool` | Layer 2 |
| `get_raw_comments_v2_tool` | Layer 3 |

## 技术亮点

- **weapi cursor**：突破 offset 限制，可跳转任意历史时间
- **对比样本**：高赞低分评论，发现算法盲区
- **六维度分析**：情感/内容/时间/结构/社交/语言

## License

MIT
