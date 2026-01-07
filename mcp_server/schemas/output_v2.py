"""
v0.7.4 输出格式 Schema

设计哲学：
- algorithm_assessment: 算法的初步判断（可被AI验证/质疑）
- quantified_facts: 客观量化数据
- samples: 代表性样本（Phase 3实现）
- signals: 异常信号（值得AI深挖）

核心原则：
1. 算法判断是"假设"不是"结论"
2. 必须附带置信度和局限性
3. AI可以验证/推翻算法判断
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class ConfidenceLevel(Enum):
    """置信度等级"""
    HIGH = "high"      # > 0.8
    MEDIUM = "medium"  # 0.5 - 0.8
    LOW = "low"        # < 0.5


@dataclass
class AlgorithmAssessment:
    """算法初步判断（可被验证/推翻）"""
    summary: str                          # 简短判断（1-2句）
    confidence: float                     # 置信度 0-1
    confidence_level: str                 # high/medium/low
    limitations: List[str]                # 算法局限性
    algorithm: str                        # 使用的算法名称
    note: str = "算法初步判断，供AI参考验证"  # 固定提示

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QuantifiedFacts:
    """量化事实（客观数据）"""
    metrics: Dict[str, Any]       # 核心指标
    statistics: Dict[str, Any]    # 统计数据
    sample_size: int              # 样本量
    method: str                   # 计算方法

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Sample:
    """单个代表性样本"""
    id: str                       # comment_id
    content: str                  # 评论内容
    likes: int                    # 点赞数
    year: Optional[int] = None    # 年份
    similar_count: int = 1        # 代表多少条类似评论
    cluster_label: str = ""       # 聚类标签
    purpose: str = ""             # 为什么选这条

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DimensionOutput:
    """维度输出格式（v0.7.4）"""
    dimension_id: str
    dimension_name: str

    # 算法初步判断（假设，非结论）
    algorithm_assessment: Dict[str, Any]

    # 量化事实（客观数据）
    quantified_facts: Dict[str, Any]

    # 代表性样本（Phase 3实现具体逻辑）
    samples: Dict[str, List[Dict]] = field(default_factory=dict)

    # 异常信号（值得AI深挖）
    signals: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def create_algorithm_assessment(
    summary: str,
    confidence: float,
    limitations: List[str],
    algorithm: str
) -> dict:
    """创建算法判断"""
    if confidence >= 0.8:
        level = "high"
    elif confidence >= 0.5:
        level = "medium"
    else:
        level = "low"

    return {
        "summary": summary,
        "confidence": round(confidence, 2),
        "confidence_level": level,
        "limitations": limitations,
        "algorithm": algorithm,
        "note": "算法初步判断，供AI参考验证"
    }


def create_quantified_facts(
    metrics: Dict[str, Any],
    statistics: Dict[str, Any],
    sample_size: int,
    method: str
) -> dict:
    """创建量化事实"""
    return {
        "metrics": metrics,
        "statistics": statistics,
        "sample_size": sample_size,
        "method": method
    }


def create_dimension_output(
    dimension_id: str,
    dimension_name: str,
    algorithm_assessment: dict,
    quantified_facts: dict,
    samples: dict = None,
    signals: list = None
) -> dict:
    """创建维度输出"""
    return {
        "dimension_id": dimension_id,
        "dimension_name": dimension_name,
        "algorithm_assessment": algorithm_assessment,
        "quantified_facts": quantified_facts,
        "samples": samples or {},
        "signals": signals or []
    }
