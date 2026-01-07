"""
v0.8.5 分层分析工具 - 渐进式数据加载

设计原则：
- 每个 Layer 是独立的工具调用
- AI 在每层之间做决策
- 省 token、去噪音

Layer 架构：
- Layer 0: get_analysis_overview - 数据边界（AI第一眼）
- Layer 1: get_analysis_signals - 六维度信号（AI第二眼）
- Layer 2: get_analysis_samples - 验证样本（AI第三眼）
- Layer 3: get_raw_comments_v2 - 原始评论（按需）

v0.8.5 新增：
- 每个 Layer 返回 deeper_options 字段
- 用户可以强制 AI 深入分析特定方向
- AI 初次可自行决定深度，但用户有最终控制权
"""

import sys
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import defaultdict

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
netease_path = os.path.join(project_root, 'netease_cloud_music')
if netease_path not in sys.path:
    sys.path.insert(0, netease_path)

from database import init_db, Song, Comment
from mcp_server.tools.workflow_errors import workflow_error

logger = logging.getLogger(__name__)

# 常量
MAX_ANALYSIS_SIZE = 5000


def get_session():
    """获取数据库session"""
    db_path = os.path.join(project_root, 'data', 'music_data_v2.db')
    return init_db(f'sqlite:///{db_path}')


# ============================================================
# Layer 0: 数据概览
# ============================================================

