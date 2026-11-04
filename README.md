# RCTA：失败轨迹根因定位

RCTA（Root-Cause Trajectory Attribution）对失败的多智能体执行轨迹做事后根因定位，输出负责角色、根因步骤、证据和解释链，并把根因（缺陷在哪里被引入）与失败表现（错误在哪里显露）分开记录。

## 快速开始

需要 Python 3.10+。在本目录执行：

```bash
# 1. 不调用模型，只检查轨迹读取与分段
python -m rcta --input-dir examples --output-dir outputs/dry-run --dry-run

# 2. 安装并配置 OpenAI 兼容接口
python -m venv .venv && source .venv/bin/activate
python -m pip install -e .
export LLM_API_KEY='YOUR_API_KEY'
export LLM_BASE_URL='https://api.deepseek.com'
export LLM_MODEL='deepseek-v4-pro'

# 3. 正式运行
python -m rcta --input-dir examples --output-dir outputs/demo --debug-sidecar
```

安装后 `rcta-analyze` 与 `python -m rcta` 等价。Windows 用 `.venv\Scripts\Activate.ps1` 激活，环境变量写成 `$env:LLM_API_KEY='...'`。`.env.example` 只是模板，程序不会自动加载。服务不支持 DeepSeek 的 thinking 字段时，设 `LLM_SEND_THINKING_CONFIG=false`。

## 常用命令

```bash
python -m rcta -i inputs -o outputs/run1 --workers 4                 # 扁平目录 inputs/*.json
python -m rcta -i inputs -b my_benchmark -o outputs/run1             # 分组目录 inputs/my_benchmark/*.json
python -m rcta -i inputs -o outputs/run1 --file x.json --overwrite   # 在原输出目录重跑单个样本
python -m rcta -i inputs -o outputs/run1 --skip-error-markers        # 续跑时跳过已记录失败的样本
python -m rcta --help
```

- 默认跳过已有完整结果的样本，所以中断后用同样的命令即可续跑。
- 首次正式运行会在输出目录写入 `run_snapshot/`，冻结三份提示词和非密钥配置。之后在同一目录运行时，若提示词、模型或配置不同，或输入不是原文件清单的子集，程序会拒绝运行。换实验设置请用新的输出目录。
- 单个样本失败会写入 `<output-dir>/_errors/`；该样本之后重跑成功时，失败标记会自动删除。

## 目录

```text
rcta/                   算法代码（入口 run.py::process_one）
  preprocess/           读取、角色识别、分段
  analyze/              局部摘要、阶段聚合、根因判定、校验
  prompts/              三阶段提示词
  output/               结果写入、展示字段、运行快照
docs/
  algorithm.md          算法流程，以及各阶段对应的代码和提示词
  data_format.md        输入格式与输出字段
  adapting.md           接入新的多智能体系统要改哪些地方
  provenance.md         代码来源与版本记录
examples/               合成示例轨迹（非实验数据）
tests/                  离线测试（脚本化模型响应，不访问接口）
```

## 测试

```bash
python -m unittest discover -s tests -v
```

测试用本地构造的模型响应检查完整流程、候选召回、委派匹配、重试、校验、输入边界和续跑逻辑，不检验实际模型准确率。

## 许可

Apache License 2.0，见 `LICENSE`。
