import copy
import unittest

from personal_ai_os.memory_context import (
    BLOCKED,
    MEMORY_REVIEW_REQUESTED,
    READY,
    SKIPPED,
    read_memory_context,
    request_memory_review,
)


def task(**overrides):
    context = {
        "memory_policy": "require_read",
        "memory_refs": ["practice-1"],
        "memory_subject": {"kind": "person", "id": "writer-a"},
        "memory_domain_id": "writing",
    }
    context.update(overrides)
    return {"task_id": "writing:brief", "domain_id": "writing", "context": context}


def registered_refs():
    return {
        "practice-1": {
            "memory_id": "practice-1",
            "title": "写作习惯",
            "status": "APPROVED",
            "subject": {"kind": "person", "id": "writer-a"},
            "domain_id": "writing",
            "source_ref": "memory://writing/practice-1",
            "facts": ["先列证据，再形成判断。"],
            "decisions": ["保留人工复核。"],
        },
        "other-domain": {
            "memory_id": "other-domain",
            "status": "APPROVED",
            "subject": {"kind": "person", "id": "writer-a"},
            "domain_id": "research",
            "source_ref": "memory://research/other-domain",
            "facts": ["不应进入写作任务。"],
        },
    }


class MemoryContextTests(unittest.TestCase):
    def test_required_read_needs_explicit_memory_references(self):
        result = read_memory_context(task(memory_refs=[]), registered_refs=registered_refs())

        self.assertEqual(BLOCKED, result["status"])
        self.assertEqual("MEMORY_REFS_REQUIRED", result["reason"])
        self.assertEqual([], result["entries"])

    def test_scope_must_match_task_domain(self):
        result = read_memory_context(
            task(memory_domain_id="research"), registered_refs=registered_refs()
        )

        self.assertEqual(BLOCKED, result["status"])
        self.assertEqual("MEMORY_SCOPE_MISMATCH", result["reason"])

    def test_only_requested_scoped_reference_is_projected(self):
        result = read_memory_context(task(), registered_refs=registered_refs())

        self.assertEqual(READY, result["status"])
        self.assertEqual(["practice-1"], result["memory_ref_ids"])
        self.assertEqual(["先列证据，再形成判断。"], result["entries"][0]["facts"])
        self.assertNotIn("other-domain", str(result))
        self.assertNotIn("facts", result["entries"][0].get("raw", {}))

    def test_reference_must_be_approved_and_source_bound(self):
        refs = registered_refs()
        refs["practice-1"]["status"] = "PROPOSED"
        result = read_memory_context(task(), registered_refs=refs)

        self.assertEqual(BLOCKED, result["status"])
        self.assertEqual("MEMORY_REF_NOT_APPROVED", result["reason"])

    def test_active_reference_is_not_approved_for_execution(self):
        refs = registered_refs()
        refs["practice-1"]["status"] = "ACTIVE"
        result = read_memory_context(task(), registered_refs=refs)

        self.assertEqual(BLOCKED, result["status"])
        self.assertEqual("MEMORY_REF_NOT_APPROVED", result["reason"])

    def test_context_budget_fails_closed(self):
        refs = registered_refs()
        refs["practice-1"]["facts"] = ["证" * 8_001]

        result = read_memory_context(task(), registered_refs=refs)

        self.assertEqual(BLOCKED, result["status"])
        self.assertEqual("MEMORY_CONTEXT_TOO_LARGE", result["reason"])
        self.assertEqual([], result["entries"])

    def test_non_memory_task_is_explicitly_skipped(self):
        result = read_memory_context(
            {"task_id": "writing:brief", "domain_id": "writing", "context": {}},
            registered_refs=registered_refs(),
        )

        self.assertEqual(SKIPPED, result["status"])
        self.assertEqual([], result["entries"])

    def test_successful_read_can_only_create_a_review_candidate(self):
        execution = {
            "run_id": "run-1",
            "status": "SUCCEEDED",
            "memory_read_status": READY,
            "memory_ref_ids": ["practice-1"],
        }
        before = copy.deepcopy(execution)

        result = request_memory_review(
            task(),
            execution,
            observation="本轮沿用了已确认的写作顺序。",
            observed_at="2026-08-26T00:00:00Z",
        )

        self.assertEqual(MEMORY_REVIEW_REQUESTED, result["event_type"])
        self.assertEqual("CANDIDATE", result["candidate"]["status"])
        self.assertFalse(result["candidate"]["promotion"]["authorized"])
        self.assertEqual("NOT_REQUESTED", result["candidate"]["promotion"]["status"])
        self.assertEqual(before, execution)


if __name__ == "__main__":
    unittest.main()