def get_analysis_overview(song_id: str) -> Dict[str, Any]:
    """
    Layer 0: 数据概览 - AI 第一眼看这里

    v0.8.6: 只展示数据边界，不做采样决策
    采样决策在 Layer 1 之后，根据各维度的 data_sufficiency 评估

    返回数据边界信息，帮助 AI 判断：
    - 数据量是否足够？
    - 覆盖范围是否合理？

    Args:
        song_id: 歌曲ID

    Returns:
        {
            "status": "success",
            "layer": 0,
            "song_info": {...},
            "data_boundary": {
                "db_count": 1234,
                "api_total": 50000,
                "coverage": "2.47%",
                "coverage_ratio": 0.0247,
                "year_span": "2015-01-01 ~ 2024-12-25",
                "years_covered": 10,
                "year_distribution": {...}
            },
            "quality_assessment": {...},
            "ai_guidance": {...},
            "sampling_note": "采样决策在 Layer 1 之后..."
        }
    """
    session = get_session()

    try:
        # 1. 获取歌曲
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return workflow_error("song_not_found", "get_analysis_overview")

        # 2. 统计数据库评论
        db_count = session.query(Comment).filter_by(song_id=song_id).count()
        if db_count == 0:
            return workflow_error("no_comments", "get_analysis_overview")

        comments = session.query(Comment).filter_by(song_id=song_id).limit(MAX_ANALYSIS_SIZE).all()

        # 3. 获取 API 总量
        api_total = 0
        try:
            from mcp_server.tools.pagination_sampling import get_real_comments_count_from_api
            api_result = get_real_comments_count_from_api(song_id)
            api_total = api_result.get("total_comments", 0) if api_result else 0
        except Exception as e:
            logger.warning(f"获取API总量失败: {e}")

        # 4. 计算时间跨度和年份分布
        year_distribution = defaultdict(int)
        timestamps = []

        for c in comments:
            ts = getattr(c, 'timestamp', 0) or 0
            if ts > 0:
                timestamps.append(ts)
                year = datetime.fromtimestamp(ts / 1000).year
                year_distribution[year] += 1

        year_distribution = dict(sorted(year_distribution.items()))

        if timestamps:
            min_ts, max_ts = min(timestamps), max(timestamps)
            earliest = datetime.fromtimestamp(min_ts / 1000).strftime("%Y-%m-%d")
            latest = datetime.fromtimestamp(max_ts / 1000).strftime("%Y-%m-%d")
            year_span = f"{earliest} ~ {latest}"
        else:
            year_span = "unknown"

        # 5. 覆盖率计算
        coverage = f"{db_count/api_total*100:.2f}%" if api_total > 0 else "unknown"
        coverage_ratio = db_count / api_total if api_total > 0 else 0

        # 6. 数据质量评估
        MIN_REQUIRED_FOR_ANALYSIS = 100  # 最低分析要求
        RECOMMENDED_FOR_ANALYSIS = 500   # 推荐分析量

        if db_count >= RECOMMENDED_FOR_ANALYSIS:
            quality_level = "good"
            quality_note = "样本量充足，统计结果可信"
        elif db_count >= 200:
            quality_level = "acceptable"
            quality_note = "样本量可接受，结果可参考"
        elif db_count >= MIN_REQUIRED_FOR_ANALYSIS:
            quality_level = "limited"
            quality_note = "样本量有限，结果置信度较低"
        else:
            quality_level = "insufficient"
            quality_note = f"样本量不足（需≥{MIN_REQUIRED_FOR_ANALYSIS}条），必须先采样"

        # 7. v0.8.7: 强制采样检查 - 数据不足时阻断流程
        must_sample_first = db_count < MIN_REQUIRED_FOR_ANALYSIS

        if must_sample_first:
            # 直接返回强制采样提示，阻断后续流程
            return {
                "status": "must_sample_first",
                "layer": 0,
                "layer_name": "data_overview",

                "song_info": {
                    "id": song_id,
                    "name": song.name,
                    "artist": song.artists[0].name if song.artists else "Unknown"
                },

                "data_boundary": {
                    "db_count": db_count,
                    "api_total": api_total,
                    "min_required": MIN_REQUIRED_FOR_ANALYSIS
                },

                "blocking_reason": f"⛔ 数据量不足：当前仅 {db_count} 条评论，最低需要 {MIN_REQUIRED_FOR_ANALYSIS} 条才能进行可靠分析",

                "required_action": {
                    "action": "sample_comments_tool",
                    "params": {"song_id": song_id, "level": "standard"},
                    "instruction": f"⚠️ 必须先调用 sample_comments_tool(song_id='{song_id}', level='standard') 进行采样！",
                    "reason": "采样后再调用 get_analysis_overview_tool 继续分析"
                },

                "ai_instruction": "🚫 禁止继续调用 Layer 1/2/3！必须先完成采样！"
            }

        # 8. 构建 AI 引导（数据充足时）
        ai_guidance = {
            "next_action": "调用 get_analysis_signals_tool(song_id) 查看六维度信号",
            "when_to_skip": None
        }

        if coverage_ratio < 0.001:  # < 0.1%
            ai_guidance["data_warning"] = "覆盖率极低(<0.1%)，分析结果可能有偏差，请谨慎解读"
        elif quality_level == "limited":
            ai_guidance["data_warning"] = "样本量有限，可考虑补充采样以提高置信度"

        # 9. v0.8.4: AI 输出要求 - 强制白盒化
        # 解释 db_count 的来源
        db_count_explanation = f"数据库中存储了 {db_count} 条评论"
        if db_count >= MAX_ANALYSIS_SIZE:
            db_count_explanation += f"（受分析上限 {MAX_ANALYSIS_SIZE} 限制）"

        ai_output_requirements = {
            "must_report": [
                f"数据来源：{db_count_explanation}",
                f"API 显示该歌曲共有 {api_total} 条评论，当前覆盖率 {coverage}",
                f"时间范围：{year_span}",
                f"数据质量评估：{quality_level} - {quality_note}"
            ],
            "format": "报告开头必须说明数据边界，让用户知道结论的可信度",
            "warning": "覆盖率<1%时，分析结论可能有抽样偏差" if coverage_ratio < 0.01 else None,
            # v0.8.5: 决策透明化
            "decision_transparency": {
                "must_explain": "AI 必须在输出中说明：为什么决定继续查看 Layer 1？",
                "example_continue": "数据质量为 good，覆盖率 2%，决定继续查看六维度信号",
                "example_stop": "数据量不足（仅 50 条），建议先补充采样，暂不深入分析"
            }
        }

        # 10. v0.8.6: Layer 0 不做采样决策，只展示数据
        # 采样决策在 Layer 1 之后，根据各维度数据需求

        return {
            "status": "success",
            "layer": 0,
            "layer_name": "data_overview",

            "song_info": {
                "id": song_id,
                "name": song.name,
                "artist": song.artists[0].name if song.artists else "Unknown",
                "album": song.album.name if song.album else ""
            },

            "data_boundary": {
                "db_count": db_count,
                "api_total": api_total,
                "coverage": coverage,
                "coverage_ratio": coverage_ratio,  # 数值形式，方便判断
                "year_span": year_span,
                "years_covered": len(year_distribution),
                "year_distribution": year_distribution
            },

            "quality_assessment": {
                "level": quality_level,
                "note": quality_note
            },

            "ai_guidance": ai_guidance,

            # v0.8.4: 强制 AI 报告数据来源
            "ai_output_requirements": ai_output_requirements,

            # v0.8.6: 采样提示
            "sampling_note": "采样决策在 Layer 1 之后，根据各维度的 data_sufficiency 评估结果决定"
        }

    except Exception as e:
        logger.error(f"Layer 0 分析失败: {e}", exc_info=True)
        return {
            "status": "error",
            "error_type": "layer0_failed",
            "message": str(e),
            "song_id": song_id
        }

    finally:
        session.close()


