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

    def test_domain_context_manifest_loads_one_domain_in_a_fixed_minimal_order(self):
        compile_domain_context = getattr(personal_ai_os, "compile_domain_context", None)
        self.assertTrue(callable(compile_domain_context), "compile_domain_context must be public")
        profiles = [
            {
                "domain_id": "science",
                "persona": "evidence-first",
                "context_layers": {
                    "domain_contract": ["contract://science/v1"],
                    "current_state": ["state://science/current"],
                    "relevant_knowledge": ["memory://science/accepted"],
                    "constraints": ["policy://science/safety"],
                },
                "allowed_tools": ["literature-search"],
            },
            {
                "domain_id": "writing",
                "persona": "reader-first",
                "context_layers": {
                    "relevant_knowledge": ["memory://writing/style"],
                },
                "allowed_tools": ["document-editor"],
            },
        ]

        result = compile_domain_context("science", profiles)

        self.assertEqual("RESOLVED", result["status"])
        self.assertEqual("personal-ai-os.domain-context/v1", result["schema_version"])
        self.assertEqual("science", result["domain_id"])
        self.assertEqual("evidence-first", result["persona"])
        self.assertEqual(
            ["domain_contract", "current_state", "relevant_knowledge", "constraints"],
            [layer["kind"] for layer in result["load_order"]],
        )
        self.assertNotIn("memory://writing/style", str(result))

    def test_domain_context_manifest_fails_closed_on_unknown_layers_or_domains(self):
        compile_domain_context = getattr(personal_ai_os, "compile_domain_context")

        unknown = compile_domain_context("missing", [])
        blocked = compile_domain_context(
            "science",
            [{
                "domain_id": "science",
                "persona": "direct",
                "context_layers": {"entire_private_archive": ["local://everything"]},
            }],
        )

        self.assertEqual({"status": "UNKNOWN", "reason": "DOMAIN_NOT_FOUND"}, unknown)
        self.assertEqual("BLOCKED", blocked["status"])
        self.assertEqual("CONTEXT_LAYER_NOT_ALLOWED", blocked["reason"])

        ambiguous = compile_domain_context(
            "science",
            [{"domain_id": "science"}, {"domain_id": "science"}],
        )
        self.assertEqual({"status": "UNKNOWN", "reason": "DOMAIN_AMBIGUOUS"}, ambiguous)
