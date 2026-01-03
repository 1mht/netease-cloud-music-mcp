"""
数据可视化工具模块
生成图表并通过 Base64 编码返回给 MCP 客户端
"""

import sys
import os
import io
import base64
from datetime import datetime
from collections import Counter

# 添加 netease_cloud_music 到 Python 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
netease_path = os.path.join(project_root, 'netease_cloud_music')
if netease_path not in sys.path:
    sys.path.insert(0, netease_path)

from database import init_db, Song, Comment
from .workflow_errors import workflow_error  # v0.6.6: 统一错误处理

# 导入可视化库
import matplotlib
matplotlib.use('Agg')  # 使用非 GUI 后端
import matplotlib.pyplot as plt
import jieba
from wordcloud import WordCloud


# 设置中文字体（避免乱码）
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


def get_session():
    """获取数据库session"""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                          'data', 'music_data_v2.db')
    return init_db(f'sqlite:///{db_path}')


def save_figure_to_file(fig, song_id: str, chart_type: str) -> dict:
    """保存matplotlib图表到文件（v0.6.5 - 避免上下文窗口溢出）

    Args:
        fig: matplotlib figure对象
        song_id: 歌曲ID
        chart_type: 图表类型（sentiment_distribution, timeline, wordcloud等）

    Returns:
        {
            "file_path": "绝对路径",
            "relative_path": "相对于项目根目录的路径",
            "file_url": "file:/// URL（跨平台兼容）"
        }
    """
    # 创建visualizations目录
    vis_dir = os.path.join(project_root, 'visualizations')
    os.makedirs(vis_dir, exist_ok=True)

    # 生成文件名：chart_type_songid_timestamp.png
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{chart_type}_{song_id}_{timestamp}.png"
    file_path = os.path.join(vis_dir, filename)

    # 保存图片
    fig.savefig(file_path, format='png', dpi=100, bbox_inches='tight')
    plt.close(fig)

    # 生成返回路径（跨平台兼容）
    abs_path = os.path.abspath(file_path)
    rel_path = os.path.relpath(file_path, project_root)

    # 转换为file:// URL（处理Windows路径）
    if os.name == 'nt':  # Windows
        # Windows: C:\path -> file:///C:/path
        file_url = 'file:///' + abs_path.replace('\\', '/')
    else:  # Linux/Mac
        file_url = 'file://' + abs_path

    return {
        "file_path": abs_path,
        "relative_path": rel_path,
        "file_url": file_url
    }


def fig_to_base64(fig) -> str:
    """将 matplotlib 图表转换为 Base64 字符串

    ⚠️ DEPRECATED in v0.6.5: 使用 save_figure_to_file() 代替
    此函数导致上下文窗口溢出，已弃用但保留以兼容旧代码

    Args:
        fig: matplotlib figure 对象

    Returns:
        Base64 编码的 PNG 图像字符串
    """
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    buf.close()
    plt.close(fig)
    return img_base64


