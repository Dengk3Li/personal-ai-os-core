import unittest

from personal_ai_os.template_selection import (
    TEMPLATE_SELECTION_VERSION,
    validate_template_selection,
)


class TemplateSelectionTests(unittest.TestCase):
    def valid_selection(self):
        return {
            "schema_version": TEMPLATE_SELECTION_VERSION,
            "template_id": "template-001",
            "version": "v3",
            "source_ref": "template-ref-001",
            "content_sha256": "A" * 64,
            "task_kind": "document-draft",
        }

    def test_selection_normalizes_identifiers_and_content_hash(self):
        result = validate_template_selection(self.valid_selection())

        self.assertEqual(TEMPLATE_SELECTION_VERSION, result["schema_version"])
        self.assertEqual("template-001", result["template_id"])
        self.assertEqual("v3", result["version"])
        self.assertEqual("template-ref-001", result["source_ref"])
        self.assertEqual("a" * 64, result["content_sha256"])
        self.assertEqual("document-draft", result["task_kind"])

    def test_selection_rejects_paths_body_credentials_and_unknown_fields(self):
        for field in ("template_id", "version", "source_ref", "task_kind"):
            selection = self.valid_selection()
            selection[field] = "/Users/private/template"
            with self.assertRaises(ValueError):
                validate_template_selection(selection)

        selection = self.valid_selection()
        selection["content"] = "private template body"
        with self.assertRaises(ValueError):
            validate_template_selection(selection)

        selection = self.valid_selection()
        selection["api_key"] = "secret-value"
        with self.assertRaises(ValueError):
            validate_template_selection(selection)

    def test_selection_rejects_invalid_hash_and_business_copy(self):
        selection = self.valid_selection()
        selection["content_sha256"] = "not-a-sha256"
        with self.assertRaises(ValueError):
            validate_template_selection(selection)

        selection = self.valid_selection()
        selection["template_id"] = "行业研究模板"
        with self.assertRaises(ValueError):
            validate_template_selection(selection)

    def test_selection_errors_do_not_echo_rejected_values(self):
        selection = self.valid_selection()
        selection["source_ref"] = "/private/sensitive-template"

        with self.assertRaises(ValueError) as raised:
            validate_template_selection(selection)

        self.assertNotIn("/private/sensitive-template", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
