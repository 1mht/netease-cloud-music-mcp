# -*- coding: utf-8 -*-
"""
数据透明度报告系统 v0.7.6

基于第一性原理设计：
1. 用户/AI必须知道数据状态
2. 采样过程必须可追踪
3. 置信度必须有数理依据
4. 不足之处必须明确告知

核心输出：
- data_status: 数据充足性评估
- sampling_trace: 采样过程追踪
- statistical_confidence: 统计置信度
- recommendations: 改进建议
"""

import sys
import os
import math
from typing import Dict, Any, Optional, List
from datetime import datetime

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
netease_path = os.path.join(project_root, 'netease_cloud_music')
if netease_path not in sys.path:
    sys.path.insert(0, netease_path)


# ===== 统计学常量 =====

# Cochran公式参数
Z_95 = 1.96  # 95%置信水平
Z_99 = 2.576  # 99%置信水平

# 采样阈值
N_MIN_BASIC = 100      # 最低可接受
N_MIN_STANDARD = 300   # 标准要求
N_IDEAL = 500          # 理想样本量
N_RARE_PATTERN = 299   # 稀有模式检测（1%出现率，95%捕获）


def calculate_margin_of_error(n: int, p: float = 0.5, z: float = Z_95) -> float:
    """
    计算比例估计的误差边界

    Args:
        n: 样本量
        p: 估计比例（默认0.5，最保守）
        z: 置信水平对应的Z值

    Returns:
        误差边界（如0.05表示±5%）
    """
    if n <= 0:
        return 1.0
    return z * math.sqrt(p * (1 - p) / n)


def calculate_required_sample_size(
    margin_of_error: float = 0.05,
    confidence_level: float = 0.95,
    p: float = 0.5
) -> int:
    """
    计算所需样本量（Cochran公式）

    Args:
        margin_of_error: 期望误差边界
        confidence_level: 置信水平
        p: 估计比例

    Returns:
        所需样本量
    """
    z = Z_95 if confidence_level < 0.99 else Z_99
    n = (z ** 2 * p * (1 - p)) / (margin_of_error ** 2)
    return int(math.ceil(n))


def assess_sample_adequacy(n: int, api_total: int = None) -> Dict[str, Any]:
    """
    评估样本充足性

    基于第一性原理：
    - 统计学：误差边界、置信度
    - 覆盖率：样本占总体比例
    - 稀有模式：能否检测到1%出现率的模式

    Args:
        n: 当前样本量
        api_total: API报告的总评论数

    Returns:
        充足性评估报告
    """
    # 计算误差边界
    margin_of_error = calculate_margin_of_error(n)

    # 评估等级
    if n >= N_IDEAL:
        level = "excellent"
        level_zh = "优秀"
    elif n >= N_MIN_STANDARD:
        level = "good"
        level_zh = "良好"
    elif n >= N_MIN_BASIC:
        level = "acceptable"
        level_zh = "可接受"
    elif n >= 50:
        level = "limited"
        level_zh = "有限"
    else:
        level = "insufficient"
        level_zh = "不足"

    # 覆盖率
    coverage = None
    if api_total and api_total > 0:
        coverage = n / api_total

    # 稀有模式检测能力
    rare_pattern_detectable = n >= N_RARE_PATTERN

    # 各分析类型的可靠性
    reliability = {
        "proportion_estimation": {
            "reliable": n >= 100,
            "margin_of_error": f"±{margin_of_error*100:.1f}%",
            "note": "如情感占比、主题分布"
        },
        "mean_estimation": {
            "reliable": n >= 50,
            "note": "如情感均分"
        },
        "rare_pattern_detection": {
            "reliable": rare_pattern_detectable,
            "detectable_rate": f"≥{math.ceil(3/n*100)}%" if n > 0 else "N/A",
            "note": "如反讽评论、特定梗"
        },
        "temporal_analysis": {
            "reliable": n >= 30 * 3,  # 至少3个时间段，每段30条
            "note": "需要每个时间段≥30条"
        }
    }

    return {
        "sample_size": n,
        "api_total": api_total,
        "coverage": f"{coverage*100:.2f}%" if coverage else "未知",
        "level": level,
        "level_zh": level_zh,
        "margin_of_error": f"±{margin_of_error*100:.1f}%",
        "confidence_level": "95%",
        "rare_pattern_detectable": rare_pattern_detectable,
        "reliability": reliability,
        "thresholds": {
            "current": n,
            "minimum_acceptable": N_MIN_BASIC,
            "standard": N_MIN_STANDARD,
            "ideal": N_IDEAL,
            "gap_to_standard": max(0, N_MIN_STANDARD - n)
        }
    }


