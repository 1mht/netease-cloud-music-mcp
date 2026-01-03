"""
播放控制工具模块
整合 CloudMusic 播放控制功能
"""

import sys
import os
import webbrowser

# 添加 netease_cloud_music 到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
netease_path = os.path.join(project_root, 'netease_cloud_music')
if netease_path not in sys.path:
    sys.path.insert(0, netease_path)

from database import init_db, Song


def get_session():
    """获取数据库session"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                          'data', 'music_data_v2.db')
    return init_db(f'sqlite:///{db_path}')


def play_music(song_id: str = None, keyword: str = None) -> dict:
    """播放指定歌曲

    Args:
        song_id: 歌曲ID（优先）
        keyword: 搜索关键词（备选）

    Returns:
        {
            "status": "success" | "error",
            "song_id": "185811",
            "song_name": "晴天",
            "message": "..."
        }
    """
    if not song_id and not keyword:
        return {
            "status": "error",
            "message": "需要提供 song_id 或 keyword 参数"
        }

    # 如果只有 keyword，先搜索
    if not song_id:
        from tools.search import search_songs

        print(f"[SEARCH] 搜索关键词: {keyword}")
        results = search_songs(keyword, limit=1)

        if not results:
            return {
                "status": "error",
                "message": f"未找到歌曲: {keyword}"
            }

        song_id = results[0]['id']
        song_name = results[0]['name']
    else:
        # 从数据库查询歌曲名称
        session = get_session()
        try:
            song = session.query(Song).filter_by(id=song_id).first()
            song_name = song.name if song else f"ID:{song_id}"
        finally:
            session.close()

    # 使用 orpheus:// URL 协议播放
    # 网易云音乐支持自定义 URL 协议：orpheus://song/{song_id}
    url = f"orpheus://song/{song_id}"

    try:
        webbrowser.open(url)
        print(f"[OK] 已发送播放指令: {song_name} (ID: {song_id})")

        return {
            "status": "success",
            "song_id": song_id,
            "song_name": song_name,
            "message": f"已发送播放指令（歌曲ID: {song_id}）",
            "note": "请确保网易云音乐客户端已安装并运行"
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"播放失败: {str(e)}"
        }


def control_playback(action: str) -> dict:
    """控制播放（播放/暂停/上一曲/下一曲）

    Args:
        action: "play_pause" | "next" | "previous" | "volume_up" | "volume_down"

    Returns:
        {
            "status": "success" | "error",
            "action": "play_pause",
            "message": "..."
        }
    """
    try:
        import pyautogui
    except ImportError:
        return {
            "status": "error",
            "message": "需要安装 pyautogui: pip install pyautogui"
        }

    # 网易云音乐全局快捷键映射
    hotkeys = {
        "play_pause": "space",          # 播放/暂停
        "next": "ctrl+right",           # 下一曲
        "previous": "ctrl+left",        # 上一曲
        "volume_up": "ctrl+up",         # 音量+
        "volume_down": "ctrl+down",     # 音量-
    }

    if action not in hotkeys:
        return {
            "status": "error",
            "message": f"未知操作: {action}。支持的操作: {list(hotkeys.keys())}"
        }

    try:
        # 模拟按键
        key = hotkeys[action]
        pyautogui.press(key.split('+'))  # 处理组合键

        print(f"[OK] 已执行播放控制: {action}")

        return {
            "status": "success",
            "action": action,
            "message": f"已执行: {action}",
            "hotkey": key,
            "note": "此功能需要网易云音乐客户端在后台运行，且支持全局快捷键"
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"执行失败: {str(e)}"
        }


def get_current_playing() -> dict:
    """获取当前播放信息（简化版）

    注意：网易云音乐没有公开 API，此功能为预留接口

    Returns:
        {
            "status": "info",
            "message": "...",
            "note": "..."
        }
    """
    try:
        import win32gui
        import win32process
        import psutil

        # 尝试找到网易云音乐窗口
        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if "网易云音乐" in title or "NetEase" in title:
                    windows.append((hwnd, title))

        windows = []
        win32gui.EnumWindows(callback, windows)

        if not windows:
            return {
                "status": "info",
                "message": "未检测到网易云音乐客户端运行",
                "is_running": False
            }

        # 解析窗口标题（通常格式：歌名 - 歌手 - 网易云音乐）
        _, title = windows[0]
        if " - " in title:
            parts = title.split(" - ")
            if len(parts) >= 2:
                return {
                    "status": "success",
                    "is_running": True,
                    "window_title": title,
                    "parsed_info": {
                        "song_name": parts[0].strip(),
                        "artist": parts[1].strip() if len(parts) > 1 else "Unknown"
                    },
                    "note": "信息来自窗口标题解析，可能不准确"
                }

        return {
            "status": "success",
            "is_running": True,
            "window_title": title,
            "message": "网易云音乐正在运行，但无法解析当前播放信息"
        }

    except ImportError:
        return {
            "status": "info",
            "message": "需要安装 pywin32 和 psutil: pip install pywin32 psutil",
            "note": "此功能仅在 Windows 平台可用"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"获取播放信息失败: {str(e)}"
        }


def play_daily_recommend() -> dict:
    """播放每日推荐（预留功能）

    Returns:
        {
            "status": "info",
            "message": "...",
            "url": "orpheus://..."
        }
    """
    # 网易云音乐每日推荐 URL
    url = "orpheus://playlist/3136952023"  # 每日推荐歌单ID（示例）

    try:
        webbrowser.open(url)
        return {
            "status": "success",
            "message": "已打开每日推荐",
            "url": url,
            "note": "此功能可能因用户不同而失效，建议替换为个人歌单ID"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"打开失败: {str(e)}"
        }
