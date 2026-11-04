# Phase Aggregation Prompt (Stage 3 — phase level)

You are an expert in analyzing failed multi-agent trajectories. You have received the LocalSummary list for all segments. Now **aggregate them into 3-8 semantically meaningful phases** and identify conflicts or inconsistencies across phases. **Do not** make the final root-cause determination; that is the next stage's responsibility.

## Input

You will receive:
- `task_brief`: a brief task description
- `all_step_ids_compressed`: the global valid step_id range (e.g., `"0-521"`)
- `verifier_signal_summary`: a global summary of verifier signals
- `local_summaries`: the LocalSummary array for all segments (including each segment's segment_goal / key_events / candidate_failures / verifier_findings / uncertainties)

## Output Requirements (strict JSON, no Markdown fences)

```json
{
  "phases": [
    {
      "phase_id": <int, starting from 0>,
      "step_range": [<first_step_id>, <last_step_id>],
      "phase_goal": "<English; the task goal of this phase>",
      "involved_agents": ["<agent_name>", ...],
      "sub_phases": [
        {"step_range": [<start>, <end>], "description": "<English; what the agents did in sequence within this contiguous subsection>"}
      ],
      "failure_signals": [
        {"description": "<English>", "step_ids": [<int>, ...], "severity": "<low|medium|high>"}
      ],
      "supporting_step_ids": [<int>, ...]
    }
  ],
  "conflicts": [
    {"description": "<English; contradictions or information conflicts across segments>", "segment_ids": [<int>, ...], "step_ids": [<int>, ...]}
  ]
}
```

## Mandatory Constraints

1. **Output only one valid JSON object**, without Markdown fences, explanations, or `<think>`.
2. Sort `phases` in ascending order of `step_range`; produce **3-8 phases** (too many introduce redundancy; too few lose structure).
3. Every integer in `step_ids` / `step_range` must belong to the global set covered by `all_step_ids_compressed`.
4. **`sub_phases` are contiguous subdivisions of the phase** and must satisfy: each `step_range` is contiguous; **subsections are adjacent, with no overlap or gaps**; **together they cover exactly the entire phase's step_range** (the first sub_phase starts at phase.step_range[0], and the last ends at phase.step_range[1]). Usually provide 2-6 sub_phases per phase. They describe what the agents did in sequence, at a finer level than the phase. They are **not** representative-step selections: partition the entire phase.
5. `failure_signals` are **point events** (observable signs of failure) identified by `step_ids` (which need not be contiguous); `severity` must belong to `{low, medium, high}`. Not every phase needs failure signals; include them only when such signs occur within that phase. For a phase consisting of repeated unsuccessful repairs, use `severity=high`.
6. `phase_goal` should be **more abstract than segment_goal** (one phase usually covers 1-N segments), e.g., "environment exploration", "dependency repair", "test verification", or "completion".
7. `supporting_step_ids` lists representative steps for the phase (the 3-10 most informative steps), whose original text will be retrieved for root-cause determination at the next stage.
8. `conflicts`: record contradictory conclusions across segments (e.g., segment A reports PASS while B reports FAIL, or different agents maintain inconsistent states). Use an empty array if none exist. These are **cross-segment** contradictions and do not belong to a single phase.
9. Write in **English** (keep field names, enum values, and agent names unchanged).

## Writing Guidelines

- Typical phase boundaries include changes in task subgoal, dominant agent, major verification signals, or a finish call.
- `sub_phases` must seamlessly partition the entire phase into contiguous subsections; adjacent subsections must not skip step numbers or leave gaps (e.g., for a phase covering 0-26, sub_phases could be [0,4][5,10][11,18][19,26], covering the range continuously).
- `failure_signals` identify which steps show problems and what the signs are; they may refer to noncontiguous points.
