"""Offline handoff checks. Scripted responses test plumbing, not LLM accuracy."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rcta import run as rcta_run
from rcta.analyze.global_reducer import (
    _augment_with_preceding_delegates,
    _collect_candidate_step_hints,
)
from rcta.core.llm_client import _is_token_limit_error
from rcta.core.schema import LocalSummary, PhaseSummary
from rcta.output.run_snapshot import freeze_run_snapshot
from rcta.preprocess.loader import build_task_brief, load_trajectory
from rcta.preprocess.segmenter import segment_trajectory
from rcta.preprocess.step_enricher import enrich_steps
from rcta.run import process_one


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples/demo_trajectory.json"


class ScriptedClient:
    """Supply deterministic responses without constructing an API client."""

    last_reasoning_content = ""

    def __init__(self, invalid_root_replies=0, invalid_local_replies=0):
        self.invalid_root_replies = invalid_root_replies
        self.invalid_local_replies = invalid_local_replies
        self.requests = []
        self.counts = {"local": 0, "phase": 0, "root": 0}

    def chat_json(self, *, system, user, stage, **kwargs):
        self.counts[stage] += 1
        data, _ = json.JSONDecoder().raw_decode(user.split("## Data (JSON)\n", 1)[1])
        self.requests.append({"stage": stage, "data": data, "system": system, "user": user})
        if stage == "local":
            candidate = 999 if self.counts[stage] <= self.invalid_local_replies else 3
            response = {
                "segment_id": data["segment_id"],
                "step_range": data["step_range"],
                "segment_goal": "Book and verify the requested train direction.",
                "key_events": [{"event": "The executor booked reversed endpoints.", "step_ids": [3]}],
                "candidate_failures": [{"type": "execution_error", "step_ids": [candidate],
                                        "why": "The direction differs from the task."}],
                "verifier_findings": [{"step_ids": [6], "result": "PASS",
                                       "note": "The verifier checked only confirmation existence."}],
                "uncertainties": [],
            }
        elif stage == "phase":
            response = {
                "phases": [{"phase_id": 0, "step_range": [0, 7],
                            "phase_goal": "Book and verify the train.",
                            "involved_agents": ["ActionAgent"],
                            "sub_phases": [{"step_range": [0, 7], "description": "Synthetic run."}],
                            "failure_signals": [{"step_ids": [3], "severity": "high",
                                                 "description": "Wrong direction."}],
                            "supporting_step_ids": [0, 3]}],
                "conflicts": [],
            }
        else:
            root = {
                "agent": "DiagnostAgent (-> ActionAgent)",
                "step": "999" if self.counts[stage] <= self.invalid_root_replies else "2",
                "reason": "The task requires A to B, but the delegation specifies B to A. "
                          "The executor faithfully books the reversed direction.",
                "evidence_step_ids": [0, 2, 3, 4, 6, 7],
                "primary_category": "C1_flawed_plan",
                "contributing_factors": ["E1_verification_gap"],
            }
            manifestation = {**root, "step": "2", "evidence_quote": "Book the train from B to A."}
            response = {
                "root_cause_event": root,
                "failure_manifestation_event": manifestation,
                "abstain": False,
                "detailed_analysis": {
                    "task_summary": "Book the requested train route.",
                    "delegation_trace": {"checked": True, "is_faithful_implementation": True,
                                         "prescribed_by_step": 2, "quote": "Book the train from B to A.",
                                         "defect_in_quote": True},
                    "failure_chain": [
                        {"step": "2", "agent": root["agent"], "role": "root_cause",
                         "description": "Reversed direction prescribed."},
                        {"step": "2", "agent": root["agent"], "role": "manifestation",
                         "description": "Concrete wrong direction in instruction."},
                        {"step": "3", "agent": "ActionAgent", "role": "propagation",
                         "description": "Faithfully executes the wrong direction."},
                        {"step": "7", "agent": "ActionAgent", "role": "terminal",
                         "description": "Submits the incorrect booking."},
                    ],
                    "counterfactual": "A corrected delegation could avoid the reversed booking.",
                    "confidence": "medium",
                    "confidence_reason": "Scripted response for an offline test only.",
                    "expert_review_hints": [],
                },
            }
        return copy.deepcopy(response), json.dumps(response), "stop"


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.steps = load_trajectory(DEMO)

    def run_pipeline(self, client, raw=None):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            source = temp / "input.json"
            source.write_text(json.dumps(raw or self.raw), encoding="utf-8")
            with patch("socket.create_connection", side_effect=AssertionError("Network is disabled in this test")):
                status = process_one(source, "", client, temp / "out", False, False, True)
            output = json.loads((temp / "out/input.json").read_text())
            debug = json.loads((temp / "out/input.debug.json").read_text())
            self.assertEqual(json.loads(source.read_text()), raw or self.raw)
            return status, output, debug

    def test_complete_pipeline_recalls_upstream_source(self):
        client = ScriptedClient()
        status, output, debug = self.run_pipeline(client)
        self.assertEqual(status, "ok")
        self.assertEqual(output["llm_mistake_step"], 2)
        self.assertEqual(output["llm_mistake_agent"], "DiagnostAgent (-> ActionAgent)")
        self.assertEqual(client.counts, {"local": 1, "phase": 1, "root": 1})
        package = next(x["data"] for x in client.requests if x["stage"] == "root")
        excerpts = {x["step_id"]: x["content"] for x in package["candidate_steps_excerpts"]}
        self.assertIn(2, excerpts)  # Not nominated by either scripted summary.
        self.assertEqual(excerpts[2], self.raw["history"][2]["content"])
        self.assertEqual(output["llm_analysis_summary"]["root_cause"]["step"], "2")
        self.assertIn("full_summary", debug)

    def test_bad_root_output_is_retried_with_feedback(self):
        client = ScriptedClient(invalid_root_replies=1)
        status, output, _ = self.run_pipeline(client)
        self.assertEqual(status, "ok")
        self.assertEqual(output["llm_mistake_step"], 2)
        self.assertEqual(client.counts["root"], 2)
        root_requests = [x for x in client.requests if x["stage"] == "root"]
        self.assertIn("Errors in the previous output", root_requests[1]["user"])

    def test_persistently_invalid_root_abstains(self):
        client = ScriptedClient(invalid_root_replies=2)
        status, output, _ = self.run_pipeline(client)
        root = output["llm_analysis_summary"]["root_cause"]
        self.assertEqual(status, "ok_needs_review")
        self.assertEqual(output["llm_mistake_step"], -1)
        self.assertTrue(root["abstain"])
        self.assertTrue(root["needs_human_review"])

    def test_local_out_of_range_id_is_retried(self):
        client = ScriptedClient(invalid_local_replies=1)
        status, output, _ = self.run_pipeline(client)
        self.assertEqual(status, "ok")
        self.assertEqual(client.counts["local"], 2)
        self.assertEqual(output["llm_mistake_step"], 2)

    def test_external_labels_do_not_enter_prompts(self):
        raw = copy.deepcopy(self.raw)
        marker = "PRIVATE_LABEL_NEVER_SEND_51b9"
        for key in ["question", "metadata", "verifier_output", "ground_truth",
                    "reference_solution", "mistake_agent", "mistake_step", "mistake_reason"]:
            raw[key] = {"benchmark": marker} if key == "metadata" else marker
        client = ScriptedClient()
        self.run_pipeline(client, raw)
        self.assertNotIn(marker, build_task_brief(raw))
        for request in client.requests:
            self.assertNotIn(marker, request["system"] + request["user"])

    def test_delegate_matching_does_not_use_other_recipient(self):
        # The judge handoff is more recent than the executor handoff.
        events = [
            {"step": 0, "name": "DiagnostAgent (-> ActionAgent)", "content": "Do the work."},
            {"step": 1, "name": "DiagnostAgent (-> JudgeAgent)", "content": "Verify the work."},
            {"step": 2, "name": "ActionAgent", "content": "Wrong action."},
        ]
        self.assertEqual(_augment_with_preceding_delegates([2], enrich_steps(events)), [0, 2])
        self.assertEqual(_augment_with_preceding_delegates([2], enrich_steps(events[1:])), [2])

    def test_segments_cover_original_steps_once(self):
        history = [{"step": i, "name": "ActionAgent", "content": "event " + str(i)} for i in range(181)]
        segments = segment_trajectory(enrich_steps(history))
        covered = [s.step_id for seg in segments for s in seg.steps]
        self.assertEqual(covered, list(range(181)))
        for prev, current in zip(segments, segments[1:]):
            self.assertEqual(current.overlap_steps, prev.steps[-5:])

    def test_candidate_limit_precedes_handoff_augmentation(self):
        local = LocalSummary(segment_id=0, step_range=[0, 99], candidate_failures=[
            {"step_ids": list(range(100)), "type": "execution_error", "why": "synthetic"}
        ])
        hints = _collect_candidate_step_hints([local], PhaseSummary(), [])
        self.assertEqual(len(hints), 80)
        self.assertEqual([h["step_id"] for h in hints], list(range(80)))


class RunnerTests(unittest.TestCase):
    """CLI-level behaviour: resume markers, snapshots, error classification."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        for name in ("a.json", "b.json"):
            (self.inputs / name).write_text(DEMO.read_text(encoding="utf-8"), encoding="utf-8")
        self.out = self.root / "out"
        patcher = patch.object(rcta_run.config, "LOGS_DIR", self.root / "logs")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def main(self, *extra, client=None):
        argv = ["-i", str(self.inputs), "-o", str(self.out), *extra]
        with patch.object(rcta_run, "LLMClient", return_value=client or ScriptedClient()):
            return rcta_run.main(argv)

    def test_rate_limit_is_not_a_token_limit(self):
        self.assertFalse(_is_token_limit_error(Exception("Error code: 429 - Rate limit exceeded")))
        self.assertTrue(_is_token_limit_error(Exception("This model's maximum context length is 128k")))

    def test_error_marker_skipped_before_submission_with_workers(self):
        marker = rcta_run.error_marker_path(self.out, "", "a.json")
        marker.parent.mkdir(parents=True)
        marker.write_text("{}", encoding="utf-8")
        client = ScriptedClient()
        self.assertEqual(self.main("--workers", "2", "--skip-error-markers", client=client), 0)
        self.assertEqual(client.counts["root"], 1)
        self.assertFalse((self.out / "a.json").exists())
        self.assertTrue((self.out / "b.json").exists())

    def test_success_clears_stale_error_marker(self):
        marker = rcta_run.error_marker_path(self.out, "", "a.json")
        marker.parent.mkdir(parents=True)
        marker.write_text("{}", encoding="utf-8")
        self.assertEqual(self.main(), 0)
        self.assertFalse(marker.exists())

    def test_dry_run_writes_no_snapshot(self):
        self.assertEqual(self.main("--dry-run"), 0)
        self.assertFalse((self.out / "run_snapshot").exists())
        self.assertEqual(self.main(), 0)

    def test_snapshot_allows_subset_rerun_but_not_new_inputs(self):
        files = sorted(self.inputs.glob("*.json"))
        kwargs = dict(out_root=self.out, benchmark="", model="m", base_url="u", input_dir=self.inputs)
        freeze_run_snapshot(input_files=files, **kwargs)
        freeze_run_snapshot(input_files=files[:1], **kwargs)
        with self.assertRaisesRegex(RuntimeError, "input files"):
            freeze_run_snapshot(input_files=files + [self.inputs / "c.json"], **kwargs)
        with self.assertRaisesRegex(RuntimeError, "model"):
            freeze_run_snapshot(input_files=files, **{**kwargs, "model": "other"})


if __name__ == "__main__":
    unittest.main()
