# 贡献指南

感谢你考虑为 NetEase Music MCP Server 做出贡献！

## 🎯 我们需要什么样的贡献

### 🐛 Bug 报告
发现了问题？请告诉我们！

### ✨ 功能建议
有好点子？我们很想听！

### 📝 文档改进
发现文档有误或不清楚？帮我们改进！

### 💻 代码贡献
想要添加功能或修复 bug？太好了！

### 🎨 设计贡献
会设计？帮我们做个 Logo！

---

## 🚀 快速开始

### 1. Fork 项目

点击 GitHub 页面右上角的 "Fork" 按钮。

### 2. 克隆你的 Fork

```bash
git clone https://github.com/your-username/netease-cloud-music-mcp.git
cd netease-cloud-music-mcp
```

### 3. 创建分支

```bash
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix
```

**分支命名规范**：
- `feature/xxx` - 新功能
- `fix/xxx` - Bug 修复
- `docs/xxx` - 文档改进
- `refactor/xxx` - 代码重构

### 4. 安装开发依赖

```bash
pip install -r requirements.txt
```

### 5. 进行你的修改

遵循下面的代码规范和提交规范。

### 6. 测试你的修改

```bash
# 运行 MCP server
python mcp_server/server.py

# 在 Claude Desktop 中测试功能
```

### 7. 提交你的修改

```bash
git add .
git commit -m "feat: 添加 XXX 功能"
git push origin feature/your-feature-name
```

### 8. 创建 Pull Request

1. 前往你的 Fork 页面
2. 点击 "New Pull Request"
3. 选择你的分支
4. 填写 PR 描述（使用下面的模板）

---

## 📋 Pull Request 模板

```markdown
## 描述
简要描述这个 PR 做了什么。

## 改动类型
- [ ] Bug 修复
- [ ] 新功能
- [ ] 文档改进
- [ ] 代码重构
- [ ] 性能优化
- [ ] 其他（请说明）

## 相关 Issue
关闭 #xxx

## 测试
描述你如何测试这些改动：
- [ ] 在 Claude Desktop 中测试
- [ ] 单元测试通过
- [ ] 手动测试步骤：...

## 截图（如果适用）
贴上改动的截图。

## Checklist
- [ ] 代码遵循项目风格
- [ ] 已更新相关文档
- [ ] 已添加测试
- [ ] 所有测试通过
```

---

## 📝 提交信息规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

### 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型

| Type | 描述 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: 添加歌单分析功能` |
| `fix` | Bug 修复 | `fix: 修复采样算法边界问题` |
| `docs` | 文档更新 | `docs: 更新 README 安装说明` |
| `style` | 代码格式 | `style: 格式化代码` |
| `refactor` | 代码重构 | `refactor: 重构采样模块` |
| `perf` | 性能优化 | `perf: 优化数据库查询` |
| `test` | 测试相关 | `test: 添加采样测试` |
| `chore` | 构建/工具 | `chore: 更新依赖版本` |

### 示例

```bash
# 好的提交信息 ✅
git commit -m "feat: 添加 QQ 音乐支持"
git commit -m "fix: 修复情感分析 NoneType 错误"
git commit -m "docs: 更新 FAQ 问题列表"

# 不好的提交信息 ❌
git commit -m "update"
git commit -m "fix bug"
git commit -m "改了一些东西"
```

---

## 💻 代码规范

### Python 代码风格

遵循 [PEP 8](https://peps.python.org/pep-0008/) 规范。

**关键规则**：

```python
# 1. 缩进使用 4 个空格
def my_function():
    return True

# 2. 行长度不超过 100 字符

# 3. 导入顺序
import os  # 标准库
import sys

from fastmcp import FastMCP  # 第三方库

from mcp_server.tools import sampling  # 本地模块

# 4. 类命名：CapWords
class CommentAnalyzer:
    pass

# 5. 函数命名：lowercase_with_underscores
def analyze_comments():
    pass

# 6. 常量命名：UPPER_CASE_WITH_UNDERSCORES
MAX_COMMENTS = 1000

# 7. 类型注解（推荐）
def get_song_id(name: str) -> str:
    return "12345"

# 8. 文档字符串
def sample_comments(song_id: str, level: str) -> dict:
    """
    采样评论数据

    Args:
        song_id: 歌曲ID
        level: 采样级别 (quick/standard/deep)

    Returns:
        包含采样结果的字典
    """
    pass
