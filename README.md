# RCTA 根因定位算法代码

RCTA（Root-Cause Trajectory Attribution）对失败智能体轨迹做事后根因定位，输出负责角色、根因步骤、证据及解释链。本包从现有实现中独立提取，保留核心算法与三阶段提示词，提供可直接运行的入口。

## 先运行一个不调用模型的示例

需要 Python 3.10 或更新版本。在解压后的本目录执行：

```bash
python -m rcta --input-dir examples --output-dir outputs/dry-run --dry-run
```

这会读取合成示例并检查轨迹分段，不调用接口，也不会生成模型归因结果。依赖未安装时也能进行该检查。

## 安装与正式运行

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .

export LLM_API_KEY='YOUR_API_KEY'
export LLM_BASE_URL='https://api.deepseek.com'
export LLM_MODEL='deepseek-v4-pro'

python -m rcta --input-dir examples --output-dir outputs/demo --debug-sidecar
```

Windows 激活虚拟环境使用 `.venv\Scripts\Activate.ps1`；PowerShell 环境变量使用 `$env:LLM_API_KEY='YOUR_API_KEY'` 等语法。也可只安装 `requirements.txt` 后在本目录运行。安装包后，命令 `rcta-analyze` 与 `python -m rcta` 等价。

`.env.example` 只提供配置模板，程序不会自动加载它。默认客户端沿用原实现的 OpenAI 兼容接口及 DeepSeek thinking 参数。对不支持这些额外字段的兼容服务，设置 `LLM_SEND_THINKING_CONFIG=false`；其他请求字段也需符合所选服务的接口。更换服务或模型后，诊断质量需另行验证。

## 输入格式

`examples/demo_trajectory.json` 是人工构造的格式示例，不是实验数据。每个 JSON 文件表示一条轨迹：

```json
{
  "question_ID": "my_task__001",
  "history": [
    {"step": 0, "role": "user", "name": "human", "content": "任务要求"},
    {"step": 1, "role": "assistant", "name": "ActionAgent", "content": "执行记录"}
  ]
}
```

`history` 应按执行顺序排列，`step` 是唯一整数编号；本算法保留原编号，不重新编号。原始任务要求、工具结果和判断依据应记录在 `history`。委派使用 `Planner (-> Executor)` 形式，例如 `DiagnostAgent (-> ActionAgent)`，原始名称会用于目标匹配。

代码根据已有角色名规则识别规划者、执行者和验证者。新系统使用不同命名时，修改 `rcta/preprocess/step_enricher.py` 的角色映射；否则未知角色仍保留原名，但无法直接使用相同的角色匹配规则。仅将工具返回记成 `Computer_terminal`，即可沿用当前工具观察识别规则。

当前模型输入由 `question_ID` 和 `history` 构造，不向模型传入人工根因标签、参考答案或轨迹外评测信息。若输入附带 `is_correct: true`，批处理会跳过该文件；其他附加字段会随原 JSON 保留在结果中，但不因此成为模型输入。

## 批量运行与结果

```bash
# 扁平目录：inputs/*.json
python -m rcta --input-dir inputs --output-dir outputs/my-run --workers 2

# 分组目录：inputs/my_benchmark/*.json
python -m rcta --input-dir inputs --benchmark my_benchmark --output-dir outputs/grouped

# 只跑一个文件
python -m rcta --input-dir examples --file demo_trajectory.json --output-dir outputs/single
```

输出沿用输入文件名。主要字段为：

- `llm_mistake_agent / llm_mistake_step / llm_mistake_reason`：负责角色、根因原始编号与原因。
- `llm_analysis_summary.root_cause`：根因、证据、类别、解释链、置信等级、拒答和人工复核标记。
- `llm_analysis_summary.failure_manifestation`：失败表现位置，与根因分开记录。
- `--debug-sidecar`：额外输出 `*.debug.json`，包含局部摘要、阶段组织和归因中间结果。

默认跳过已有完整结果，`--overwrite` 可重新处理。每个输出目录保存 `run_snapshot/`，冻结三份提示词和非密钥配置；换输入文件清单、模型或提示词时请使用新的输出目录。完整参数见 `python -m rcta --help`。

## 核心代码在哪里

```text
rcta/
├── __main__.py                   # python -m rcta
├── run.py                        # 整体流程、重试、批处理
├── config.py                     # 分段、模型和类别配置
├── core/
│   ├── schema.py                 # Step、局部摘要、阶段和根因结构
│   └── llm_client.py             # 接口调用、JSON 解析、长度与网络重试
├── preprocess/
│   ├── loader.py                 # 轨迹读取及输入白名单
│   ├── step_enricher.py          # 角色、动作和验证信号抽取
│   └── segmenter.py              # 连续分段与重叠上下文
├── analyze/
│   ├── local_summarizer.py       # 局部摘要
│   ├── global_reducer.py         # 阶段聚合、候选原文、委派补全、最终归因
│   └── validator.py              # 编号、角色、类别和引文校验
├── prompts/
│   ├── local_summary.md
│   ├── phase_aggregate.md
│   └── root_cause.md
└── output/                       # 原子保存、结果展示和运行快照
```

阅读算法可从 `run.py::process_one()` 开始，再看 `global_reducer.py` 中的 `_collect_candidate_step_hints()`、`_augment_with_preceding_delegates()` 和 `diagnose_root_cause()`。

算法顺序为：分段 → 局部摘要 → 阶段聚合 → 候选原文召回 → 目标匹配的上游委派补全 → 指令与执行比较 → 字段和引文校验。核心是区分上游引入的缺陷与执行时新增的错误；反事实判断不执行实际修复重跑，校验不证明因果结论正确。

## 检查代码包

```bash
python -m unittest discover -s tests -v
```

测试使用本地构造的模型响应，检查包内完整流程、原文召回、委派匹配、错误重试、校验和输入边界；不访问模型接口，不检验实际模型准确率。

`PACKAGE_INFO.json` 记录提取来源与修改范围，`SHA256SUMS` 记录文件校验值。本次整理只调整独立运行路径、命令入口与打包配置；核心归因代码及三份提示词保持原文件内容。包内保留原 `LICENSE`，不包含完整数据集、实验结果或个人运行配置。
