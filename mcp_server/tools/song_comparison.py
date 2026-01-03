"""
歌曲PK对比工具模块 - Feature 3: 歌曲对比分析
对比两首歌曲的评论特征，发现差异和相似之处

Author: 1mht + Claude
Version: v0.7.0
Date: 2025-12-31
"""

import sys
import os
from typing import Dict, Any, List, Set
from collections import Counter

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
DEFAULT_SAMPLE_SIZE = 200  # 每首歌默认采样数
MIN_SAMPLE_SIZE = 30       # 最小采样数

# ===== v0.7.1: Workflow 强制校验阈值 =====
COMPARISON_MIN_REQUIRED = 50  # 对比分析每首歌最低评论数


def get_session():
    """获取数据库session"""
    db_path = os.path.join(project_root, 'data', 'music_data_v2.db')
    return init_db(f'sqlite:///{db_path}')


def _extract_keywords_from_comments(comments: List[Comment], top_n: int = 15) -> List[str]:
    """从评论中提取关键词

    Args:
        comments: 评论列表
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
        '歌', '歌曲', '音乐', '评论', '听', '唱', '首', '这首', '那首'
    }

    word_count = Counter()

    for c in comments:
        if not c.content:
            continue
        words = jieba.cut(c.content)
        for word in words:
            word = word.strip()
            if len(word) >= 2 and word not in stopwords:
                word_count[word] += 1

    return [word for word, _ in word_count.most_common(top_n)]


def _calculate_similarity(keywords_a: List[str], keywords_b: List[str]) -> float:
    """计算两个关键词列表的相似度（Jaccard系数）

    Args:
        keywords_a: 第一个关键词列表
        keywords_b: 第二个关键词列表

    Returns:
        相似度 0-1
    """
    if not keywords_a or not keywords_b:
        return 0.0

    set_a = set(keywords_a)
    set_b = set(keywords_b)

    intersection = len(set_a & set_b)
    union = len(set_a | set_b)

    return round(intersection / union, 3) if union > 0 else 0.0


def _analyze_song_comments(song: Song, comments: List[Comment], analyzer, sample_size: int) -> Dict[str, Any]:
    """分析单首歌的评论数据

    Args:
        song: 歌曲对象
        comments: 评论列表
        analyzer: 情感分析器
        sample_size: 采样大小

    Returns:
        分析结果字典
    """
    import random

    # 采样
    if len(comments) > sample_size:
        sampled = random.sample(comments, sample_size)
    else:
        sampled = comments

    # 情感分析
    scores = []
    valid_comments = []

    for c in sampled:
        if not c.content or len(c.content) < 3:
            continue
        try:
            score = analyzer.analyze(c.content)
            scores.append(score)
            valid_comments.append(c)
        except:
            continue

    if not scores:
        return None

    # 统计
    positive = sum(1 for s in scores if s >= 0.6)
    negative = sum(1 for s in scores if s <= 0.4)
    neutral = len(scores) - positive - negative
    avg_score = sum(scores) / len(scores)

    # 关键词
    keywords = _extract_keywords_from_comments(valid_comments, top_n=15)

    # 互动数据
    total_likes = sum(c.liked_count or 0 for c in valid_comments)
    avg_likes = total_likes / len(valid_comments) if valid_comments else 0
    hot_comments = sum(1 for c in valid_comments if (c.liked_count or 0) >= 1000)

    return {
        "song_info": {
            "id": song.id,
            "name": song.name,
            "artist": song.artists[0].name if song.artists else "Unknown"
        },
        "sample_size": len(scores),
        "total_in_db": len(comments),
        "sentiment": {
            "avg_score": round(avg_score, 3),
            "positive_count": positive,
            "neutral_count": neutral,
            "negative_count": negative,
            "positive_rate": round(positive / len(scores), 3),
            "negative_rate": round(negative / len(scores), 3)
        },
        "keywords": keywords,
        "engagement": {
            "total_likes": total_likes,
            "avg_likes": round(avg_likes, 1),
            "hot_comments": hot_comments  # 点赞>=1000的评论数
        }
    }


def compare_songs_advanced(
    song_id_a: str,
    song_id_b: str,
    sample_size: int = DEFAULT_SAMPLE_SIZE
) -> Dict[str, Any]:
    """对比两首歌曲的评论特征（增强版）

    核心功能：多维度对比两首歌的评论，发现差异和相似之处

    ✅ v0.7.1: 支持内部自动采样！

    ⚠️ 重要：对比前必须让用户确认两首歌的选择！
    ┌─────────────────────────────────────────────────────────────┐
    │ 正确流程（严禁AI自作主张选歌）:                              │
    │                                                             │
    │ 1. search_songs_tool("歌曲A名字")                           │
    │    → 展示结果，让用户选择                                    │
    │ 2. confirm_song_selection_tool(用户选择的index)             │
    │                                                             │
    │ 3. search_songs_tool("歌曲B名字")                           │
    │    → 展示结果，让用户选择                                    │
    │ 4. confirm_song_selection_tool(用户选择的index)             │
    │                                                             │
    │ 5. compare_songs_tool(song_id_a, song_id_b)                 │
    │    → 工具内部自动采样，返回对比结果                          │
    └─────────────────────────────────────────────────────────────┘

    ❌ 错误用法：AI搜索后直接选第一个，不让用户确认
    ✅ 正确用法：每首歌都必须让用户确认选择

    📊 数据要求: 每首歌至少50条评论（不足时自动采样）

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
                    "a_score": 0.68,
                    "b_score": 0.75,
                    "winner": "b",
                    "gap": 0.07,
                    "insight": "《七里香》更正面，《晴天》略带忧郁"
                },
                "keywords": {
                    "a_unique": ["emo", "深夜", "失恋"],
                    "b_unique": ["甜蜜", "夏天", "初恋"],
                    "common": ["青春", "怀念", "高中"],
                    "insight": "共同主题是'青春怀旧'，但《晴天》更忧郁"
                },
                "engagement": {
                    "a_total_likes": 125000,
                    "b_total_likes": 98000,
                    "winner": "a",
                    "insight": "《晴天》互动量更高"
                }
            },

            "overall": {
                "similarity": 0.72,
                "verdict": "两首歌相似度较高，都以'青春回忆'为主题",
                "key_difference": "《晴天》更多'忧郁'情绪，《七里香》更多'甜蜜'情绪"
            },

            "data_quality": {
                "a_sample": 200,
                "b_sample": 180,
                "confidence": "high"
            },

            "suggestion": "如需深入对比，可分别调用analyze_sentiment_timeline查看情感变化",
            "next_step": "可继续对比其他歌曲，或深入分析某首歌的特定维度"
        }

    使用示例:
        用户: "对比《晴天》和《七里香》"
        AI: [先confirm两首歌，然后调用 compare_songs_advanced]
            对比结果：
            📊 情感：《七里香》(0.75)略胜《晴天》(0.68)
            🔤 关键词：共同主题'青春怀旧'，《晴天》更忧郁，《七里香》更甜蜜
            💬 互动：《晴天》点赞量更高

    ⚠️ 注意:
        - 两首歌都需要在数据库中
        - 样本量太少时结果可能不稳定
    """
    session = get_session()

    try:
        # ===== 1. 参数验证 =====
        sample_size = min(max(sample_size, MIN_SAMPLE_SIZE), MAX_ANALYSIS_SIZE)

        # ===== 2. 获取歌曲A =====
        song_a = session.query(Song).filter_by(id=song_id_a).first()
        if not song_a:
            return workflow_error("song_not_found", "compare_songs_tool",
                                  extra_info=f"歌曲A (ID: {song_id_a}) 不存在")

        comments_a = session.query(Comment).filter_by(song_id=song_id_a).all()

        if not comments_a:
            return workflow_error("no_comments", "compare_songs_tool",
                                  extra_info=f"歌曲《{song_a.name}》没有评论数据")

        # ===== v0.7.1: 检查歌曲A评论数量，不足则自动采样 =====
        sampling_info_a = None
        if len(comments_a) < COMPARISON_MIN_REQUIRED:
            print(f"[自动采样] 歌曲A《{song_a.name}》数据不足({len(comments_a)}条)，启动分层采样...")
            try:
                from .pagination_sampling import full_stratified_sample
                sample_result = full_stratified_sample(song_id_a, analysis_type="comparison")

                if sample_result.get('all_comments'):
                    # 转换采样数据为Comment-like对象
                    sampled_comments = sample_result['all_comments']
                    comments_a = []
                    for c in sampled_comments:
                        class CommentLike:
                            def __init__(self, data):
                                self.content = data.get('content', '')
                                self.liked_count = data.get('liked_count', 0)
                                self.timestamp = data.get('timestamp', 0)
                        comments_a.append(CommentLike(c))
                    sampling_info_a = sample_result.get('stats', {})
                    print(f"[自动采样] 歌曲A完成! 获取{len(comments_a)}条评论")
            except Exception as e:
                print(f"[自动采样] 歌曲A异常: {e}")
                # 采样失败，继续使用原有数据（可能不足）

        # ===== 3. 获取歌曲B =====
        song_b = session.query(Song).filter_by(id=song_id_b).first()
        if not song_b:
            return workflow_error("song_not_found", "compare_songs_tool",
                                  extra_info=f"歌曲B (ID: {song_id_b}) 不存在")

        comments_b = session.query(Comment).filter_by(song_id=song_id_b).all()

        if not comments_b:
            return workflow_error("no_comments", "compare_songs_tool",
                                  extra_info=f"歌曲《{song_b.name}》没有评论数据")

        # ===== v0.7.1: 检查歌曲B评论数量，不足则自动采样 =====
        sampling_info_b = None
        if len(comments_b) < COMPARISON_MIN_REQUIRED:
            print(f"[自动采样] 歌曲B《{song_b.name}》数据不足({len(comments_b)}条)，启动分层采样...")
            try:
                from .pagination_sampling import full_stratified_sample
                sample_result = full_stratified_sample(song_id_b, analysis_type="comparison")

                if sample_result.get('all_comments'):
                    # 转换采样数据为Comment-like对象
                    sampled_comments = sample_result['all_comments']
                    comments_b = []
                    for c in sampled_comments:
                        class CommentLike:
                            def __init__(self, data):
                                self.content = data.get('content', '')
                                self.liked_count = data.get('liked_count', 0)
                                self.timestamp = data.get('timestamp', 0)
                        comments_b.append(CommentLike(c))
                    sampling_info_b = sample_result.get('stats', {})
                    print(f"[自动采样] 歌曲B完成! 获取{len(comments_b)}条评论")
            except Exception as e:
                print(f"[自动采样] 歌曲B异常: {e}")
                # 采样失败，继续使用原有数据（可能不足）

        # ===== 4. 初始化分析器 =====
        analyzer = get_analyzer("simple")

        # ===== 5. 分析两首歌 =====
        result_a = _analyze_song_comments(song_a, comments_a, analyzer, sample_size)
        result_b = _analyze_song_comments(song_b, comments_b, analyzer, sample_size)

        if not result_a or not result_b:
            return {
                "status": "error",
                "error_type": "analysis_failed",
                "message": "评论分析失败，可能是有效评论太少"
            }

        # ===== 6. 对比分析 =====

        # 情感对比
        score_a = result_a["sentiment"]["avg_score"]
        score_b = result_b["sentiment"]["avg_score"]
        sentiment_gap = round(abs(score_a - score_b), 3)
        sentiment_winner = "a" if score_a > score_b else ("b" if score_b > score_a else "tie")

        # 生成情感洞察
        if sentiment_gap < 0.05:
            sentiment_insight = f"两首歌情感倾向相似（差距仅{sentiment_gap}）"
        else:
            higher = result_a["song_info"]["name"] if score_a > score_b else result_b["song_info"]["name"]
            lower = result_b["song_info"]["name"] if score_a > score_b else result_a["song_info"]["name"]
            sentiment_insight = f"《{higher}》更正面，《{lower}》略带忧郁"

        # 关键词对比
        keywords_a = set(result_a["keywords"])
        keywords_b = set(result_b["keywords"])
        common_keywords = list(keywords_a & keywords_b)
        unique_a = list(keywords_a - keywords_b)[:5]
        unique_b = list(keywords_b - keywords_a)[:5]

        similarity = _calculate_similarity(result_a["keywords"], result_b["keywords"])

        # 生成关键词洞察
        if common_keywords:
            keywords_insight = f"共同主题：{', '.join(common_keywords[:3])}"
            if unique_a and unique_b:
                keywords_insight += f"；《{result_a['song_info']['name']}》独有：{', '.join(unique_a[:2])}，《{result_b['song_info']['name']}》独有：{', '.join(unique_b[:2])}"
        else:
            keywords_insight = "两首歌话题差异较大"

        # 互动对比
        likes_a = result_a["engagement"]["total_likes"]
        likes_b = result_b["engagement"]["total_likes"]
        engagement_winner = "a" if likes_a > likes_b else ("b" if likes_b > likes_a else "tie")

        higher_engagement = result_a["song_info"]["name"] if likes_a > likes_b else result_b["song_info"]["name"]
        engagement_insight = f"《{higher_engagement}》互动量更高" if likes_a != likes_b else "两首歌互动量相近"

        # ===== 7. 整体结论 =====
        if similarity >= 0.5:
            verdict = f"两首歌相似度较高（{similarity}），评论话题有较多重叠"
        elif similarity >= 0.2:
            verdict = f"两首歌有一定相似性（{similarity}），但各有特色"
        else:
            verdict = f"两首歌差异较大（相似度{similarity}），评论风格明显不同"

        # 关键差异
        if sentiment_gap >= 0.1:
            key_diff = sentiment_insight
        elif unique_a and unique_b:
            key_diff = f"《{result_a['song_info']['name']}》关键词偏向'{unique_a[0] if unique_a else '—'}'，《{result_b['song_info']['name']}》偏向'{unique_b[0] if unique_b else '—'}'"
        else:
            key_diff = "两首歌在各方面都比较相似"

        # ===== 8. 数据质量评估 =====
        min_sample = min(result_a["sample_size"], result_b["sample_size"])
        if min_sample >= 100:
            confidence = "high"
        elif min_sample >= 50:
            confidence = "medium"
        else:
            confidence = "low"

        # ===== 9. 构建返回结果 =====
        return {
            "status": "success",
            "songs": {
                "a": result_a["song_info"],
                "b": result_b["song_info"]
            },
            "comparison": {
                "sentiment": {
                    "a_score": score_a,
                    "b_score": score_b,
                    "a_positive_rate": result_a["sentiment"]["positive_rate"],
                    "b_positive_rate": result_b["sentiment"]["positive_rate"],
                    "winner": sentiment_winner,
                    "gap": sentiment_gap,
                    "insight": sentiment_insight
                },
                "keywords": {
                    "a_keywords": result_a["keywords"][:10],
                    "b_keywords": result_b["keywords"][:10],
                    "a_unique": unique_a,
                    "b_unique": unique_b,
                    "common": common_keywords[:5],
                    "insight": keywords_insight
                },
                "engagement": {
                    "a_total_likes": likes_a,
                    "b_total_likes": likes_b,
                    "a_hot_comments": result_a["engagement"]["hot_comments"],
                    "b_hot_comments": result_b["engagement"]["hot_comments"],
                    "winner": engagement_winner,
                    "insight": engagement_insight
                }
            },
            "overall": {
                "similarity": similarity,
                "verdict": verdict,
                "key_difference": key_diff
            },
            "data_quality": {
                "a_sample": result_a["sample_size"],
                "b_sample": result_b["sample_size"],
                "a_total_in_db": result_a["total_in_db"],
                "b_total_in_db": result_b["total_in_db"],
                "confidence": confidence
            },
            # v0.7.1: 采样信息
            "sampling_info": {
                "a_auto_sampled": sampling_info_a is not None,
                "b_auto_sampled": sampling_info_b is not None,
                "a_sampling_stats": sampling_info_a,
                "b_sampling_stats": sampling_info_b
            } if (sampling_info_a or sampling_info_b) else None,
            "suggestion": "如需深入对比，可分别调用analyze_sentiment_timeline查看情感变化趋势",
            "next_step": "可继续对比其他歌曲，或深入分析某首歌的特定维度"
        }

    except Exception as e:
        return {
            "status": "error",
            "error_type": "comparison_failed",
            "message": f"对比分析失败: {str(e)}"
        }

    finally:
        session.close()
