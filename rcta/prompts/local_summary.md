# Local Summary Prompt (Stage 2 — segment level)

You are an expert in analyzing failed multi-agent trajectories. At this stage, examine **only one segment of the trajectory** and extract its key events, suspected errors, and verification signals. **Do not** determine the root cause of the entire trajectory; that is the responsibility of a later stage.

## Input

You will receive:
- `task_brief`: only the benchmark and task_id that can be determined from the released fields. If task instructions are available, read them only from trajectory events recorded in `segment_steps` / `overlap_steps`
- `segment_id`: the current segment number
- `step_range`: `[first_step_id, last_step_id]`
- `agent_set`: the set of original agent names appearing in this segment
- `verifier_signal_seq`: the sequence of verifier/terminal PASS/FAIL signals in this segment
- `step_id_list`: the set of **valid step_id values for this segment** (an array); every step_id you output must belong to this set
- `overlap_steps`: the last N steps of the preceding segment (for context only; do not treat them as events in the current segment. Their step_id values are **not** in `step_id_list`; they only provide preceding context)
- `segment_steps`: all steps in this segment; each step contains `step_id / agent / agent_role / action_type / exit_code / verifier_signal / content (complete text, without truncation) / content_len / step_hash`

## Output Requirements (strict JSON, no Markdown fences)

```json
{
  "segment_id": <int>,
  "step_range": [<first>, <last>],
  "segment_goal": "<English; the goal/subtask served by this segment within the overall task>",
  "key_events": [
    {"event": "<event description in English>", "step_ids": [<int>, ...]}
  ],
  "candidate_failures": [
    {
      "type": "<planning_error|execution_error|verifier_error|tool_error|communication_error|none>",
      "step_ids": [<int>, ...],
      "why": "<English; why this is a suspected failure point>"
    }
  ],
  "verifier_findings": [
    {"step_ids": [<int>, ...], "result": "<PASS|FAIL|UNKNOWN>", "note": "<English>"}
  ],
  "uncertainties": ["<English; aspects you cannot assess reliably>"]
}
```

## Mandatory Constraints

1. **Output only one valid JSON object**, without Markdown fences, explanations, or `<think>`.
2. Every integer in a `step_ids` array **must** appear in `step_id_list`. If you need to refer to an overlap step, describe it in the text of `uncertainties` instead.
3. `candidate_failures[].type` must belong to `{planning_error, execution_error, verifier_error, tool_error, communication_error, none}`. If this segment contains no suspected failure, output `[{"type": "none", "step_ids": [], "why": "No apparent failure in this segment"}]`.
4. `verifier_findings[].result` must belong to `{PASS, FAIL, UNKNOWN}`.
5. **Write in English** (`segment_goal / event / why / note / uncertainties` must all be in English; keep field names and enum values unchanged).
6. Do not invent step_id values or events. If uncertain, state the uncertainty in `uncertainties`.
7. Do not determine the overall root cause; that is a later stage's responsibility. This stage only describes **the current segment** locally.

## Writing Guidelines

- `segment_goal`: one concise sentence (e.g., "ActionAgent attempts to resolve a dependency version issue").
- `key_events`: 3-8 items, each linked to 1-3 step_id values.
- `candidate_failures`: 0-3 items, usually with 1-2 step_ids each.
- `uncertainties`: record steps that appear incorrect but whose root-cause status is uncertain.
