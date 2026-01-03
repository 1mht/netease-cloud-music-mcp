#!/usr/bin/env python3
"""
NetEase Music Data Science MCP Server
网易云音乐数据科学 MCP 服务器

功能：
1. 数据收集：搜索歌曲、添加到数据库、爬取评论
2. 数据分析：情感分析、可视化
3. 播放控制：调用网易云客户端播放（暂未启用）

Author: 1mht
Date: 2025-12-27
"""

import sys
import os
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入 FastMCP
try:
    from fastmcp import FastMCP
except ImportError:
    print("❌ 错误: 未安装 fastmcp")
    print("请运行: pip install fastmcp")
    sys.exit(1)

# 导入工具模块
from tools.search import search_songs, format_search_results, confirm_song_selection
from tools.data_collection import (
    add_song_basic,
    crawl_all_comments,
    get_song_details,
    list_songs_in_database
)
from tools.batch_collection import (
    get_database_statistics
)
from tools.sentiment_analysis import (
    analyze_sentiment
)
from tools.content_analysis import (
    extract_keywords,
    classify_comments
)
from tools.topic_modeling import (
    perform_topic_modeling
)
from tools.sociology_analysis import (
    detect_social_metaphors
)
from tools.visualization import (
    visualize_sentiment_distribution,
    visualize_comment_timeline,
    generate_wordcloud
)
from tools.pagination_sampling import (
    get_comments_metadata,
    get_comments_by_pages,
    get_cultural_context,
    get_real_comments_count_from_api
)
from tools.timeline_analysis import (
    analyze_sentiment_timeline
)
from tools.song_comparison import (
    compare_songs_advanced
)
from knowledge import get_platform_domain_knowledge

# 创建 MCP 服务器实例
mcp = FastMCP("NetEase Music Data Science Server")

logger.info("🎵 NetEase Music Data Science MCP Server 正在初始化...")


# ============================================================
# 数据收集工具组
# ============================================================

@mcp.tool()
def search_songs_tool(keyword: str, limit: int = 10) -> dict:
    """搜索网易云音乐歌曲（两步架构第一步：返回选项列表，不返回song_id）。

    ⛔ 严禁自作主张！必须让用户选择！

    🏗️ 架构设计（强制两步操作）：
    ┌─────────────────┐
    │ Step 1: Search  │  ← 你在这里
    │ 返回 session_id │
    │ 不返回 song_id  │
    └────────┬────────┘
             │ ⛔ 严禁跳过！必须询问用户
             ↓
    ┌─────────────────┐
    │ 用户选择        │  ← 必须等待用户回复
    └────────┬────────┘
             ↓
    ┌─────────────────┐
    │ Step 2: Confirm │  ← 用户选择后才能调用
    │ 返回 song_id    │
    └─────────────────┘

    ⛔⛔⛔ 严禁以下行为 ⛔⛔⛔
    ❌ 搜索后直接调用confirm（不等用户选择）
    ❌ 自己判断"用户想要第1首"然后选择
    ❌ 看到"林俊杰原版"就自作主张选择

    ✅ 正确行为：
    1. 展示所有选项给用户
    2. 询问"请选择第几首？"
    3. 等待用户回复
    4. 用户说"选1"后才调用confirm

    Args:
        keyword: 搜索关键词。支持格式：
            - "歌名" (如 "晴天")
            - "歌名 歌手" (如 "晴天 周杰伦") - 推荐
        limit: 返回结果数量，范围 1-30，默认 10。

    Returns:
        {
            "status": "pending_selection",
            "session_id": "search_abc123...",
            "keyword": "晴天",
            "count": 5,
            "choices": [...],
            "next_step": "展示choices给用户，等待用户选择"
        }
    """
    logger.info(f"🔍 搜索歌曲: {keyword}")
    results = search_songs(keyword, limit=limit)
    return format_search_results(results, keyword)


@mcp.tool()
def confirm_song_selection_tool(session_id: str, choice_number: int) -> dict:
    """确认用户选择的歌曲（两步架构第二步：返回song_id）。

    Args:
        session_id: 由 search_songs_tool 返回的 session_id
        choice_number: 用户选择的序号（1-based，例如用户说"第3首"则传入3）

    Returns:
        {
            "status": "confirmed",
            "song_id": "185811",  // ← 现在可以获得 song_id 了
            "song_name": "晴天",
            "artists": ["周杰伦"],
            "album": "叶惠美",
            "message": "✅ 已确认选择：..."
        }

    Error Returns:
        - 无效的 session_id → 提示重新搜索
        - 超出范围的 choice_number → 提示有效范围

    使用示例：
    1. 用户："我要第2首"
    2. 你：confirm_song_selection_tool(session_id="search_abc123", choice_number=2)
    3. 获得 song_id 后：get_comments_metadata_tool(song_id="...")
    """
    logger.info(f"✅ 确认选择: session={session_id}, choice={choice_number}")
    return confirm_song_selection(session_id, choice_number)


