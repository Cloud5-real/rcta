# 输入与输出格式

## 输入

每个 JSON 文件是一条轨迹，示例见 `examples/demo_trajectory.json`：

```json
{
  "question_ID": "my_task__001",
  "history": [
    {"step": 0, "role": "user", "name": "human", "content": "任务要求"},
    {"step": 1, "role": "assistant", "name": "DiagnostAgent (-> ActionAgent)", "content": "委派指令"},
    {"step": 2, "role": "assistant", "name": "ActionAgent", "content": "执行记录"},
    {"step": 3, "role": "user", "name": "Computer_terminal", "content": "工具返回"}
  ]
}
```

- `history` 按执行顺序排列；`step` 是唯一整数编号，算法保留原编号，不重新编号。
- 委派写成 `规划者 (-> 接收者)`，接收者名称用于委派匹配。
- 工具返回记成 `Computer_terminal`，即可沿用现有的工具观察识别规则。
- `question_ID` 中 `__` 之前的部分会作为 benchmark 名传给模型。
- 原始任务要求、工具结果和判断依据都应写在 `history` 里。

**模型只看到 `question_ID` 和 `history`。** 人工标签（`mistake_*`）、参考答案、`question`、`metadata`、评测输出等字段不会进入提示词，这一点由测试 `test_external_labels_do_not_enter_prompts` 保证。若文件带 `is_correct: true`，该样本会被跳过。

## 输出

输出文件与输入同名，内容是原 JSON 的完整拷贝，顶层另外加入四个字段：

| 字段 | 内容 |
|---|---|
| `llm_mistake_agent` | 根因负责角色（轨迹中的原始名称） |
| `llm_mistake_step` | 根因步编号（整数）；拒答或无效时为 `-1` |
| `llm_mistake_reason` | 根因说明 |
| `llm_analysis_summary` | 结构化分析，见下表 |

`llm_mistake_*` 与 Who&When 标注格式的 `mistake_agent / mistake_step / mistake_reason` 一一对应，可直接比较。

`llm_analysis_summary` 的主要内容：

| 键 | 内容 |
|---|---|
| `meta` | 模型、schema 版本、步数、阶段数 |
| `phases` / `cross_phase_conflicts` | 阶段划分与跨阶段冲突 |
| `root_cause` | 根因：角色、步、主因/次因分类、证据步、原文引用、`failure_chain`、反事实、置信度、`abstain`、`needs_human_review`；回溯到委派时附 `delegation_trace` |
| `failure_manifestation` | 失败表现位置，字段同上（不含链），仅供审阅 |
| `category_legend` | 本条用到的分类代码说明 |
| `step_ref_index` | 被引用步的索引，方便定位原文 |
| `ai_summary_markdown` / `root_cause_markdown` | 供人阅读的渲染文本 |

## 输出目录中的其他文件

| 路径 | 何时出现 | 内容 |
|---|---|---|
| `<name>.debug.json` | 加 `--debug-sidecar` | 局部摘要、阶段聚合、根因阶段中间结果和思维链 |
| `run_snapshot/` | 首次正式运行 | 三份提示词原文、模型、接口地址、配置、输入文件清单（不含密钥） |
| `_errors/<name>.json` | 样本处理抛出异常 | 错误类型和信息；重跑成功后自动删除 |

运行日志写到当前目录的 `logs/`，可用 `RCTA_LOG_DIR` 修改。
