# 常见问题 (FAQ)

## 基础问题

### Q1: 采样600条能代表200万条吗？

**A**: 不能完全代表，但已经足够发现主要模式。原因：

- ✅ 使用**分层采样**（热评+最新+历史），不是简单随机
- ✅ 覆盖 **20+年时间跨度**，捕捉历史演变
- ✅ **透明告知**覆盖率和局限性，AI 知道边界
- ✅ 对于发现主要模式（如情感倾向、核心话题）已经足够
- ❌ 无法覆盖所有小众观点和边缘内容

**类比**：就像民意调查不需要问所有人，1000个样本足以反映大致趋势（置信区间内）。

---

### Q2: 为什么分析时间需要60秒？

**A**: 因为需要多次调用网易云 API：

1. **API 请求频率限制**：每次请求需要间隔 0.5-1.5 秒
2. **多次请求**：
   - 热评：1次
   - 最新评论：offset 翻页 8-15次
   - 历史评论：cursor 跳转 8-10次（每年1次）
3. **standard 级别**约需 15-30 个请求

**优化**：
- quick 级别（200条）约 30秒
- deep 级别（1000条）约 100秒

---

### Q3: 支持其他音乐平台吗？

**A**: 目前只支持网易云音乐。

**未来计划**：
- [ ] QQ 音乐
- [ ] Spotify
- [ ] Apple Music

