# Step 32 录屏 Runbook

## 交付目标

录制一个 3 分 30 秒标准版；必要时从同一素材裁出 90 秒版。录屏只使用公开仓库、模拟数据和离线 Provider。

## 时间轴

| 时间 | 画面 | 讲解重点 |
|---|---|---|
| 00:00-00:25 | Deck 第 1 页 | 项目定位、模拟数据、155 Tests |
| 00:25-01:05 | Deck 第 2 页 | Context、Planner、Tools、Evidence、Verifier、Trace |
| 01:05-01:45 | `/demo` 或 Deck 第 3 页 | nginx 复合 Query 与 3 个 Tool |
| 01:45-02:20 | `/evaluation` 或 Deck 第 4 页 | Baseline、61.76% 到 100%、冻结集边界 |
| 02:20-03:00 | Evolution 文档或终端摘要 | 9 个失败、3 个候选、9 个修复、0 回归、不可自激活 |
| 03:00-03:30 | Deck 第 5 页与 CI | 工程证据、公开边界、下一步 |

字幕文件：[Software-Agent-3m30s.srt](recording/Software-Agent-3m30s.srt)

## 演示前准备

```bash
uvicorn app.api.server:app --host 127.0.0.1 --port 8000
```

另一个终端：

```bash
python examples/interview_demo.py --skip-evaluation
python examples/interview_rehearsal.py --mode standard
python evaluation/evolution_eval.py
```

浏览器预先打开：

- `http://127.0.0.1:8000/demo`
- `http://127.0.0.1:8000/evaluation`
- GitHub Actions Run `33363220127`
- `docs/Software-Agent-Interview-Deck.pptx`

## 录制顺序

1. 先完成一次不录制的标准版演练，目标 190-230 秒。
2. 清空终端历史，只保留将要执行的三条命令。
3. 关闭通知、聊天窗口、邮件、密码管理器和无关浏览器标签。
4. 从 Deck 第 1 页开始录制，切换页面时保持口播连续。
5. Demo 只输入固定 nginx Query，不临场尝试未知问题。
6. Evolution 页只展示汇总字段，不滚动完整 Candidate JSON。
7. 最后一页停留 3 秒，让仓库地址和边界信息可读。

## 画面与隐私验收

- 建议画布为 1920×1080，浏览器缩放保持 100%。
- 不显示 `.env`、API Key、数据库连接串、本机用户名或绝对路径。
- 不显示真实华为文档、聊天记录、邮箱、工号或内部系统页面。
- 不把 193/193 表述为开放领域 100%。
- 不把离线 Proxy 表述为 GPT、Claude 或 Gemini 实测。
- 不把 100/100 与 40/40 表述为生产容量或 SLA。
- 明确真实 Provider A/B 尚未执行。

## 失败降级

| 问题 | 处理 |
|---|---|
| FastAPI 启动失败 | 全程使用 Deck 第 3、4 页截图 |
| 浏览器页面异常 | 使用 `examples/interview_demo.py --skip-evaluation` |
| Evolution 输出过长 | 使用能力矩阵中的固定实验摘要 |
| GitHub 网络异常 | 使用 Deck 第 5 页的 Run ID 与 Job 结果 |
| 口播超时 | 删除 PostgreSQL 细节，保留定位、复合 Query、自进化边界 |

## 导出检查

- 标准版文件名：`Software-Agent-Demo-3m30s.mp4`
- 精简版文件名：`Software-Agent-Demo-90s.mp4`
- 视频从第 1 秒起有有效画面和声音，末尾无多余桌面停留。
- 人声清楚，字幕不遮挡页面关键数字。
- 重新完整播放一遍，确认无通知弹窗、凭据、路径或内部数据。
- GitHub README 只在视频实际生成并完成隐私复核后再添加视频链接。
