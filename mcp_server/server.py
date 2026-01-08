#!/usr/bin/env python3
"""
NetEase Music Data Science MCP Server (v0.8.7)

核心工具 (9个):
1. search_songs_tool - 搜索歌曲
2. confirm_song_selection_tool - 确认选择
3. add_song_to_database - 入库
4. sample_comments_tool - 采样(三级: quick/standard/deep)
5. get_analysis_overview_tool - Layer 0: 数据概览
6. get_analysis_signals_tool - Layer 1: 六维度信号
7. get_analysis_samples_tool - Layer 2: 验证样本
8. search_comments_by_keyword_tool - Layer 2.5: 关键词检索（DB内验证）
9. get_raw_comments_v2_tool - Layer 3: 原始评论

v0.8.7 设计:
- 两个独立系统：采样系统 + 分析系统
- 采样：三级统一接口 (quick/standard/deep)
- 分析：渐进式 Layer 0→1→2→2.5→3

Author: 1mht
Date: 2025-12-27
Updated: 2026-01-06 (v0.8.7)
"""

import sys
import os
import logging

# 添加路径（确保导入正常工作）
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 导入 FastMCP
try:
    from fastmcp import FastMCP
except ImportError:
    sys.stderr.write("错误: 未安装 fastmcp\n")
    sys.stderr.write("请运行: pip install fastmcp\n")
    sys.exit(1)

# ============================================================
# 导入核心工具模块
# ============================================================
from tools.search import search_songs, format_search_results, confirm_song_selection
from tools.data_collection import add_song_basic

# 分层分析工具
from tools.layered_analysis import (
    get_analysis_overview,  # Layer 0
    get_analysis_signals,  # Layer 1
    get_analysis_samples,  # Layer 2
    search_comments_by_keyword,  # Layer 2.5
    get_raw_comments_v2,  # Layer 3
)

# 创建 MCP 服务器实例
mcp = FastMCP("NetEase Music MCP Server (v0.8.7)")

logger.info("NetEase Music MCP Server v0.8.7 正在初始化...")


# ============================================================
# 工具 1: 搜索歌曲
# ============================================================


@mcp.tool()
def search_songs_tool(keyword: str, limit: int = 10) -> dict:
    """搜索网易云音乐歌曲。

    返回候选列表，需要用户选择后调用 confirm_song_selection_tool。

    Args:
        keyword: 搜索关键词，支持 "歌名" 或 "歌名 歌手"
        limit: 返回结果数量 (1-30)

    Returns:
        {
            "status": "pending_selection",
            "session_id": "search_xxx",
            "choices": ["1. 晴天 - 周杰伦", ...],
            "next_step": "请用户选择序号，然后调用 confirm_song_selection_tool"
        }
    """
    logger.info(f"搜索歌曲: {keyword}")
    results = search_songs(keyword, limit=limit)
    return format_search_results(results, keyword)


# ============================================================
# 工具 2: 确认选择
# ============================================================


@mcp.tool()
def confirm_song_selection_tool(session_id: str, choice_number: int) -> dict:
    """确认用户选择的歌曲，返回 song_id。

    Args:
        session_id: search_songs_tool 返回的 session_id
        choice_number: 用户选择的序号 (1-based)

    Returns:
        {
            "status": "confirmed",
            "song_id": "185811",
            "song_name": "晴天",
            "artists": ["周杰伦"]
        }
    """
    logger.info(f"确认选择: session={session_id}, choice={choice_number}")
    return confirm_song_selection(session_id, choice_number)


# ============================================================
# 工具 3: 入库
# ============================================================


@mcp.tool()
def add_song_to_database(song_id: str) -> dict:
    """将歌曲添加到数据库（元数据 + 热门评论 + 最新评论）。

    Args:
        song_id: 歌曲ID (从 confirm_song_selection_tool 获取)

    Returns:
        {
            "status": "success",
            "song_id": "185811",
            "song_name": "晴天",
            "data_collected": {"hot_comments": 50, "recent_comments": 20}
        }
    """
    logger.info(f"入库: song_id={song_id}")
    return add_song_basic(None, song_id=str(song_id))


