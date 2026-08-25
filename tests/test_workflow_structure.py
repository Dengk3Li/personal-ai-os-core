from __future__ import annotations

import unittest

from personal_ai_os import (
    compile_workflow_structure,
    evaluate_workflow_structure,
)


def _task(node_id: str) -> dict[str, object]:
    return {"node_id": node_id, "kind": "task", "task_id": node_id}


class WorkflowStructureTests(unittest.TestCase):
    def test_sequence_and_branch_release_deterministic_leaf_tasks(self) -> None:
        structure = {
            "schema_version": "personal-ai-os.workflow-structure/v1",
            "root": {
                "node_id": "root",
                "kind": "sequence",
                "children": [
                    _task("scope"),
                    {
                        "node_id": "paths",
                        "kind": "branch",
                        "children": [_task("path-a"), _task("path-b")],
                    },
                    {
                        "node_id": "merge",
                        "kind": "join",
                        "policy": "all",
                        "children": [_task("analysis-a"), _task("analysis-b")],
                    },
                ],
            },
        }

        compiled = compile_workflow_structure(structure)
        self.assertEqual("READY", compiled["status"])
        first = evaluate_workflow_structure(compiled, {})
        self.assertEqual(["scope"], first["ready_task_ids"])

        branched = evaluate_workflow_structure(compiled, {"scope": "DONE"})
        self.assertEqual(["path-a", "path-b"], branched["ready_task_ids"])

    def test_if_waits_for_a_registered_predicate_and_selects_one_branch(self) -> None:
        structure = {
            "schema_version": "personal-ai-os.workflow-structure/v1",
            "root": {
                "node_id": "quality-check",
                "kind": "if",
                "condition_ref": "evidence.sufficient",
                "branches": {"true": _task("write"), "false": _task("collect-more")},
            },
        }
        compiled = compile_workflow_structure(structure)

        waiting = evaluate_workflow_structure(compiled, {}, predicates={})
        self.assertEqual([], waiting["ready_task_ids"])
        self.assertEqual(["quality-check"], waiting["waiting_decision_ids"])

        selected = evaluate_workflow_structure(
            compiled, {}, predicates={"evidence.sufficient": True}
        )
        self.assertEqual(["write"], selected["ready_task_ids"])

    def test_join_all_and_any_release_the_next_sequence_step(self) -> None:
        join_all = compile_workflow_structure(
            {
                "schema_version": "personal-ai-os.workflow-structure/v1",
                "root": {
                    "node_id": "merge-all",
                    "kind": "join",
                    "policy": "all",
                    "children": [_task("path-a"), _task("path-b")],
                },
            }
        )
        waiting_all = evaluate_workflow_structure(
            join_all, {"path-a": "DONE", "path-b": "QUEUED"}
        )
        self.assertEqual(["path-b"], waiting_all["ready_task_ids"])
        self.assertFalse(waiting_all["complete"])

        sequence_with_any = compile_workflow_structure(
            {
                "schema_version": "personal-ai-os.workflow-structure/v1",
                "root": {
                    "node_id": "root",
                    "kind": "sequence",
                    "children": [
                        {
                            "node_id": "merge-any",
                            "kind": "join",
                            "policy": "any",
                            "children": [_task("source-a"), _task("source-b")],
                        },
                        _task("next-step"),
                    ],
                },
            }
        )
        released = evaluate_workflow_structure(
            sequence_with_any,
            {"source-a": "DONE", "source-b": "QUEUED"},
        )
        self.assertEqual(["next-step"], released["ready_task_ids"])

    def test_loop_is_bounded_and_never_evaluates_arbitrary_code(self) -> None:
        structure = {
            "schema_version": "personal-ai-os.workflow-structure/v1",
            "root": {
                "node_id": "research-loop",
                "kind": "loop",
                "continue_condition_ref": "research.needs_next_round",
                "max_iterations": 3,
                "body": _task("experiment"),
            },
        }
        compiled = compile_workflow_structure(structure)
        active = evaluate_workflow_structure(
            compiled,
            {},
            predicates={"research.needs_next_round": True},
            loop_iterations={"research-loop": 2},
        )
        self.assertEqual(["experiment"], active["ready_task_ids"])

        stopped = evaluate_workflow_structure(
            compiled,
            {},
            predicates={"research.needs_next_round": True},
            loop_iterations={"research-loop": 3},
        )
        self.assertEqual([], stopped["ready_task_ids"])
        self.assertTrue(stopped["complete"])

        repeat = evaluate_workflow_structure(
            compiled,
            {"experiment": "DONE"},
            predicates={"research.needs_next_round": True},
            loop_iterations={"research-loop": 2},
        )
        self.assertFalse(repeat["complete"])
        self.assertEqual(["research-loop"], repeat["repeat_loop_ids"])

        malicious = {
            **structure,
            "root": {
                **structure["root"],
                "continue_condition_ref": "__import__('os').system('echo unsafe')",
            },
        }
        with self.assertRaisesRegex(ValueError, "registered predicate"):
            compile_workflow_structure(malicious)

    def test_duplicate_ids_and_unbounded_loops_fail_before_execution(self) -> None:
        duplicate = {
            "schema_version": "personal-ai-os.workflow-structure/v1",
            "root": {
                "node_id": "root",
                "kind": "branch",
                "children": [_task("same"), _task("same")],
            },
        }
        with self.assertRaisesRegex(ValueError, "duplicate workflow node"):
            compile_workflow_structure(duplicate)

        unbounded = {
            "schema_version": "personal-ai-os.workflow-structure/v1",
            "root": {
                "node_id": "loop",
                "kind": "loop",
                "continue_condition_ref": "research.more",
                "body": _task("task"),
            },
        }
        with self.assertRaisesRegex(ValueError, "max_iterations"):
            compile_workflow_structure(unbounded)

        duplicate_task = {
            "schema_version": "personal-ai-os.workflow-structure/v1",
            "root": {
                "node_id": "root",
                "kind": "branch",
                "children": [
                    {"node_id": "path-a", "kind": "task", "task_id": "same-task"},
                    {"node_id": "path-b", "kind": "task", "task_id": "same-task"},
                ],
            },
        }
        with self.assertRaisesRegex(ValueError, "duplicate workflow task"):
            compile_workflow_structure(duplicate_task)

    def test_non_boolean_conditions_and_invalid_loop_counters_fail_closed(self) -> None:
        conditional = compile_workflow_structure(
            {
                "schema_version": "personal-ai-os.workflow-structure/v1",
                "root": {
                    "node_id": "quality-check",
                    "kind": "if",
                    "condition_ref": "evidence.sufficient",
                    "branches": {
                        "true": _task("write"),
                        "false": _task("collect-more"),
                    },
                },
            }
        )
        waiting = evaluate_workflow_structure(
            conditional,
            {},
            predicates={"evidence.sufficient": "yes"},
        )
        self.assertEqual(["quality-check"], waiting["waiting_decision_ids"])
        self.assertEqual([], waiting["ready_task_ids"])

        loop = compile_workflow_structure(
            {
                "schema_version": "personal-ai-os.workflow-structure/v1",
                "root": {
                    "node_id": "research-loop",
                    "kind": "loop",
                    "continue_condition_ref": "research.more",
                    "max_iterations": 3,
                    "body": _task("experiment"),
                },
            }
        )
        waiting_loop = evaluate_workflow_structure(
            loop,
            {},
            predicates={"research.more": 1},
        )
        self.assertEqual(["research-loop"], waiting_loop["waiting_decision_ids"])

        for invalid in (True, -1, "1", 4):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "loop iteration"):
                    evaluate_workflow_structure(
                        loop,
                        {},
                        predicates={"research.more": True},
                        loop_iterations={"research-loop": invalid},
                    )


if __name__ == "__main__":
    unittest.main()