@mcp.tool()
def add_song_to_database(song_data: dict = None, song_id: str = None) -> dict:
    """将歌曲添加到数据库（元数据 + 歌词 + 热门评论/最新评论）。

    📋 前置条件（v0.6.6）:
    ✓ 推荐流程: search_songs_tool → confirm_song_selection_tool 获取完整歌曲信息
    ✓ 如果已知 song_id，可直接传 song_id 调用

    Args:
        song_data: confirm_song_selection_tool 返回的 full_info 字段
                  或者包含 'id' 字段的歌曲对象
        song_id: Optional song ID (use when you already know the ID)

    正确调用方式:
    ```python
    # Step 1: 搜索
    result1 = search_songs_tool(keyword="晴天")

    # Step 2: 确认选择
    result2 = confirm_song_selection_tool(
        session_id=result1["session_id"],
        choice_number=1
    )

    # Step 3: 添加到数据库 ✅ 使用 full_info
    result3 = add_song_to_database(song_data=result2["full_info"])
    ```

    Returns:
        {
            "status": "success",
            "song_id": "185811",
            "song_name": "晴天",
            "data_collected": {...},
            "next_actions": "..."  # v0.6.6: workflow引导
        }
    """
    display_name = None
    if isinstance(song_data, dict):
        display_name = song_data.get("name")
    logger.info(f"Add song to database: {display_name or song_id or 'Unknown'}")

    if song_data is None:
        if not song_id:
            return {
                "status": "error",
                "message": "song_data or song_id is required"
            }
        result = add_song_basic(None, song_id=song_id)
    else:
        result = add_song_basic(song_data)

    # v0.6.6: 添加next_actions引导AI完成workflow
    if result.get("status") == "success":
        song_id = result.get("song_id")
        song_name = result.get("song_name")
        result["next_actions"] = f"""
【workflow引导 - v0.6.6】

✅ 歌曲已成功添加到数据库！
📋 song_id: {song_id}
🎵 歌曲: {song_name}

下一步操作:

1️⃣ 获取评论数据（必需，才能进行分析）:
   → 推荐: get_comments_by_pages_tool(song_id="{song_id}", data_source="api", pages=[1,2,3])
   → 或全量爬取: crawl_all_comments_for_song(song_id="{song_id}") ⚠️ 耗时长

2️⃣ 数据分析（需要先完成步骤1）:
   → 情感分析: analyze_sentiment_tool(song_id="{song_id}")
   → 关键词提取: extract_keywords_tool(song_id="{song_id}")
   → 主题聚类: cluster_comments_tool(song_id="{song_id}")

3️⃣ 数据可视化（需要先完成步骤1）:
   → 情感分布: visualize_sentiment_tool(song_id="{song_id}")
   → 时间趋势: visualize_timeline_tool(song_id="{song_id}")
   → 词云图: generate_wordcloud_tool(song_id="{song_id}")
"""

    return result


@mcp.tool()
def crawl_all_comments_for_song(song_id: str, confirm: bool = True, detect_deletions: bool = False) -> dict:
    """抓取歌曲的全部评论。

    Args:
        song_id: 歌曲ID。
        confirm: True (默认) 仅返回预估耗时信息；False 开始实际抓取。
        detect_deletions: 是否检测已删除的评论（仅在 full sync 时使用）。

    Returns:
        预估信息 (confirm=True) 或 抓取结果 (confirm=False)。
    """
    logger.info(f"🕷️  爬取评论: song_id={song_id}, confirm={confirm}, detect_deletions={detect_deletions}")
    return crawl_all_comments(song_id, confirm, detect_deletions=detect_deletions)


@mcp.tool()
def get_song_info(song_id: str, include_comments: bool = True) -> dict:
    """获取数据库中存储的歌曲详细信息。

    Args:
        song_id: 歌曲ID。
        include_comments: 是否包含评论预览 (默认 True)。

    Returns:
        歌曲详情，包括元数据和部分评论。
    """
    logger.info(f"📊 获取歌曲详情: song_id={song_id}")
    return get_song_details(song_id, include_comments=include_comments)