```

### 代码审查要点

在提交 PR 前，请自查：

- [ ] 代码可读性良好（清晰的变量名、适当的注释）
- [ ] 没有硬编码的魔法数字（使用常量）
- [ ] 错误处理合理（try-except）
- [ ] 没有调试用的 print 语句
- [ ] 遵循项目的文件组织结构

---

## 🧪 测试规范

### 手动测试

在 Claude Desktop 中测试你的改动：

```
1. 搜索歌曲
2. 采样评论
3. 查看分析结果
4. 检查边界情况（冷门歌、新歌等）
```

### 自动化测试（计划中）

```bash
# 运行测试
pytest tests/

# 查看覆盖率
pytest --cov=mcp_server tests/
```

---

## 📚 文档规范

### 更新文档时机

- ✅ 添加新功能 → 更新 README 和相关文档
- ✅ 修改 API → 更新 API 文档
- ✅ 修复重要 bug → 更新 FAQ 或 troubleshooting
- ✅ 更改配置 → 更新安装指南

### 文档写作规范

```markdown
# 1. 使用清晰的标题层级
## 二级标题
### 三级标题

# 2. 代码块注明语言
```bash
pip install requirements.txt
```

```python
def hello():
    print("Hello")
```

# 3. 使用表格组织信息
| 列1 | 列2 |
|-----|-----|
| 数据 | 数据 |

# 4. 使用引用块强调
> **重要**：这是一个重要提示

# 5. 使用列表
- 无序列表项
- 另一项

1. 有序列表项
2. 另一项
```

---

## 🎯 不同类型贡献的指南

### 🐛 报告 Bug

创建 Issue 时，请包含：

```markdown
**描述问题**
简要描述 bug。

**复现步骤**
1. 执行操作 A
2. 执行操作 B
3. 看到错误

**预期行为**
描述你期望发生什么。

**实际行为**
描述实际发生了什么。

**环境信息**
- OS: [如 Windows 11, macOS 14.0]
- Python 版本: [如 3.10.5]
- Claude Desktop 版本: [如 0.7.1]

**错误日志（如果有）**
```
粘贴错误信息
```

**截图（如果有）**
贴上截图帮助说明问题。
```

### ✨ 提出功能建议

创建 Issue 时，请包含：

```markdown
**功能描述**
清晰描述你想要的功能。

**使用场景**
为什么需要这个功能？什么场景下会用到？

**建议的实现方式**
如果有想法，描述一下如何实现。

**替代方案**
有没有其他可行的方案？

**额外信息**
其他相关信息或截图。
```

### 💻 贡献代码

#### 适合新手的 Issue

寻找标签为 `good first issue` 的 Issue，这些适合初次贡献者。

#### 领取 Issue

在 Issue 下评论表示你想处理这个问题，避免重复工作。

#### 大型功能

如果你想添加大型功能，请先创建 Issue 讨论，确保方向正确。

---

## 🤝 Code Review 流程

### 提交 PR 后

1. **自动检查**（计划中）
   - 代码风格检查
   - 测试通过

2. **人工审查**
   - 维护者会审查你的代码
   - 可能会提出修改建议

3. **修改和讨论**
   - 根据反馈修改代码
   - 在 PR 中讨论技术方案

4. **合并**
   - 审查通过后，维护者会合并 PR
   - 你的贡献会出现在项目中！

### 审查标准

Code Review 关注：

- ✅ 功能是否正确
- ✅ 代码质量和可读性
- ✅ 是否有测试
- ✅ 文档是否更新
- ✅ 是否符合项目架构

---

## 📜 行为准则

### 我们的承诺

为了营造一个开放和友好的环境，我们承诺：

- ✅ 尊重不同的观点和经验
- ✅ 优雅地接受建设性批评
- ✅ 关注对社区最有利的事情
- ✅ 对其他社区成员表示同理心

### 不可接受的行为

- ❌ 使用性化的语言或图像
- ❌ 人身攻击或政治攻击
- ❌ 公开或私下骚扰
- ❌ 未经许可发布他人私人信息

---

## 🏆 贡献者

感谢所有贡献者！

<!-- ALL-CONTRIBUTORS-LIST:START -->
<!-- 这里会自动生成贡献者列表 -->
<!-- ALL-CONTRIBUTORS-LIST:END -->

---

## ❓ 还有问题？

- 查看 [FAQ](docs/faq.md)
- 在 [Discussions](https://github.com/1mht/netease-cloud-music-mcp/discussions) 提问
- 创建 [Issue](https://github.com/1mht/netease-cloud-music-mcp/issues)

---

**再次感谢你的贡献！🎉**
