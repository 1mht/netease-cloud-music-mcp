"""
主题建模工具模块 (NLP 进阶)
使用 LDA (Latent Dirichlet Allocation) 算法将评论聚类为潜在话题
"""

import sys
import os
import logging
from typing import List, Dict, Any
import re

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
netease_path = os.path.join(project_root, 'netease_cloud_music')
if netease_path not in sys.path:
    sys.path.insert(0, netease_path)

from database import init_db, Comment, Song  # v0.6.6: 添加Song模型
from .workflow_errors import workflow_error  # v0.6.6: 统一错误处理

logger = logging.getLogger(__name__)

# ===== 统计学常量（v0.6.4+v0.6.5）=====
MAX_ANALYSIS_SIZE = 5000           # v0.6.5: 内存安全上限
MIN_VIABLE_SIZE = 30               # 30条：最小可分析（LDA需要更多样本）
RECOMMENDED_SIZE = 100             # 100条：建议线

def get_session():
    """获取数据库session"""
    db_path = os.path.join(project_root, 'data', 'music_data_v2.db')
    return init_db(f'sqlite:///{db_path}')

def clean_text(text: str) -> str:
    """简单清洗文本：去除空白字符"""
    if not text:
        return ""
    # 替换掉非标准字符，避免编码问题
    return text.strip()