如果你对某个平台特别感兴趣，欢迎在 [Issues](https://github.com/1mht/netease-cloud-music-mcp/issues) 留言！

---

### Q4: 数据存储在哪里？安全吗？

**A**:
- **存储位置**：本地 SQLite 数据库，路径 `data/music.db`
- **隐私**：所有数据存储在你的本地机器，不会上传到任何服务器
- **安全**：评论数据来自公开的网易云音乐 API

---

### Q5: 会不会被网易云封IP？

**A**: 理论上安全，但建议合理使用：

✅ **安全措施**：
- 使用了请求间隔控制（0.5-1.5秒）
- 模拟正常用户行为
- 不做高频率批量请求

⚠️ **建议**：
- 不要短时间内分析几十首歌
- 不要修改代码降低请求间隔
- 仅用于个人学习研究

---

## 安装与配置

### Q6: 安装后找不到 claude_desktop_config.json 文件？

**A**: 配置文件位置取决于操作系统：

**Windows**:
```
%APPDATA%\Claude\claude_desktop_config.json
```
完整路径通常是：`C:\Users\你的用户名\AppData\Roaming\Claude\claude_desktop_config.json`

**macOS**:
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Linux**:
```
~/.config/Claude/claude_desktop_config.json
```

**如果文件不存在**：
1. 确认已安装 Claude Desktop
2. 手动创建该文件
3. 添加配置内容（参考 README）

---

### Q7: 配置后 Claude Desktop 无法识别工具？

**A**: 排查步骤：

1. **检查配置文件语法**：
   ```bash
   # 使用在线工具验证 JSON 格式
   # https://jsonlint.com/
   ```

2. **检查路径是否正确**：
   - 必须是**绝对路径**，不能是相对路径
   - Windows 用户注意反斜杠：`D:\\path\\to\\server.py`

3. **检查 Python 命令**：
   ```bash
   # 测试 Python 是否可用
   python --version
   # 或
   python3 --version
   ```

4. **查看 Claude Desktop 日志**：
   - Windows: `%APPDATA%\Claude\logs\`
   - macOS: `~/Library/Logs/Claude/`

5. **重启 Claude Desktop**：
   - 完全退出（包括系统托盘）
   - 重新打开

---

### Q8: 提示缺少 Python 依赖？

**A**: 确保已安装所有依赖：

```bash
cd netease-cloud-music-mcp
pip install -r requirements.txt
```

**如果仍然报错**：
```bash
# 更新 pip
pip install --upgrade pip

# 重新安装
pip install -r requirements.txt --force-reinstall
```

---

## 使用问题

### Q9: 如何分析特定年份的评论？

**A**: 使用 Layer 3 工具：

```
你：帮我看看《晴天》2020年的评论

Claude 会：
1. 先调用 Layer 0/1/2 了解整体情况
2. 然后调用 get_original_comments_tool，筛选条件 year=2020
```

---

### Q10: 分析结果不准确怎么办？

**A**: 可能的原因和解决方案：

**原因1：采样不足**
- 解决：使用 `deep` 级别采样（1000条）

**原因2：算法误判**
- AI 会自动检测（通过对比样本）
- 查看报告中的"局限说明"部分

**原因3：歌曲评论太少**
- 冷门歌曲（<100条评论）分析可靠性较低
- 系统会在报告中标注

---

### Q11: 能否对比两首歌的评论区？

**A**: 可以！直接对话即可：

```
你：对比《晴天》和《七里香》的评论区

Claude 会：
1. 分别分析两首歌
2. 提取关键差异
3. 生成对比报告
```

---

### Q12: 能否分析歌单或专辑？

**A**: 当前版本暂不支持，但在计划中：

**Roadmap**：
- [ ] v0.9.0: 歌曲对比分析优化
- [ ] v1.0.0: 歌单/专辑整体分析
- [ ] v1.1.0: 艺术家评论画像

关注 [Releases](https://github.com/1mht/netease-cloud-music-mcp/releases) 了解最新进展。

---

## 技术问题

### Q13: 六维度分析的置信度是什么意思？

**A**: 置信度表示该维度分析结果的可靠程度：

| 置信度 | 含义 | 示例 |
|-------|------|------|
| **0.9** | 非常可靠 | 结构维度（评论长度统计） |
| **0.7-0.85** | 较可靠 | 社交维度（点赞分布） |
| **0.5-0.7** | 需验证 | 情感维度（可能误判） |

**使用建议**：
- 置信度 ≥0.8：可直接使用
- 置信度 0.6-0.8：结合样本验证
- 置信度 <0.6：仅作参考

---

### Q14: 为什么情感分析置信度这么低？

**A**: 因为 SnowNLP 对音乐评论有系统性偏差：

**问题**：训练数据是商品评论，不适合音乐评论的"感伤式金句"

**示例**：
```
评论："每次听都想起她，眼泪流下来"
算法判断：负面（0.25）
实际含义：深度共鸣（正面）
```

**解决**：
- 系统自动提供"高赞低分样本"
- AI 会阅读原文并修正判断
- 最终报告会说明修正过程

---

### Q15: cursor 参数是什么？如何发现的？

**A**: cursor 是网易云 API 的一个参数，可以跳转到任意历史时间点。

**发现过程**：
1. 发现 offset 参数有限制（~1100条）
2. 通过浏览器抓包分析 API 请求
3. 发现 weapi 接口的 cursor 参数
4. 测试验证：cursor 值为时间戳（毫秒）
5. 实现跨年份时间跳转采样

**技术意义**：
- 突破了 offset 限制
- 可以访问任意历史时间的评论
- 实现了真正的时间跨度采样

---

## 贡献与开发

### Q16: 如何参与贡献？

**A**: 欢迎！请查看 [CONTRIBUTING.md](../CONTRIBUTING.md)

**可以贡献的内容**：
- 🐛 报告 bug
- ✨ 提出新功能建议
- 📝 改进文档
- 💻 提交代码（修复/功能）
- 🎨 设计 Logo/UI

---

### Q17: 如何本地开发和测试？

**A**:

```bash
# 1. Fork 并克隆
git clone https://github.com/your-username/netease-cloud-music-mcp.git
cd netease-cloud-music-mcp

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行 server
python mcp_server/server.py

# 4. 配置 Claude Desktop 指向本地路径

# 5. 测试你的改动
```

---

## 其他问题

### Q18: 项目的 License 是什么？

**A**: MIT License - 可以自由使用、修改、分发，但需保留原作者信息。

详见 [LICENSE](../LICENSE) 文件。

---

### Q19: 有没有演示视频？

**A**:
- [ ] YouTube 演示（计划中）
- [ ] B站演示（计划中）

在此之前，可以查看 README 中的文字演示。

---

### Q20: 如何联系作者？

**A**:
- **GitHub Issues**: [提问题](https://github.com/1mht/netease-cloud-music-mcp/issues)
- **GitHub Discussions**: [讨论](https://github.com/1mht/netease-cloud-music-mcp/discussions)
- **项目主页**: https://github.com/1mht/netease-cloud-music-mcp

---

## 找不到答案？

如果你的问题不在此列表中：

1. 搜索 [GitHub Issues](https://github.com/1mht/netease-cloud-music-mcp/issues)
2. 查看 [故障排除文档](troubleshooting.md)
3. 提交新的 Issue

---

**最后更新**：2024-01-07