def visualize_sentiment_distribution(song_id: str) -> dict:
    """可视化歌曲评论的情感分布

    📋 前置条件（v0.6.6）:
    ✓ 歌曲必须已存在于数据库（通过search→confirm→add_song流程添加）
    ✓ 数据库中必须有评论数据（通过get_comments_by_pages_tool获取）

    ⚠️ 如果前置条件不满足:
    本工具会返回workflow_error，指引你完成正确流程

    ⚠️ AI使用指南（v0.6.6）：
    1. 调用成功后，**必须使用返回值中的user_message告知用户**
    2. user_message已包含文件路径，直接输出即可
    3. 示例：直接输出result["user_message"]到对话

    Args:
        song_id: 歌曲ID

    Returns:
        {
            "status": "success",
            "song_name": "晴天",
            "chart_type": "pie",
            "chart_path": "D:/path/to/visualizations/sentiment_xxx.png",
            "chart_url": "file:///D:/path/to/visualizations/sentiment_xxx.png",
            "relative_path": "visualizations/sentiment_xxx.png",
            "user_message": "✅ 情感分布图已生成并保存到：visualizations/sentiment_xxx.png",  # v0.6.6
            "statistics": {...}
        }
    """
    session = get_session()

    try:
        # v0.6.6: check song exists (use id)
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return workflow_error("song_not_found", "visualize_sentiment_tool")

        comments = session.query(Comment).filter_by(song_id=song_id).all()
        if not comments:
            return workflow_error("no_comments", "visualize_sentiment_tool")

        print(f"[Visualize] 生成《{song.name}》的情感分布图...")

        # 2. 进行情感分析
        from tools.sentiment_analysis import get_analyzer

        analyzer = get_analyzer("simple")
        scores = []

        for comment in comments:
            if len(comment.content) >= 5:
                try:
                    score = analyzer.analyze(comment.content)
                    scores.append(score)
                except:
                    continue

        if not scores:
            return {"status": "error", "message": "没有有效评论可分析"}

        # 3. 统计情感分布
        positive = sum(1 for s in scores if s >= 0.6)
        negative = sum(1 for s in scores if s <= 0.4)
        neutral = len(scores) - positive - negative

        # 4. 创建饼图
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # 饼图
        labels = [f'Positive\n{positive}', f'Neutral\n{neutral}', f'Negative\n{negative}']
        sizes = [positive, neutral, negative]
        colors = ['#66c2a5', '#fc8d62', '#8da0cb']
        explode = (0.1, 0, 0.1)  # 突出正面和负面

        ax1.pie(sizes, explode=explode, labels=labels, colors=colors,
                autopct='%1.1f%%', shadow=True, startangle=90)
        ax1.set_title(f'Sentiment Distribution - {song.name}', fontsize=14, fontweight='bold')

        # 柱状图
        categories = ['Positive', 'Neutral', 'Negative']
        values = [positive, neutral, negative]

        bars = ax2.bar(categories, values, color=colors, alpha=0.8)
        ax2.set_ylabel('Comment Count', fontsize=12)
        ax2.set_title(f'Sentiment Counts - {song.name}', fontsize=14, fontweight='bold')
        ax2.grid(axis='y', alpha=0.3)

        # 添加数值标签
        for bar in bars:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}',
                    ha='center', va='bottom', fontsize=11)

        plt.tight_layout()

        # 5. 保存到文件（v0.6.5 - 避免上下文窗口溢出）
        path_info = save_figure_to_file(fig, song_id, "sentiment_distribution")

        print(f"[OK] 图表已保存到: {path_info['relative_path']}")

        # v0.6.6: 生成user_message引导AI告知用户
        user_message = f"✅ 情感分布图已生成并保存到：{path_info['relative_path']}"

        return {
            "status": "success",
            "song_id": song_id,
            "song_name": song.name,
            "chart_type": "sentiment_distribution",
            "chart_path": path_info["file_path"],
            "chart_url": path_info["file_url"],
            "relative_path": path_info["relative_path"],
            "user_message": user_message,  # v0.6.6: AI应将此消息告知用户
            "statistics": {
                "positive": positive,
                "neutral": neutral,
                "negative": negative,
                "total": len(scores)
            }
        }

    finally:
        session.close()


