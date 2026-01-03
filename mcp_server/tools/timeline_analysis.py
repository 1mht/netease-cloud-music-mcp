"""
时间线分析工具模块 - Feature 1: 评论情感时间线
分析评论情感随时间的变化趋势，发现"网抑云"现象等转折点

Author: 1mht + Claude
Version: v0.7.0
Date: 2025-12-30
"""

import sys
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
netease_path = os.path.join(project_root, 'netease_cloud_music')
if netease_path not in sys.path:
    sys.path.insert(0, netease_path)

from database import init_db, Song, Comment
from .workflow_errors import workflow_error
from .sentiment_analysis import get_analyzer, MAX_ANALYSIS_SIZE

# ===== 常量配置 =====
MIN_COMMENTS_PER_PERIOD = 5     # 每个时间段最少评论数
DEFAULT_SAMPLE_PER_PERIOD = 50  # 默认每时间段采样数
MAX_SAMPLE_PER_PERIOD = 200     # 每时间段最大采样数

# ===== v0.7.1: Workflow 强制校验阈值 =====
TIMELINE_MIN_COMMENTS = 100      # 时间线分析最低评论数
TIMELINE_MIN_YEARS = 2           # 时间线分析最低覆盖年数


def get_session():
    """获取数据库session"""
    db_path = os.path.join(project_root, 'data', 'music_data_v2.db')
    return init_db(f'sqlite:///{db_path}')


def _timestamp_to_period(timestamp: int, granularity: str) -> str:
    """将时间戳转换为时间段标签

    Args:
        timestamp: 毫秒级时间戳
        granularity: "year" / "quarter" / "month"

    Returns:
        时间段标签，如 "2020", "2020-Q3", "2020-07"
    """
    try:
        dt = datetime.fromtimestamp(timestamp / 1000)

        if granularity == "year":
            return str(dt.year)
        elif granularity == "quarter":
            quarter = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{quarter}"
        elif granularity == "month":
            return f"{dt.year}-{dt.month:02d}"
        else:
            return str(dt.year)
    except:
        return "unknown"


def _calculate_sentiment_stats(comments: List[Comment], analyzer) -> Dict[str, Any]:
    """计算一组评论的情感统计

    Args:
        comments: 评论列表
        analyzer: 情感分析器实例

    Returns:
        {
            "sample_size": 50,
            "avg_sentiment": 0.65,
            "sentiment_distribution": {"positive": 30, "neutral": 12, "negative": 8},
            "top_keywords": ["青春", "怀念", ...]
        }
    """
    if not comments:
        return None

    scores = []
    valid_contents = []

    for c in comments:
        if not c.content or len(c.content) < 3:
            continue
        try:
            score = analyzer.analyze(c.content)
            scores.append(score)
            valid_contents.append(c.content)
        except:
            continue

    if not scores:
        return None

    # 计算分布
    positive = sum(1 for s in scores if s >= 0.6)
    negative = sum(1 for s in scores if s <= 0.4)
    neutral = len(scores) - positive - negative

    avg_score = sum(scores) / len(scores)

    # 简单关键词提取（高频词）
    top_keywords = _extract_simple_keywords(valid_contents, top_n=5)

    return {
        "sample_size": len(scores),
        "avg_sentiment": round(avg_score, 3),
        "sentiment_distribution": {
            "positive": positive,
            "neutral": neutral,
            "negative": negative
        },
        "positive_rate": round(positive / len(scores), 3) if scores else 0,
        "negative_rate": round(negative / len(scores), 3) if scores else 0,
        "top_keywords": top_keywords
    }