@mcp.tool()
def list_all_songs() -> list:
    """列出数据库中已有的所有歌曲。

    Returns:
        歌曲列表摘要。
    """
    logger.info("📋 列出数据库中的所有歌曲")
    return list_songs_in_database()


# ============================================================
# 批量数据收集工具组
# ============================================================

@mcp.tool()
def get_stats_tool() -> dict:
    """获取数据库整体统计信息。

    Returns:
        包含歌曲总数、评论总数等统计数据。
    """
    logger.info("[Stats] 获取数据库统计")
    return get_database_statistics()


# ============================================================
# 情感分析工具组
# ============================================================

@mcp.tool()
def analyze_sentiment_tool(song_id: str, model_type: str = "simple") -> dict:
    """分析歌曲评论的情感分布（正面/中性/负面）。

    使用 SnowNLP 对评论进行情感打分 (0-1)，统计情感分布。

    Args:
        song_id: 歌曲ID。
        model_type:
            - "simple" (默认): 使用 SnowNLP，速度快
            - "advanced": 使用增强模型（暂未实现）

    Returns:
        {
            "status": "success",
            "song_name": "晴天",
            "total_analyzed": 500,
            "sentiment_distribution": {
                "positive": {"count": 300, "percentage": "60.0%"},
                "neutral": {"count": 150, "percentage": "30.0%"},
                "negative": {"count": 50, "percentage": "10.0%"}
            },
            "average_score": 0.72,  # 0-1，越高越正面
            "sample_comments": {...}  # 各类别示例
        }

    ⚠️ AI必读:
        - 如果返回 status="error"，检查 suggestion 字段获取解决方案
        - 样本量 < 100 时，结果可能不具代表性，需提示用户
        - 网易云评论普遍偏正面（平均 0.65-0.75），低于 0.5 说明负面情绪显著
    """
    logger.info(f"[Sentiment] 分析情感: song_id={song_id}")
    return analyze_sentiment(song_id, model_type)


@mcp.tool()
def extract_keywords_tool(song_id: str, top_k: int = 20, sampling_strategy: str = "auto") -> dict:
    """提取评论区的核心关键词 (TF-IDF)。

    用于发现评论区的讨论焦点、热门梗或情感载体。
    比词云图片更适合 AI 直接理解。

    Args:
        song_id: 歌曲ID。
        top_k: 返回前K个关键词 (默认 20)。
        sampling_strategy: "auto" (智能采样，默认), "full", "random_sample"。
    """
    logger.info(f"[NLP] 提取关键词: song_id={song_id}, top_k={top_k}, strategy={sampling_strategy}")
    return extract_keywords(song_id, top_k, sampling_strategy)


@mcp.tool()
def classify_comments_tool(song_id: str, sampling_strategy: str = "auto") -> dict:
    """[核心工具] 评论成分分类器。

    将评论区自动分类为：
    1. Story (故事/小作文): 含金量最高，包含用户情感经历
    2. Meme (玩梗/吐槽): 网易云特色，包含流行语
    3. Review (乐评): 讨论音乐制作本身
    4. Short (短评): 信息量低

    Args:
        song_id: 歌曲ID
        sampling_strategy: "auto" (智能采样，默认), "full", "random_sample"。

    用途：
    - 想看"故事"时，只看 Story 类
    - 想了解"梗"时，看 Meme 类
    - 过滤掉无关信息，提高分析质量

    ⚠️ 注意:
        - 如果 Short 占比过高 (>80%)，说明该评论区可能缺乏深度讨论。
        - 此时应降低分析预期，不要强行寻找"深刻故事"。
    """
    logger.info(f"[NLP] 评论分类: song_id={song_id}, strategy={sampling_strategy}")
    return classify_comments(song_id, sampling_strategy)


@mcp.tool()
def detect_social_metaphors_tool(song_id: str, sampling_strategy: str = "auto") -> dict:
    """[高级工具] 社会学隐喻检测器。
    
    分析评论区隐含的话语策略，包括：
    - Nationalism: 宏大叙事/民族主义
    - Resistance_Irony: 解构/反讽/抵抗
    - Identity: 群体归属/认同建构
    - Hyperreality: 符号游戏/后真实
    
    Args:
        song_id: 歌曲ID
        sampling_strategy: 
            - "auto" (默认): 智能采样，平衡速度与覆盖。
            - "full": 强制分析所有数据（仅限小规模评论区）。
            - "top_liked": 只分析热门评论（看主流观点）。
            - "recent": 只分析最新评论（看即时舆论）。

    ⚠️ 风险控制:
        - 如果某个维度的占比极低 (<1%)，请如实报告"未检测到显著特征"。
        - **严禁**对低频词汇进行过度解读或强行关联理论。
    """
    logger.info(f"[Sociology] 隐喻检测: song_id={song_id}, strategy={sampling_strategy}")
    return detect_social_metaphors(song_id, sampling_strategy)