def visualize_comment_timeline(song_id: str, interval: str = "month") -> dict:
    """可视化评论时间线（评论数随时间变化）

    📋 前置条件（v0.6.6）:
    ✓ 歌曲必须已存在于数据库（通过search→confirm→add_song流程添加）
    ✓ 数据库中必须有评论数据（通过get_comments_by_pages_tool获取）

    ⚠️ 如果前置条件不满足:
    本工具会返回workflow_error，指引你完成正确流程

    ⚠️ AI使用指南（v0.6.6）：
    1. 调用成功后，**必须使用返回值中的user_message告知用户**
    2. user_message已包含文件路径和时间范围，直接输出即可

    Args:
        song_id: 歌曲ID
        interval: 时间间隔 ("day" | "month" | "year")

    Returns:
        {
            "status": "success",
            "song_name": "晴天",
            "chart_type": "timeline",
            "chart_path": "...",
            "chart_url": "...",
            "relative_path": "visualizations/timeline_xxx.png",
            "user_message": "✅ 评论时间线图已生成...",  # v0.6.6
            "time_range": {...}
        }
    """
    # ===== 参数验证 =====
    valid_intervals = ["day", "month", "year"]
    if interval not in valid_intervals:
        return {
            "status": "error",
            "message": f"无效的时间间隔: {interval}",
            "valid_options": valid_intervals
        }

    session = get_session()

    try:
        # v0.6.6: check song exists (use id)
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return workflow_error("song_not_found", "visualize_timeline_tool")

        comments = session.query(Comment).filter_by(song_id=song_id)\
            .filter(Comment.timestamp.isnot(None))\
            .order_by(Comment.timestamp.asc()).all()

        if not comments:
            return workflow_error("no_comments", "visualize_timeline_tool")

        print(f"[Visualize] 生成《{song.name}》的评论时间线...")

        # 2. 提取时间戳并转换
        timestamps = []
        for comment in comments:
            try:
                # 网易云时间戳是毫秒
                dt = datetime.fromtimestamp(comment.timestamp / 1000)
                timestamps.append(dt)
            except:
                continue

        if not timestamps:
            return {"status": "error", "message": "无法解析时间戳"}

        # 3. 按时间间隔分组
        if interval == "month":
            time_groups = {}
            for ts in timestamps:
                key = ts.strftime('%Y-%m')
                time_groups[key] = time_groups.get(key, 0) + 1
        elif interval == "day":
            time_groups = {}
            for ts in timestamps:
                key = ts.strftime('%Y-%m-%d')
                time_groups[key] = time_groups.get(key, 0) + 1
        else:  # year
            time_groups = {}
            for ts in timestamps:
                key = ts.strftime('%Y')
                time_groups[key] = time_groups.get(key, 0) + 1

        # 排序
        sorted_times = sorted(time_groups.items())
        time_labels = [t[0] for t in sorted_times]
        counts = [t[1] for t in sorted_times]

        # 4. 创建折线图
        fig, ax = plt.subplots(figsize=(14, 6))

        ax.plot(time_labels, counts, marker='o', linewidth=2, markersize=6,
                color='#3498db', label='Comment Count')
        ax.fill_between(range(len(counts)), counts, alpha=0.3, color='#3498db')

        ax.set_xlabel('Time', fontsize=12, fontweight='bold')
        ax.set_ylabel('Comment Count', fontsize=12, fontweight='bold')
        ax.set_title(f'Comment Timeline - {song.name}', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend()

        # 旋转 x 轴标签
        plt.xticks(rotation=45, ha='right')

        plt.tight_layout()

        # 5. 保存到文件（v0.6.5 - 避免上下文窗口溢出）
        path_info = save_figure_to_file(fig, song_id, "comment_timeline")

        print(f"[OK] 时间线图表已保存到: {path_info['relative_path']}")

        # v0.6.6: 生成user_message引导AI告知用户
        time_start = min(timestamps).strftime('%Y-%m-%d')
        time_end = max(timestamps).strftime('%Y-%m-%d')
        user_message = f"✅ 评论时间线图已生成并保存到：{path_info['relative_path']}\n数据时间范围：{time_start} 至 {time_end}，共 {len(timestamps)} 条评论"

        return {
            "status": "success",
            "song_id": song_id,
            "song_name": song.name,
            "chart_type": "comment_timeline",
            "chart_path": path_info["file_path"],
            "chart_url": path_info["file_url"],
            "relative_path": path_info["relative_path"],
            "user_message": user_message,  # v0.6.6: AI应将此消息告知用户
            "time_range": {
                "start": time_start,
                "end": time_end,
                "total_comments": len(timestamps)
            }
        }

    finally:
        session.close()


def generate_wordcloud(song_id: str, max_words: int = 100) -> dict:
    """生成评论词云图

    📋 前置条件（v0.6.6）:
    ✓ 歌曲必须已存在于数据库（通过search→confirm→add_song流程添加）
    ✓ 数据库中必须有评论数据（通过get_comments_by_pages_tool获取）

    ⚠️ 如果前置条件不满足:
    本工具会返回workflow_error，指引你完成正确流程

    ⚠️ AI使用指南（v0.6.6）：
    1. 调用成功后，**必须使用返回值中的user_message告知用户**
    2. user_message已包含文件路径和Top3高频词，直接输出即可

    Args:
        song_id: 歌曲ID
        max_words: 最多显示多少个词

    Returns:
        {
            "status": "success",
            "song_name": "晴天",
            "chart_type": "wordcloud",
            "chart_path": "...",
            "chart_url": "...",
            "relative_path": "visualizations/wordcloud_xxx.png",
            "user_message": "✅ 词云图已生成...",  # v0.6.6
            "top_words": [...]
        }
    """
    session = get_session()

    try:
        # v0.6.6: check song exists (use id)
        song = session.query(Song).filter_by(id=song_id).first()
        if not song:
            return workflow_error("song_not_found", "generate_wordcloud_tool")

        comments = session.query(Comment).filter_by(song_id=song_id).all()
        if not comments:
            return workflow_error("no_comments", "generate_wordcloud_tool")

        print(f"[Visualize] 生成《{song.name}》的词云图...")

        # 2. 合并所有评论文本
        text = ' '.join([c.content for c in comments])

        # 3. 使用 jieba 分词
        words = jieba.cut(text)

        # 过滤停用词和短词
        stopwords = set(['的', '了', '是', '在', '我', '有', '和', '就', '不', '人',
                        '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
                        '你', '会', '着', '没有', '看', '好', '自己', '这', '那', '吗'])

        filtered_words = [w for w in words if len(w) >= 2 and w not in stopwords]

        # 4. 统计词频
        word_counts = Counter(filtered_words)
        top_words = word_counts.most_common(max_words)

        if not top_words:
            return {"status": "error", "message": "没有有效词汇"}

        # 5. 生成词云
        wordcloud = WordCloud(
            width=1200,
            height=600,
            background_color='white',
            font_path='C:/Windows/Fonts/msyh.ttc',  # 微软雅黑
            max_words=max_words,
            relative_scaling=0.5,
            colormap='viridis'
        ).generate_from_frequencies(dict(top_words))

        # 6. 创建图表
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.imshow(wordcloud, interpolation='bilinear')
        ax.axis('off')
        ax.set_title(f'Word Cloud - {song.name}', fontsize=16, fontweight='bold', pad=20)

        plt.tight_layout()

        # 7. 保存到文件（v0.6.5 - 避免上下文窗口溢出）
        path_info = save_figure_to_file(fig, song_id, "wordcloud")

        print(f"[OK] 词云图已保存到: {path_info['relative_path']} ({len(top_words)} 个词)")

        # v0.6.6: 生成user_message引导AI告知用户
        top3_words = ", ".join([f"「{w}」({c}次)" for w, c in top_words[:3]])
        user_message = f"✅ 词云图已生成并保存到：{path_info['relative_path']}\n高频词Top 3：{top3_words}"

        return {
            "status": "success",
            "song_id": song_id,
            "song_name": song.name,
            "chart_type": "wordcloud",
            "chart_path": path_info["file_path"],
            "chart_url": path_info["file_url"],
            "relative_path": path_info["relative_path"],
            "user_message": user_message,  # v0.6.6: AI应将此消息告知用户
            "top_words": [
                {"word": word, "count": count}
                for word, count in top_words[:20]  # 只返回前20个
            ],
            "total_words_analyzed": len(filtered_words),
            "unique_words": len(word_counts)
        }

    finally:
        session.close()


def visualize_song_comparison(song_ids: list, metric: str = "sentiment") -> dict:
    """对比多首歌曲的指标（雷达图或柱状图）

    📋 前置条件（v0.6.6）:
    ✓ 歌曲必须已存在于数据库（通过search→confirm→add_song流程添加）
    ✓ 数据库中必须有评论数据（通过get_comments_by_pages_tool获取）

    ⚠️ 注意：本工具会跳过不存在的歌曲，只要有2首以上有效歌曲即可生成对比

    ⚠️ AI使用指南（v0.6.6）：
    1. 调用成功后，**必须使用返回值中的user_message告知用户**
    2. user_message已包含文件路径和对比结果，直接输出即可

    Args:
        song_ids: 歌曲ID列表（2-5首）
        metric: 对比指标 ("sentiment" | "comment_count" | "engagement")

    Returns:
        {
            "status": "success",
            "chart_type": "comparison",
            "chart_path": "...",
            "chart_url": "...",
            "relative_path": "visualizations/comparison_xxx.png",
            "user_message": "✅ 歌曲对比图已生成...",  # v0.6.6
            "songs": [...]
        }
    """
    if len(song_ids) < 2 or len(song_ids) > 5:
        return {"status": "error", "message": "请提供2-5首歌曲进行对比"}

    session = get_session()

    try:
        print(f"[Visualize] 对比 {len(song_ids)} 首歌曲...")

        # 1. 获取歌曲数据
        songs_data = []

        for song_id in song_ids:
            # v0.6.6: use Song.id for lookup
            song = session.query(Song).filter_by(id=song_id).first()
            if not song:
                continue

            comment_count = session.query(Comment).filter_by(song_id=song_id).count()

            # 计算情感分数（如果需要）
            if metric == "sentiment":
                from tools.sentiment_analysis import analyze_sentiment
                result = analyze_sentiment(song_id)

                if result.get('status') != 'error':
                    avg_sentiment = result['average_score']
                else:
                    avg_sentiment = 0.5

                songs_data.append({
                    "name": song.name,
                    "sentiment": avg_sentiment,
                    "comment_count": comment_count
                })
            else:
                songs_data.append({
                    "name": song.name,
                    "comment_count": comment_count
                })

        if not songs_data:
            return {"status": "error", "message": "没有有效歌曲数据"}

        # 2. 创建对比图
        fig, ax = plt.subplots(figsize=(12, 6))

        if metric == "sentiment":
            # 情感对比柱状图
            names = [s['name'] for s in songs_data]
            sentiments = [s['sentiment'] for s in songs_data]

            bars = ax.bar(names, sentiments, color='#3498db', alpha=0.8)
            ax.set_ylabel('Average Sentiment Score', fontsize=12, fontweight='bold')
            ax.set_title('Song Sentiment Comparison', fontsize=14, fontweight='bold')
            ax.set_ylim(0, 1)
            ax.axhline(y=0.5, color='r', linestyle='--', alpha=0.5, label='Neutral (0.5)')
            ax.legend()

            # 添加数值标签
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.3f}',
                       ha='center', va='bottom', fontsize=10)

        else:  # comment_count
            names = [s['name'] for s in songs_data]
            counts = [s['comment_count'] for s in songs_data]

            bars = ax.bar(names, counts, color='#e74c3c', alpha=0.8)
            ax.set_ylabel('Comment Count', fontsize=12, fontweight='bold')
            ax.set_title('Song Comment Count Comparison', fontsize=14, fontweight='bold')

            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(height)}',
                       ha='center', va='bottom', fontsize=10)

        ax.grid(axis='y', alpha=0.3)
        plt.xticks(rotation=15, ha='right')
        plt.tight_layout()

        # 3. 保存到文件（v0.6.5 - 避免上下文窗口溢出）
        # 对比图使用第一个song_id作为文件名
        path_info = save_figure_to_file(fig, song_ids[0], f"comparison_{metric}")

        print(f"[OK] 对比图表已保存到: {path_info['relative_path']}")

        # v0.6.6: 生成user_message引导AI告知用户
        song_names = "、".join([f"《{s['name']}》" for s in songs_data])
        if metric == "sentiment":
            best_song = max(songs_data, key=lambda x: x['sentiment'])
            user_message = f"✅ 歌曲情感对比图已生成并保存到：{path_info['relative_path']}\n对比歌曲：{song_names}\n结果：《{best_song['name']}》情感评分最高({best_song['sentiment']:.3f})"
        else:
            best_song = max(songs_data, key=lambda x: x['comment_count'])
            user_message = f"✅ 歌曲评论数对比图已生成并保存到：{path_info['relative_path']}\n对比歌曲：{song_names}\n结果：《{best_song['name']}》评论数最多({best_song['comment_count']}条)"

        return {
            "status": "success",
            "chart_type": "song_comparison",
            "chart_path": path_info["file_path"],
            "chart_url": path_info["file_url"],
            "relative_path": path_info["relative_path"],
            "user_message": user_message,  # v0.6.6: AI应将此消息告知用户
            "metric": metric,
            "songs": songs_data
        }

    finally:
        session.close()
