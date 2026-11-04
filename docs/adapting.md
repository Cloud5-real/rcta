# 接入新的多智能体系统

RCTA 依赖角色名判断"谁在规划、谁在执行、谁在验证"。现有规则覆盖 Who&When 数据中的 OpenHands 风格（DiagnostAgent / ActionAgent / JudgeAgent）、Magentic-One 和 AutoGen 风格（`*_Expert`）的命名。新系统用不同命名时，按下面顺序检查。

## 1. 角色名映射（必改）

文件：`rcta/preprocess/step_enricher.py` 中 "Agent normalization" 一节。

| 集合 | 作用 |
|---|---|
| `PLANNERS` | 规划者。归因到规划者时有额外校验 |
| `EXECUTORS` | 执行者。用于委派匹配和忠实实现线索 |
| `VERIFIERS` | 验证者。其步骤标为 `judge`，用于提取 PASS/FAIL 信号 |
| `TERMINAL_NAMES` | 工具/环境返回，标为 `observation` |
| `HUMAN_NAMES` | 用户输入 |
| `MAGENTIC_ONE_NAMES` | 轨迹中出现任一名称时，根因阶段额外启用基于关键词的候选召回 |

未登记的名称会被归为 `unknown`。名称以 `Expert` 结尾的除外：含 verif/validat 的归为验证者，其余归为执行者。`unknown` 角色不会让程序出错，但会让分段边界、委派匹配和规划者校验失效。

最省事的做法是在转换数据时把工具返回统一命名为 `Computer_terminal`，委派写成 `规划者 (-> 接收者)`。

## 2. 验证信号与退出码（按需）

同一文件中的 `RE_VERIFIER_PASS` / `RE_VERIFIER_FAIL` 识别 `VERDICT: PASS`、`tests passed` 等写法，`RE_EXIT_CODE` 识别 `exit_code: 0` 等写法。新系统的验证者或终端输出格式不同时，在这里补正则；它们影响分段边界和提供给模型的验证信号摘要。

## 3. 提示词中的系统说明（建议改）

`rcta/prompts/root_cause.md` 第 0 节用表格介绍了 OpenHands / Magentic-One / TravelPlanner 的角色分工，全文还有约 20 处以 DiagnostAgent / ActionAgent / JudgeAgent 举例。新系统结构不同时，在第 0 节补充它的角色说明即可；示例可以保留。`local_summary.md` 只有一处示例提到 ActionAgent，不必改。

修改提示词后，请同步更新 `rcta/config.py` 的 `PROMPT_VERSIONS`，并使用新的输出目录。

## 4. 检查

```bash
python -m rcta -i my_inputs -o outputs/check --dry-run --verbose
```

dry-run 会显示每条轨迹的步数和分段情况。如果分段数异常（例如长轨迹只切成按长度截断的段），通常说明角色名没有被识别。也可以直接检查角色识别结果：

```bash
python -c "import json,sys; from rcta.preprocess.step_enricher import enrich_steps; \
[print(s.step_id, s.agent_name_raw, s.agent_normalized, s.action_type) for s in enrich_steps(json.load(open(sys.argv[1]))['history'])]" my_inputs/x.json
```
