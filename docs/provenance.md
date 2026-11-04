# 代码来源与版本记录

## 来源

本包从研究代码库的 `agent-error-trajectory-analysis/` 目录提取，提取日期 2026-11-04。

提取时只复制了推理所需的代码、三份提示词、合成示例和离线测试。真实轨迹、人工标注、实验结果、API 凭据、日志和调试输出都不在包内。

## 与论文实验代码的对应关系

git tag `v0.1.0-baseline` 是提取时的原样版本：除 `config.py`（运行路径改为相对当前目录、导入时不再建目录）和 `run.py`（独立运行的模块名与帮助文本）外，核心模块和三份提示词与源目录逐字节一致。源文件 SHA-256（前 16 位）：

| 源文件 | SHA-256 | 提取时 |
|---|---|---|
| `__init__.py` | `c4be4ce1d96cff3f` | 原样 |
| `analyze/global_reducer.py` | `398318e09cd97e1a` | 原样 |
| `analyze/local_summarizer.py` | `c01f8e9e66091155` | 原样 |
| `analyze/validator.py` | `2029a6c8a6003673` | 原样 |
| `config.py` | `44b80738d22a3d90` | 改路径/CLI 文本 |
| `core/llm_client.py` | `a27fcd7ec92618cb` | 原样 |
| `core/schema.py` | `565444ca3259e631` | 原样 |
| `output/io_writer.py` | `0872817521f21e6e` | 原样 |
| `output/presenter.py` | `8d290d1b228c7cae` | 原样 |
| `output/run_snapshot.py` | `ab8eedeb8ae8c66c` | 原样 |
| `preprocess/loader.py` | `7938befa1caebc2a` | 原样 |
| `preprocess/segmenter.py` | `bc0e6bec2c3eb47b` | 原样 |
| `preprocess/step_enricher.py` | `6f8013ac419809ca` | 原样 |
| `prompts/local_summary.md` | `02de0b4b0972695f` | 原样 |
| `prompts/phase_aggregate.md` | `42250346ee6a13d8` | 原样 |
| `prompts/root_cause.md` | `704545ca836a8672` | 原样 |
| `run.py` | `9973b36a29e86ecd` | 改路径/CLI 文本 |

需要与源目录的结果严格对齐时，请检出 `v0.1.0-baseline`，或用上表核对源目录。

## 版本记录

### 0.2.0（2026-11-04）

推理逻辑与三份提示词未改动；以下修改只影响运行器和代码组织。

修复：
- 429 限流错误曾因关键词 `exceed` 被误判为上下文超长而不重试，现在会正常退避重试。
- 并发运行（`--workers > 1`）时 `--skip-error-markers` 不起作用：带失败标记的样本仍会调用模型。现在提交前就跳过。
- 样本重跑成功后删除旧的失败标记。
- dry-run 不再写入 `run_snapshot/`，以免之后无法在同一目录正式运行。
- 运行快照允许在原输出目录重跑原文件清单的子集（如 `--file x.json --overwrite`），不匹配时报出具体是哪一项不同。
- 缺少 API key 时先报错退出，不再留下空的运行快照。
- `--sample-timeout` 在 Windows（无 SIGALRM）或并发模式下改为给出警告并忽略，不再崩溃或静默失效。

整理：
- `DeepSeekClient` 更名为 `LLMClient`（保留旧名别名），`config.WHO_WHEN_DIR` 更名为 `config.INPUT_DIR`，日志名统一为 `rcta`。
- 删除未使用的常量（`SUPPORTED_BENCHMARKS`、`REPO_ROOT`、`TASK_*_CHARS`、`ROOT_VERIFIER_CHARS`、`LLM_REASONING_EFFORT_DEFAULT`）和函数 `list_bench_files`；修正与实际配置不符的注释。
- Magentic-One 角色名从 `global_reducer.py` 移到 `step_enricher.py`，与其他角色映射放在一起。
- 文档拆分到 `docs/`；`PACKAGE_INFO.json`、`SHA256SUMS` 由本文件和 git 历史取代；删除与 `pyproject.toml` 重复的 `requirements.txt`。
- 新增 5 个运行器回归测试（共 13 个）。

### 0.1.0（2026-11-04）

从研究代码库提取的初始独立版本，对应 tag `v0.1.0-baseline`。
