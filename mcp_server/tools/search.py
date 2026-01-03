"""
搜索工具模块
封装网易云音乐搜索功能
"""

import sys
import os
import uuid
from typing import Dict, List, Optional

# 添加 netease_cloud_music 到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
netease_path = os.path.join(project_root, 'netease_cloud_music')
if netease_path not in sys.path:
    sys.path.insert(0, netease_path)

from get_song_id import search_songs as netease_search_songs

# 搜索会话存储（临时存储搜索结果）
# 格式：{session_id: {"results": [...], "keyword": "...", "timestamp": ...}}
_search_sessions: Dict[str, Dict] = {}


def search_songs(keyword: str, limit: int = 10):
    """搜索网易云音乐

    Args:
        keyword: 搜索关键词，支持"歌名 歌手"格式
        limit: 返回结果数量，默认10

    Returns:
        搜索结果列表 (list)，如果没有结果返回空列表 []

    Examples:
        >>> search_songs("晴天 周杰伦", limit=5)
        [
            {
                'id': '185811',
                'name': '晴天',
                'artists': ['周杰伦'],
                'artists_details': [{'id': '6452', 'name': '周杰伦'}],
                'album': '叶惠美',
                'album_id': 18903,
                'album_pic_url': 'https://...',
                'duration_ms': 269000,
                'publish_time': 1059580800000
            },
            ...
        ]
    """
    try:
        results = netease_search_songs(keyword, limit=limit, offset=0)
        return results if results else []
    except Exception as e:
        print(f"[搜索错误] {e}")
        return []


def format_search_results(results, keyword):
    """格式化搜索结果为MCP返回格式（两步架构：不返回song_id）

    Args:
        results: search_songs() 的返回结果
        keyword: 搜索关键词

    Returns:
        格式化的字典，包含 session_id 和选项列表（不包含 song_id）
    """
    if not results:
        return {
            "status": "no_results",
            "keyword": keyword,
            "count": 0,
            "message": "未找到相关歌曲",
            "suggestion": "可以尝试：1) 简化关键词 2) 只搜歌名 3) 换个写法"
        }

    # 生成唯一 session_id
    session_id = f"search_{uuid.uuid4().hex[:12]}"

    # 保存搜索结果到临时存储
    import time
    _search_sessions[session_id] = {
        "results": results,
        "keyword": keyword,
        "timestamp": time.time()
    }

    # ===== Phase 2: 去中心化决策 - 提供元数据而非判断 =====
    # 不再做"原版/翻唱"判断，提供丰富信息让用户决定

    choices = []
    for i, song in enumerate(results, 1):
        artists = song.get('artists', ['未知'])
        artists_str = ", ".join(artists)
        album = song.get('album', '未知专辑')

        # 获取时长（转换为分:秒格式）
        duration_ms = song.get('duration', 0)
        duration_str = f"{duration_ms//60000}:{duration_ms%60000//1000:02d}" if duration_ms > 0 else "未知"

        # 新格式：提供充分信息，让用户判断
        # 格式：序号. 歌名 - 艺术家 | 专辑:xxx | 时长:x:xx
        choice_text = (
            f"{i}. {song.get('name')} - {artists_str} | "
            f"专辑:{album} | 时长:{duration_str}"
        )
        choices.append(choice_text)

    return {
        "status": "pending_selection",
        "session_id": session_id,
        "keyword": keyword,
        "count": len(results),
        "choices": choices,
        "must_ask_user": True,
        "next_step": f"""⛔ 严禁自作主张选择！必须让用户决定！

找到 {len(results)} 首歌曲，请展示给用户：
{chr(10).join(choices)}

【正确做法】
1. 将以上列表展示给用户
2. 询问："请选择第几首？"
3. ⛔ 停在这里！等待用户回复！
4. 用户回复后才能调用 confirm_song_selection_tool

【严禁行为】
❌ 不要自己选择第1首
❌ 不要判断"用户可能想要xxx"
❌ 不要在用户回复前调用confirm
"""
    }


def confirm_song_selection(session_id: str, choice_number: int) -> dict:
    """确认用户选择的歌曲（两步架构第二步）

    Args:
        session_id: 搜索会话ID（由 search_songs_tool 返回）
        choice_number: 用户选择的序号（1-based）

    Returns:
        选中的歌曲信息，包含 song_id
    """
    # 检查 session 是否存在
    if session_id not in _search_sessions:
        return {
            "status": "error",
            "message": f"无效的 session_id: {session_id}",
            "suggestion": "请先调用 search_songs_tool 进行搜索"
        }

    session = _search_sessions[session_id]
    results = session["results"]

    # 验证选择范围
    if choice_number < 1 or choice_number > len(results):
        return {
            "status": "error",
            "message": f"选择超出范围，有效范围：1-{len(results)}",
            "suggestion": f"请重新选择 1-{len(results)} 之间的数字"
        }

    # 获取选中的歌曲（转为0-based索引）
    selected_song = results[choice_number - 1]

    # 清理已使用的 session（节省内存）
    del _search_sessions[session_id]

    # v0.6.6: 添加next_step引导AI完成后续workflow
    song_id = selected_song['id']
    song_name = selected_song['name']
    artists_str = ', '.join(selected_song.get('artists', ['未知']))

    return {
        "status": "confirmed",
        "song_id": song_id,
        "song_name": song_name,
        "artists": selected_song.get('artists', ['未知']),
        "album": selected_song.get('album', '未知专辑'),
        "full_info": selected_song,
        "message": f"✅ 已确认选择：{song_name} - {artists_str}",
        "next_step": f"""
【workflow引导 - v0.6.6】

✅ 已确认歌曲：{song_name} - {artists_str}
📋 song_id: {song_id}

下一步操作（根据用户需求选择）:

1️⃣ 如果需要分析评论/可视化:
   → 调用 add_song_to_database(song_id="{song_id}")
   → 然后调用 get_comments_by_pages_tool(song_id="{song_id}", data_source="api", pages=[1,2,3])
   → 最后调用分析/可视化工具

2️⃣ 如果只是查询歌曲信息:
   → 已完成，可直接告知用户歌曲信息

⚠️ 大多数分析工具需要歌曲已入库，请遵循步骤1的流程
"""  # v0.6.6: 引导AI理解正确的workflow
    }
