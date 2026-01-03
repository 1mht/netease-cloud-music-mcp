"""
采样策略 v2.2 - 基于Cursor时间跳转的分层采样

核心突破：发现weapi cursor参数可跳转到任意历史时间点，突破V1 GET API的offset限制

策略架构:
    Layer 1: 热门评论（社区共识层）- V1 GET hotComments - 15条
    Layer 2: 最新评论（时效层）- V1 GET offset翻页 - ~100条
    Layer 3: 历史分层采样（时间线层）- weapi POST cursor - 11年×50条=550条

理论支撑:
    - Cochran公式: n₀ = 384 (95%置信度, 5%误差)
    - 安全系数: 1.5（社交媒体高异质性）
    - 目标样本量: 600-700条

Author: 1mht + Claude
Version: v0.7.1
Date: 2026-01-01
"""

import sys
import os
import time
import random
import requests
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
from utils import create_weapi_params

# ===== 统计学常量 =====
CONFIDENCE_LEVEL = 0.95          # 置信度
MARGIN_OF_ERROR = 0.05           # 允许误差
COCHRAN_N0 = 384                 # Cochran公式基准样本量
SAFETY_FACTOR = 1.5              # 安全系数（社交媒体高异质性）

# ===== 采样参数 =====
HOT_SAMPLE_SIZE = 15             # 热评采样量（API固定返回）
RECENT_SAMPLE_SIZE = 100         # 最新评论采样量
HISTORICAL_YEARS = list(range(2024, 2013, -1))  # 2024→2014 共11年
SAMPLES_PER_YEAR = 50            # 每年采样量（≥30统计学最小值）
TARGET_TOTAL = 665               # 目标总样本量

# ===== 反爬策略 =====
DELAY_BETWEEN_REQUESTS = 0.5     # 请求间延迟(秒)
MAX_RETRIES = 3                  # 最大重试次数
RETRY_BACKOFF = 2.0              # 指数退避系数
REQUEST_TIMEOUT = 15             # 请求超时(秒)

# ===== API配置 =====
V1_API_BASE = "http://music.163.com/api/v1/resource/comments/R_SO_4_{song_id}"
WEAPI_URL = "https://music.163.com/weapi/comment/resource/comments/get?csrf_token="
PAGE_SIZE = 20

# ===== 缓存版本 =====
SAMPLE_VERSION = "v2.2"


def get_session():
    """获取数据库session"""
    db_path = os.path.join(project_root, 'data', 'music_data_v2.db')
    return init_db(f'sqlite:///{db_path}')


