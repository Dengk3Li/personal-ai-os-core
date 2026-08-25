import json
import tempfile
import unittest
from pathlib import Path

import personal_ai_os


class RuntimeRouteConfigTests(unittest.TestCase):
    def write_catalog(self, directory, routes, *, schema="personal-ai-os.runtime-routes/v1"):
        path = Path(directory) / "routes.json"
        path.write_text(
            json.dumps({"schema_version": schema, "routes": routes}),
            encoding="utf-8",
        )
        return path

    def test_loader_returns_a_normalized_versioned_route_catalog(self):
        load_runtime_routes = getattr(personal_ai_os, "load_runtime_routes", None)
        self.assertTrue(callable(load_runtime_routes), "load_runtime_routes must be public")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routes.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "personal-ai-os.runtime-routes/v1",
                        "routes": [
                            {
                                "route": "standard-research",
                                "tier": "standard",
                                "capabilities": ["research", "writing"],
                                "max_context_tokens": 160000,
                                "adapter_id": "openai-compatible",
                                "model": "model-standard",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            routes = load_runtime_routes(path)

        self.assertEqual(
            [
                {
                    "route": "standard-research",
                    "tier": "standard",
                    "capabilities": ["research", "writing"],
                    "max_context_tokens": 160000,
                    "adapter_id": "openai-compatible",
                    "model": "model-standard",
                    "enabled": True,
                }
            ],
            routes,
        )

    def test_loader_rejects_an_unsupported_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_catalog(directory, [], schema="personal-ai-os.runtime-routes/v0")

            with self.assertRaisesRegex(ValueError, "unsupported runtime route schema"):
                personal_ai_os.load_runtime_routes(path)

    def test_loader_rejects_duplicate_or_incomplete_bindings(self):
        valid = {
            "route": "standard",
            "tier": "standard",
            "capabilities": ["research"],
            "max_context_tokens": 160000,
            "adapter_id": "openai-compatible",
            "model": "model-standard",
        }
        with tempfile.TemporaryDirectory() as directory:
            duplicate = self.write_catalog(directory, [valid, valid])
            with self.assertRaisesRegex(ValueError, "duplicate runtime route: standard"):
                personal_ai_os.load_runtime_routes(duplicate)

            incomplete = self.write_catalog(directory, [{**valid, "route": "deep", "model": ""}])
            with self.assertRaisesRegex(ValueError, "runtime route model is required: deep"):
                personal_ai_os.load_runtime_routes(incomplete)

    def test_loader_rejects_secret_bearing_route_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_catalog(
                directory,
                [
                    {
                        "route": "standard",
                        "tier": "standard",
                        "capabilities": ["research"],
                        "max_context_tokens": 160000,
                        "adapter_id": "openai-compatible",
                        "model": "model-standard",
                        "api_key": "must-not-live-here",
                    }
                ],
            )

            with self.assertRaisesRegex(ValueError, "runtime route field not allowed: api_key"):
                personal_ai_os.load_runtime_routes(path)

            path.write_text(
                json.dumps(
                    {
                        "schema_version": "personal-ai-os.runtime-routes/v1",
                        "routes": [],
                        "api_key": "must-not-live-here-either",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "runtime route catalog field not allowed: api_key"):
                personal_ai_os.load_runtime_routes(path)

    def test_loader_rejects_route_contracts_that_cannot_be_dispatched(self):
        valid = {
            "route": "standard",
            "tier": "standard",
            "capabilities": ["research"],
            "max_context_tokens": 160000,
            "adapter_id": "openai-compatible",
            "model": "model-standard",
        }
        cases = [
            ({**valid, "route": ""}, "runtime route id is required"),
            ({**valid, "adapter_id": ""}, "runtime route adapter_id is required: standard"),
            ({**valid, "tier": "turbo"}, "runtime route tier is invalid: standard"),
            ({**valid, "capabilities": "research"}, "runtime route capabilities are invalid: standard"),
            ({**valid, "max_context_tokens": 0}, "runtime route context limit is invalid: standard"),
            ({**valid, "enabled": "yes"}, "runtime route enabled flag is invalid: standard"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for route, message in cases:
                with self.subTest(message=message):
                    path = self.write_catalog(directory, [route])
                    with self.assertRaisesRegex(ValueError, message):
                        personal_ai_os.load_runtime_routes(path)

    def test_loader_rejects_an_empty_or_non_list_catalog(self):
        load_runtime_routes = personal_ai_os.load_runtime_routes
        with tempfile.TemporaryDirectory() as directory:
            empty = self.write_catalog(directory, [])
            with self.assertRaisesRegex(ValueError, "runtime routes must be a non-empty list"):
                load_runtime_routes(empty)

            path = Path(directory) / "routes.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "personal-ai-os.runtime-routes/v1",
                        "routes": "standard",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "runtime routes must be a non-empty list"):
                load_runtime_routes(path)


if __name__ == "__main__":
    unittest.main()