@mcp.tool()
def cluster_comments_tool(song_id: str, n_topics: int = 3) -> dict:
    """使用 LDA 算法将评论聚类为潜在主题。

    这是一个高级数据分析工具 (Topic Modeling)。
    它可以自动发现评论区隐含的几个讨论方向（例如：玩梗、歌词感悟、社会议题）。

    Args:
        song_id: 歌曲ID。
        n_topics: 希望发现几个主题 (默认 3)。

    Returns:
        包含每个主题的关键词列表和权重。AI 应根据关键词总结主题含义。
    """
    logger.info(f"[NLP] 主题聚类 (LDA): song_id={song_id}, n_topics={n_topics}")
    return perform_topic_modeling(song_id, n_topics)


# ============================================================
# 时间线分析工具组 (v0.7.0 Feature 1)
# ============================================================

@mcp.tool()
def analyze_sentiment_timeline_tool(
    song_id: str,
    time_granularity: str = "year",
    sample_per_period: int = 50
) -> dict:
    """【v0.7.0新功能】分析评论情感随时间的变化趋势。

    核心价值：发现"网抑云"现象何时开始、情感转折点在哪里。

    📋 前置条件:
    ✓ 歌曲必须已存在于数据库（通过search→confirm流程）
    ✓ 数据库中必须有带时间戳的评论数据（建议100+条）

    Args:
        song_id: 歌曲ID（需先调用confirm_song_selection获取）
        time_granularity: 时间粒度
            - "year": 按年聚合（适合老歌，如《晴天》发布12年）
            - "quarter": 按季度（适合2-3年内的歌曲）
            - "month": 按月（适合1年内的新歌）
        sample_per_period: 每个时间段采样评论数（默认50，建议30-100）

    Returns:
        {
            "status": "success",
            "song_info": {"id": "185811", "name": "晴天", "artist": "周杰伦"},
            "time_range": {"start": "2013-07-15", "end": "2025-12-30", "span_years": 12.5},
            "timeline": [
                {"period": "2015", "avg_sentiment": 0.72, "top_keywords": ["青春", "回忆"]},
                {"period": "2020", "avg_sentiment": 0.45, "top_keywords": ["emo", "网抑云"]}
            ],
            "insights": {
                "trend": "declining",
                "turning_points": [{"period": "2020", "change": -0.27, "possible_reason": "网抑云文化"}],
                "summary": "情感从2015年的0.72下降到2020年的0.45"
            }
        }

    使用示例:
        用户: "分析《晴天》的情感变化"
        AI: [调用 analyze_sentiment_timeline_tool(song_id="185811", time_granularity="year")]
            发现《晴天》的评论情感从2013年的0.72下降到2020年的0.45，
            转折点在2020年，与"网抑云"文化兴起时间吻合。

    ⚠️ 注意:
        - 新歌（<1年）建议用 month 粒度
        - 老歌（>5年）建议用 year 粒度
        - 样本太少时结果可能不稳定
    """
    logger.info(f"[Timeline] 情感时间线分析: song_id={song_id}, granularity={time_granularity}")
    return analyze_sentiment_timeline(song_id, time_granularity, sample_per_period)


# ============================================================
# 歌曲对比工具组 (v0.7.0 Feature 3)
# ============================================================

