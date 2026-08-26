import json
import tempfile
import unittest
from pathlib import Path

import personal_ai_os
from personal_ai_os.runtime import ExecutionBroker, RuntimeStore, install_workflow_preset


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
            "external_run_id": "protocol-run-1",
            "status": "SUCCEEDED",
            "output_text": "protocol-aware result",
            "usage": {"input_tokens": 20, "output_tokens": 10},
        }


class WorkProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "runtime.db"

    def tearDown(self):
        self.temp.cleanup()

    def test_catalog_loader_rejects_secrets_and_normalizes_protocols(self):
        payload = {
            "schema_version": "personal-ai-os.work-protocols/v1",
            "protocols": [
                {
                    "protocol_id": "meeting-source-first-v1",
                    "name": "完整会议记录",
                    "domain_id": "professional",
                    "workflow_ids": ["meeting-notes"],
                    "instruction_refs": ["instruction://meeting/source-first"],
                    "template_refs": ["template://meeting/full-record-v3"],
                    "rules": ["原始逐字记录是事实来源", "保留完整结构，不降级为精简摘要"],
                    "memory_subject": {"kind": "team", "id": "meeting-notes"},
                    "learning_review": "candidate",
                }
            ],
        }
        source = Path(self.temp.name) / "protocols.json"
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        catalog = personal_ai_os.load_work_protocols(source)

        self.assertEqual("meeting-source-first-v1", catalog[0]["protocol_id"])
        self.assertEqual("candidate", catalog[0]["learning_review"])
        payload["protocols"][0]["api_key"] = "secret"
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "forbidden"):
            personal_ai_os.load_work_protocols(source)

        del payload["protocols"][0]["api_key"]
        for secret in (
            "api_key=" + "sk-" + ("x" * 24),
            "ghp_" + ("x" * 32),
            "client_secret=" + ("x" * 24),
            "-----BEGIN PRIVATE KEY-----",
            "https://user:password@example.invalid/api",
            "postgresql://user:password@example.invalid/db",
        ):
            payload["protocols"][0]["rules"] = [secret]
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sensitive"):
                personal_ai_os.load_work_protocols(source)

        payload["protocols"][0]["rules"] = ["保留完整会议结构"]
        payload["protocols"][0]["api_key"] = "sk-direct-constructor-secret"
        with self.assertRaisesRegex(ValueError, "forbidden"):
            ExecutionBroker(RuntimeStore(self.database), {}, work_protocols=payload["protocols"])

    def test_meeting_preset_loads_required_protocol_before_adapter_start(self):
        store = RuntimeStore(self.database)
        install_workflow_preset(store, "meeting-notes")
        store.create_memory_candidate(
            {
                "schema_version": "personal-ai-os.memory-candidate/v1",
                "candidate_id": "meeting-practice-1",
                "subject": {"kind": "team", "id": "meeting-notes"},
                "domain_id": "writing",
                "category": "workflow",
                "statement": "先核对逐字记录，再整理正文。",
                "evidence_refs": ["artifact://reviewed-meeting-1"],
                "sample_count": 3,
                "privacy_class": "team",
            }
        )
        store.review_memory_candidate(
            "meeting-practice-1", decision="APPROVED", reviewed_by="owner"
        )
        adapter = CaptureAdapter()
        broker = ExecutionBroker(
            store,
            {adapter.adapter_id: adapter},
            work_protocols=personal_ai_os.work_protocol_catalog(),
        )

        result = broker.dispatch(
            "notes:intake", adapter_id=adapter.adapter_id, model="model-a"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            "meeting-source-first-v1",
            store.get_workflow("meeting-notes")["protocol_id"],
        )
        protocol = adapter.context_packs[0]["work_protocol"]
        self.assertEqual("meeting-source-first-v1", protocol["protocol_id"])
        self.assertEqual("candidate", protocol["learning_review"])
        self.assertIn("原始逐字记录", "".join(protocol["rules"]))
        self.assertTrue(protocol["template_refs"])
        self.assertEqual(
            ["先核对逐字记录，再整理正文。"],
            adapter.context_packs[0]["operating_practices"],
        )
        self.assertEqual(
            1,
            sum(
                event["event_type"] == "MEMORY_REVIEW_REQUESTED"
                for event in store.snapshot()["events"]
            ),
        )
        review_event = next(
            event
            for event in store.snapshot()["events"]
            if event["event_type"] == "MEMORY_REVIEW_REQUESTED"
        )
        self.assertEqual("CANDIDATE", review_event["payload"]["candidate"]["status"])
        self.assertEqual("notes:intake", review_event["payload"]["candidate"]["source_task_id"])
        self.assertEqual(
            store.snapshot()["runs"][0]["run_id"],
            review_event["payload"]["candidate"]["source_run_id"],
        )
        self.assertFalse(review_event["payload"]["candidate"]["promotion"]["authorized"])
        self.assertNotIn("memory_read_status", review_event["payload"])

    def test_missing_required_protocol_blocks_before_run_claim(self):
        store = RuntimeStore(self.database)
        store.create_workflow(
            {
                "workflow_id": "private-meeting",
                "name": "会议工作线",
                "caption": "",
                "layout": "milestones",
                "goal": "形成会议记录",
                "domain_id": "professional",
                "protocol_id": "private-meeting-v3",
            }
        )
        store.create_task(
            {
                "task_id": "private-meeting:intake",
                "workflow_id": "private-meeting",
                "title": "读取会议材料",
                "acceptance": "来源可追溯",
            }
        )
        adapter = CaptureAdapter()
        broker = ExecutionBroker(store, {adapter.adapter_id: adapter})

        result = broker.dispatch(
            "private-meeting:intake",
            adapter_id=adapter.adapter_id,
            model="model-a",
        )

        self.assertFalse(result["ok"])
        self.assertEqual("WORK_PROTOCOL_REQUIRED", result["reason"])
        self.assertEqual([], adapter.context_packs)
        self.assertEqual([], store.snapshot()["runs"])
        self.assertEqual("QUEUED", store.get_task("private-meeting:intake")["status"])

    def test_protocol_cannot_cross_its_declared_workflow_or_domain(self):
        store = RuntimeStore(self.database)
        store.create_workflow(
            {
                "workflow_id": "other-writing",
                "name": "其他写作线",
                "caption": "",
                "layout": "milestones",
                "goal": "形成文稿",
                "domain_id": "writing",
                "protocol_id": "meeting-source-first-v1",
            }
        )
        store.create_task(
            {
                "task_id": "other-writing:draft",
                "workflow_id": "other-writing",
                "title": "形成文稿",
                "acceptance": "内容可核对",
                "domain_id": "writing",
            }
        )
        adapter = CaptureAdapter()

        result = ExecutionBroker(store, {adapter.adapter_id: adapter}).dispatch(
            "other-writing:draft", adapter_id=adapter.adapter_id, model="model-a"
        )

        self.assertEqual("WORK_PROTOCOL_SCOPE_MISMATCH", result["reason"])
        self.assertEqual([], store.snapshot()["runs"])
        self.assertEqual([], adapter.context_packs)

    def test_protocol_memory_subject_cannot_be_overridden_by_one_task(self):
        store = RuntimeStore(self.database)
        install_workflow_preset(store, "meeting-notes")
        store.create_task(
            {
                "task_id": "notes:override",
                "workflow_id": "meeting-notes",
                "title": "整理会议正文",
                "acceptance": "遵循已确认的会议规范",
                "context": {
                    "model_context": {
                        "practice_subject": {"kind": "person", "id": "other"}
                    }
                },
            }
        )
        adapter = CaptureAdapter()

        result = ExecutionBroker(store, {adapter.adapter_id: adapter}).dispatch(
            "notes:override", adapter_id=adapter.adapter_id, model="model-a"
        )

        self.assertEqual("WORK_PROTOCOL_MEMORY_SCOPE_MISMATCH", result["reason"])
        self.assertEqual("writing", store.get_task("notes:override")["domain_id"])
        self.assertEqual([], store.snapshot()["runs"])
        self.assertEqual([], adapter.context_packs)


if __name__ == "__main__":
    unittest.main()
