"""
社会学分析工具模块
专注于检测评论中的社会隐喻、集体情绪和话语策略
"""

import sys
import os
import logging
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

# ===== 统计学常量（v0.6.5）=====
MAX_ANALYSIS_SIZE = 5000           # v0.6.5: 内存安全上限
SAMPLE_SIZE_RANDOM = 3000          # 随机采样数量
SAMPLE_SIZE_FILTERED = 1000        # 过滤采样数量（top_liked, recent）

def get_session():
    """获取数据库session"""
    db_path = os.path.join(project_root, 'data', 'music_data_v2.db')
    return init_db(f'sqlite:///{db_path}')

def detect_social_metaphors(song_id: str, sampling_strategy: str = "auto") -> Dict[str, Any]:
    """
    [社会学进阶] 隐喻与话语检测器 - 检测评论中的社会隐喻和话语策略

    ✅ 可直接调用，工具会自动处理数据 (v0.7.1)

    📋 简化调用方式:
    ┌─────────────────────────────────────────────────────────────┐
    │ 直接调用: detect_social_metaphors_tool(song_id)             │
    │                                                             │
    │ 工具内部自动:                                               │
    │ - 检查歌曲和评论是否存在                                     │
    │ - 如果数据不足会返回workflow_error提示                       │
    │ - 大数据集自动采样，避免超时                                 │
    └─────────────────────────────────────────────────────────────┘

    📊 数据要求:
    - 最低: 100条评论
    - 推荐: 300条评论（隐喻检测更可靠）

    Args:
        song_id: 歌曲ID
        sampling_strategy: 采样策略，平衡覆盖率与性能
            - "auto": 智能判断 (默认)。如果 > 5000 条，自动切换为 random_sample。
            - "full": 强制全量 (慎用，可能超时)。
            - "random_sample": 随机抽取 3000 条 (适合大规模概览)。
            - "top_liked": 只看点赞最高的 1000 条 (适合看主流共识)。
            - "recent": 只看最新的 1000 条 (适合看即时舆论)。
    """
    # ===== 参数验证 =====
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
            return workflow_error("song_not_found", "detect_social_metaphors_tool")

        # 优化：先只查数量，决定是否需要全量加载
        total_count = session.query(Comment).filter_by(song_id=song_id).count()

        if total_count == 0:
            return workflow_error("no_comments", "detect_social_metaphors_tool")

        # 采样逻辑
        query = session.query(Comment).filter_by(song_id=song_id)
        
        strategy_used = sampling_strategy
        limit = total_count

        if sampling_strategy == "auto":
            if total_count > MAX_ANALYSIS_SIZE:
                strategy_used = "random_sample"
            else:
                strategy_used = "full"

        comments = []
        if strategy_used == "full":
            # v0.6.5: 即使是全量也要限制上限
            comments = query.limit(MAX_ANALYSIS_SIZE).all()
        elif strategy_used == "random_sample":
            # v0.6.5: 使用常量替代硬编码值
            candidates = query.limit(MAX_ANALYSIS_SIZE * 2).all()
            limit = SAMPLE_SIZE_RANDOM
            comments = random.sample(candidates, min(len(candidates), limit))
        elif strategy_used == "top_liked":
            limit = SAMPLE_SIZE_FILTERED
            comments = query.order_by(Comment.liked_count.desc()).limit(limit).all()
        elif strategy_used == "recent":
            limit = SAMPLE_SIZE_FILTERED
            comments = query.order_by(Comment.timestamp.desc()).limit(limit).all()
        else:
            # 默认全量（带上限）
            comments = query.limit(MAX_ANALYSIS_SIZE).all()

        total_analyzed = len(comments)
        
        # 定义隐喻模式 (基于社会学研究的关键词映射)
        patterns = {
            "Nationalism": {
                "keywords": ["中国", "第一", "国家", "自豪", "骄傲", "强大", "厉害", "祖国", "主权"],
                "theory": "安德森: '想象的共同体' 话语实践",
                "count": 0,
                "examples": []
            },
            "Resistance_Irony": {
                "keywords": ["工资", "缓发", "秩序", "讽刺", "阴阳", "反讽", "懂的都懂", "计划", "疑似", "泄露"],
                "theory": "斯科特: '弱者的武器' / 隐秘文本 (Hidden Transcript)",
                "count": 0,
                "examples": []
            },
            "Identity": {
                "keywords": ["我们", "这代人", "集体", "打卡", "见证", "历史", "爷青回", "破防", "DNA"],
                "theory": "塔菲尔: 社会认同理论 / 仪式性参与",
                "count": 0,
                "examples": []
            },
            "Hyperreality": {
                "keywords": ["POV", "梗", "团建", "乐子", "抽象", "活", "整活", "狂欢"],
                "theory": "鲍德里亚: '仿真与内爆' / 符号优先于内容",
                "count": 0,
                "examples": []
            }
        }
        
        for c in comments:
            content = c.content
            if not content: continue
            
            for p_name, p_data in patterns.items():
                found_keywords = [k for k in p_data["keywords"] if k in content]
                if found_keywords:
                    p_data["count"] += 1
                    if len(p_data["examples"]) < 3 and len(content) < 100:
                        p_data["examples"].append(content)

        # 整理结果
        findings = []
        for p_name, p_data in patterns.items():
            ratio = p_data["count"] / total_analyzed  # v0.6.6: 修复变量名错误
            findings.append({
                "metaphor_type": p_name,
                "occurrence_ratio": round(ratio, 4),
                "occurrence_percent": f"{ratio:.1%}",
                "sociological_theory": p_data["theory"],
                "evidence_keywords": p_data["keywords"][:5],
                "sample_quotes": p_data["examples"]
            })

        # 按频率排序
        findings.sort(key=lambda x: x['occurrence_ratio'], reverse=True)

        return {
            "status": "success",
            "song_id": song_id,
            "total_available": total_count,
            "total_analyzed": total_analyzed,
            "sampling_strategy": strategy_used,
            "metaphor_analysis": findings,
            "summary_for_ai": "请结合 occurrence_ratio 和 sociological_theory 进行深度解读。高比例的 Resistance_Irony 通常暗示评论区存在解构主义情绪。"
        }

    except Exception as e:
        logger.error(f"隐喻检测失败: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        session.close()