def create_transparency_report(
    song_id: str,
    db_count: int,
    api_total: int = None,
    sampling_occurred: bool = False,
    sampling_details: Dict = None
) -> Dict[str, Any]:
    """
    创建完整的透明度报告

    这是v0.7.6的核心改进：让用户/AI完全了解数据状态

    Args:
        song_id: 歌曲ID
        db_count: 数据库中的评论数
        api_total: API报告的总评论数
        sampling_occurred: 是否进行了采样
        sampling_details: 采样过程详情

    Returns:
        透明度报告
    """
    adequacy = assess_sample_adequacy(db_count, api_total)

    # 数据来源追踪
    data_source = {
        "database_count": db_count,
        "api_total": api_total if api_total else "未查询",
        "source_type": "cached" if not sampling_occurred else "fresh_sampled",
        "last_check": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    # 采样追踪
    sampling_trace = None
    if sampling_occurred and sampling_details:
        sampling_trace = {
            "occurred": True,
            "strategy": sampling_details.get("strategy", "unknown"),
            "target": sampling_details.get("target", "N/A"),
            "actual": sampling_details.get("actual", db_count),
            "stop_reason": sampling_details.get("stop_reason", "unknown"),
            "pages_fetched": sampling_details.get("pages_fetched", "N/A"),
            "stability_achieved": sampling_details.get("stability_achieved", None)
        }
    else:
        sampling_trace = {
            "occurred": False,
            "reason": "使用缓存数据" if db_count > 0 else "无数据"
        }

    # 生成建议
    recommendations = []

    if adequacy["level"] == "insufficient":
        recommendations.append({
            "priority": "critical",
            "action": "需要采样更多数据",
            "detail": f"当前{db_count}条，至少需要{N_MIN_BASIC}条",
            "command": f"get_comments_metadata_tool(song_id='{song_id}', include_api_count=True)"
        })
    elif adequacy["level"] == "limited":
        recommendations.append({
            "priority": "high",
            "action": "建议增加采样",
            "detail": f"当前{db_count}条，建议达到{N_MIN_STANDARD}条",
            "gap": N_MIN_STANDARD - db_count
        })

    if not adequacy["rare_pattern_detectable"]:
        recommendations.append({
            "priority": "medium",
            "action": "稀有模式检测受限",
            "detail": f"需要{N_RARE_PATTERN}条才能可靠检测1%出现率的模式（如反讽）"
        })

    if api_total is None:
        recommendations.append({
            "priority": "info",
            "action": "建议查询API总数",
            "detail": "可计算覆盖率，判断数据代表性"
        })

    # AI探索建议
    ai_exploration_hints = []

    if adequacy["level"] in ["insufficient", "limited"]:
        ai_exploration_hints.append(
            "⚠️ 数据量有限，分析结论需谨慎解读"
        )

    if not adequacy["rare_pattern_detectable"]:
        ai_exploration_hints.append(
            "⚠️ 可能遗漏低频模式（如特定梗、反讽评论）"
        )

    if adequacy["coverage"] != "未知":
        coverage_val = float(adequacy["coverage"].replace("%", ""))
        if coverage_val < 1:
            ai_exploration_hints.append(
                f"ℹ️ 覆盖率仅{adequacy['coverage']}，高赞热评可能未全部捕获"
            )

    return {
        "transparency_version": "0.7.6",
        "song_id": song_id,
        "data_source": data_source,
        "sample_adequacy": adequacy,
        "sampling_trace": sampling_trace,
        "recommendations": recommendations,
        "ai_exploration_hints": ai_exploration_hints,
        "statistical_notes": {
            "methodology": "基于Cochran公式和中心极限定理",
            "assumptions": [
                "假设评论分布近似正态（对于大样本成立）",
                "假设采样是随机的（实际可能有偏差）",
                "热评采样可能过度代表极端观点"
            ]
        }
    }


def format_transparency_for_ai(report: Dict[str, Any]) -> str:
    """
    格式化透明度报告，供AI阅读

    Args:
        report: 透明度报告

    Returns:
        格式化的文本
    """
    lines = []
    lines.append("=" * 50)
    lines.append("数据透明度报告")
    lines.append("=" * 50)

    adequacy = report.get("sample_adequacy", {})
    source = report.get("data_source", {})

    lines.append(f"\n📊 样本量: {adequacy.get('sample_size', 0)}条")
    lines.append(f"📈 API总数: {source.get('api_total', '未知')}")
    lines.append(f"📉 覆盖率: {adequacy.get('coverage', '未知')}")
    lines.append(f"🎯 充足性: {adequacy.get('level_zh', '未知')} ({adequacy.get('level', '')})")
    lines.append(f"📐 误差边界: {adequacy.get('margin_of_error', 'N/A')}")

    lines.append(f"\n稀有模式检测: {'可靠' if adequacy.get('rare_pattern_detectable') else '不可靠'}")

    # 建议
    recommendations = report.get("recommendations", [])
    if recommendations:
        lines.append("\n⚠️ 建议:")
        for rec in recommendations:
            lines.append(f"  [{rec.get('priority', '')}] {rec.get('action', '')}")
            lines.append(f"      {rec.get('detail', '')}")

    # AI提示
    hints = report.get("ai_exploration_hints", [])
    if hints:
        lines.append("\n💡 AI探索提示:")
        for hint in hints:
            lines.append(f"  {hint}")

    return "\n".join(lines)


# ===== 导出 =====

__all__ = [
    "calculate_margin_of_error",
    "calculate_required_sample_size",
    "assess_sample_adequacy",
    "create_transparency_report",
    "format_transparency_for_ai",
    "N_MIN_BASIC",
    "N_MIN_STANDARD",
    "N_IDEAL",
    "N_RARE_PATTERN"
]
