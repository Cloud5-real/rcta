"""Stage 2:对每个 segment 调一次 LLM 产出 LocalSummary。"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, List, Optional, Set

from .. import config
from ..core.schema import Step, Segment, LocalSummary
from ..core.llm_client import DeepSeekClient

LOG = logging.getLogger("MAS_trajectory_analysis.local")


SYS_PROMPT = None  # 延迟加载


def _load_prompt() -> str:
    global SYS_PROMPT
    if SYS_PROMPT is None:
        SYS_PROMPT = (config.PROMPTS_DIR / "local_summary.md").read_text(encoding="utf-8")
    return SYS_PROMPT


def _step_to_inline(step: Step) -> Dict[str, Any]:
    # Round 6:发完整正文(不再 head/tail 截断;委派计划的核心逻辑常在中段)。仅极高安全帽防失控大 step。
    content = step.content_full
    if len(content) > config.STEP_FULL_MAX_CHARS:
        content = content[: config.STEP_FULL_MAX_CHARS] + "\n…[truncated, oversized step]"
    return {
        "step_id": step.step_id,
        "agent": step.agent_name_raw,
        "agent_role": step.agent_normalized,
        "action_type": step.action_type,
        "exit_code": step.exit_code,
        "verifier_signal": step.verifier_signal,
        "step_hash": step.step_hash,
        "content": content,
        "content_len": step.content_len,
    }


def _build_user_message(
    seg: Segment,
    task_brief: str,
    previous_errors: Optional[List[str]] = None,
) -> str:
    payload = {
        "task_brief": task_brief,
        "segment_id": seg.segment_id,
        "step_range": seg.step_range,
        "agent_set": seg.agent_set,
        "verifier_signal_seq": seg.verifier_signal_seq,
        "step_id_list": seg.step_ids,
        "overlap_steps": [_step_to_inline(s) for s in seg.overlap_steps],
        "segment_steps": [_step_to_inline(s) for s in seg.steps],
    }
    msg = (
        "## Task\n"
        "Produce a JSON summary of the segment below according to the prompt section Output Requirements. "
        "All step_ids must belong to `step_id_list`. "
        "Write in English.\n\n"
        "## Data (JSON)\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    if previous_errors:
        msg += (
            "\n\n## Errors in the previous output; please correct them\n"
            + "\n".join(f"- {e}" for e in previous_errors[:20])
        )
    return msg


def summarize_segment(
    client: DeepSeekClient,
    seg: Segment,
    task_brief: str,
    previous_errors: Optional[List[str]] = None,
) -> LocalSummary:
    system = _load_prompt()
    user = _build_user_message(seg, task_brief, previous_errors=previous_errors)
    parsed, raw, finish = client.chat_json(
        system=system, user=user,
        temperature=config.LLM_TEMPERATURE_DEFAULT,
        max_tokens=config.LLM_MAX_TOKENS_LOCAL,
        reasoning_effort=config.LLM_REASONING_EFFORT_LOCAL,
        thinking=config.LLM_THINKING_LOCAL,
        stage="local",
    )
    ls = LocalSummary(
        segment_id=seg.segment_id,
        step_range=list(seg.step_range),
        raw_text=raw,
    )
    if parsed is None:
        LOG.warning(
            "seg %d LLM JSON parse failed (finish=%s, raw_len=%d). using empty placeholder.",
            seg.segment_id, finish, len(raw or ""),
        )
        ls.needs_human_review = True
        return ls

    ls.segment_goal = str(parsed.get("segment_goal") or "").strip()
    ls.key_events = list(parsed.get("key_events") or [])
    ls.candidate_failures = list(parsed.get("candidate_failures") or [])
    ls.verifier_findings = list(parsed.get("verifier_findings") or [])
    ls.uncertainties = list(parsed.get("uncertainties") or [])

    # 若 LLM 返回了不一样的 segment_id / step_range,以输入为准
    ls.segment_id = seg.segment_id
    ls.step_range = list(seg.step_range)
    return ls
