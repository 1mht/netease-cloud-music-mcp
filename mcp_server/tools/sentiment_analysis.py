"""
情感分析工具模块
支持评论情感分析、歌曲对比、网抑云排行等功能
使用策略模式支持模型热插拔（SnowNLP / 自定义模型）
"""

import sys
import os
from abc import ABC, abstractmethod

# 添加 netease_cloud_music 到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
netease_path = os.path.join(project_root, 'netease_cloud_music')
if netease_path not in sys.path:
    sys.path.insert(0, netease_path)

from database import init_db, Song, Comment
from typing import Optional, List, Dict, Any
from .workflow_errors import workflow_error  # v0.6.6: 统一错误处理

# ===== 统计学常量 =====
MAX_ANALYSIS_SIZE = 5000           # 内存安全：最大分析数量（防止爆栈）
DEGRADED_MODE_THRESHOLD = 5        # ≤5条：降级模式（展示，不分析）
MIN_VIABLE_SIZE = 30               # 30条：最小可分析（极低置信度）
RECOMMENDED_SIZE = 100             # 100条：建议线（正常置信度）

# ===== v0.7.1: Workflow 强制校验阈值 =====
WORKFLOW_MIN_REQUIRED = 100        # 硬性最低要求：低于此值自动采样（v2.2建议100条）


def check_sample_size(comments_count: int, song_id: str, comments_list: list = None) -> Optional[dict]:
    """检查样本量并返回相应策略（分层降级）

    Args:
        comments_count: 评论数量
        song_id: 歌曲ID
        comments_list: 评论列表（用于降级模式返回评论文本）

    Returns:
        如果需要降级/警告，返回对应字典；否则返回 None
    """
    # 情况1：≤5条 - 降级模式（不做统计分析，直接返回评论文本）
    if comments_count <= DEGRADED_MODE_THRESHOLD:
        preview = []
        if comments_list:
            preview = [
                {
                    "content": c.content,
                    "liked_count": c.liked_count,
                    "time": str(c.time) if hasattr(c, 'time') else None
                }
                for c in comments_list[:5]
            ]

        return {
            "status": "error",
            "error_type": "insufficient_sample",
            "mode": "simple_display",
            "count": comments_count,
            "message": f"⚠️ 评论量极少（{comments_count}条），无法进行统计分析",
            "comments_preview": preview,
            "explanation": {
                "why_no_analysis": "2-5条评论无统计意义，任何分析结论都不可靠",
                "what_you_can_do": [
                    "直接阅读以上评论内容",
                    "等待更多用户评论后再分析",
                    f"爬取更多数据：crawl_all_comments_for_song(song_id='{song_id}')",
                    "分析其他评论更多的歌曲"
                ]
            },
            "next_step": f"如需查看完整评论，调用 get_all_comments_tool(song_id='{song_id}')"
        }

    # 情况2-4：返回 None，但会在主函数中添加警告标记
    return None


