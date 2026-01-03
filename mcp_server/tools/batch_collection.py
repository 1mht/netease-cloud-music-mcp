"""
批量数据收集工具模块
支持歌单批量抓取、并发处理等功能
"""

import sys
import os
import requests
import time
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加 netease_cloud_music 到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
netease_path = os.path.join(project_root, 'netease_cloud_music')
if netease_path not in sys.path:
    sys.path.insert(0, netease_path)

from database import init_db, Song, Comment
from tools.search import search_songs
from tools.data_collection import add_song_basic, get_session

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': 'https://music.163.com/'
}


def parse_playlist_url(playlist_url: str) -> list:
    """解析歌单 URL，获取所有歌曲 ID 和名称

    Args:
        playlist_url: 歌单 URL，格式如 https://music.163.com/playlist?id=123456

    Returns:
        [
            {"id": "185811", "name": "晴天"},
            ...
        ]
    """
    try:
        print(f"[START] 正在解析歌单: {playlist_url}")

        response = requests.get(playlist_url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        ul_tag = soup.find('ul', class_='f-hide')

        if not ul_tag:
            print("[ERROR] 未找到歌曲列表（ul.f-hide）")
            return []

        songs = []
        for li in ul_tag.find_all('li'):
            a_tag = li.find('a')
            if a_tag:
                song_id = a_tag['href'].split('=')[1]
                song_name = a_tag.text.strip()
                songs.append({'id': song_id, 'name': song_name})

        print(f"[OK] 解析成功，共找到 {len(songs)} 首歌曲")
        return songs

    except Exception as e:
        print(f"[ERROR] 解析歌单失败: {e}")
        return []


def add_playlist_to_database(playlist_url: str, max_songs: int = None, use_threading: bool = True) -> dict:
    """批量添加歌单中的歌曲到数据库（Level 2 数据）

    Args:
        playlist_url: 歌单 URL
        max_songs: 最多添加多少首歌（None 表示全部）
        use_threading: 是否使用多线程（默认 True）

    Returns:
        {
            "status": "success" | "error",
            "playlist_url": "...",
            "total_songs": 50,
            "songs_added": 45,
            "songs_skipped": 5,
            "failed_songs": [],
            "message": "..."
        }
    """
    # 1. 解析歌单
    songs = parse_playlist_url(playlist_url)

    if not songs:
        return {
            "status": "error",
            "message": "歌单解析失败或歌单为空"
        }

    # 2. 限制数量
    if max_songs:
        songs = songs[:max_songs]
        print(f"[INFO] 限制添加数量为 {max_songs} 首")

    # 3. 检查哪些歌曲已存在
    session = get_session()
    try:
        existing_ids = set(s.id for s in session.query(Song.id).all())
    finally:
        session.close()

    # 过滤已存在的歌曲
    new_songs = [s for s in songs if s['id'] not in existing_ids]
    skipped_count = len(songs) - len(new_songs)

    if skipped_count > 0:
        print(f"[INFO] 跳过 {skipped_count} 首已存在的歌曲")

    if not new_songs:
        return {
            "status": "success",
            "total_songs": len(songs),
            "songs_added": 0,
            "songs_skipped": skipped_count,
            "message": "所有歌曲已存在于数据库"
        }

    # 4. 批量添加（多线程或单线程）
    print(f"\n[START] 开始添加 {len(new_songs)} 首新歌曲...")
    print("=" * 70)

    added_count = 0
    failed_songs = []

    def add_single_song(song_info):
        """添加单首歌曲的任务函数"""
        try:
            # 先搜索获取完整元数据
            results = search_songs(song_info['name'], limit=1)
            if not results:
                print(f"[WARNING] 搜索失败: {song_info['name']}")
                return {"status": "failed", "song": song_info, "reason": "search_failed"}

            # 添加到数据库
            result = add_song_basic(results[0])

            if result.get('status') == 'success':
                print(f"[OK] {song_info['name']} - 成功")
                return {"status": "success", "song": song_info}
            else:
                print(f"[ERROR] {song_info['name']} - {result.get('message')}")
                return {"status": "failed", "song": song_info, "reason": result.get('message')}

        except Exception as e:
            print(f"[ERROR] {song_info['name']} - {str(e)}")
            return {"status": "failed", "song": song_info, "reason": str(e)}

    if use_threading:
        # 多线程处理（每批 3 首歌）
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(add_single_song, song) for song in new_songs]

            for future in as_completed(futures):
                result = future.result()
                if result['status'] == 'success':
                    added_count += 1
                else:
                    failed_songs.append(result['song'])

                # 延迟避免请求过快
                time.sleep(1)
    else:
        # 单线程处理
        for song in new_songs:
            result = add_single_song(song)
            if result['status'] == 'success':
                added_count += 1
            else:
                failed_songs.append(result['song'])

            time.sleep(2)  # 单线程延迟更长

    print("=" * 70)
    print(f"[COMPLETED] 添加完成")
    print(f"  成功: {added_count} 首")
    print(f"  跳过: {skipped_count} 首（已存在）")
    print(f"  失败: {len(failed_songs)} 首")

    return {
        "status": "success",
        "playlist_url": playlist_url,
        "total_songs": len(songs),
        "songs_added": added_count,
        "songs_skipped": skipped_count,
        "failed_songs": [s['name'] for s in failed_songs],
        "message": f"成功添加 {added_count}/{len(new_songs)} 首新歌曲"
    }