# ============================================================
# 工具 4: 采样 (v0.8.7 三级统一接口)
# ============================================================


@mcp.tool()
def sample_comments_tool(song_id: str, level: str = "standard") -> dict:
    """【采样】三级采样工具

    固定结构：热评(15) + 最新(offset) + 年份(cursor)

    三个级别：
    - quick: 200条，快速预览
    - standard: 600条，日常分析（推荐）
    - deep: 1000条，深度研究

    智能适配：
    - 新歌(≤2年): 主要用offset
    - 中等(3-5年): 20% offset + 80% 年份
    - 正常(6-10年): 30% offset + 70% 年份
    - 老歌(>10年): 限制采10年

    Args:
        song_id: 歌曲ID
        level: "quick" / "standard" / "deep"

    Returns:
        {
            "status": "success",
            "level": "standard",
            "target": 600,
            "actual": 587,
            "samples": {"hot": 15, "recent": 172, "yearly": 400},
            "coverage": {"years_span": 8, "years_sampled": 8},
            "ai_guidance": {"next_action": "get_analysis_signals_tool"}
        }
    """
    logger.info(f"[采样] song_id={song_id}, level={level}")

    try:
        from mcp_server.tools.sampling_v6 import sample_comments_v6
        from mcp_server.tools.pagination_sampling import (
            get_real_comments_count_from_api,
        )

        # 获取 API 总数
        api_result = get_real_comments_count_from_api(song_id)
        api_total = api_result.get("total_comments", 0) if api_result else 0

        if api_total == 0:
            return {
                "status": "error",
                "message": "无法获取 API 评论总数",
                "song_id": song_id,
            }

        # 执行采样
        result = sample_comments_v6(
            song_id=song_id, api_total=api_total, level=level, save_to_db=True
        )

        return result

    except Exception as e:
        logger.error(f"采样失败: {e}", exc_info=True)
        return {"status": "error", "message": str(e), "song_id": song_id}


# ============================================================
# 工具 5: Layer 0 数据概览
# ============================================================


@mcp.tool()
def get_analysis_overview_tool(song_id: str) -> dict:
    """【Layer 0】数据概览 - 分析评论区的第一步

    ⚠️ 重要：这是分析流程的入口！
    如果返回 status="must_sample_first"，必须先采样再继续！

    正确流程：
    1. 调用本工具查看数据边界
    2. 如果返回 must_sample_first → 调用 sample_comments_tool
    3. 采样完成后再调用本工具
    4. 数据充足后 → 继续 Layer 1

    返回数据边界信息：
    - 数据库有多少条评论
    - API说有多少条评论
    - 覆盖率是多少
    - 时间跨度

    Args:
        song_id: 歌曲ID

    Returns:
        如果数据充足：{"status": "success", "layer": 0, ...}
        如果数据不足：{"status": "must_sample_first", "required_action": {...}}
    """
    logger.info(f"[Layer 0] song_id={song_id}")
    return get_analysis_overview(song_id)


# ============================================================
# 工具 6: Layer 1 六维度信号
# ============================================================


@mcp.tool()
def get_analysis_signals_tool(song_id: str) -> dict:
    """【Layer 1】六维度信号 - 量化分析

    ⚠️ 前置条件：数据库需有≥100条评论！
    如果返回 status="must_sample_first"，必须先采样！

    六个维度：
    - sentiment: 情感分布
    - content: 主题关键词
    - temporal: 时间趋势
    - structural: 长度分布
    - social: 点赞集中度
    - linguistic: 评论类型

    正确流程：
    1. 先调用 Layer 0 确认数据充足
    2. 如果数据不足，先调用 sample_comments_tool
    3. 数据充足后调用本工具
    4. 继续 Layer 2 验证样本

    Args:
        song_id: 歌曲ID

    Returns:
        如果数据充足：{"status": "success", "layer": 1, "dimensions": {...}}
        如果数据不足：{"status": "must_sample_first", "required_action": {...}}
    """
    logger.info(f"[Layer 1] song_id={song_id}")
    return get_analysis_signals(song_id)