def perform_topic_modeling(song_id: str, n_topics: int = 3, n_top_words: int = 8) -> Dict[str, Any]:
    """
    对评论区进行 LDA 主题聚类分析

    📋 前置条件（v0.6.6）:
    ✓ 歌曲必须已存在于数据库（通过search→confirm→add_song流程添加）
    ✓ 数据库中必须有评论数据（通过get_comments_by_pages_tool获取）
    ✓ 推荐至少100条评论以获得可靠的主题聚类结果

    ⚠️ 如果前置条件不满足:
    本工具会返回workflow_error，指引你完成正确流程

    正确调用顺序示例:
    1. search_songs_tool → confirm_song_selection_tool → add_song_to_database
    2. get_comments_by_pages_tool (获取评论数据)
    3. 👉 cluster_comments_tool ← 当前工具

    这是一个无监督学习算法，能自动发现评论区隐含的几个讨论方向（Topic）。

    Args:
        song_id: 歌曲ID
        n_topics: 希望发现几个主题（默认3个）
        n_top_words: 每个主题展示前几个关键词

    Returns:
        {
            "song_id": "...",
            "topics": [
                {
                    "topic_id": 0,
                    "top_words": ["青春", "回忆", "学校", "遗憾"],
                    "weight": 0.45  # 该主题在所有评论中的占比
                },
                ...
            ]
        }
    """
    import jieba
    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.decomposition import LatentDirichletAllocation

    # ===== 参数验证 =====
    if not isinstance(n_topics, int) or n_topics < 2 or n_topics > 20:
        return {
            "status": "error",
            "message": f"n_topics 必须是 2-20 之间的整数，当前值: {n_topics}",
            "valid_range": "2-20",
            "suggestion": "建议使用 3-5 个主题以获得最佳效果"
        }

    if not isinstance(n_top_words, int) or n_top_words < 3 or n_top_words > 20:
        return {
            "status": "error",
            "message": f"n_top_words 必须是 3-20 之间的整数，当前值: {n_top_words}",
            "valid_range": "3-20"
        }

    session = get_session()
    try:
        # v0.6.6: 检查歌曲是否存在
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return workflow_error("song_not_found", "cluster_comments_tool")

        # 1. 获取评论数据
        comments = session.query(Comment.content).filter_by(song_id=song_id).all()

        # 数据量检查
        if not comments:
            return workflow_error("no_comments", "cluster_comments_tool")
            
        raw_documents = [c.content for c in comments if c.content and len(c.content) > 2]

        # v0.6.5: 大数据集采样，防止内存溢出和LDA超时
        original_count = len(raw_documents)
        if original_count > MAX_ANALYSIS_SIZE:
            import random
            raw_documents = random.sample(raw_documents, MAX_ANALYSIS_SIZE)
            logger.info(f"[cluster_comments] 数据集过大({original_count}条)，已自动采样到{MAX_ANALYSIS_SIZE}条")

        # v0.6.6: 样本量不足同样需要引导获取更多数据
        if len(raw_documents) < MIN_VIABLE_SIZE:
            return workflow_error("no_comments", "cluster_comments_tool")

        # 2. 文本预处理与分词
        processed_docs = []
        for doc in raw_documents:
            try:
                # 确保是字符串
                if not isinstance(doc, str):
                    continue
                    
                # 仅保留名词、动词、形容词，过滤掉无意义词汇
                words = jieba.cut(doc.strip())
                
                # 简单的停用词过滤
                stop_words = {'的', '了', '是', '在', '我', '也', '就', '不', '都', '这', '那', '有', '啊', '吧', '呢', '吗', 'user', 'reply'}
                filtered_words = [w for w in words if len(w) > 1 and w not in stop_words]
                
                if filtered_words:
                    processed_docs.append(" ".join(filtered_words))
            except Exception:
                continue

        if not processed_docs:
             return {"status": "error", "message": "预处理后没有剩余有效文本。"}

        # 3. 向量化 (CountVectorizer)
        # max_df=0.95: 忽略出现在95%以上文档中的词（太通用的词）
        # min_df=2: 忽略只出现过一次的词（太生僻的词）
        tf_vectorizer = CountVectorizer(max_df=0.95, min_df=2, max_features=1000)
        tf = tf_vectorizer.fit_transform(processed_docs)
        
        # 4. 训练 LDA 模型
        # n_jobs=1 避免 Windows 下 joblib 临时文件路径含中文导致的 UnicodeEncodeError
        # v0.6.5: max_iter 从 10 降至 5，加快收敛速度
        lda = LatentDirichletAllocation(
            n_components=n_topics,
            max_iter=5,
            learning_method='online',
            random_state=42,
            n_jobs=1
        )
        lda.fit(tf)

        # 5. 提取结果
        feature_names = tf_vectorizer.get_feature_names_out()
        topics = []
        
        # 简单的权重归一化（并不严谨，仅供参考）
        topic_dist = lda.transform(tf)
        topic_weights = topic_dist.sum(axis=0)
        topic_weights /= topic_weights.sum()

        for topic_idx, topic in enumerate(lda.components_):
            top_features_ind = topic.argsort()[:-n_top_words - 1:-1]
            top_words = [feature_names[i] for i in top_features_ind]
            
            topics.append({
                "topic_id": topic_idx + 1,
                "keywords": top_words,
                "importance": round(topic_weights[topic_idx], 2),
                "interpretation_guide": "请根据关键词推测该主题的含义（如：情感宣泄、歌词讨论、玩梗等）"
            })

        # 按重要性排序
        topics.sort(key=lambda x: x['importance'], reverse=True)

        result = {
            "status": "success",
            "song_id": song_id,
            "algorithm": "LDA (Latent Dirichlet Allocation)",
            "total_documents": len(processed_docs),
            "topics": topics,
            "note": "Keywords是该主题下的高频词，Importance是该主题在评论区的大致占比"
        }

        # v0.6.5: 添加采样信息
        if original_count > MAX_ANALYSIS_SIZE:
            result["sampling_info"] = {
                "sampled": True,
                "original_count": original_count,
                "sampled_count": MAX_ANALYSIS_SIZE,
                "reason": "数据集过大，自动采样以防止超时"
            }

        return result

    except Exception as e:
        # 使用 repr(e) 避免在错误处理时再次触发编码错误
        error_msg = repr(e)
        return {
            "status": "error",
            "message": f"主题分析失败: {error_msg}",
            "suggestion": "可能是数据量不足或scikit-learn环境问题"
        }
    finally:
        session.close()
