import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import i18n
from src.palette import available_palette_presets

TOOL_SOURCE = os.path.join(os.path.dirname(__file__), "..", "src", "tool.py")


class TranslationTests(unittest.TestCase):
    def test_english_and_chinese_define_the_same_keys(self):
        self.assertEqual(set(i18n.UI_TEXT["en"]), set(i18n.UI_TEXT["zh"]))
        self.assertEqual(
            set(i18n.PARAMETER_LABELS["en"]), set(i18n.PARAMETER_LABELS["zh"])
        )
        self.assertEqual(
            set(i18n.PALETTE_LABELS["en"]), set(i18n.PALETTE_LABELS["zh"])
        )

    def test_every_palette_preset_has_a_label(self):
        for language in ("en", "zh"):
            self.assertEqual(
                set(i18n.PALETTE_LABELS[language]), set(available_palette_presets())
            )

    def test_every_parameter_has_a_label_and_tooltips(self):
        for key in i18n.PARAMETER_LABELS["en"]:
            self.assertIn(key, i18n.PARAMETER_TOOLTIPS_EN)
        for key in i18n.PARAMETER_TOOLTIPS_ZH:
            self.assertIn(key, i18n.PARAMETER_LABELS["zh"])

    def test_tool_only_uses_defined_message_keys(self):
        with open(TOOL_SOURCE, encoding="utf-8") as handle:
            source = handle.read()
        used = set(re.findall(r'_tr\(\s*"([a-z_]+)"', source))
        self.assertTrue(used)
        self.assertLessEqual(used, set(i18n.UI_TEXT["en"]))

    def test_help_pages_accept_the_size_limits(self):
        limits = {"export_min": 2, "export_max": 16000}
        for text in (i18n.PARAMETER_HELP_HTML_EN, i18n.PARAMETER_HELP_HTML_ZH):
            rendered = text.format(**limits)
            self.assertIn("16000", rendered)
            self.assertNotIn("{", rendered)

    def test_message_templates_format_with_their_named_fields(self):
        samples = {"error": "e", "count": 1, "preset": "p", "path": "x",
                   "width": 1, "height": 1, "maximum": 8000, "name": "n", "low": 1,
                   "high": 2, "value": 1, "export_min": 1, "export_max": 2, "gb": "6"}
        for language, table in i18n.UI_TEXT.items():
            for key, template in table.items():
                with self.subTest(language=language, key=key):
                    template.format(**samples)


if __name__ == "__main__":
    unittest.main()
