"""
Workflow错误处理模块 (v0.6.6)

统一管理所有工具的workflow相关错误，确保AI能理解正确的调用顺序。
"""

from typing import Dict, Any


def workflow_error(error_type: str, current_tool: str) -> Dict[str, Any]:
    """
    生成标准化的workflow错误响应

    Args:
        error_type: 错误类型 ('song_not_found', 'no_comments', 'invalid_workflow')
        current_tool: 当前调用的工具名称

    Returns:
        标准化的错误响应字典
    """

    workflows = {
        "song_not_found": {
            "message": "⚠️ 歌曲不存在于数据库",
            "required_workflow": [
                "Step 1: search_songs_tool(keyword='歌名')",
                "Step 2: confirm_song_selection_tool(session_id='...', choice_number=N)",
                "Step 3: add_song_to_database(song_id='...')",
                "Alt: add_song_to_database(song_id='...') if you already know the ID",
                f"Step 4: 重试 {current_tool}"
            ],
            "why": f"{current_tool}需要歌曲已存在于数据库中",
            "example": """
示例流程:
用户: "分析晴天的评论"
AI: search_songs_tool(keyword="晴天")  # 搜索歌曲
    → confirm_song_selection_tool(choice_number=1)  # 确认选择
    → add_song_to_database(song_id="185811")  # 添加到数据库
    → {current_tool}(song_id="185811")  # 然后才能调用分析工具
            """.format(current_tool=current_tool),
            "critical": True
        },

        "no_comments": {
            "message": "⚠️ 数据库中没有评论数据",
            "required_workflow": [
                "Option A (推荐): get_comments_by_pages_tool(song_id='...', data_source='api', pages=[1,2,3])",
                "Option B (大量数据): crawl_all_comments_for_song(song_id='...') - ⚠️已弃用，耗时长",
                f"然后: 重试 {current_tool}"
            ],
            "why": f"{current_tool}需要至少有一些评论数据才能分析",
            "tip": "推荐先用get_comments_metadata_tool检查数据量，再决定采样策略",
            "critical": True
        },

        "invalid_workflow": {
            "message": "⚠️ 工具调用顺序不正确",
            "required_workflow": [
                "请查看工具的Docstring中的'📋 前置条件'章节",
                "确保满足所有前置条件后再调用"
            ],
            "why": "某些工具之间存在依赖关系，需要按正确顺序调用",
            "critical": True
        }
    }

    if error_type not in workflows:
        # 兜底错误
        return {
            "status": "workflow_error",
            "error_type": "unknown",
            "message": f"未知的workflow错误类型: {error_type}",
            "current_tool": current_tool
        }

    error_info = workflows[error_type]

    return {
        "status": "workflow_error",
        "error_type": error_type,
        "current_tool": current_tool,
        **error_info
    }


def success_with_next_step(status_data: Dict[str, Any], next_step_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    成功响应中添加next_step指引

    Args:
        status_data: 原始成功响应数据
        next_step_info: 下一步建议信息

    Returns:
        增强后的响应
    """
    return {
        **status_data,
        "next_step": next_step_info
    }