def get_session():
    """获取数据库session"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                          'data', 'music_data_v2.db')
    return init_db(f'sqlite:///{db_path}')


# ===== 策略模式：支持多种分析引擎 =====

class SentimentAnalyzer(ABC):
    """情感分析器基类"""
    @abstractmethod
    def analyze(self, text: str) -> float:
        """返回情感分数 0-1（0=极负面，1=极正面）"""
        pass


class SnowNLPAnalyzer(SentimentAnalyzer):
    """SnowNLP 实现（简单快速）"""
    def __init__(self):
        try:
            from snownlp import SnowNLP
            self.SnowNLP = SnowNLP
        except ImportError:
            raise ImportError("请先安装 snownlp: pip install snownlp")

    def analyze(self, text: str) -> float:
        s = self.SnowNLP(text)
        return s.sentiments


class CustomModelAnalyzer(SentimentAnalyzer):
    """自定义模型接口（预留，用于课设扩展）

    示例：加载 BERT/RoBERTa 模型
    """
    def __init__(self, model_path: str):
        # TODO: 加载你的自定义模型
        # import torch
        # self.model = torch.load(model_path)
        # self.tokenizer = ...
        self.model_path = model_path
        print(f"[INFO] 自定义模型接口（预留）: {model_path}")

    def analyze(self, text: str) -> float:
        # TODO: 调用自定义模型进行推理
        # inputs = self.tokenizer(text, return_tensors='pt')
        # outputs = self.model(**inputs)
        # score = torch.softmax(outputs.logits, dim=1)[0][1].item()
        # return score

        # 暂时返回默认值
        print("[WARNING] 自定义模型功能尚未实现，使用 SnowNLP 替代")
        return SnowNLPAnalyzer().analyze(text)


def get_analyzer(model_type: str = "simple") -> SentimentAnalyzer:
    """工厂函数：根据类型返回分析器

    Args:
        model_type: "simple" (SnowNLP) | "advanced" (自定义模型)

    Returns:
        SentimentAnalyzer 实例
    """
    if model_type == "simple":
        return SnowNLPAnalyzer()
    elif model_type == "advanced":
        # 预留：加载自定义模型
        return CustomModelAnalyzer("models/sentiment_bert.pth")
    else:
        raise ValueError(f"未知模型类型: {model_type}")


# ===== 核心分析函数 =====

def analyze_sentiment(song_id: str, model_type: str = "simple") -> dict:
    """分析歌曲评论的情感分布

    ✅ v0.7.1: 支持内部自动采样！

    📋 简化的调用方式:
    ┌─────────────────────────────────────────────────────────────┐
    │ 直接调用: analyze_sentiment_tool(song_id)                   │
    │                                                             │
    │ 工具内部自动处理:                                           │
    │ - 检查数据库评论数量                                        │
    │ - 如果 < 100条 → 自动触发分层采样(stratified_v2.2)         │
    │ - 采样覆盖: 热评15条 + 最新100条 + 历史10年(每年30条)      │
    │ - 返回结果中包含 sampling_info 字段说明采样详情             │
    └─────────────────────────────────────────────────────────────┘

    ✅ 正确用法: 直接调用此工具即可
    ℹ️ 可选步骤: 先调用 get_comments_metadata_tool 了解数据状态

    📊 采样策略 (v2.2):
    - Layer 1: 热评15条 (API固定返回)
    - Layer 2: 最新100条 (offset翻页)
    - Layer 3: 历史分层 (cursor按年跳转，每年30条，共10年)
    - 总计: 约400条，覆盖歌曲发布以来的完整生命周期

    Args:
        song_id: 歌曲ID
        model_type: "simple" (SnowNLP) | "advanced" (自定义模型)

    Returns:
        {
            "song_id": "185811",
            "song_name": "晴天",
            "total_comments": 318,
            "sentiment_distribution": {
                "positive": 215,
                "neutral": 50,
                "negative": 53
            },
            "average_score": 0.65,
            "representative_comments": {...},
            "sampling_info": {  # v0.7.1新增
                "auto_sampled": true,
                "strategy": "stratified_v2.2",
                "hot_count": 15,
                "recent_count": 100,
                "historical_count": 203,
                "years_covered": 10
            }
        }
    """
    session = get_session()

    try:
        # 1. 获取歌曲和评论
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            # v0.6.6: 使用统一的workflow错误
            return workflow_error("song_not_found", "analyze_sentiment_tool")

        comments = session.query(Comment).filter_by(song_id=song_id).all()

        if not comments:
            # v0.6.6: 使用统一的workflow错误
            return workflow_error("no_comments", "analyze_sentiment_tool")

        count = len(comments)

        # ===== v0.7.1: 自动分层采样 =====
        # 如果评论数低于硬性最低要求，自动调用分层采样
        auto_sampled = False
        sampling_stats = None

        if count < WORKFLOW_MIN_REQUIRED:
            print(f"[自动采样] 数据库仅有{count}条，启动分层采样...")

            try:
                from .pagination_sampling import full_stratified_sample
                sample_result = full_stratified_sample(song_id, analysis_type="sentiment")

                if sample_result.get('all_comments'):
                    # 使用采样的评论替代数据库评论
                    sampled_comments = sample_result['all_comments']
                    count = len(sampled_comments)
                    auto_sampled = True
                    sampling_stats = sample_result.get('stats', {})

                    # 转换为统一格式（模拟Comment对象的属性）
                    comments = []
                    for c in sampled_comments:
                        class CommentLike:
                            def __init__(self, data):
                                self.content = data.get('content', '')
                                self.liked_count = data.get('liked_count', 0)
                                self.timestamp = data.get('timestamp', 0)
                        comments.append(CommentLike(c))

                    print(f"[自动采样] 完成! 获取{count}条评论，覆盖{sampling_stats.get('years_covered', 0)}年")
                else:
                    # 采样失败，返回错误
                    return {
                        "status": "workflow_error",
                        "error_type": "sampling_failed",
                        "message": f"自动采样失败，数据库仅有{count}条评论",
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

        # ===== Phase 1: 内存安全检查（防止爆栈） =====
        if count > MAX_ANALYSIS_SIZE:
            return {
                "status": "error",
                "error_type": "dataset_too_large",
                "message": f"⚠️ 数据集过大：{count}条评论",
                "current_size": count,
                "max_allowed": MAX_ANALYSIS_SIZE,
                "recommendation": {
                    "action": "使用采样分析而非全量加载",
                    "suggested_call": f"get_comments_by_pages_tool(song_id='{song_id}', pages=[1,10,20,30,40])",
                    "expected_sample_size": "约100-200条",
                    "why_sampling": "采样分析可获得接近全量的统计结果，同时避免内存溢出"
                }
            }

        # ===== Phase 3: 分层样本量检查（降级模式） =====
        degraded_check = check_sample_size(count, song_id, comments)
        if degraded_check:
            return degraded_check  # 降级模式直接返回

        print(f"[START] 分析《{song.name}》的评论情感...")

        # 2. 初始化分析器
        analyzer = get_analyzer(model_type)

        # 3. 分析每条评论
        scores = []
        for comment in comments:
            if len(comment.content) < 5:  # 过滤过短评论
                continue
            try:
                score = analyzer.analyze(comment.content)
                scores.append({
                    "content": comment.content,
                    "score": score,
                    "liked_count": comment.liked_count
                })
            except Exception as e:
                # 跳过分析失败的评论
                continue

        if not scores:
            return {"status": "error", "message": "没有有效的评论可供分析"}

        # 4. 统计
        positive = sum(1 for s in scores if s['score'] >= 0.6)
        negative = sum(1 for s in scores if s['score'] <= 0.4)
        neutral = len(scores) - positive - negative
        avg_score = sum(s['score'] for s in scores) / len(scores)

        # 5. 找出代表性评论
        scores_sorted = sorted(scores, key=lambda x: x['score'])
        most_negative = scores_sorted[0]
        most_positive = scores_sorted[-1]

        print(f"[OK] 分析完成: 正面={positive}, 中性={neutral}, 负面={negative}")

        # 构建基础结果
        result = {
            "song_id": song_id,
            "song_name": song.name,
            "total_comments": len(scores),
            "sentiment_distribution": {
                "positive": positive,
                "neutral": neutral,
                "negative": negative
            },
            "average_score": round(avg_score, 3),
            "representative_comments": {
                "most_positive": {
                    "content": most_positive['content'][:80],
                    "score": round(most_positive['score'], 3),
                    "liked_count": most_positive['liked_count']
                },
                "most_negative": {
                    "content": most_negative['content'][:80],
                    "score": round(most_negative['score'], 3),
                    "liked_count": most_negative['liked_count']
                }
            }
        }

        # ===== Phase 3: 添加置信度标记 =====
        if count < MIN_VIABLE_SIZE:
            # 6-29条：极低置信度
            result["status"] = "success"
            result["confidence"] = "extremely_low"
            result["warning"] = {
                "type": "very_small_sample",
                "message": f"⚠️ 样本量很小（{count}条），分析结果仅供参考",
                "reliability": "极低 - 结论可能随新评论大幅变化",
                "suggestion": "建议：1) 仅作初步了解，2) 爬取更多数据后重新分析"
            }
        elif count < RECOMMENDED_SIZE:
            # 30-99条：低置信度
            result["status"] = "success"
            result["confidence"] = "low"
            result["warning"] = {
                "type": "small_sample",
                "message": f"ℹ️ 样本量偏小（{count}条），建议谨慎解读",
                "reliability": "中等 - 基本趋势可信，细节可能有偏差",
                "suggestion": "达到100条评论后分析会更可靠"
            }
        else:
            # 100+条：正常
            result["status"] = "success"
            result["confidence"] = "normal"
            result["sample_info"] = {
                "count": count,
                "reliability": "正常 - 样本量足够，结论可靠"
            }

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

    finally:
        session.close()


def compare_songs(song_id_1: str, song_id_2: str) -> dict:
    """对比两首歌的情感差异

    Args:
        song_id_1: 第一首歌ID
        song_id_2: 第二首歌ID

    Returns:
        {
            "song_1": {...},
            "song_2": {...},
            "difference": {
                "sentiment_gap": 0.30,
                "conclusion": "《晴天》比《海底》更治愈"
            }
        }
    """
    print(f"[START] 对比两首歌的情感...")

    result1 = analyze_sentiment(song_id_1)
    result2 = analyze_sentiment(song_id_2)

    if result1.get('status') == 'error' or result2.get('status') == 'error':
        return {
            "status": "error",
            "message": "其中一首歌曲分析失败",
            "song_1_error": result1.get('message') if result1.get('status') == 'error' else None,
            "song_2_error": result2.get('message') if result2.get('status') == 'error' else None
        }

    gap = result1['average_score'] - result2['average_score']

    # 判断情感倾向
    def get_emotion(score):
        if score >= 0.6:
            return "positive"
        elif score <= 0.4:
            return "negative"
        else:
            return "neutral"

    # 生成结论
    if abs(gap) < 0.05:
        conclusion = f"《{result1['song_name']}》与《{result2['song_name']}》情感倾向相似"
    elif gap > 0:
        conclusion = f"《{result1['song_name']}》比《{result2['song_name']}》更{'治愈' if result1['average_score'] >= 0.6 else '正面'}"
    else:
        conclusion = f"《{result2['song_name']}》比《{result1['song_name']}》更{'治愈' if result2['average_score'] >= 0.6 else '正面'}"

    print(f"[OK] 对比完成: {conclusion}")

    return {
        "song_1": {
            "id": result1['song_id'],
            "name": result1['song_name'],
            "avg_sentiment": result1['average_score'],
            "dominant_emotion": get_emotion(result1['average_score']),
            "comment_count": result1['total_comments']
        },
        "song_2": {
            "id": result2['song_id'],
            "name": result2['song_name'],
            "avg_sentiment": result2['average_score'],
            "dominant_emotion": get_emotion(result2['average_score']),
            "comment_count": result2['total_comments']
        },
        "difference": {
            "sentiment_gap": round(abs(gap), 3),
            "conclusion": conclusion
        }
    }


def find_wangyiyun_songs(limit: int = 10) -> list:
    """找出数据库中最"网抑云"的歌曲

    Args:
        limit: 返回前N首（默认10首）

    Returns:
        [
            {
                "rank": 1,
                "song_id": "123456",
                "song_name": "海底",
                "artist": "一颗小葱",
                "avg_sentiment": 0.28,
                "negative_ratio": 0.75,
                "wangyiyun_score": 0.85,
                "sample_comment": "..."
            },
            ...
        ]
    """
    session = get_session()

    try:
        print(f"[START] 查找最网抑云的歌曲...")

        songs = session.query(Song).all()
        results = []

        for song in songs:
            comments = session.query(Comment).filter_by(song_id=song.id).all()
            if not comments:
                continue

            # 分析情感
            analyzer = get_analyzer("simple")
            scores = []
            valid_comments = []

            for comment in comments:
                if len(comment.content) >= 5:
                    try:
                        score = analyzer.analyze(comment.content)
                        scores.append(score)
                        valid_comments.append(comment)
                    except:
                        continue

            if not scores:
                continue

            # 计算指标
            avg_score = sum(scores) / len(scores)
            negative_ratio = sum(1 for s in scores if s <= 0.4) / len(scores)

            # "网抑云指数" = (1 - 平均情感) * 负面占比
            # 这个公式确保：情感越负面 + 负面评论占比越高 = 越网抑云
            wangyiyun_score = (1 - avg_score) * negative_ratio

            # 找一条最负面的评论作为示例
            negative_comments = [(c, s) for c, s in zip(valid_comments, scores) if s <= 0.4]
            if negative_comments:
                sample_comment = min(negative_comments, key=lambda x: x[1])[0].content[:60]
            else:
                sample_comment = valid_comments[0].content[:60] if valid_comments else ""

            results.append({
                "song_id": song.id,
                "song_name": song.name,
                "artist": song.artists[0].name if song.artists else "Unknown",
                "avg_sentiment": round(avg_score, 3),
                "negative_ratio": round(negative_ratio, 3),
                "wangyiyun_score": round(wangyiyun_score, 3),
                "sample_comment": sample_comment,
                "comment_count": len(valid_comments)
            })

        # 排序
        results.sort(key=lambda x: x['wangyiyun_score'], reverse=True)

        # 添加排名
        for i, r in enumerate(results[:limit], 1):
            r['rank'] = i

        print(f"[OK] 找到 {len(results[:limit])} 首网抑云歌曲")

        return results[:limit]

    finally:
        session.close()
