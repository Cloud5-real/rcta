"""轨迹文件读取 + 输入文件列表枚举。

每个输入文件是一条轨迹 JSON,`history` 字段是 step 数组(格式见 docs/data_format.md)。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from ..core.schema import Step
from .step_enricher import enrich_steps


def list_input_files(input_dir: Path, benchmark: Optional[str] = None) -> List[Path]:
    """列出待处理文件(按文件名稳定排序),忽略 *.debug.json。

    - 给了 benchmark: 读 <input_dir>/<benchmark>/*.json(经典布局)。
    - 没给 benchmark: 读 <input_dir>/*.json(扁平布局,如他人自带的 bench 目录)。
    """
    base = (input_dir / benchmark) if benchmark else input_dir
    if not base.exists():
        raise FileNotFoundError(f"input dir not found: {base}")
    return sorted(
        p for p in base.glob("*.json")
        if p.is_file() and not p.name.endswith(".debug.json")
    )


def load_raw(src_path: Path) -> Dict[str, Any]:
    """读原始 JSON,返回 dict(完整保留所有字段)。"""
    with src_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_trajectory(src_path: Path) -> Tuple[Dict[str, Any], List[Step]]:
    """读原始 JSON 并将 history 经启发式抽取转成 Step 列表。"""
    data = load_raw(src_path)
    history = data.get("history") or []
    steps = enrich_steps(history)
    return data, steps


def build_task_brief(data: Dict[str, Any], src_name: str = "") -> str:
    """用发布数据中的标识字段生成给 LLM 看的任务概况。

    任务指令若存在,已经是 ``history`` 中的轨迹事件,不在这里重复注入。
    此函数不得读取发布 schema 之外的 ``question``、``metadata``、
    ``is_correct``、评测器输出、参考答案或人工标注字段。
    """
    stem = (src_name or "").removesuffix(".json")
    task_id = str(data.get("question_ID") or stem or "?")
    benchmark = task_id.split("__", 1)[0] if "__" in task_id else "?"
    return f"benchmark: {benchmark}\n\ntask_id: {task_id}"