@mcp.tool()
def compare_songs_tool(
    song_id_a: str,
    song_id_b: str,
    sample_size: int = 200
) -> dict:
    """【v0.7.0新功能】对比两首歌曲的评论特征。

    核心价值：多维度对比两首歌，发现差异和相似之处。

    📋 前置条件:
    ✓ 两首歌必须已存在于数据库（通过search→confirm流程）
    ✓ 两首歌必须有评论数据（建议各100+条）

    Args:
        song_id_a: 第一首歌的ID
        song_id_b: 第二首歌的ID
        sample_size: 每首歌采样评论数（默认200，建议100-500）

    Returns:
        {
            "status": "success",
            "songs": {
                "a": {"id": "185811", "name": "晴天", "artist": "周杰伦"},
                "b": {"id": "186016", "name": "七里香", "artist": "周杰伦"}
            },
            "comparison": {
                "sentiment": {
                    "a_score": 0.68, "b_score": 0.75,
                    "winner": "b", "insight": "《七里香》更正面"
                },
                "keywords": {
                    "common": ["青春", "怀念"],
                    "a_unique": ["emo", "深夜"],
                    "b_unique": ["甜蜜", "夏天"],
                    "insight": "共同主题'青春'，但风格不同"
                },
                "engagement": {
                    "a_total_likes": 125000, "b_total_likes": 98000,
                    "insight": "《晴天》互动量更高"
                }
            },
            "overall": {
                "similarity": 0.72,
                "verdict": "两首歌相似度较高",
                "key_difference": "《晴天》更忧郁，《七里香》更甜蜜"
            }
        }

    使用示例:
        用户: "对比《晴天》和《七里香》"
        AI: [先confirm两首歌，然后调用 compare_songs_tool]
            📊 情感：《七里香》(0.75)略胜《晴天》(0.68)
            🔤 关键词：共同主题'青春'，《晴天》更忧郁，《七里香》更甜蜜
            💬 互动：《晴天》点赞量更高
            📈 相似度：72%

    ⚠️ 注意:
        - 两首歌都需要在数据库中
        - 如果某首歌评论太少，结果可能不稳定
    """
    logger.info(f"[Compare] 歌曲对比: {song_id_a} vs {song_id_b}")
    return compare_songs_advanced(song_id_a, song_id_b, sample_size)


# ============================================================
# 数据可视化工具组
# ============================================================

@mcp.tool()
def visualize_sentiment_tool(song_id: str) -> dict:
    """生成情感分布的可视化图表 (Base64)。

    Args:
        song_id: 歌曲ID。

    Returns:
        包含图像 Base64 编码的字典。
    """
    logger.info(f"[Visualize] 情感分布图: song_id={song_id}")
    return visualize_sentiment_distribution(song_id)


@mcp.tool()
def visualize_timeline_tool(song_id: str, interval: str = "month") -> dict:
    """生成评论时间趋势图表 (Base64)。

    Args:
        song_id: 歌曲ID。
        interval: 聚合间隔 ("day", "month", "year")。

    Returns:
        包含图像 Base64 编码的字典。
    """
    logger.info(f"[Visualize] 时间线图: song_id={song_id}, interval={interval}")
    return visualize_comment_timeline(song_id, interval)


@mcp.tool()
def generate_wordcloud_tool(song_id: str, max_words: int = 100) -> dict:
    """生成评论词云图 (Base64)。

    Args:
        song_id: 歌曲ID。
        max_words: 词云最大词数。

    Returns:
        包含图像 Base64 编码的字典。
    """
    logger.info(f"[Visualize] 词云图: song_id={song_id}, max_words={max_words}")
    return generate_wordcloud(song_id, max_words)


# ============================================================
# AI智能采样工具组（原子化设计）
# ============================================================

@mcp.tool()
def get_real_comment_count_tool(song_id: str) -> dict:
    """从网易云 API 获取歌曲的真实评论总数。

    Args:
        song_id: 歌曲ID。

    Returns:
        包含 total_comments (API真实值)。
    """
    logger.info(f"[API Count] 获取真实评论总数: song_id={song_id}")
    return get_real_comments_count_from_api(song_id)


@mcp.tool()
def get_comments_metadata_tool(song_id: str, include_api_count: bool = True) -> dict:
    """【关键工具】获取评论数据的元信息，用于判断数据是否充足。

    在进行任何分析之前，建议先调用此工具检查数据状态。

    Args:
        song_id: 歌曲ID（从 search_songs_tool 结果中获取）。
        include_api_count: 是否请求 API 获取真实评论总数，默认 True。

    Returns:
        {
            "song_id": "185811",
            "database_count": 500,        # 数据库中的评论数
            "api_total_count": 10000,     # API真实评论总数
            "cache_status": {
                "cache_level": "sampled",   # none/basic/sampled/full
                "cache_freshness": "fresh"  # very_fresh/fresh/stale/outdated
            },
            "comparison": {
                "database_coverage": "5.0%",  # 覆盖率
                "data_status": "partial",     # insufficient/partial/sufficient/fresh
                "suggestion": "建议采样更多数据..."
            }
        }

    ⚠️ AI必读:
        - coverage < 10%: 数据严重不足，分析结果可能不可靠
        - coverage 10-30%: 可做初步分析，需提示用户样本量有限
        - coverage > 30%: 可进行正常分析

    常见后续操作:
        - 数据不足 → get_comments_by_pages_tool(data_source='api')
        - 需要完整数据 → crawl_all_comments_for_song()
    """
    logger.info(f"[Metadata] 获取评论元信息: song_id={song_id}, include_api_count={include_api_count}")
    return get_comments_metadata(song_id, include_api_count)


