import unittest

import personal_ai_os


TASKS = [
    {
        "task_id": "scope",
        "title": "Define the research question",
        "acceptance": "One bounded question is recorded",
        "depends_on": [],
        "parent_id": None,
        "human_gate": True,
    },
    {
        "task_id": "evidence",
        "title": "Build the evidence map",
        "acceptance": "Each claim has a source",
        "depends_on": ["scope"],
        "parent_id": "scope",
        "human_gate": False,
    },
    {
        "task_id": "draft",
        "title": "Draft the review",
        "acceptance": "The draft covers the accepted outline",
        "depends_on": ["evidence"],
        "parent_id": "scope",
        "human_gate": False,
    },
]


class LongTaskPlanningTests(unittest.TestCase):
    def test_valid_plan_becomes_a_human_review_candidate(self):
        validate_plan = getattr(personal_ai_os, "validate_plan", None)
        self.assertTrue(callable(validate_plan), "validate_plan must be public")

        plan = validate_plan("Write a source-grounded research review", TASKS)

        self.assertEqual("CANDIDATE", plan["status"])
        self.assertEqual("READY_FOR_HUMAN_REVIEW", plan["validation_status"])
        self.assertEqual(3, plan["summary"]["task_count"])
        self.assertEqual(1, plan["summary"]["human_gate_count"])
        self.assertEqual([], plan["findings"])

    def test_missing_dependency_and_cycles_fail_closed(self):
        validate_plan = getattr(personal_ai_os, "validate_plan", None)
        self.assertTrue(callable(validate_plan), "validate_plan must be public")
        missing = [{**TASKS[0], "depends_on": ["unknown"]}]
        cyclic = [
            {**TASKS[0], "depends_on": ["evidence"]},
            {**TASKS[1], "depends_on": ["scope"]},
        ]

        missing_result = validate_plan("Research task", missing)
        cyclic_result = validate_plan("Research task", cyclic)

        self.assertEqual("BLOCKED", missing_result["status"])
        self.assertIn("MISSING_DEPENDENCY", [item["code"] for item in missing_result["findings"]])
        self.assertEqual("BLOCKED", cyclic_result["status"])
        self.assertIn("DEPENDENCY_CYCLE", [item["code"] for item in cyclic_result["findings"]])

    def test_parent_cycles_block_an_unrenderable_hierarchy(self):
        validate_plan = getattr(personal_ai_os, "validate_plan", None)
        self.assertTrue(callable(validate_plan), "validate_plan must be public")
        tasks = [
            {**TASKS[0], "parent_id": "evidence"},
            {**TASKS[1], "parent_id": "scope", "depends_on": []},
        ]

        result = validate_plan("Research task", tasks)

        self.assertEqual("BLOCKED", result["status"])
        self.assertIn("PARENT_CYCLE", [item["code"] for item in result["findings"]])

    def test_only_accepted_ready_and_human_cleared_tasks_can_run(self):
        validate_plan = getattr(personal_ai_os, "validate_plan", None)
        ready_tasks = getattr(personal_ai_os, "ready_tasks", None)
        self.assertTrue(callable(validate_plan), "validate_plan must be public")
        self.assertTrue(callable(ready_tasks), "ready_tasks must be public")
        candidate = validate_plan("Write a research review", TASKS)
        states = {task["task_id"]: "QUEUED" for task in TASKS}

        before_plan_acceptance = ready_tasks(candidate, states, {})
        before_human_decision = ready_tasks(
            {**candidate, "status": "ACCEPTED"}, states, {}
        )
        after_human_decision = ready_tasks(
            {**candidate, "status": "ACCEPTED"},
            states,
            {"scope": "APPROVED"},
        )
        after_first_task = ready_tasks(
            {**candidate, "status": "ACCEPTED"},
            {**states, "scope": "DONE"},
            {"scope": "APPROVED"},
        )

        self.assertEqual([], before_plan_acceptance)
        self.assertEqual([], before_human_decision)
        self.assertEqual(["scope"], [task["task_id"] for task in after_human_decision])
        self.assertEqual(["evidence"], [task["task_id"] for task in after_first_task])

    def test_changing_status_cannot_bypass_failed_plan_validation(self):
        validate_plan = getattr(personal_ai_os, "validate_plan", None)
        ready_tasks = getattr(personal_ai_os, "ready_tasks", None)
        self.assertTrue(callable(validate_plan), "validate_plan must be public")
        self.assertTrue(callable(ready_tasks), "ready_tasks must be public")
        blocked = validate_plan(
            "Research task",
            [{**TASKS[0], "acceptance": ""}],
        )

        result = ready_tasks(
            {**blocked, "status": "ACCEPTED"},
            {"scope": "QUEUED"},
            {"scope": "APPROVED"},
        )

        self.assertEqual([], result)

    def test_projection_keeps_hierarchy_progress_and_operating_lanes_together(self):
        validate_plan = getattr(personal_ai_os, "validate_plan", None)
        project_plan = getattr(personal_ai_os, "project_plan", None)
        self.assertTrue(callable(validate_plan), "validate_plan must be public")
        self.assertTrue(callable(project_plan), "project_plan must be public")
        plan = {**validate_plan("Write a research review", TASKS), "status": "ACCEPTED"}

        projection = project_plan(
            plan,
            {"scope": "DONE", "evidence": "IN_PROGRESS", "draft": "QUEUED"},
            {"evidence": {"executor": "worker:research", "route": "standard"}},
        )

        self.assertEqual({"done": 1, "total": 3, "percent": 33}, projection["progress"])
        self.assertEqual(["evidence"], projection["lanes"]["IN_PROGRESS"])
        self.assertEqual("scope", projection["hierarchy"][0]["task_id"])
        self.assertEqual(
            ["evidence", "draft"],
            [child["task_id"] for child in projection["hierarchy"][0]["children"]],
        )
        self.assertEqual("worker:research", projection["cards"]["evidence"]["executor"])


if __name__ == "__main__":
    unittest.main()