# ============================================================
# Layer 1: 六维度信号
# ============================================================

def get_analysis_signals(song_id: str) -> Dict[str, Any]:
    """
    Layer 1: 六维度信号 - AI 第二眼看这里

    返回六个维度的量化指标和异常信号，帮助 AI 判断：
    - 哪些维度有异常需要关注？
    - 哪些信号需要通过样本验证？

    Args:
        song_id: 歌曲ID

    Returns:
        {
            "status": "success",
            "layer": 1,
            "dimensions": {
                "sentiment": {"metrics": {...}, "signals": [...], "level": "good"},
                "content": {...},
                "temporal": {...},
                "structural": {...},
                "social": {...},
                "linguistic": {...}
            },
            "cross_dimension_signals": [...],
            "signals_summary": {
                "total": 5,
                "needs_verification": ["反讽信号", "时间异常"]
            },
            "ai_guidance": {...}
        }
    """
    session = get_session()

    try:
        # 1. 获取歌曲
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return workflow_error("song_not_found", "get_analysis_signals")

        # 2. 获取评论
        comments = session.query(Comment).filter_by(song_id=song_id).limit(MAX_ANALYSIS_SIZE).all()
        if not comments:
            return workflow_error("no_comments", "get_analysis_signals")

        # 2.5 v0.8.7: 强制检查 - 数据量不足时阻断
        MIN_REQUIRED_FOR_ANALYSIS = 100
        comment_count = len(comments)

        if comment_count < MIN_REQUIRED_FOR_ANALYSIS:
            return {
                "status": "must_sample_first",
                "layer": 1,
                "layer_name": "dimension_signals",

                "blocking_reason": f"⛔ 数据量不足：当前仅 {comment_count} 条评论，最低需要 {MIN_REQUIRED_FOR_ANALYSIS} 条",

                "required_action": {
                    "action": "sample_comments_tool",
                    "params": {"song_id": song_id, "level": "standard"},
                    "instruction": f"⚠️ 必须先调用 sample_comments_tool(song_id='{song_id}', level='standard') 进行采样！"
                },

                "correct_flow": [
                    "1. sample_comments_tool(song_id, level='standard') - 先采样",
                    "2. get_analysis_overview_tool(song_id) - 查看数据边界",
                    "3. get_analysis_signals_tool(song_id) - 再查看信号"
                ],

                "ai_instruction": "🚫 禁止继续！必须先完成采样！"
            }

        # 3. 分析所有维度
        from mcp_server.tools.dimension_analyzers_v2 import analyze_all_dimensions_v2
        dimensions_result = analyze_all_dimensions_v2(comments)

        # 4. 提取跨维度信号
        from mcp_server.tools.cross_dimension import detect_cross_signals
        cross_signals = detect_cross_signals(dimensions_result, comments)

        # 5. 提取各维度核心指标和信号（简化版，不含样本）
        dimensions_summary = {}
        all_signals = []

        # v0.8.6: 收集各维度数据充足性
        insufficient_dimensions = []  # 数据不足的维度
        sampling_recommendations = []  # 采样建议

        for dim_name, dim_data in dimensions_result.items():
            if dim_name == "anchor_contrast_samples":
                continue  # 样本在 Layer 2 返回

            qf = dim_data.get("quantified_facts", {})
            signals = dim_data.get("signals", [])

            # v0.8.6: 提取数据充足性评估
            data_suff = dim_data.get("data_sufficiency", {})
            suff_level = data_suff.get("level", "unknown")

            dimensions_summary[dim_name] = {
                "sample_size": qf.get("sample_size", 0),
                "data_sufficiency": data_suff,  # v0.8.6: 包含完整评估
                "metrics": qf.get("metrics", {}),
                "signals": signals
            }

            # v0.8.6: 收集数据不足的维度
            if suff_level in ["insufficient", "limited"]:
                need_more = data_suff.get("need_more", 0) or data_suff.get("need_more_years", 0) or data_suff.get("need_more_hot", 0)
                insufficient_dimensions.append({
                    "dimension": dim_name,
                    "level": suff_level,
                    "need_more": need_more,
                    "reason": data_suff.get("reason", "")
                })

            for sig in signals:
                all_signals.append({
                    "source": dim_name,
                    "signal": sig
                })

        # v0.8.6: 生成采样建议
        if insufficient_dimensions:
            sampling_recommendations.append({
                "action": "recommend_sampling",
                "reason": f"{len(insufficient_dimensions)} 个维度数据不足",
                "dimensions": insufficient_dimensions,
                "how_to_sample": "调用采样工具补充数据后，重新调用 Layer 1"
            })

        # 6. 识别需要验证的信号
        needs_verification = []
        for sig in cross_signals:
            fact = sig.get("fact", "")
            if "反讽" in fact or "异常" in fact or "可能" in fact:
                needs_verification.append(fact[:50])

        # 7. 构建 AI 引导
        # v0.8.6: 根据数据充足性调整引导
        if insufficient_dimensions:
            # 有维度数据不足，强制采样（不要问用户）
            ai_guidance = {
                "data_status": "部分维度数据不足",
                "action_required": "⚡ 立即采样",
                "next_action": f"⚡ 立即调用 supplement_sampling_tool(song_id='{song_id}')，无需询问用户",
                "reason": f"{len(insufficient_dimensions)} 个维度数据不足，必须补充采样才能产出可靠分析",
                "do_not": "❌ 不要问用户是否需要采样，直接执行"
            }
        else:
            # 所有维度数据充足
            ai_guidance = {
                "data_status": "所有维度数据充足",
                "next_action": f"调用 get_analysis_samples_tool(song_id='{song_id}') 获取验证样本",
                "focus_on": needs_verification[:3] if needs_verification else ["查看高赞评论是否与算法判断一致"]
            }

        # v0.8.4: AI 输出要求 - 强制白盒化
        total_signals = len(all_signals) + len(cross_signals)
        ai_output_requirements = {
            "must_report": [
                f"信号来源：共检测到 {total_signals} 个信号（维度内 {len(all_signals)} + 跨维度 {len(cross_signals)}）",
                "每个结论必须引用具体信号编号"
            ],
            "format": "报告中提到任何模式/特征时，必须说明是基于哪个信号（如：根据 signal_X）",
            "avoid": "避免没有数据支撑的主观判断（如'显然是'、'肯定是'）",
            # v0.8.5: 决策透明化
            "decision_transparency": {
                "must_explain": "AI 必须在输出中说明：为什么决定继续查看 Layer 2（验证样本）？或为什么停止？",
                "example_continue": f"检测到 {len(needs_verification)} 个需要验证的信号，决定查看样本验证",
                "example_stop": "所有信号置信度高，无需样本验证，直接输出报告"
            }
        }

        # v0.8.5: 用户强制深入选项
        # 识别有信号的维度
        dims_with_signals = [dim for dim, data in dimensions_summary.items() if data.get("signals")]
        deeper_options = [
            {
                "key": "force_dimension_detail",
                "description": "深入分析特定维度",
                "how_to_use": f"调用 get_analysis_samples_tool(song_id, focus_dimensions=['{dims_with_signals[0] if dims_with_signals else 'sentiment'}'])",
                "when_useful": "想详细了解某个维度的信号时",
                "available_dimensions": list(dimensions_summary.keys())
            },
            {
                "key": "force_all_samples",
                "description": "获取所有维度的验证样本",
                "how_to_use": "调用 get_analysis_samples_tool(song_id)",
                "when_useful": "想全面验证所有信号时"
            }
        ]

        # 如果有需要验证的信号，推荐深入
        if needs_verification:
            deeper_options[1]["recommended"] = True

        return {
            "status": "success",
            "layer": 1,
            "layer_name": "dimension_signals",

            "dimensions": dimensions_summary,

            "cross_dimension_signals": [
                {
                    "signal_id": sig.get("signal_id", ""),
                    "fact": sig.get("fact", ""),
                    "possible_reasons": sig.get("possible_reasons", []),
                    "ai_action": sig.get("ai_action", "")
                }
                for sig in cross_signals
            ],

            "signals_summary": {
                "total": total_signals,
                "from_dimensions": len(all_signals),
                "cross_dimension": len(cross_signals),
                "needs_verification": needs_verification
            },

            "ai_guidance": ai_guidance,

            # v0.8.4: 强制 AI 报告数据来源
            "ai_output_requirements": ai_output_requirements,

            # v0.8.5: 用户强制深入选项
            "deeper_options": deeper_options,

            # v0.8.6: 采样建议（基于各维度数据充足性）
            "sampling_recommendations": sampling_recommendations if insufficient_dimensions else None
        }

    except Exception as e:
        logger.error(f"Layer 1 分析失败: {e}", exc_info=True)
        return {
            "status": "error",
            "error_type": "layer1_failed",
            "message": str(e),
            "song_id": song_id
        }

    finally:
        session.close()