def batch_add_songs_by_keywords(keywords: list, max_per_keyword: int = 1) -> dict:
    """批量搜索并添加歌曲

    Args:
        keywords: 关键词列表，如 ["晴天 周杰伦", "海底 一颗小葱"]
        max_per_keyword: 每个关键词最多添加几首歌

    Returns:
        {
            "status": "success",
            "total_keywords": 10,
            "songs_added": 8,
            "failed_keywords": ["xxx"],
            "message": "..."
        }
    """
    print(f"[START] 批量添加 {len(keywords)} 个关键词对应的歌曲...")

    added_count = 0
    failed_keywords = []

    for idx, keyword in enumerate(keywords, 1):
        try:
            print(f"\n[{idx}/{len(keywords)}] 搜索: {keyword}")

            # 搜索歌曲
            results = search_songs(keyword, limit=max_per_keyword)

            if not results:
                print(f"[WARNING] 未找到歌曲")
                failed_keywords.append(keyword)
                continue

            # 添加第一首（或前N首）
            for song_data in results[:max_per_keyword]:
                result = add_song_basic(song_data)

                if result.get('status') == 'success':
                    added_count += 1
                    print(f"[OK] 添加成功: {song_data.get('name')}")
                else:
                    print(f"[ERROR] 添加失败: {result.get('message')}")

            # 延迟
            time.sleep(2)

        except Exception as e:
            print(f"[ERROR] 处理关键词失败: {e}")
            failed_keywords.append(keyword)

    return {
        "status": "success",
        "total_keywords": len(keywords),
        "songs_added": added_count,
        "failed_keywords": failed_keywords,
        "message": f"成功添加 {added_count} 首歌曲"
    }


def get_database_statistics() -> dict:
    """获取数据库统计信息

    Returns:
        {
            "total_songs": 14,
            "total_comments": 1072,
            "songs_with_lyrics": 9,
            "songs_without_lyrics": 5,
            "avg_comments_per_song": 76.5
        }
    """
    session = get_session()

    try:
        total_songs = session.query(Song).count()
        total_comments = session.query(Comment).count()

        songs_with_lyrics = session.query(Song).filter(Song.lyric.isnot(None), Song.lyric != '').count()
        songs_without_lyrics = total_songs - songs_with_lyrics

        avg_comments = total_comments / total_songs if total_songs > 0 else 0

        return {
            "total_songs": total_songs,
            "total_comments": total_comments,
            "songs_with_lyrics": songs_with_lyrics,
            "songs_without_lyrics": songs_without_lyrics,
            "avg_comments_per_song": round(avg_comments, 2)
        }

    finally:
        session.close()