def _extract_simple_keywords(texts: List[str], top_n: int = 5) -> List[str]:
    """简单关键词提取（基于jieba分词 + 词频）

    Args:
        texts: 文本列表
        top_n: 返回前N个关键词

    Returns:
        关键词列表
    """
    try:
        import jieba
    except ImportError:
        return []

    # 停用词
    stopwords = {
        '的', '了', '是', '我', '你', '他', '她', '它', '们', '这', '那', '有', '在', '和', '与',
        '就', '都', '也', '又', '被', '把', '给', '让', '向', '从', '到', '为', '对', '着',
        '很', '太', '好', '真', '啊', '吧', '呢', '哦', '嗯', '哈', '呀', '哇', '哎', '唉',
        '一个', '一种', '一下', '一些', '什么', '怎么', '这个', '那个', '没有', '不是',
        '可以', '因为', '所以', '如果', '但是', '虽然', '还是', '或者', '而且', '然后',
        '歌', '歌曲', '音乐', '评论', '听', '唱', '首'  # 音乐相关通用词
    }

    word_count = defaultdict(int)

    for text in texts:
        words = jieba.cut(text)
        for word in words:
            word = word.strip()
            if len(word) >= 2 and word not in stopwords:
                word_count[word] += 1

    # 排序并返回top_n
    sorted_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
    return [word for word, count in sorted_words[:top_n]]


def _detect_turning_points(timeline: List[Dict]) -> List[Dict]:
    """检测情感转折点

    Args:
        timeline: 时间线数据

    Returns:
        转折点列表
    """
    turning_points = []

    if len(timeline) < 2:
        return turning_points

    for i in range(1, len(timeline)):
        prev = timeline[i-1]
        curr = timeline[i]

        if prev.get("avg_sentiment") is None or curr.get("avg_sentiment") is None:
            continue

        change = curr["avg_sentiment"] - prev["avg_sentiment"]

        # 变化超过0.1视为转折点
        if abs(change) >= 0.1:
            direction = "下降" if change < 0 else "上升"

            # 尝试推断原因
            possible_reason = None
            if change < -0.15 and "2020" in curr["period"]:
                possible_reason = "可能与'网抑云'文化兴起相关"
            elif change > 0.15:
                possible_reason = "评论氛围好转"

            turning_points.append({
                "period": curr["period"],
                "change": round(change, 3),
                "direction": direction,
                "from_score": prev["avg_sentiment"],
                "to_score": curr["avg_sentiment"],
                "possible_reason": possible_reason
            })

    return turning_points


def _determine_trend(timeline: List[Dict]) -> str:
    """判断整体趋势

    Args:
        timeline: 时间线数据

    Returns:
        "rising" / "stable" / "declining"
    """
    if len(timeline) < 2:
        return "unknown"

    # 取首尾有效数据
    first_valid = None
    last_valid = None

    for t in timeline:
        if t.get("avg_sentiment") is not None:
            if first_valid is None:
                first_valid = t["avg_sentiment"]
            last_valid = t["avg_sentiment"]

    if first_valid is None or last_valid is None:
        return "unknown"

    diff = last_valid - first_valid

    if diff > 0.1:
        return "rising"
    elif diff < -0.1:
        return "declining"
    else:
        return "stable"


