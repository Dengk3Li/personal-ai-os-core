import unittest

import personal_ai_os


ROUTES = [
    {
        "domain": "engineering",
        "executor": "local-agent",
        "allowed_inputs": ["source"],
        "allowed_outputs": ["candidate"],
    }
]


class DomainRoutingTests(unittest.TestCase):
    def test_explicit_route_enforces_its_input_and_output_scope(self):
        route_task = getattr(personal_ai_os, "route_task", None)
        self.assertTrue(callable(route_task), "route_task must be public")

        resolved = route_task(
            {"domain": "engineering", "inputs": ["source"], "outputs": ["candidate"]},
            ROUTES,
        )
        blocked = route_task(
            {"domain": "engineering", "inputs": ["private-memory"], "outputs": ["candidate"]},
            ROUTES,
        )
        unknown = route_task(
            {"domain": "unknown-domain", "inputs": [], "outputs": []},
            ROUTES,
        )

        self.assertEqual(
            {"status": "RESOLVED", "domain": "engineering", "executor": "local-agent"},
            resolved,
        )
        self.assertEqual("BLOCKED", blocked["status"])
        self.assertEqual("INPUT_SCOPE_VIOLATION", blocked["reason"])
        self.assertEqual({"status": "UNKNOWN", "reason": "ROUTE_NOT_FOUND"}, unknown)