@mcp.tool()
def get_comments_by_pages_tool(song_id: str, pages: list, sort_by: str = "time", data_source: str = "auto") -> dict:
    """获取指定页码的评论列表。

    Args:
        song_id: 歌曲ID。
        pages: 页码列表 (例如 [1, 2, 10])。
        sort_by: 排序方式 ("time" 或 "hot")。
        data_source: "auto" (智能切换), "database" (仅本地), "api" (仅远程)。

    Returns:
        包含评论列表的字典。
    """
    logger.info(f"[Pagination] 获取评论: song_id={song_id}, pages={pages}, sort_by={sort_by}, data_source={data_source}")
    return get_comments_by_pages(song_id, pages, sort_by, data_source)


@mcp.tool()
def get_cultural_context_tool(song_id: str) -> dict:
    """获取相关的网络文化背景知识。

    Args:
        song_id: 歌曲ID。

    Returns:
        包含文化现象解释、艺术家背景等。
    """
    logger.info(f"[Cultural] 获取文化背景: song_id={song_id}")
    return get_cultural_context(song_id)


@mcp.tool()
def get_platform_knowledge_tool() -> dict:
    """获取网易云音乐平台的统计特征和领域知识。

    Returns:
        包含评论分布统计、采样建议等参考知识。
    """
    logger.info("[Platform Knowledge] 获取平台领域知识")
    return get_platform_domain_knowledge()


# ============================================================
# 服务器信息工具
# ============================================================

@mcp.tool()
def get_server_info() -> dict:
    """获取服务器状态和功能列表。"""
    logger.info("ℹ️  获取服务器信息")

    return {
        "server_name": "NetEase Music Data Science Server",
        "version": "0.7.0",
        "description": "Atomic Tool Design + MCP Resources (v0.7.0)",
        "features": {
            "data_collection": True,
            "sentiment_analysis": True,
            "sentiment_timeline": True,
            "song_comparison": True,
            "data_analysis": True,
            "visualization": True,
            "playback_control": True,
            "ai_intelligent_sampling": True,  # 新增：AI智能翻页
            "cultural_context": True,         # 新增：文化背景知识
            "content_analysis": True,         # 新增：NLP内容挖掘
            "topic_modeling": True,
            "comment_classification": True,
            "sociology_analysis": True       # 新增：社会学隐喻分析
        },
        "tools_count": 23,
        "resources_count": 6,
        "resources": [
            "netease://database/schema",      # 数据库结构
            "netease://database/statistics",  # 数据库统计
            "netease://guide/best-practices", # 最佳实践(可选参考)
            "netease://songs/list",           # 已入库歌曲列表
            "netease://cache/overview",       # 缓存状态概览
            "netease://tools/catalog"         # 工具分类目录
        ],
        "tools": [
            # 基础数据收集（6个）
            "search_songs_tool",
            "confirm_song_selection_tool",
            "add_song_to_database",
            "crawl_all_comments_for_song",
            "get_song_info",
            "list_all_songs",
            # 统计信息（1个）
            "get_stats_tool",
            # 情感分析（2个）
            "analyze_sentiment_tool",
            "analyze_sentiment_timeline_tool",
            # 歌曲对比（1个）
            "compare_songs_tool",
            # 内容挖掘（4个）
            "extract_keywords_tool",
            "cluster_comments_tool",
            "classify_comments_tool",
            "detect_social_metaphors_tool",
            # 数据可视化（3个）
            "visualize_sentiment_tool",
            "visualize_timeline_tool",
            "generate_wordcloud_tool",
            # AI智能采样（4个）- 核心创新
            "get_comments_metadata_tool",
            "get_comments_by_pages_tool",
            "get_real_comment_count_tool",
            "get_cultural_context_tool",
            "get_platform_knowledge_tool",
            # 服务器信息（1个）
            "get_server_info"
        ],
        "database_path": "data/music_data_v2.db",
        "status": "running"
    }


# ============================================================
# MCP Resources（被动数据流，供AI主动读取上下文）
# ============================================================

