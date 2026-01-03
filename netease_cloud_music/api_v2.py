# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
import os
import sys

# 确保能导入同级目录的模型
sys.path.append(os.path.dirname(__file__))

from database import init_db, Song, Artist, Album, Comment
from get_song_id import search_songs
from db_utils import save_song_info, save_comments, update_lyric
from utils import get_params
from collector import crawl_all_comments_task
import requests

app = FastAPI(title="NetEase Music Crawler API V2")

# 允许跨域（为第五步前端准备）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据库 Session 管理
def get_db():
    db_dir = os.path.join(os.path.dirname(__file__), '../data')
    db_path = f'sqlite:///{os.path.join(db_dir, "music_data_v2.db")}'
    session = init_db(db_path)
    try:
        yield session
    finally:
        session.close()

# --- Pydantic 模型 (用于响应) ---

class ArtistSchema(BaseModel):
    id: str
    name: str
    class Config: from_attributes = True

class AlbumSchema(BaseModel):
    id: str
    name: str
    publish_time: Optional[int]
    pic_url: Optional[str] = None # 新增字段
    class Config: from_attributes = True

class SongBaseSchema(BaseModel):
    id: str
    name: str
    duration_ms: Optional[int]
    artists: List[ArtistSchema]
    album: Optional[AlbumSchema]
    class Config: from_attributes = True

class CommentSchema(BaseModel):
    comment_id: str
    content: str
    liked_count: int
    user_nickname: str
    user_avatar: Optional[str] = None
    time_str: Optional[str]
    timestamp: Optional[int] = None # 新增字段
    class Config: from_attributes = True

class SongDetailSchema(SongBaseSchema):
    lyric: Optional[str]
    hot_comments: List[CommentSchema]
    recent_comments: List[CommentSchema]
    class Config: from_attributes = True

# --- API 路由 ---

@app.get("/")
def read_root():
    return {"status": "success", "message": "NetEase Music API V2 is running"}

@app.get("/api/v2/search")
def search_online(keyword: str, limit: int = 10, offset: int = 0):
    """在线搜索歌曲 (实时从网易云接口获取)"""
    results = search_songs(keyword, limit=limit, offset=offset)
    return {"keyword": keyword, "results": results}

@app.get("/api/v2/songs", response_model=List[SongBaseSchema])
def list_local_songs(db=Depends(get_db)):
    """获取本地数据库中已有的歌曲列表"""
    return db.query(Song).all()

@app.get("/api/v2/songs/{song_id}", response_model=SongDetailSchema)
def get_song_detail(song_id: str, db=Depends(get_db)):
    """获取歌曲详细信息（含歌词和评论）"""
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=404, detail="Song not found in local database")
    
    # 手动处理评论分类
    all_comments = song.comments
    
    # 热门评论：过滤点赞数大于10的评论，按点赞数倒序，如果数量大于15则取前15条
    filtered_comments = [c for c in all_comments if c.liked_count > 10]
    hot_comments = sorted(filtered_comments, key=lambda c: c.liked_count, reverse=True)
    if len(hot_comments) > 15:
        hot_comments = hot_comments[:15]
    
    # # 获取热门评论的 ID 集合，以便在全部评论中排除（可选，看你喜好）
    # hot_ids = {c.comment_id for c in hot_comments}

    # # 全部/最新评论：
    # # 策略升级：使用 timestamp 排序（重建数据库后）
    # # 过滤掉已在热评区展示的评论
    # other_comments = [c for c in all_comments if c.comment_id not in hot_ids]
    
    # 按 timestamp 倒序排列（最新在前），如果没有 timestamp 则回退到 0
    recent_comments = sorted(all_comments, key=lambda c: c.timestamp or 0, reverse=True)[:500]
    
    # 构造返回对象
    return {
        "id": song.id,
        "name": song.name,
        "duration_ms": song.duration_ms,
        "artists": song.artists,
        "album": song.album,
        "lyric": song.lyric,
        "hot_comments": hot_comments,
        "recent_comments": recent_comments
    }

from typing import List, Optional, Union, Any, Dict

# ... (SongCrawlRequest 类可以保留，但我们下面的函数不再强制使用它) ...

@app.post("/api/v2/songs/crawl")
def crawl_and_save_song(song_data: Dict[str, Any], db=Depends(get_db)):
    """接收前端传来的搜索结果（以纯字典形式），保存元数据，并触发抓取"""
    
    # 既然是字典，直接使用，不需要 .dict()
    song_dict = song_data
    
    # 强转 ID 为字符串，确保数据库兼容性
    # 容错处理：确保 id 存在
    if 'id' not in song_dict:
        raise HTTPException(status_code=400, detail="Missing 'id' field")
        
    song_dict['id'] = str(song_dict['id'])
    if song_dict.get('album_id'):
        song_dict['album_id'] = str(song_dict['album_id'])
    
    try:
        # 保存基本信息
        save_song_info(db, song_dict)
        
        # 2. 触发同步（抓热评和歌词）
        # 复用 sync 逻辑
        sync_song_data(song_dict['id'], db)
        
        return {"status": "success", "message": f"Song {song_dict.get('name')} crawled successfully"}
    except Exception as e:
        # 打印错误堆栈到后台控制台，方便调试
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
    try:
        # 保存基本信息
        save_song_info(db, song_dict)
        
        # 2. 触发同步（抓热评和歌词）
        # 复用 sync 逻辑
        sync_song_data(song_data.id, db)
        
        return {"status": "success", "message": f"Song {song_data.name} crawled successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v2/songs/{song_id}/sync")
def sync_song_data(song_id: str, db=Depends(get_db)):
    """手动触发同步：抓取热评和歌词并入库"""
    # 1. 查找歌曲（必须先存在于数据库中，或者从搜索结果同步）
    # 这里为了简化，我们先从搜索中找这首歌的元数据
    # 在实际应用中，前端会先调 search，然后把选中的 song 对象发过来
    
    # 这是一个示例触发逻辑
    from get_song_lyric import get_lyric
    
    # 抓取并保存歌词
    lyric = get_lyric(song_id)
    if lyric:
        update_lyric(db, song_id, lyric)
    
    # 抓取并保存评论
    url = "https://music.163.com/weapi/comment/resource/comments/get?csrf_token="
    enc_params = get_params(song_id)
    data = {"params": enc_params[0], "encSecKey": enc_params[1]}
    resp = requests.post(url, data=data)
    hot_comments = resp.json().get('data', {}).get('hotComments', [])
    if hot_comments:
        save_comments(db, song_id, hot_comments)
        
    return {"status": "success", "message": f"Song {song_id} synced successfully"}

@app.post("/api/v2/songs/{song_id}/crawl_all_comments")
def start_crawl_all_comments(song_id: str, background_tasks: BackgroundTasks):
    """
    启动后台任务：抓取全量评论
    """
    # 计算数据库路径传给后台任务
    db_dir = os.path.join(os.path.dirname(__file__), '../data')
    db_path = f'sqlite:///{os.path.join(db_dir, "music_data_v2.db")}'
    
    # 添加到后台任务队列
    background_tasks.add_task(crawl_all_comments_task, song_id, db_path)
    
    return {"status": "started", "message": f"Started crawling all comments for {song_id}. This may take a while."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

