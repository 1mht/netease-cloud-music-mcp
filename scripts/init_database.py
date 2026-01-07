#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初始化数据库脚本
自动爬取 10-15 首精选歌曲的基础数据
"""

import sys
import os
import time

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, 'mcp_server'))
sys.path.insert(0, os.path.join(project_root, 'netease_cloud_music'))

from tools.search import search_songs
from tools.data_collection import add_song_basic

# 精选歌曲列表
REPRESENTATIVE_SONGS = [
    "孤勇者 陈奕迅",
    "起风了 买辣椒也用券",
    "海底 一颗小葱",
    "晴天 周杰伦",
    "稻香 周杰伦",
    "告白气球 周杰伦",
    "夜曲 周杰伦",
    "青花瓷 周杰伦",
    "七里香 周杰伦",
    "喜剧之王 李荣浩",
    "Dirty EsDeeKid",
    "匆匆那年 王菲",
]


def init_database_with_songs(max_songs=12):
    """初始化数据库，爬取精选歌曲"""
    print("=" * 70)
    print("NetEase Music Database Initialization")
    print("=" * 70)
    print(f"目标: 爬取 {max_songs} 首精选歌曲")
    print("=" * 70)
    print()

    success_count = 0
    failed_songs = []

    for idx, song_query in enumerate(REPRESENTATIVE_SONGS, 1):
        if success_count >= max_songs:
            print(f"\n[OK] 已达到目标数量 ({max_songs} 首)")
            break

        print(f"\n[{idx}/{len(REPRESENTATIVE_SONGS)}] 处理: {song_query}")
        print("-" * 70)

        try:
            # 1. 搜索歌曲
            print(f"  [搜索] 正在搜索...")
            results = search_songs(song_query, limit=1, auto_select=False)

            if not results:
                print(f"  [ERROR] 未找到歌曲")
                failed_songs.append(song_query)
                continue

            song_data = results[0]
            song_name = song_data.get('name', 'Unknown')
            artists = ', '.join(song_data.get('artists', []))

            print(f"  [OK] 找到: 《{song_name}》 - {artists}")
            print(f"       ID: {song_data.get('id')}")

            # 2. 添加到数据库
            print(f"  [添加] 正在保存到数据库...")
            result = add_song_basic(song_data)

            if result.get('status') == 'success':
                data_info = result.get('data_collected', {})
                total_comments = data_info.get('total_comments', 0)

                print(f"  [OK] 添加成功!")
                print(f"       歌词: {'有' if data_info.get('lyric') else '无'}")
                print(f"       评论: {total_comments} 条")

                success_count += 1
            else:
                print(f"  [ERROR] 添加失败: {result.get('message')}")
                failed_songs.append(song_query)

            # 3. 延迟
            if success_count < max_songs:
                delay = 3
                print(f"  [等待] {delay} 秒...")
                time.sleep(delay)

        except Exception as e:
            print(f"  [ERROR] 处理失败: {e}")
            failed_songs.append(song_query)
            time.sleep(2)

    # 总结
    print("\n" + "=" * 70)
    print("初始化完成!")
    print("=" * 70)
    print(f"成功添加: {success_count} 首")
    print(f"失败/跳过: {len(failed_songs)} 首")

    if failed_songs:
        print(f"\n失败列表:")
        for song in failed_songs:
            print(f"  - {song}")

    print("\n" + "=" * 70)
    print("数据库初始化完成! 现在可以使用 MCP Server")
    print("=" * 70)

    return success_count, failed_songs


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='初始化网易云音乐数据库')
    parser.add_argument('--max-songs', type=int, default=12,
                        help='最多爬取多少首歌 (默认: 12)')
    parser.add_argument('--quick', action='store_true',
                        help='快速模式: 只爬取5首歌')

    args = parser.parse_args()

    max_songs = 5 if args.quick else args.max_songs

    try:
        success, failed = init_database_with_songs(max_songs=max_songs)

        if success > 0:
            print(f"\n[SUCCESS] 初始化成功! 数据库现在包含 {success} 首歌曲")
            sys.exit(0)
        else:
            print(f"\n[FAILED] 初始化失败!")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] 用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