@mcp.resource("netease://database/schema")
def resource_database_schema() -> str:
    """数据库结构说明 - 让AI理解数据模型。

    Returns:
        数据库表结构的文本描述。
    """
    return """
# NetEase Music Database Schema (v0.6.6)

## 表: songs (歌曲表)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(20) | 歌曲ID (主键) |
| name | String(200) | 歌曲名称 |
| artist | String(200) | 歌手名称 |
| album | String(200) | 专辑名称 |
| duration_ms | Integer | 时长(毫秒) |
| publish_time | BigInteger | 发布时间戳 |
| lyrics | Text | 歌词内容 |
| created_at | DateTime | 入库时间 |
| cache_level | String(20) | 缓存级别: none/basic/sampled/full |
| cache_updated_at | BigInteger | 缓存更新时间 |
| cache_freshness | String(20) | 新鲜度: very_fresh/fresh/stale/outdated |
| api_total_comments_snapshot | Integer | API评论总数快照 |

## 表: comments (评论表)
| 字段 | 类型 | 说明 |
|------|------|------|
| comment_id | String(30) | 评论ID (主键) |
| song_id | String(20) | 所属歌曲ID (外键) |
| user_id | String(30) | 用户ID |
| user_name | String(100) | 用户名 |
| content | Text | 评论内容 |
| liked_count | Integer | 点赞数 |
| timestamp | BigInteger | 评论时间戳 |
| is_hot | Boolean | 是否热门评论 |
| is_deleted | Boolean | 是否已删除(软删除) |
| deleted_at | BigInteger | 删除检测时间 |

## 关系
- songs 1:N comments (一首歌有多条评论)
"""


@mcp.resource("netease://database/statistics")
def resource_database_statistics() -> str:
    """数据库当前状态统计 - 让AI了解可用数据规模。

    Returns:
        当前数据库的统计信息。
    """
    try:
        stats = get_database_statistics()
        return f"""
# 数据库统计概览

- 歌曲总数: {stats.get('total_songs', 0)} 首
- 评论总数: {stats.get('total_comments', 0)} 条
- 平均每首歌评论数: {stats.get('avg_comments_per_song', 0):.1f} 条

## 缓存状态分布
- 完整缓存 (full): 适合深度分析
- 采样缓存 (sampled): 适合概览分析
- 基础缓存 (basic): 仅热门评论
- 无缓存 (none): 需要先爬取

## 使用建议
- 分析前先调用 get_comments_metadata_tool 检查数据状态
- 数据不足时使用 data_source='api' 从API采样
"""
    except Exception as e:
        return f"# 数据库统计\n\n获取失败: {str(e)}"


@mcp.resource("netease://guide/best-practices")
def resource_best_practices() -> str:
    """工具使用最佳实践指南 - AI可选择性参考。

    Returns:
        工具使用的建议和注意事项（非强制）。
    """
    return """
# 工具使用最佳实践（建议参考，非强制流程）

## 核心原则
1. **数据优先**: 分析前检查数据是否充足
2. **用户确认**: 多选情况必须询问用户
3. **如实报告**: 数据不足时不要强行解读

## 常见场景建议

### 场景1: 用户想分析某首歌
建议顺序: 搜索 → 检查数据 → (可选)采样 → 分析
- 先用 get_comments_metadata_tool 看覆盖率
- 覆盖率 < 30% 时，建议先采样或爬取

### 场景2: 用户想看情感分布
- 评论数 < 100 条时，结果可能不具代表性
- 应提示用户"样本量较小，结论仅供参考"

### 场景3: 用户想做社会学研究
- 优先使用 classify_comments_tool 了解评论成分
- 如果 Short 类占比 > 80%，说明深度内容少
- 不要强行寻找"深刻含义"

## 参数选择建议
- sampling_strategy="auto": 大多数情况下使用
- sampling_strategy="top_liked": 想看主流观点
- sampling_strategy="recent": 想看最新舆论

## 风险提醒
- 网易云评论有时效性，热门评论可能变化
- 部分评论可能被删除，分析结果反映的是当前状态
"""


@mcp.resource("netease://songs/list")
def resource_songs_list() -> str:
    """已入库歌曲列表 - 让AI快速了解可分析的歌曲。

    Returns:
        数据库中所有歌曲的摘要列表。
    """
    try:
        songs = list_songs_in_database()
        if not songs:
            return "# 已入库歌曲\n\n数据库为空，请先使用 search_songs_tool 搜索并添加歌曲。"

        lines = ["# 已入库歌曲列表\n"]
        lines.append(f"共 {len(songs)} 首歌曲\n")
        lines.append("| 序号 | 歌曲名 | 歌手 | 评论数 | 缓存状态 |")
        lines.append("|------|--------|------|--------|----------|")

        for i, song in enumerate(songs, 1):
            name = song.get('name', '未知')[:20]
            artist = song.get('artist', '未知')[:15]
            comments = song.get('comment_count', 0)
            cache = song.get('cache_level', 'none')
            song_id = song.get('id', '')
            lines.append(f"| {i} | {name} | {artist} | {comments} | {cache} | `{song_id}` |")

        return "\n".join(lines)
    except Exception as e:
        return f"# 已入库歌曲\n\n获取失败: {str(e)}"