# ============================================================
# 工具 7: Layer 2 验证样本
# ============================================================


@mcp.tool()
def get_analysis_samples_tool(song_id: str) -> dict:
    """【Layer 2】验证样本 - AI用来验证信号

    锚点样本（不依赖算法）：
    - most_liked: 最高赞
    - earliest: 最早
    - latest: 最新
    - longest: 最长

    对比样本（发现算法盲区）：
    - high_likes_low_score: 高赞但算法低分
    - low_likes_but_long: 低赞但长文

    AI应该：
    1. 阅读样本验证 Layer 1 信号
    2. 判断算法是否误判
    3. 决定是否需要 Layer 3
    4. ⚠️ 分析完后，如果返回 sampling_upgrade_prompt 不为 null，
       必须询问用户是否需要更深入的采样分析！

    Args:
        song_id: 歌曲ID

    Returns:
        {
            "layer": 2,
            "samples": {"anchors": [...], "contrast": [...]},
            "ai_verification_tasks": [...],
            "ai_guidance": {...},
            "sampling_upgrade_prompt": {...}  // 如果不是 deep 级别，会有此字段
        }
    """
    logger.info(f"[Layer 2] song_id={song_id}")
    return get_analysis_samples(song_id)


# ============================================================
# 工具 8: Layer 2.5 关键词检索
# ============================================================


@mcp.tool()
def search_comments_by_keyword_tool(
    song_id: str,
    keyword: str,
    limit: int = 20,
    min_likes: int = 0,
) -> dict:
    """【Layer 2.5】DB内关键词检索 - 用于验证 Layer 1 的关键词/主题信号

    设计目标：
    - 避免把 TF-IDF 的 weight 误读为“占比”
    - 直接在 DB 里确认某个关键词是否真实大量出现

    Args:
        song_id: 歌曲ID
        keyword: 关键词（子串匹配）
        limit: 返回条数
        min_likes: 最低点赞数

    Returns:
        {
            "status": "success",
            "keyword": "网抑云",
            "match_total": 123,
            "comments": [...]
        }
    """
    logger.info(
        f"[Layer 2.5] song_id={song_id}, keyword={keyword}, limit={limit}, min_likes={min_likes}"
    )
    return search_comments_by_keyword(
        song_id, keyword=keyword, limit=limit, min_likes=min_likes
    )


# ============================================================
# 工具 9: Layer 3 原始评论
# ============================================================


@mcp.tool()
def get_raw_comments_v2_tool(
    song_id: str, year: int = None, min_likes: int = 0, limit: int = 20
) -> dict:
    """【Layer 3】原始评论 - 深入验证时按需调用

    用于：
    - 验证 Layer 1/2 发现的异常
    - 获取特定年份/条件的评论
    - 深入分析具体内容

    Args:
        song_id: 歌曲ID
        year: 筛选年份
        min_likes: 最低点赞数
        limit: 返回条数 (默认20)

    Returns:
        {
            "layer": 3,
            "filter": {"year": 2020, "min_likes": 100},
            "comments": [{"content": "...", "likes": 500, ...}, ...]
        }
    """
    logger.info(f"[Layer 3] song_id={song_id}, year={year}, min_likes={min_likes}")
    return get_raw_comments_v2(song_id, year=year, min_likes=min_likes, limit=limit)


# ============================================================
# 启动服务器
# ============================================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("NetEase Music MCP Server v0.8.7")
    logger.info("工具: search → confirm → add → sample → Layer0→1→2→2.5→3")
    logger.info("=" * 60)
    mcp.run()
