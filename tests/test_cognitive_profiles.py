import tempfile
import unittest
from pathlib import Path

from personal_ai_os.cognition import compile_operating_practices, validate_memory_candidate
from personal_ai_os.runtime import ExecutionBroker, RuntimeStore


class CaptureAdapter:
    adapter_id = "capture-adapter"

    def __init__(self):
        self.context_packs = []

    def probe(self):
        return {"adapter_id": self.adapter_id, "available": True}

    def start(self, task, *, model, context_pack):
        self.context_packs.append(context_pack)
        return {
            "ok": True,
            "external_run_id": "capture-run-1",
            "status": "SUCCEEDED",
            "output_text": "One inspectable result.",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }


class CognitiveProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RuntimeStore(Path(self.temp.name) / "runtime.db")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def candidate(candidate_id="habit-1", **overrides):
        payload = {
            "schema_version": "personal-ai-os.memory-candidate/v1",
            "candidate_id": candidate_id,
            "subject": {"kind": "person", "id": "writer-a"},
            "domain_id": "writing",
            "category": "style",
            "statement": "先列出证据，再形成判断。",
            "evidence_refs": ["artifact:reviewed-1"],
            "sample_count": 3,
            "privacy_class": "private",
        }
        payload.update(overrides)
        return payload

    def test_candidates_start_proposed_and_only_approved_rules_compile(self):
        proposed = self.store.create_memory_candidate(self.candidate())

        self.assertEqual("PROPOSED", proposed["status"])
        self.assertEqual([], compile_operating_practices(
            self.store.snapshot()["memory_candidates"],
            subject={"kind": "person", "id": "writer-a"},
            domain_id="writing",
        )["rules"])

        approved = self.store.review_memory_candidate(
            "habit-1", decision="APPROVED", reviewed_by="owner"
        )
        profile = compile_operating_practices(
            self.store.snapshot()["memory_candidates"],
            subject={"kind": "person", "id": "writer-a"},
            domain_id="writing",
        )

        self.assertEqual("APPROVED", approved["status"])
        review_events = self.store.snapshot()["memory_candidate_events"]
        self.assertEqual(
            [{"candidate_id": "habit-1", "event_type": "APPROVED", "by": "owner"}],
            [
                {key: event[key] for key in ("candidate_id", "event_type", "by")}
                for event in review_events
                if event["event_type"] == "APPROVED"
            ],
        )
        self.assertEqual(["先列出证据，再形成判断。"], profile["rules"])
        self.assertEqual(["artifact:reviewed-1"], profile["evidence_refs"])

    def test_subject_and_domain_boundaries_prevent_style_cross_talk(self):
        self.store.create_memory_candidate(self.candidate())
        self.store.review_memory_candidate("habit-1", decision="APPROVED", reviewed_by="owner")

        other_person = compile_operating_practices(
            self.store.snapshot()["memory_candidates"],
            subject={"kind": "person", "id": "writer-b"},
            domain_id="writing",
        )
        other_domain = compile_operating_practices(
            self.store.snapshot()["memory_candidates"],
            subject={"kind": "person", "id": "writer-a"},
            domain_id="research",
        )

        self.assertEqual([], other_person["rules"])
        self.assertEqual([], other_domain["rules"])

    def test_candidate_requires_evidence_and_cannot_self_approve(self):
        with self.assertRaisesRegex(ValueError, "evidence"):
            validate_memory_candidate(self.candidate(evidence_refs=[]))
        with self.assertRaisesRegex(ValueError, "PROPOSED"):
            validate_memory_candidate(self.candidate(status="APPROVED"))

    def test_review_requires_an_identified_owner(self):
        self.store.create_memory_candidate(self.candidate())

        with self.assertRaisesRegex(ValueError, "reviewer"):
            self.store.review_memory_candidate(
                "habit-1", decision="APPROVED", reviewed_by="  "
            )

        self.assertEqual("PROPOSED", self.store.get_memory_candidate("habit-1")["status"])

    def test_operating_practices_share_the_model_context_character_budget(self):
        oversized = self.candidate(statement="证" * 2_001)
        with self.assertRaisesRegex(ValueError, "statement"):
            validate_memory_candidate(oversized)

        with self.assertRaisesRegex(ValueError, "context budget"):
            from personal_ai_os.secretary import build_context_pack

            build_context_pack(
                {
                    "task_id": "writing:large-context",
                    "title": "边界测试",
                    "context": {"model_context": {"material": "文" * 8_000}},
                },
                {
                    "domain_id": "writing",
                    "operating_practices": ["规" * 5_000],
                    "practice_evidence_refs": ["artifact:accepted"],
                },
            )

        approved = [
            {
                **self.candidate(candidate_id=f"habit-{index}"),
                "status": "APPROVED",
            }
            for index in range(33)
        ]
        with self.assertRaisesRegex(ValueError, "rule limit"):
            compile_operating_practices(
                approved,
                subject={"kind": "person", "id": "writer-a"},
                domain_id="writing",
            )

    def test_only_approved_scoped_practices_reach_the_execution_context(self):
        self.store.create_workflow({
            "workflow_id": "writing",
            "name": "写作线",
            "caption": "受控风格加载",
            "layout": "pipeline",
            "goal": "形成可复核文本",
            "domain_id": "writing",
        })
        self.store.create_task({
            "task_id": "writing:draft",
            "workflow_id": "writing",
            "title": "形成初稿",
            "acceptance": "结构和证据对应",
            "context": {
                "model_context": {
                    "practice_subject": {"kind": "person", "id": "writer-a"}
                }
            },
        })
        self.store.create_memory_candidate(self.candidate())
        adapter = CaptureAdapter()

        ExecutionBroker(self.store, {adapter.adapter_id: adapter}).dispatch(
            "writing:draft", adapter_id=adapter.adapter_id, model="model-a"
        )
        self.assertEqual([], adapter.context_packs[0]["operating_practices"])

        self.store.create_task({
            "task_id": "writing:revision",
            "workflow_id": "writing",
            "title": "修订初稿",
            "acceptance": "修订遵循已确认工作方式",
            "context": {
                "model_context": {
                    "practice_subject": {"kind": "person", "id": "writer-a"}
                }
            },
        })
        self.store.review_memory_candidate("habit-1", decision="APPROVED", reviewed_by="owner")
        ExecutionBroker(self.store, {adapter.adapter_id: adapter}).dispatch(
            "writing:revision", adapter_id=adapter.adapter_id, model="model-a"
        )

        self.assertEqual(["先列出证据，再形成判断。"], adapter.context_packs[1]["operating_practices"])

    def test_oversized_practice_context_is_rejected_before_run_claim(self):
        self.store.create_workflow({
            "workflow_id": "writing",
            "name": "写作线",
            "caption": "受控风格加载",
            "layout": "pipeline",
            "goal": "形成可复核文本",
            "domain_id": "writing",
        })
        self.store.create_task({
            "task_id": "writing:oversized-practices",
            "workflow_id": "writing",
            "title": "形成初稿",
            "acceptance": "上下文预算必须在执行前核验",
            "context": {
                "model_context": {
                    "practice_subject": {"kind": "person", "id": "writer-a"}
                }
            },
        })
        for index in range(7):
            candidate_id = f"large-habit-{index}"
            self.store.create_memory_candidate(self.candidate(
                candidate_id=candidate_id,
                statement="规" * 2_000,
            ))
            self.store.review_memory_candidate(
                candidate_id, decision="APPROVED", reviewed_by="owner"
            )
        adapter = CaptureAdapter()

        result = ExecutionBroker(
            self.store, {adapter.adapter_id: adapter}
        ).dispatch(
            "writing:oversized-practices",
            adapter_id=adapter.adapter_id,
            model="model-a",
        )
        snapshot = self.store.snapshot()

        self.assertFalse(result["ok"])
        self.assertEqual("CONTEXT_BUDGET_EXCEEDED", result["reason"])
        self.assertEqual([], adapter.context_packs)
        self.assertEqual("QUEUED", self.store.get_task("writing:oversized-practices")["status"])
        self.assertEqual([], snapshot["runs"])
        self.assertNotIn(
            "ADAPTER_STARTED",
            [event["event_type"] for event in snapshot["events"]],
        )

    def test_required_memory_policy_fails_closed_before_run_claim_without_scope(self):
        self.store.create_workflow({
            "workflow_id": "writing",
            "name": "写作线",
            "caption": "受控记忆读取",
            "layout": "pipeline",
            "goal": "形成可复核文本",
            "domain_id": "writing",
        })
        self.store.create_task({
            "task_id": "writing:missing-memory-scope",
            "workflow_id": "writing",
            "title": "形成初稿",
            "acceptance": "运行前必须读取已确认工作方式",
            "context": {"memory_policy": "require_read"},
        })
        adapter = CaptureAdapter()

        result = ExecutionBroker(
            self.store, {adapter.adapter_id: adapter}
        ).dispatch(
            "writing:missing-memory-scope",
            adapter_id=adapter.adapter_id,
            model="model-a",
        )

        self.assertFalse(result["ok"])
        self.assertEqual("MEMORY_SCOPE_REQUIRED", result["reason"])
        self.assertEqual("QUEUED", self.store.get_task("writing:missing-memory-scope")["status"])
        self.assertEqual([], self.store.snapshot()["runs"])
        self.assertEqual([], adapter.context_packs)

    def test_required_memory_policy_exposes_approved_refs_and_only_requests_review(self):
        self.store.create_workflow({
            "workflow_id": "writing",
            "name": "写作线",
            "caption": "受控记忆读取",
            "layout": "pipeline",
            "goal": "形成可复核文本",
            "domain_id": "writing",
        })
        self.store.create_task({
            "task_id": "writing:memory-aware",
            "workflow_id": "writing",
            "title": "形成初稿",
            "acceptance": "运行前必须读取已确认工作方式",
            "context": {
                "memory_policy": "require_read",
                "memory_subject": {"kind": "person", "id": "writer-a"},
                "memory_domain_id": "writing",
            },
        })
        self.store.create_memory_candidate(self.candidate())
        self.store.review_memory_candidate("habit-1", decision="APPROVED", reviewed_by="owner")
        adapter = CaptureAdapter()

        result = ExecutionBroker(
            self.store, {adapter.adapter_id: adapter}
        ).dispatch(
            "writing:memory-aware", adapter_id=adapter.adapter_id, model="model-a"
        )

        self.assertTrue(result["ok"])
        context_pack = adapter.context_packs[0]
        self.assertEqual(["habit-1"], context_pack["approved_practice_refs"])
        self.assertEqual(["先列出证据，再形成判断。"], context_pack["operating_practices"])
        events = self.store.snapshot()["events"]
        memory_events = [item for item in events if item["event_type"] == "MEMORY_REVIEW_REQUESTED"]
        self.assertEqual(1, len(memory_events))
        self.assertEqual("require_read", memory_events[0]["payload"]["memory_policy"])
        self.assertEqual(["habit-1"], memory_events[0]["payload"]["approved_practice_refs"])
        self.assertEqual("APPROVED", self.store.get_memory_candidate("habit-1")["status"])


if __name__ == "__main__":
    unittest.main()