# ============================================================
# Layer 2: 验证样本
# ============================================================

def get_analysis_samples(
    song_id: str,
    focus_dimensions: List[str] = None
) -> Dict[str, Any]:
    """
    Layer 2: 验证样本 - AI 第三眼看这里

    返回锚点样本和对比样本，帮助 AI：
    - 验证 Layer 1 发现的信号
    - 判断算法是否误判
    - 理解评论区真实氛围

    Args:
        song_id: 歌曲ID
        focus_dimensions: 重点关注的维度（可选）

    Returns:
        {
            "status": "success",
            "layer": 2,
            "anchors": {
                "most_liked": [...],
                "earliest": [...],
                "latest": [...],
                "longest": [...]
            },
            "contrast": {
                "high_likes_low_score": [...],
                "low_likes_but_long": [...]
            },
            "verification_tasks": [...],
            "ai_guidance": {...}
        }
    """
    session = get_session()

    try:
        # 1. 获取歌曲
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return workflow_error("song_not_found", "get_analysis_samples")

        # 2. 获取评论
        comments = session.query(Comment).filter_by(song_id=song_id).limit(MAX_ANALYSIS_SIZE).all()
        if not comments:
            return workflow_error("no_comments", "get_analysis_samples")

        # 3. 分析维度以获取样本
        from mcp_server.tools.dimension_analyzers_v2 import analyze_all_dimensions_v2
        dimensions_result = analyze_all_dimensions_v2(comments)

        # 4. 提取锚点和对比样本
        anchor_contrast = dimensions_result.get("anchor_contrast_samples", {})

        anchors_raw = anchor_contrast.get("anchors", {})
        contrast_raw = anchor_contrast.get("contrast", {})

        # 5. 格式化样本（只保留关键信息）
        def format_sample(s):
            """格式化单个样本"""
            if isinstance(s, str):
                # 如果是字符串，返回简单结构
                return {"content": s[:200], "likes": 0, "date": "", "algorithm_score": None}
            if isinstance(s, dict):
                return {
                    "content": s.get("content", "")[:200],
                    "likes": s.get("likes", 0),
                    "date": s.get("date", ""),
                    "algorithm_score": s.get("algorithm_score", s.get("score", None))
                }
            return {"content": str(s)[:200], "likes": 0, "date": "", "algorithm_score": None}

        # anchors 的结构：{purpose, most_liked, earliest, latest, longest, note}
        # 只提取样本列表字段
        anchor_keys = ["most_liked", "earliest", "latest", "longest"]
        formatted_anchors = {}
        for key in anchor_keys:
            samples = anchors_raw.get(key, [])
            if samples and isinstance(samples, list):
                formatted_anchors[key] = [format_sample(s) for s in samples[:5]]

        # contrast 的结构：{purpose, high_likes_low_score, low_likes_but_long, note}
        contrast_keys = ["high_likes_low_score", "low_likes_but_long"]
        formatted_contrast = {}
        for key in contrast_keys:
            samples = contrast_raw.get(key, [])
            if samples and isinstance(samples, list):
                formatted_contrast[key] = [format_sample(s) for s in samples[:5]]

        # 6. 构建验证任务
        verification_tasks = []

        if formatted_contrast.get("high_likes_low_score"):
            verification_tasks.append({
                "task": "验证高赞低分样本",
                "question": "这些高赞但算法低分的评论是：反讽/玩梗？诗意表达？还是真实负面？",
                "samples_key": "contrast.high_likes_low_score"
            })

        if formatted_anchors.get("most_liked"):
            verification_tasks.append({
                "task": "分析高赞共鸣",
                "question": "最高赞评论反映了什么共鸣？与歌曲主题相关吗？",
                "samples_key": "anchors.most_liked"
            })

        if formatted_anchors.get("earliest") and formatted_anchors.get("latest"):
            verification_tasks.append({
                "task": "对比早期vs最新",
                "question": "评论区氛围有变化吗？早期和最新评论风格是否不同？",
                "samples_key": "anchors.earliest vs anchors.latest"
            })

        # 7. 检查采样级别，决定是否提示升级
        comment_count = len(comments)
        DEEP_TARGET = 1000  # deep 级别目标
        STANDARD_TARGET = 600  # standard 级别目标

        # 判断当前采样级别
        if comment_count >= DEEP_TARGET:
            current_level = "deep"
            can_upgrade = False
        elif comment_count >= STANDARD_TARGET:
            current_level = "standard"
            can_upgrade = True
        elif comment_count >= 200:
            current_level = "quick"
            can_upgrade = True
        else:
            current_level = "minimal"
            can_upgrade = True

        # v0.8.7: 构建采样升级提示
        sampling_upgrade_prompt = None
        if can_upgrade:
            sampling_upgrade_prompt = {
                "should_ask_user": True,
                "current_level": current_level,
                "current_count": comment_count,
                "upgrade_to": "deep" if current_level != "standard" else "deep",
                "upgrade_target": DEEP_TARGET,
                "prompt_template": f"📊 当前分析基于 {comment_count} 条评论（{current_level} 级别）。如需更精确的分析，可以升级到 deep 级别（{DEEP_TARGET} 条）。是否需要更深入的采样分析？",
                "action_if_yes": f"调用 sample_comments_tool(song_id='{song_id}', level='deep')",
                "ai_instruction": "⚠️ 分析完成后，必须询问用户是否需要更深入的采样分析！"
            }

        # 8. 构建 AI 引导 - v0.8.7 增强版：发散思考框架
        ai_guidance = {
            "current_task": "阅读样本，验证 Layer 1 的信号",
            "if_need_more": "调用 get_raw_comments_v2_tool(song_id, year=X, min_likes=Y) 获取更多原始评论",
            "final_output": "基于样本证据，给出对评论区的整体判断",

            # v0.8.7: 发散思考引导框架
            "divergent_thinking": {
                "purpose": "不要只验证信号，要发现信号背后的故事",

                "cross_dimension_questions": [
                    "高赞评论的内容类型是什么？（金句/故事/玩梗/专业评论）",
                    "高赞低分样本揭示了什么？（算法盲区=用户真正认可什么）",
                    "时间线上有什么演化？（早期vs复兴期vs当下，氛围变化）",
                    "社交集中度反映了什么？（是精英控场还是大众狂欢）"
                ],

                "cultural_lens": [
                    "有没有文化现象？（谐音梗、玩梗传播、纯爱文化、怀旧情绪）",
                    "评论区的本质是什么？（音乐讨论/情感树洞/文案博物馆/社交广场）",
                    "存在什么'隐性规则'？（抢热评、复制金句、讲故事求赞）"
                ],

                "algorithm_blindspots": [
                    "算法把什么误判为负面？（感伤式金句、反讽、诗意表达）",
                    "用户真正认可什么内容？（高赞低分样本是最好的证据）",
                    "算法不理解什么？（如'痛苦的美学价值'）"
                ],

                "synthesis_prompts": [
                    "用一句话概括这个评论区的本质",
                    "这个评论区和其他音乐评论区有什么不同？",
                    "如果要给别人推荐看这首歌的评论区，你会说什么？"
                ]
            }
        }

        # 统计样本数量
        anchor_count = sum(len(v) for v in formatted_anchors.values())
        contrast_count = sum(len(v) for v in formatted_contrast.values())

        # v0.8.4: AI 输出要求 - 强制白盒化 + 避免 confirmation bias
        ai_output_requirements = {
            "must_report": [
                f"样本来源：锚点样本 {anchor_count} 条，对比样本 {contrast_count} 条",
                "每个判断必须引用具体样本内容"
            ],
            "format": "报告结论时必须引用原文（如：'根据样本 XXX...'）",
            "avoid_confirmation_bias": [
                "不要预设结论再找证据",
                "如果样本证据与预期不符，应该调整判断",
                "多种可能性并存时，应列出所有可能而非只选一个"
            ],
            "objectivity": "让用户看到你的推理过程，而不只是结论",
            # v0.8.5: 决策透明化
            "decision_transparency": {
                "must_explain": "AI 必须在输出中说明：样本是否足够支撑结论？是否需要 Layer 3（原始评论）？",
                "example_continue": "样本中发现异常模式，需要更多原始评论验证，调用 get_raw_comments_v2",
                "example_stop": f"锚点样本 {anchor_count} 条 + 对比样本 {contrast_count} 条足够验证信号，输出最终报告"
            },

            # v0.8.7: 报告模板 - 让报告更深入、更好看
            "report_template": {
                "structure": [
                    "## 📊 数据基础",
                    "  - 分析样本：X条（样本构成：热评+最新+年度采样）",
                    "  - 覆盖率：X%（API总量 vs 采样量）",
                    "  - 时间跨度：YYYY-YYYY（X年）",
                    "  - ⚠️ 数据局限性：覆盖率<1%时必须说明",
                    "",
                    "## 🎯 核心发现（3-5个）",
                    "  - 每个发现必须：有标题 + 有样本证据 + 有解读",
                    "  - 引用格式：\"具体评论内容\"（X万赞，日期）",
                    "",
                    "## 🧠 深层机制",
                    "  - 为什么是这首歌？（歌曲特质如何催生评论区文化）",
                    "  - 评论区演化路径（早期→中期→现在）",
                    "",
                    "## 📌 与其他评论区对比（表格）",
                    "  | 维度 | 本评论区 | 典型评论区 |",
                    "",
                    "## 🔍 一句话总结",
                    "  - 用一句话概括评论区本质",
                    "",
                    "## 💡 推荐语",
                    "  - 如果要给别人推荐看这个评论区，你会说什么？"
                ],
                "formatting_rules": [
                    "使用 emoji 作为章节标题前缀",
                    "高赞评论用引用格式（>）突出显示",
                    "数据对比用表格呈现",
                    "关键发现用**加粗**强调",
                    "每个判断必须附带样本证据"
                ],
                "depth_requirements": [
                    "不要只描述现象，要解释原因",
                    "不要只列举数据，要挖掘洞察",
                    "不要只验证信号，要发现信号背后的故事",
                    "要有'这个评论区独特在哪里'的视角"
                ]
            }
        }

        # v0.8.5: 用户强制深入选项
        deeper_options = [
            {
                "key": "force_more_samples",
                "description": "获取更多原始评论（当前样本不足时）",
                "how_to_use": "调用 get_raw_comments_v2_tool(song_id, limit=50)",
                "when_useful": "当样本数量不足以得出可靠结论时"
            },
            {
                "key": "force_high_likes_only",
                "description": "只看高赞评论（>=1000赞）",
                "how_to_use": "调用 get_raw_comments_v2_tool(song_id, min_likes=1000)",
                "when_useful": "想了解社区认可的主流观点"
            },
            {
                "key": "force_specific_year",
                "description": "查看特定年份的评论",
                "how_to_use": "调用 get_raw_comments_v2_tool(song_id, year=XXXX)",
                "when_useful": "想深入分析某个时期的评论区氛围"
            }
        ]

        # 根据样本情况调整建议
        total_samples = anchor_count + contrast_count
        if total_samples < 10:
            deeper_options[0]["recommended"] = True

        return {
            "status": "success",
            "layer": 2,
            "layer_name": "verification_samples",

            "anchors": formatted_anchors,
            "contrast": formatted_contrast,

            "sample_counts": {
                "anchors": anchor_count,
                "contrast": contrast_count,
                "total": total_samples
            },

            "verification_tasks": verification_tasks,

            "ai_guidance": ai_guidance,

            # v0.8.4: 强制 AI 报告数据来源 + 避免 confirmation bias
            "ai_output_requirements": ai_output_requirements,

            # v0.8.5: 用户强制深入选项
            "deeper_options": deeper_options,

            # v0.8.7: 采样升级提示（如果不是 deep 级别）
            "sampling_upgrade_prompt": sampling_upgrade_prompt
        }

    except Exception as e:
        logger.error(f"Layer 2 分析失败: {e}", exc_info=True)
        return {
            "status": "error",
            "error_type": "layer2_failed",
            "message": str(e),
            "song_id": song_id
        }

    finally:
        session.close()


# ============================================================
# Layer 3: 原始评论 (已有 get_raw_comments_v2)
# ============================================================

# 从 comprehensive_analysis_v2.py 导入
from mcp_server.tools.comprehensive_analysis_v2 import get_raw_comments_v2


# ============================================================
# 导出
# ============================================================

__all__ = [
    "get_analysis_overview",     # Layer 0
    "get_analysis_signals",      # Layer 1
    "get_analysis_samples",      # Layer 2
    "get_raw_comments_v2",       # Layer 3
]
