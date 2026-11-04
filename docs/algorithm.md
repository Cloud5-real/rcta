# 算法流程

一条轨迹的处理入口是 `rcta/run.py::process_one()`。整体分四个阶段，后三个阶段各调用一次模型，每次调用的输出都会经过校验，不合格时带着错误清单重试一次。

```text
history ──► ① 预处理与分段 ──► ② 局部摘要(每段 1 次) ──► ③ 阶段聚合(1 次) ──► ④ 根因判定(1 次) ──► 输出
             确定性，无模型        抽取型，关 thinking        开 thinking            开 thinking
```

## 各阶段与代码、提示词对照

| 阶段 | 做什么 | 代码 | 提示词 | 校验 |
|---|---|---|---|---|
| ① 预处理 | 读取 `history`，识别角色（planner / executor / verifier / terminal / human）、动作类型、验证信号、退出码 | `preprocess/loader.py`、`preprocess/step_enricher.py` | 无 | 无 |
| ① 分段 | 按语义边界（finish、PASS↔FAIL 翻转、委派时角色切换）和长度上限切段，每段附带上一段末尾 5 步作上下文 | `preprocess/segmenter.py` | 无 | 超长段运行时二分 |
| ② 局部摘要 | 每段提炼目标、关键事件、候选失败步、验证结论 | `analyze/local_summarizer.py` | `prompts/local_summary.md` | `validate_local_summary`：step_id 不得越出本段 |
| ③ 阶段聚合 | 把局部摘要合并为 3–8 个阶段，标出失败信号和跨段冲突 | `analyze/global_reducer.py::aggregate_phases` | `prompts/phase_aggregate.md` | `validate_phase_summary`；解析失败时每段退化为一个阶段 |
| ④ 根因判定 | 召回候选步原文，补全上游委派，判断根因与失败表现 | `analyze/global_reducer.py::diagnose_root_cause` | `prompts/root_cause.md` | `validate_root_cause`，见下文 |

## 根因判定阶段的关键设计

阅读顺序：`_collect_candidate_step_hints()` → `_augment_with_preceding_delegates()` → `_build_delegate_linkage_hints()` → `diagnose_root_cause()`。

1. **候选原文召回。** 从局部摘要的 `candidate_failures`、阶段的 `failure_signals` 和 `supporting_step_ids`（前 3 个）收集候选步，最多 80 个，回拉完整原文给模型。Magentic-One 风格轨迹另外按正文关键词召回执行者事件、规划者决策和终止前上下文，并把"报错但之后恢复"的步标为噪声。
2. **目标匹配的上游委派补全。** 对每个候选步，补上它之前最近一次**委派给同一角色**的委派步（如执行步只匹配 `X (-> ActionAgent)`，不匹配 `X (-> JudgeAgent)`）。这样模型能看到缺陷是否在规划者的指令里就已存在。
3. **忠实实现线索。** 如果执行步明确说"按计划/按委派"，或与委派步共享足够多的代码标识符（共享 ≥3 个、执行步自身 ≥5 个、重叠率 ≥34%），就生成一条提示，交给模型比较指令与执行。线索只是提示，不强制结论。
4. **双层定位。** 模型同时输出 `root_cause_event`（缺陷被引入处，用于顶层 `llm_mistake_*` 和准确率统计）与 `failure_manifestation_event`（错误显露处，仅供审阅），以及包含 root_cause / propagation / manifestation / terminal 角色的 `failure_chain`。

## 根因输出的校验（`analyze/validator.py`）

- 根因步必须是轨迹中真实存在的编号，角色名必须是轨迹中出现过的原始名称。
- `primary_category` 必须属于 `config.CATEGORY_META` 的 15 个分类之一，次因不得重复。
- `failure_chain` 必须包含 root_cause、manifestation、terminal 三类节点。
- 归因到规划者时，根因步必须确实是规划者的步，且主因不得是执行/验证/环境类（D*/E*/X*）。
- 声称"执行者忠实实现了有缺陷的委派"时，`delegation_trace.quote` 必须能在该委派步原文中找到（归一化子串或 ≥80% 词重叠），根因步必须等于该委派步，角色名必须是委派态（含 ` (-> `），主因必须是 C1 或 A2。

重试后仍不合格时，`coerce_root_cause` 做温和修正并标记 `needs_human_review`；关键字段缺失则 `abstain=true`，顶层 `llm_mistake_step=-1`。

校验只保证字段合法、引文可在原文中找到，不证明因果判断正确。反事实分析由模型推理完成，不实际修复后重跑。

## 主要可调参数（`rcta/config.py`）

| 参数 | 默认值 | 说明 |
|---|---|---|
| `SEG_TARGET_CHARS` / `SEG_MAX_CHARS` | 24000 / 32000 | 分段目标长度与硬上限（字符） |
| `SEG_MIN_STEPS` / `SEG_MAX_STEPS` / `SEG_OVERLAP_STEPS` | 8 / 80 / 5 | 分段步数限制与重叠步数 |
| `LLM_THINKING_LOCAL` / `_PHASE` / `_ROOT` | False / True / True | 各阶段是否开启 thinking |
| `LLM_REASONING_EFFORT_PHASE` / `_ROOT` | high / high | 推理强度 |
| `LLM_MAX_TOKENS_LOCAL` / `_PHASE` / `_ROOT` | 4000 / 6000 / 8000 | 输出长度上限，可用同名环境变量覆盖 |
| `PROMPT_VERSIONS` | local 1.2 / phase 1.0 / root 2.0 | 修改提示词时同步更新，会写入输出和运行快照 |

修改任何会影响结果的参数或提示词后，请使用新的输出目录，运行快照会阻止新旧结果混在同一目录。