def analyze_sentiment_timeline(
    song_id: str,
    time_granularity: str = "year",
    sample_per_period: int = DEFAULT_SAMPLE_PER_PERIOD
) -> Dict[str, Any]:
    """分析评论情感随时间的变化趋势

    核心功能：发现情感转折点，如"网抑云"现象何时开始

    ✅ v0.7.1: 支持内部自动采样！

    📋 简化的调用方式:
    ┌─────────────────────────────────────────────────────────────┐
    │ 直接调用: analyze_sentiment_timeline_tool(song_id)          │
    │                                                             │
    │ 工具内部自动处理:                                           │
    │ - 检查数据库评论数量和时间覆盖                               │
    │ - 如果评论 < 100条 或 覆盖 < 2年 → 自动分层采样             │
    │ - 采样策略(v2.2): 热评15条 + 最新50条 + 历史11年(每年50条)  │
    │ - 返回结果中包含 sampling_info 字段说明采样详情             │
    └─────────────────────────────────────────────────────────────┘

    ✅ 正确用法: 直接调用此工具即可
    ℹ️ 可选步骤: 先调用 get_comments_metadata_tool 了解数据状态

    📊 采样策略 (v2.2 for timeline):
    - Layer 1: 热评15条 (API固定返回)
    - Layer 2: 最新50条 (offset翻页)
    - Layer 3: 历史分层 (cursor按年跳转，每年50条，共11年)
    - 总计: 约600条，覆盖歌曲发布以来的完整时间线

    Args:
        song_id: 歌曲ID（需先调用confirm_song_selection获取）
        time_granularity: 时间粒度
            - "year": 按年聚合（适合长周期歌曲，如《晴天》发布12年）
            - "quarter": 按季度（适合2-3年内的歌曲）
            - "month": 按月（适合1年内的新歌）
        sample_per_period: 每个时间段采样评论数
            - 默认50，建议30-100
            - 太少：结果不稳定
            - 太多：处理慢

    Returns:
        {
            "status": "success",
            "song_info": {"id": "185811", "name": "晴天", "artist": "周杰伦"},
            "time_range": {"start": "2013-07-15", "end": "2025-12-30", "span_years": 12.5},
            "granularity": "year",

            "timeline": [
                {
                    "period": "2013",
                    "sample_size": 50,
                    "avg_sentiment": 0.72,
                    "sentiment_distribution": {"positive": 35, "neutral": 10, "negative": 5},
                    "positive_rate": 0.70,
                    "negative_rate": 0.10,
                    "top_keywords": ["好听", "经典", "周杰伦"]
                },
                ...
            ],

            "insights": {
                "trend": "declining",
                "overall_change": -0.27,
                "turning_points": [
                    {"period": "2020", "change": -0.15, "possible_reason": "网抑云文化"}
                ],
                "summary": "情感从2013年的0.72下降到2025年的0.45"
            },

            "data_quality": {
                "total_comments_used": 500,
                "periods_with_data": 10,
                "avg_sample_per_period": 50,
                "confidence": "high"
            },

            "suggestion": "发现2020年情感明显下降，可能与'网抑云'现象相关",
            "next_step": "如需深入分析某时间段，可调用get_comments_by_pages指定时间范围"
        }

    示例对话:
        用户: "分析这首歌的情感变化"
        AI: [调用 analyze_sentiment_timeline(song_id="185811")]
            发现《晴天》的评论情感从2013年的0.72下降到2020年的0.45，
            转折点在2020年，与"网抑云"文化兴起时间吻合。
    """
    session = get_session()

    try:
        # ===== 1. 参数验证 =====
        if time_granularity not in ["year", "quarter", "month"]:
            return {
                "status": "error",
                "error_type": "invalid_parameter",
                "message": f"无效的时间粒度: {time_granularity}",
                "valid_options": ["year", "quarter", "month"],
                "suggestion": "year适合老歌，month适合新歌"
            }

        sample_per_period = min(max(sample_per_period, 10), MAX_SAMPLE_PER_PERIOD)

        # ===== 2. 获取歌曲信息 =====
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return workflow_error("song_not_found", "analyze_sentiment_timeline_tool")

        # ===== 3. 获取评论 =====
        comments = session.query(Comment).filter_by(song_id=song_id).all()

        if not comments:
            return workflow_error("no_comments", "analyze_sentiment_timeline_tool")

        # 过滤无效时间戳
        valid_comments = [c for c in comments if getattr(c, "timestamp", None) and c.timestamp > 0]

        # ===== v0.7.1: 自动分层采样 =====
        auto_sampled = False
        sampling_stats = None

        # 检查评论数量或时间覆盖是否不足
        need_sampling = False
        if len(valid_comments) < TIMELINE_MIN_COMMENTS:
            need_sampling = True
            print(f"[自动采样] 评论数不足({len(valid_comments)}<{TIMELINE_MIN_COMMENTS})，启动分层采样...")
        else:
            timestamps_check = [c.timestamp for c in valid_comments]
            min_ts_check, max_ts_check = min(timestamps_check), max(timestamps_check)
            span_years_check = (max_ts_check - min_ts_check) / (1000 * 60 * 60 * 24 * 365)
            if span_years_check < TIMELINE_MIN_YEARS:
                need_sampling = True
                print(f"[自动采样] 时间覆盖不足({span_years_check:.1f}<{TIMELINE_MIN_YEARS}年)，启动分层采样...")

        if need_sampling:
            try:
                from .pagination_sampling import full_stratified_sample
                sample_result = full_stratified_sample(song_id, analysis_type="timeline")

                if sample_result.get('all_comments'):
                    sampled_comments = sample_result['all_comments']
                    auto_sampled = True
                    sampling_stats = sample_result.get('stats', {})

                    # 转换为统一格式（模拟Comment对象）
                    class CommentLike:
                        def __init__(self, data):
                            self.content = data.get('content', '')
                            self.liked_count = data.get('liked_count', 0)
                            self.timestamp = data.get('timestamp', 0)

                    valid_comments = [CommentLike(c) for c in sampled_comments if c.get('timestamp', 0) > 0]
                    print(f"[自动采样] 完成! 获取{len(valid_comments)}条评论，覆盖{sampling_stats.get('years_covered', 0)}年")
                else:
                    return {
                        "status": "workflow_error",
                        "error_type": "sampling_failed",
                        "message": f"自动采样失败",
                        "song_id": song_id,
                        "song_name": song.name
                    }
            except Exception as e:
                print(f"[自动采样] 异常: {e}")
                return {
                    "status": "workflow_error",
                    "error_type": "sampling_error",
                    "message": f"自动采样异常: {str(e)}",
                    "song_id": song_id,
                    "song_name": song.name
                }

        if len(valid_comments) < 10:
            return {
                "status": "error",
                "error_type": "insufficient_data",
                "message": f"有效评论太少（{len(valid_comments)}条），无法进行时间线分析",
                "suggestion": "需要更多带时间戳的评论数据",
                "next_step": f"调用 crawl_all_comments_tool(song_id='{song_id}') 获取更多数据"
            }

        # 按时间分桶
        buckets = defaultdict(list)
        for c in valid_comments:
            period = _timestamp_to_period(c.timestamp, time_granularity)
            if period != "unknown":
                buckets[period].append(c)

        if not buckets:
            return {
                "status": "error",
                "error_type": "no_valid_periods",
                "message": "无法按时间分组，评论时间数据可能有问题"
            }

        # ===== 4. 计算时间范围 =====
        timestamps = [c.timestamp for c in valid_comments]
        min_ts = min(timestamps)
        max_ts = max(timestamps)

        start_date = datetime.fromtimestamp(min_ts / 1000).strftime("%Y-%m-%d")
        end_date = datetime.fromtimestamp(max_ts / 1000).strftime("%Y-%m-%d")
        span_years = round((max_ts - min_ts) / (1000 * 60 * 60 * 24 * 365), 1)

        # ===== 5. 初始化分析器 =====
        analyzer = get_analyzer("simple")

        # ===== 6. 分析每个时间段 =====
        timeline = []
        total_sampled = 0

        # 按时间排序
        sorted_periods = sorted(buckets.keys())

        for period in sorted_periods:
            period_comments = buckets[period]

            # 采样
            if len(period_comments) > sample_per_period:
                import random
                sampled = random.sample(period_comments, sample_per_period)
            else:
                sampled = period_comments

            total_sampled += len(sampled)

            # 计算统计
            stats = _calculate_sentiment_stats(sampled, analyzer)

            if stats:
                timeline.append({
                    "period": period,
                    "total_in_period": len(period_comments),
                    **stats
                })
            else:
                # 数据不足的时间段
                timeline.append({
                    "period": period,
                    "total_in_period": len(period_comments),
                    "sample_size": 0,
                    "avg_sentiment": None,
                    "note": "该时间段有效评论不足"
                })

        # ===== 7. 生成洞察 =====
        trend = _determine_trend(timeline)
        turning_points = _detect_turning_points(timeline)

        # 计算总体变化
        valid_timeline = [t for t in timeline if t.get("avg_sentiment") is not None]
        overall_change = 0
        summary = ""

        if len(valid_timeline) >= 2:
            first_score = valid_timeline[0]["avg_sentiment"]
            last_score = valid_timeline[-1]["avg_sentiment"]
            overall_change = round(last_score - first_score, 3)

            first_period = valid_timeline[0]["period"]
            last_period = valid_timeline[-1]["period"]
            summary = f"情感从{first_period}年的{first_score}{'下降' if overall_change < 0 else '上升'}到{last_period}年的{last_score}"

        # ===== 8. 数据质量评估 =====
        periods_with_data = len([t for t in timeline if t.get("sample_size", 0) > 0])
        avg_sample = total_sampled / periods_with_data if periods_with_data > 0 else 0

        if avg_sample >= 40 and periods_with_data >= 3:
            confidence = "high"
        elif avg_sample >= 20 and periods_with_data >= 2:
            confidence = "medium"
        else:
            confidence = "low"

        # ===== 9. 构建返回结果 =====
        result = {
            "status": "success",
            "song_info": {
                "id": song_id,
                "name": song.name,
                "artist": song.artists[0].name if song.artists else "Unknown"
            },
            "time_range": {
                "start": start_date,
                "end": end_date,
                "span_years": span_years
            },
            "granularity": time_granularity,
            "timeline": timeline,
            "insights": {
                "trend": trend,
                "trend_cn": {"rising": "上升", "stable": "平稳", "declining": "下降"}.get(trend, "未知"),
                "overall_change": overall_change,
                "turning_points": turning_points,
                "summary": summary
            },
            "data_quality": {
                "total_comments_in_db": len(comments),
                "total_comments_used": total_sampled,
                "periods_analyzed": len(timeline),
                "periods_with_data": periods_with_data,
                "avg_sample_per_period": round(avg_sample, 1),
                "confidence": confidence
            }
        }

        # 生成建议
        if turning_points:
            biggest_change = max(turning_points, key=lambda x: abs(x["change"]))
            result["suggestion"] = f"发现{biggest_change['period']}情感{biggest_change['direction']}明显（{biggest_change['change']:+.2f}）"
            if biggest_change.get("possible_reason"):
                result["suggestion"] += f"，{biggest_change['possible_reason']}"
        else:
            result["suggestion"] = f"情感整体{result['insights']['trend_cn']}，无明显转折点"

        result["next_step"] = "如需深入分析某个时间段，可调用get_comments_by_pages指定时间范围"

        # ===== v0.7.1: 添加采样信息（透明展示） =====
        if auto_sampled and sampling_stats:
            result["sampling_info"] = {
                "auto_sampled": True,
                "strategy": "stratified_v2.2",
                "hot_count": sampling_stats.get('hot_count', 0),
                "recent_count": sampling_stats.get('recent_count', 0),
                "historical_count": sampling_stats.get('historical_count', 0),
                "total_unique": sampling_stats.get('total_unique', 0),
                "years_covered": sampling_stats.get('years_covered', 0),
                "year_list": sampling_stats.get('year_list', []),
                "note": "数据通过自动分层采样获取（热评+最新+历史cursor跳转）"
            }

        return result

    except Exception as e:
        return {
            "status": "error",
            "error_type": "analysis_failed",
            "message": f"分析失败: {str(e)}",
            "song_id": song_id
        }

    finally:
        session.close()