@mcp.resource("netease://cache/overview")
def resource_cache_overview() -> str:
    """缓存状态概览 - 让AI判断哪些歌曲需要更新数据。

    Returns:
        各歌曲的缓存新鲜度和建议操作。
    """
    try:
        songs = list_songs_in_database()
        if not songs:
            return "# 缓存状态概览\n\n数据库为空。"

        lines = ["# 缓存状态概览\n"]

        # 按缓存状态分类
        fresh_songs = []
        stale_songs = []
        outdated_songs = []

        for song in songs:
            freshness = song.get('cache_freshness', 'unknown')
            info = f"- {song.get('name', '?')} ({song.get('id', '?')}): {song.get('comment_count', 0)} 条评论"

            if freshness in ('very_fresh', 'fresh'):
                fresh_songs.append(info)
            elif freshness == 'stale':
                stale_songs.append(info)
            else:
                outdated_songs.append(info)

        lines.append("## 🟢 新鲜数据 (可直接分析)")
        lines.extend(fresh_songs if fresh_songs else ["- 无"])

        lines.append("\n## 🟡 轻度过期 (建议刷新)")
        lines.extend(stale_songs if stale_songs else ["- 无"])

        lines.append("\n## 🔴 严重过期 (强烈建议重新爬取)")
        lines.extend(outdated_songs if outdated_songs else ["- 无"])

        lines.append("\n## 操作建议")
        lines.append("- 新鲜数据: 直接进行分析")
        lines.append("- 轻度过期: 可先分析，如需最新数据再爬取")
        lines.append("- 严重过期: 建议使用 crawl_all_comments_for_song 更新")

        return "\n".join(lines)
    except Exception as e:
        return f"# 缓存状态概览\n\n获取失败: {str(e)}"


@mcp.resource("netease://tools/catalog")
def resource_tools_catalog() -> str:
    """工具分类目录 - 帮助AI快速找到合适的工具。

    Returns:
        按功能分类的工具列表和使用场景。
    """
    return """# MCP ??????

## ???? (6?)
| ?? | ?? | ?? |
|------|------|------|
| `search_songs_tool` | ???? | ???"??XX??" |
| `confirm_song_selection_tool` | ???? | ??????? song_id |
| `add_song_to_database` | ???? | ???????? |
| `crawl_all_comments_for_song` | ???? | ???????? |
| `get_song_info` | ???? | ???????? |
| `list_all_songs` | ???? | ?????? |

## ???? (5?)
| ?? | ?? | ?? |
|------|------|------|
| `analyze_sentiment_tool` | ???? | ????????? |
| `extract_keywords_tool` | ????? | ?????? |
| `classify_comments_tool` | ???? | ????/??/?? |
| `detect_social_metaphors_tool` | ???? | ????? |
| `cluster_comments_tool` | ???? | ?????? |

## ????? (1?)
| ?? | ?? | ?? |
|------|------|------|
| `analyze_sentiment_timeline_tool` | ????? | ??????? |

## ???? (1?)
| ?? | ?? | ?? |
|------|------|------|
| `compare_songs_tool` | ??PK?? | ??/???/??????? |

## ??? (3?)
| ?? | ?? | ?? |
|------|------|------|
| `visualize_sentiment_tool` | ????? | Base64 ?? |
| `visualize_timeline_tool` | ????? | Base64 ?? |
| `generate_wordcloud_tool` | ??? | Base64 ?? |

## ???? (4?)
| ?? | ?? | ?? |
|------|------|------|
| `get_comments_metadata_tool` | **??** ?????? | ?????? |
| `get_comments_by_pages_tool` | ?????? | ????? |
| `get_real_comment_count_tool` | ??????? | ??????? |
| `get_cultural_context_tool` | ???? | ????? |

## ???? (2?)
| ?? | ?? |
|------|------|
| `get_stats_tool` | ????? |
| `get_platform_knowledge_tool` | ?????? |

## ??????
1. ??/?? ? `search_songs_tool` + `confirm_song_selection_tool`
2. ???? ? `get_comments_metadata_tool`
3. ??/?? ? `get_comments_by_pages_tool` ? `crawl_all_comments_for_song`
4. ?? ? ??????????
5. ??? ? ????????
"""


# ============================================================
# 启动服务器
# ============================================================

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("[NetEase Music MCP Server v0.5.0 - Atomic & Simplified]")
    logger.info("=" * 70)
    # FastMCP 会自动处理 stdio 通信
    mcp.run()
