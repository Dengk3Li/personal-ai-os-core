import unittest

import personal_ai_os


ROUTES = [
    {
        "route": "quick",
        "tier": "quick",
        "available": True,
        "capabilities": ["writing"],
        "max_context_tokens": 64000,
    },
    {
        "route": "standard",
        "tier": "standard",
        "available": True,
        "capabilities": ["writing", "research"],
        "max_context_tokens": 160000,
    },
    {
        "route": "deep",
        "tier": "deep",
        "available": True,
        "capabilities": ["writing", "research", "code"],
        "max_context_tokens": 240000,
    },
]


class DynamicDispatchTests(unittest.TestCase):
    def test_batch_dispatch_allows_non_conflicting_tasks_inside_one_domain(self):
        select_dispatch_batch = getattr(personal_ai_os, "select_dispatch_batch", None)
        self.assertTrue(callable(select_dispatch_batch), "select_dispatch_batch must be public")
        result = select_dispatch_batch([
            {"task_id": "R-1", "domain_id": "research", "status": "QUEUED",
             "dispatch_ready": True, "resource_locks": ["path:research/data"]},
            {"task_id": "R-2", "domain_id": "research", "status": "QUEUED",
             "dispatch_ready": True, "resource_locks": ["path:research/report"]},
        ])

        self.assertEqual("READY", result["status"])
        self.assertEqual(["R-1", "R-2"], [item["task_id"] for item in result["selected"]])
        self.assertEqual(5, result["global_limit"])
        self.assertTrue(all(item["acquisition"] == "ATOMIC_SORTED"
                            for item in result["selected"]))

    def test_batch_dispatch_blocks_path_overlap_and_unknown_active_resources(self):
        select_dispatch_batch = getattr(personal_ai_os, "select_dispatch_batch", None)
        active = [{"task_id": "ACTIVE", "state": "running",
                   "resource_locks": ["path:research/data"]}]
        conflict = select_dispatch_batch([
            {"task_id": "NEXT", "domain_id": "research", "status": "QUEUED",
             "dispatch_ready": True, "resource_locks": ["path:research/data/raw"]},
        ], active_tasks=active)
        unknown = select_dispatch_batch([
            {"task_id": "NEXT", "domain_id": "research", "status": "QUEUED",
             "dispatch_ready": True, "resource_locks": ["path:research/report"]},
        ], active_tasks=[{"task_id": "ACTIVE", "state": "running"}])

        self.assertEqual(["NEXT"], conflict["blocked_task_ids"])
        self.assertEqual("UNKNOWN", unknown["status"])
        self.assertEqual("ACTIVE_RESOURCE_UNKNOWN", unknown["reason"])

    def test_auto_route_selects_the_smallest_capable_context_window(self):
        select_execution_route = getattr(personal_ai_os, "select_execution_route", None)
        self.assertTrue(callable(select_execution_route), "select_execution_route must be public")
        task = {
            "task_id": "evidence",
            "complexity": "standard",
            "required_capabilities": ["research"],
            "estimated_context_tokens": 80000,
        }

        result = select_execution_route(task, ROUTES)

        self.assertEqual("RESOLVED", result["status"])
        self.assertEqual("standard", result["route"])
        self.assertEqual(160000, result["max_context_tokens"])

    def test_unavailable_route_falls_forward_without_lowering_requirements(self):
        select_execution_route = getattr(personal_ai_os, "select_execution_route", None)
        self.assertTrue(callable(select_execution_route), "select_execution_route must be public")
        routes = [{**ROUTES[0], "available": False}, *ROUTES[1:]]

        result = select_execution_route(
            {
                "task_id": "draft",
                "complexity": "quick",
                "required_capabilities": ["writing"],
                "estimated_context_tokens": 12000,
            },
            routes,
        )

        self.assertEqual("standard", result["route"])

    def test_manual_override_cannot_bypass_task_requirements(self):
        select_execution_route = getattr(personal_ai_os, "select_execution_route", None)
        self.assertTrue(callable(select_execution_route), "select_execution_route must be public")

        result = select_execution_route(
            {
                "task_id": "synthesis",
                "complexity": "deep",
                "required_capabilities": ["research"],
                "estimated_context_tokens": 120000,
            },
            ROUTES,
            requested_route="quick",
        )

        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("ROUTE_REQUIREMENTS_NOT_MET", result["reason"])

    def test_assignment_prefers_a_compatible_executor_with_free_capacity(self):
        assign_task = getattr(personal_ai_os, "assign_task", None)
        self.assertTrue(callable(assign_task), "assign_task must be public")
        task = {"task_id": "evidence", "required_capabilities": ["research"]}
        route = {"status": "RESOLVED", "route": "standard"}
        executors = [
            {
                "executor": "worker:busy",
                "capabilities": ["research"],
                "supported_routes": ["standard"],
                "active_tasks": 2,
                "capacity": 2,
            },
            {
                "executor": "worker:research",
                "capabilities": ["research", "writing"],
                "supported_routes": ["standard", "deep"],
                "active_tasks": 0,
                "capacity": 1,
            },
        ]

        result = assign_task(task, route, executors)

        self.assertEqual("ASSIGNED", result["status"])
        self.assertEqual("worker:research", result["executor"])
        self.assertEqual("standard", result["route"])

    def test_no_compatible_capacity_stays_waiting_for_assignment(self):
        assign_task = getattr(personal_ai_os, "assign_task", None)
        self.assertTrue(callable(assign_task), "assign_task must be public")

        result = assign_task(
            {"task_id": "evidence", "required_capabilities": ["research"]},
            {"status": "RESOLVED", "route": "standard"},
            [
                {
                    "executor": "worker:writer",
                    "capabilities": ["writing"],
                    "supported_routes": ["standard"],
                    "active_tasks": 0,
                    "capacity": 1,
                }
            ],
        )

        self.assertEqual("WAITING_ASSIGNMENT", result["status"])
        self.assertEqual("NO_COMPATIBLE_CAPACITY", result["reason"])


if __name__ == "__main__":
    unittest.main()
