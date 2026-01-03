"""
内容分析工具模块 (NLP)
专注于评论文本的深度挖掘：关键词提取、话题聚类等
"""

import sys
import os
import logging
import re
import random
from typing import List, Dict, Any

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
netease_path = os.path.join(project_root, 'netease_cloud_music')
if netease_path not in sys.path:
    sys.path.insert(0, netease_path)

from database import init_db, Comment, Song  # v0.6.6: 添加Song模型
from .workflow_errors import workflow_error  # v0.6.6: 统一错误处理

logger = logging.getLogger(__name__)

# ===== 统计学常量（v0.6.4）=====
MAX_ANALYSIS_SIZE = 5000           # 内存安全：最大分析数量
DEGRADED_MODE_THRESHOLD = 5        # ≤5条：降级模式
MIN_VIABLE_SIZE = 30               # 30条：最小可分析
RECOMMENDED_SIZE = 100             # 100条：建议线

def get_session():
    """获取数据库session"""
    db_path = os.path.join(project_root, 'data', 'music_data_v2.db')
    return init_db(f'sqlite:///{db_path}')

def classify_comments(song_id: str, sampling_strategy: str = "auto") -> Dict[str, Any]:
    """
    [核心升级] 评论成分分类器 - 将评论分为故事/玩梗/乐评/短评

    ✅ 可直接调用，工具会自动处理数据。

    📋 简化调用方式 (v0.7.1):
    ┌─────────────────────────────────────────────────────────────┐
    │ 直接调用: classify_comments_tool(song_id)                   │
    │                                                             │
    │ 工具内部自动:                                               │
    │ - 检查数据库评论数量                                        │
    │ - 如果数据不足会返回workflow_error提示                       │
    └─────────────────────────────────────────────────────────────┘

    📊 数据要求:
    - 最低: 100条评论
    - 推荐: 200条评论（分类更准确）

    Args:
        song_id: 歌曲ID
        sampling_strategy: 采样策略 ("auto", "full", "random_sample")
    """
    session = get_session()
    try:
        # v0.6.6: 检查歌曲是否存在
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return workflow_error("song_not_found", "classify_comments_tool")

        # 获取总数
        total_count = session.query(Comment).filter_by(song_id=song_id).count()

        if total_count == 0:
            return workflow_error("no_comments", "classify_comments_tool")

        # ===== Phase 1: 内存安全检查（v0.6.5优化）=====
        # 只在用户强制全量时才警告，auto模式会自动采样
        if total_count > MAX_ANALYSIS_SIZE and sampling_strategy == "full":
            return {
                "status": "dataset_too_large",
                "message": f"⚠️ 数据集过大：{total_count}条评论",
                "current_size": total_count,
                "max_allowed": MAX_ANALYSIS_SIZE,
                "recommendation": {
                    "action": "使用采样分析",
                    "suggested_call": f"classify_comments(song_id='{song_id}', sampling_strategy='auto')",
                    "why": "auto模式会自动采样，避免内存溢出"
                }
            }

        # 采样逻辑（改进：上限5000）
        query = session.query(Comment).filter_by(song_id=song_id)

        strategy_used = sampling_strategy
        if sampling_strategy == "auto":
            strategy_used = "random_sample" if total_count > MAX_ANALYSIS_SIZE else "full"

        if strategy_used == "random_sample":
            # 改进：限制采样上限为MAX_ANALYSIS_SIZE
            candidates = query.limit(MAX_ANALYSIS_SIZE * 2).all()
            sample_size = min(len(candidates), MAX_ANALYSIS_SIZE)
            comments = random.sample(candidates, sample_size)
        else:
            comments = query.limit(MAX_ANALYSIS_SIZE).all()  # 安全上限

        # ===== Phase 3: 分层样本量检查 =====
        # v0.6.6: 样本过少同样需要引导获取更多数据
        if len(comments) <= DEGRADED_MODE_THRESHOLD:
            return workflow_error("no_comments", "classify_comments_tool")

        # [改进 2] 语言检测 (简单启发式)
        # 统计包含中文字符的评论比例
        def has_chinese(text):
            return any('\u4e00' <= char <= '\u9fff' for char in text)
            
        chinese_count = sum(1 for c in comments if c.content and has_chinese(c.content))
        chinese_ratio = chinese_count / len(comments)
        
        language_warning = None
        if chinese_ratio < 0.5:
            language_warning = f"⚠️ 检测到非中文评论占主导 ({100-chinese_ratio*100:.1f}%)。SnowNLP情感分析和社会学隐喻检测可能失效。"

        categories = {
            "Story": [],
            "Meme": [],
            "Review": [],
            "Short": []
        }
        
        # 音乐术语库
        music_terms = {'编曲', '作词', '作曲', '音色', '吉他', '贝斯', '鼓点', '混音', '前奏', '尾奏', '和声', '唱功', '嗓音'}
        # 故事特征词
        story_indicators = {'那时候', '记得', '后来', '曾经', '感觉', '想起', '因为', '虽然', '年', '岁'}
        
        for c in comments:
            content = c.content
            if not content:
                continue
                
            length = len(content)
            
            # 1. 判定 Short (过短)
            if length < 6:
                categories["Short"].append(c)
                continue
                
            # 2. 判定 Review (乐评)
            # 如果包含2个以上音乐术语
            term_count = sum(1 for term in music_terms if term in content)
            if term_count >= 1 or (term_count >=1 and length > 20):
                categories["Review"].append(c)
                continue
                
            # 3. 判定 Story (故事)
            # 长度够长，且包含第一人称或叙事词
            story_score = 0
            if length > 40: story_score += 2
            if length > 80: story_score += 2
            if '我' in content: story_score += 1
            if any(i in content for i in story_indicators): story_score += 1
            
            if story_score >= 3:
                categories["Story"].append(c)
                continue
                
            # 4. 判定 Meme (玩梗) - 剩下的较短但有特色的
            # 网易云的梗通常短小精悍，或者带有特殊符号
            if length < 30 and ('哈哈哈' in content or '?' in content or 'doge' in content):
                 categories["Meme"].append(c)
                 continue
            
            # 默认归类
            if length < 15:
                categories["Short"].append(c)
            else:
                # 剩下的归为 Meme/Other 混杂，这里暂时放 Short 或 Meme 视情况
                # 简单起见，中等长度非故事非乐评，暂归 Meme (广义的吐槽)
                categories["Meme"].append(c)

        # 整理返回结果 (只返回前5条精选，避免Token爆炸)
        def format_top(clist):
            # 按点赞排序
            sorted_list = sorted(clist, key=lambda x: x.liked_count or 0, reverse=True)[:5]
            return [{"content": x.content, "liked": x.liked_count} for x in sorted_list]

        return {
            "status": "success",
            "song_id": song_id,
            "total_analyzed": len(comments),
            "distribution": {
                "Story": len(categories["Story"]),
                "Meme": len(categories["Meme"]),
                "Review": len(categories["Review"]),
                "Short": len(categories["Short"])
            },
            "distribution_percent": {
                k: f"{len(v)/len(comments):.1%}" for k,v in categories.items()
            },
            "classification": {
                "counts": {
                    "Story": len(categories["Story"]),
                    "Meme": len(categories["Meme"]),
                    "Review": len(categories["Review"]),
                    "Short": len(categories["Short"])
                },
                "percentages": {
                    k: f"{len(v)/len(comments):.1%}" for k,v in categories.items()
                }
            },
            "highlights": {
                "Story": format_top(categories["Story"]),
                "Review": format_top(categories["Review"]),
                "Meme": format_top(categories["Meme"])
            },
            "language_warning": language_warning,
            "note": "Story=小作文/故事, Meme=玩梗/吐槽, Review=乐评/鉴赏"
        }

    except Exception as e:
        logger.error(f"分类失败: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()

def extract_keywords(song_id: str, top_k: int = 20, sampling_strategy: str = "auto") -> Dict[str, Any]:
    """
    提取评论区的核心关键词 (TF-IDF算法)

    ✅ 可直接调用，工具会自动处理数据 (v0.7.1)

    📋 简化调用方式:
    ┌─────────────────────────────────────────────────────────────┐
    │ 直接调用: extract_keywords_tool(song_id)                    │
    │                                                             │
    │ 工具内部自动:                                               │
    │ - 检查歌曲和评论是否存在                                     │
    │ - 如果数据不足会返回workflow_error提示                       │
    └─────────────────────────────────────────────────────────────┘

    📊 数据要求: 推荐至少100条评论以获得可靠结果

    Args:
        song_id: 歌曲ID
        top_k: 返回前K个关键词
        sampling_strategy: 采样策略 ("auto", "full", "random_sample")
    """
    import jieba.analyse

    # ===== 参数验证 =====
    # 验证 top_k
    if not isinstance(top_k, int) or top_k <= 0 or top_k > 100:
        return {
            "status": "error",
            "message": f"top_k 必须是 1-100 之间的整数，当前值: {top_k}",
            "valid_range": "1-100"
        }

    # 验证 sampling_strategy
    valid_strategies = ["auto", "full", "random_sample", "top_liked", "recent"]
    if sampling_strategy not in valid_strategies:
        return {
            "status": "error",
            "message": f"无效的采样策略: {sampling_strategy}",
            "valid_options": valid_strategies
        }

    session = get_session()
    try:
        # v0.6.6: 检查歌曲是否存在
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return workflow_error("song_not_found", "extract_keywords_tool")

        # 获取总数
        total_count = session.query(Comment).filter_by(song_id=song_id).count()
        if total_count == 0:
            return workflow_error("no_comments", "extract_keywords_tool")

        # 采样逻辑
        query = session.query(Comment).filter_by(song_id=song_id)
        
        strategy_used = sampling_strategy
        if sampling_strategy == "auto":
            strategy_used = "random_sample" if total_count > 5000 else "full"
            
        if strategy_used == "random_sample":
            candidates = query.limit(10000).all()
            comments = random.sample(candidates, min(len(candidates), 3000))
        else:
            comments = query.all()

        text = " ".join([c.content for c in comments if c.content])

        # 2. 提取关键词
        # allowPOS: 仅提取名词(n)、动词(v)、形容词(a)等，过滤掉无意义的虚词
        tags = jieba.analyse.extract_tags(text, topK=top_k, withWeight=True, allowPOS=('n', 'nr', 'ns', 'nt', 'nz', 'v', 'vd', 'vn', 'a', 'ad', 'an'))

        keywords = [{"word": tag, "weight": round(weight, 4)} for tag, weight in tags]

        return {
            "status": "success",
            "song_id": song_id,
            "total_comments_analyzed": len(comments),
            "algorithm": "TF-IDF",
            "keywords": keywords,
            "note": "权重(weight)越高，代表该词在评论区越重要且独特"
        }

    except Exception as e:
        logger.error(f"关键词提取失败: {e}")
        return {
            "status": "error",
            "message": f"关键词提取失败: {str(e)}"
        }
    finally:
        session.close()