def _load_cookie() -> Optional[str]:
    """加载Cookie文件"""
    try:
        cookie_path = os.path.join(netease_path, 'cookie.txt')
        if os.path.exists(cookie_path):
            with open(cookie_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content and not content.startswith('#'):
                    return content
    except Exception as e:
        print(f"[Warning] 读取Cookie失败: {e}")
    return None


def _get_headers() -> Dict[str, str]:
    """获取请求头"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://music.163.com/',
        'Origin': 'https://music.163.com',
    }
    cookie = _load_cookie()
    if cookie:
        headers['Cookie'] = cookie
    return headers


def _fetch_with_retry(
    method: str,
    url: str,
    headers: Dict,
    data: Dict = None,
    max_retries: int = MAX_RETRIES
) -> Optional[Dict]:
    """带重试的请求"""
    for attempt in range(max_retries):
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            else:
                response = requests.post(url, data=data, headers=headers, timeout=REQUEST_TIMEOUT)

            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:
                    return result
                else:
                    print(f"[API Error] code={result.get('code')}, attempt {attempt+1}/{max_retries}")
            else:
                print(f"[HTTP Error] status={response.status_code}, attempt {attempt+1}/{max_retries}")

        except Exception as e:
            print(f"[Request Error] {e}, attempt {attempt+1}/{max_retries}")

        if attempt < max_retries - 1:
            sleep_time = DELAY_BETWEEN_REQUESTS * (RETRY_BACKOFF ** attempt)
            time.sleep(sleep_time)

    return None


def _parse_comment(raw_comment: Dict) -> Dict:
    """解析评论数据为统一格式"""
    user_info = raw_comment.get('user', {})
    return {
        "comment_id": str(raw_comment.get('commentId', '')),
        "content": raw_comment.get('content', ''),
        "liked_count": raw_comment.get('likedCount', 0),
        "timestamp": raw_comment.get('time', 0),
        "user_nickname": user_info.get('nickname', ''),
        "user_id": str(user_info.get('userId', '')),
    }


# ===== Layer 1: 热门评论 =====

def _fetch_hot_comments(song_id: str) -> List[Dict]:
    """
    Layer 1: 获取热门评论（社区共识层）

    来源: V1 GET API的hotComments字段
    数量: 通常15条（API固定返回）
    价值: 反映社区共识，有历史跨度（2014-2023）
    """
    url = V1_API_BASE.format(song_id=song_id) + "?limit=1&offset=0"
    headers = _get_headers()

    result = _fetch_with_retry("GET", url, headers)
    if not result:
        return []

    hot_comments = result.get('hotComments', [])
    return [_parse_comment(c) for c in hot_comments]


# ===== Layer 2: 最新评论 =====

def _fetch_recent_comments(song_id: str, limit: int = RECENT_SAMPLE_SIZE) -> List[Dict]:
    """
    Layer 2: 获取最新评论（时效层）

    来源: V1 GET API offset翻页
    数量: ~100条（offset限制内最大化）
    价值: 反映近期情绪（最近4个月）
    限制: offset > 1000 时返回空
    """
    headers = _get_headers()
    all_comments = []

    # 计算需要的页数
    pages_needed = (limit + PAGE_SIZE - 1) // PAGE_SIZE
    pages_needed = min(pages_needed, 50)  # offset限制，最多50页

    for page in range(pages_needed):
        offset = page * PAGE_SIZE
        url = V1_API_BASE.format(song_id=song_id) + f"?limit={PAGE_SIZE}&offset={offset}"

        result = _fetch_with_retry("GET", url, headers)
        if not result:
            break

        comments = result.get('comments', [])
        if not comments:
            break

        all_comments.extend([_parse_comment(c) for c in comments])

        if len(all_comments) >= limit:
            break

        time.sleep(DELAY_BETWEEN_REQUESTS)

    return all_comments[:limit]


# ===== Layer 3: 历史分层采样（核心突破） =====

def _fetch_historical_by_cursor(
    song_id: str,
    years: List[int] = None,
    samples_per_year: int = SAMPLES_PER_YEAR
) -> List[Dict]:
    """
    Layer 3: 历史分层采样（时间线层）

    来源: weapi POST + cursor参数
    方式: 跳转到每年年中，采样该年评论
    覆盖: 2014-2024年，共11年
    数量: 每年50条 × 11年 = 550条
    价值: 覆盖全时期，支持时间线分析

    关键技术: cursor = 时间戳(毫秒)，可跳转任意历史时间点
    """
    if years is None:
        years = HISTORICAL_YEARS

    headers = _get_headers()
    headers['Content-Type'] = 'application/x-www-form-urlencoded'

    all_samples = []
    years_sampled = {}

    for year in years:
        # 跳转到该年年中 (7月1日)
        try:
            cursor = str(int(datetime(year, 7, 1).timestamp() * 1000))
        except:
            continue

        year_samples = []
        max_iterations = 5  # 每年最多请求5次

        for iteration in range(max_iterations):
            if len(year_samples) >= samples_per_year:
                break

            payload = {
                'rid': f'R_SO_4_{song_id}',
                'threadId': f'R_SO_4_{song_id}',
                'pageNo': '1',
                'pageSize': '20',
                'cursor': cursor,
                'offset': '0',
                'orderType': '1',
                'csrf_token': ''
            }

            params = create_weapi_params(payload)
            data = {'params': params['params'], 'encSecKey': params['encSecKey']}

            result = _fetch_with_retry("POST", WEAPI_URL, headers, data)
            if not result:
                break

            comments = result.get('data', {}).get('comments', [])
            if not comments:
                break

            # 只保留该年的评论
            for c in comments:
                c_time = c.get('time', 0)
                if c_time:
                    c_year = datetime.fromtimestamp(c_time / 1000).year
                    if c_year == year:
                        year_samples.append(_parse_comment(c))

            # 更新cursor为最后一条评论的时间戳
            new_cursor = str(comments[-1].get('time', 0))
            if new_cursor == cursor:
                break  # 防止死循环
            cursor = new_cursor

            time.sleep(DELAY_BETWEEN_REQUESTS)

        # 截取需要的样本数
        year_samples = year_samples[:samples_per_year]
        all_samples.extend(year_samples)
        years_sampled[year] = len(year_samples)

        print(f"[Sampling] Year {year}: {len(year_samples)} comments")

    return all_samples, years_sampled


# ===== 合并去重 =====

def _merge_and_dedupe(
    hot: List[Dict],
    recent: List[Dict],
    historical: List[Dict]
) -> List[Dict]:
    """合并三层并按comment_id去重"""
    all_comments = []
    seen_ids = set()

    # 优先级: 热评 > 最新 > 历史
    for c in hot + recent + historical:
        cid = c.get('comment_id')
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            all_comments.append(c)

    return all_comments


# ===== 主入口函数 =====

def get_smart_sample(
    song_id: str,
    purpose: str = "general",
    force_refresh: bool = False,
    save_to_db: bool = True
) -> Dict[str, Any]:
    """
    智能采样主入口 - 自动获取分层样本

    Args:
        song_id: 歌曲ID
        purpose: 采样目的，影响采样策略
            - "general": 通用（默认，665条）
            - "sentiment": 情感分析（400条）
            - "timeline": 时间线分析（600条，侧重历史）
            - "keywords": 关键词分析（500条）
            - "comparison": 歌曲对比（250条）
        force_refresh: 强制刷新（忽略缓存）
        save_to_db: 是否保存到数据库

    Returns:
        {
            "status": "success",
            "comments": [...],           # 合并去重后的评论
            "stats": {
                "hot": 15,
                "recent": 100,
                "historical": 550,
                "total_unique": 620,
                "years_covered": {2024: 50, 2023: 50, ...}
            },
            "source": "api",
            "sample_version": "v2.2",
            "purpose": "general"
        }
    """
    session = get_session()

    try:
        # 1. 检查歌曲是否存在
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return {
                "status": "error",
                "error_type": "song_not_found",
                "message": f"歌曲 {song_id} 不存在于数据库",
                "suggestion": "请先使用 search_songs_tool 搜索并添加歌曲"
            }

        # 2. 根据目的调整采样参数
        sample_config = _get_sample_config(purpose)

        # 3. 检查缓存（如果不强制刷新）
        if not force_refresh:
            cached = _check_cache(session, song_id, sample_config)
            if cached:
                return cached

        print(f"[Sampling] 开始采样《{song.name}》, 目的: {purpose}")

        # 4. 执行三层采样
        hot_comments = _fetch_hot_comments(song_id)
        print(f"[Layer 1] 热评: {len(hot_comments)} 条")

        recent_comments = _fetch_recent_comments(song_id, sample_config['recent'])
        print(f"[Layer 2] 最新: {len(recent_comments)} 条")

        historical_comments, years_sampled = _fetch_historical_by_cursor(
            song_id,
            years=HISTORICAL_YEARS,
            samples_per_year=sample_config['per_year']
        )
        print(f"[Layer 3] 历史: {len(historical_comments)} 条, 覆盖 {len(years_sampled)} 年")

        # 5. 合并去重
        all_comments = _merge_and_dedupe(hot_comments, recent_comments, historical_comments)
        print(f"[Merged] 去重后: {len(all_comments)} 条")

        # 6. 保存到数据库（可选）
        if save_to_db:
            saved_count = _save_to_database(session, song_id, all_comments)
            print(f"[Saved] 保存到数据库: {saved_count} 条")

        # 7. 构建返回结果
        return {
            "status": "success",
            "song_id": song_id,
            "song_name": song.name,
            "comments": all_comments,
            "stats": {
                "hot": len(hot_comments),
                "recent": len(recent_comments),
                "historical": len(historical_comments),
                "total_unique": len(all_comments),
                "years_covered": years_sampled
            },
            "source": "api",
            "sample_version": SAMPLE_VERSION,
            "purpose": purpose,
            "theory": {
                "cochran_n0": COCHRAN_N0,
                "safety_factor": SAFETY_FACTOR,
                "target_total": TARGET_TOTAL
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "error_type": "sampling_failed",
            "message": f"采样失败: {str(e)}",
            "song_id": song_id
        }

    finally:
        session.close()


def _get_sample_config(purpose: str) -> Dict[str, int]:
    """根据目的获取采样配置"""
    configs = {
        "general": {"hot": 15, "recent": 100, "per_year": 50},
        "sentiment": {"hot": 15, "recent": 100, "per_year": 30},
        "timeline": {"hot": 15, "recent": 50, "per_year": 50},
        "keywords": {"hot": 15, "recent": 100, "per_year": 40},
        "comparison": {"hot": 15, "recent": 50, "per_year": 20},
    }
    return configs.get(purpose, configs["general"])


def _check_cache(session, song_id: str, config: Dict) -> Optional[Dict]:
    """检查缓存是否可用"""
    # 简单实现：检查数据库中是否有足够的评论
    comment_count = session.query(Comment).filter_by(song_id=song_id).count()

    # 如果数据库有足够评论（超过目标的80%），可以使用缓存
    target = config['hot'] + config['recent'] + config['per_year'] * len(HISTORICAL_YEARS)

    if comment_count >= target * 0.8:
        # 从数据库加载
        comments = session.query(Comment).filter_by(song_id=song_id).all()

        # 转换格式
        comment_list = [{
            "comment_id": c.comment_id,
            "content": c.content,
            "liked_count": c.liked_count,
            "timestamp": c.timestamp,
            "user_nickname": getattr(c, 'user_nickname', ''),
        } for c in comments]

        song = session.query(Song).filter_by(id=song_id).first()

        return {
            "status": "success",
            "song_id": song_id,
            "song_name": song.name if song else "",
            "comments": comment_list,
            "stats": {
                "total_from_cache": len(comment_list),
            },
            "source": "cache",
            "sample_version": SAMPLE_VERSION,
            "note": "数据来自本地缓存"
        }

    return None


def _save_to_database(session, song_id: str, comments: List[Dict]) -> int:
    """保存评论到数据库"""
    saved_count = 0

    for c in comments:
        # 检查是否已存在
        existing = session.query(Comment).filter_by(comment_id=c['comment_id']).first()
        if existing:
            continue

        # 创建新评论
        new_comment = Comment(
            comment_id=c['comment_id'],
            song_id=song_id,
            content=c['content'],
            liked_count=c['liked_count'],
            timestamp=c['timestamp'],
            user_nickname=c.get('user_nickname', ''),
        )

        try:
            session.add(new_comment)
            session.commit()
            saved_count += 1
        except Exception as e:
            session.rollback()
            # 忽略重复键等错误
            continue

    return saved_count


# ===== 工具函数 =====

def get_sample_stats(song_id: str) -> Dict[str, Any]:
    """获取采样统计信息（用于调试和监控）"""
    session = get_session()

    try:
        comments = session.query(Comment).filter_by(song_id=song_id).all()

        if not comments:
            return {"status": "no_data", "song_id": song_id}

        # 按年份统计
        year_counts = defaultdict(int)
        for c in comments:
            if c.timestamp:
                year = datetime.fromtimestamp(c.timestamp / 1000).year
                year_counts[year] += 1

        # 时间范围
        timestamps = [c.timestamp for c in comments if c.timestamp]

        return {
            "status": "success",
            "song_id": song_id,
            "total_comments": len(comments),
            "year_distribution": dict(sorted(year_counts.items())),
            "time_range": {
                "earliest": datetime.fromtimestamp(min(timestamps)/1000).isoformat() if timestamps else None,
                "latest": datetime.fromtimestamp(max(timestamps)/1000).isoformat() if timestamps else None,
            },
            "years_covered": len(year_counts)
        }

    finally:
        session.close()


# ===== 测试入口 =====

if __name__ == "__main__":
    # 测试采样
    print("=== 采样策略 v2.2 测试 ===")

    # 测试歌曲: Viva La Vida
    test_song_id = "3986241"

    result = get_smart_sample(test_song_id, purpose="timeline", save_to_db=False)

    if result["status"] == "success":
        print(f"\n采样成功!")
        print(f"歌曲: {result['song_name']}")
        print(f"总样本: {result['stats']['total_unique']}")
        print(f"热评: {result['stats']['hot']}")
        print(f"最新: {result['stats']['recent']}")
        print(f"历史: {result['stats']['historical']}")
        print(f"年份覆盖: {result['stats']['years_covered']}")
    else:
        print(f"\n采样失败: {result['message']}")
