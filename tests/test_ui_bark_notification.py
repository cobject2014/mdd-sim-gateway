"""Source-level registration checks around the independently-built Bark card.

The generator itself has executable Node tests; these checks protect the narrow React/API
registration boundary in a frontend that does not otherwise include a DOM test runner.
"""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PARENT = (ROOT / "webui/src/views/UnifiedPages.jsx").read_text(encoding="utf-8")
API = (ROOT / "webui/src/api.js").read_text(encoding="utf-8")
I18N = (ROOT / "webui/src/i18n.jsx").read_text(encoding="utf-8")
COMPONENT_PATH = ROOT / "webui/src/views/BarkNotificationCard.jsx"


class BarkNotificationUiTests(unittest.TestCase):
    def test_bark_card_is_an_independent_component(self):
        self.assertTrue(COMPONENT_PATH.is_file())
        component = COMPONENT_PATH.read_text(encoding="utf-8")
        self.assertIn("export default function BarkNotificationCard", component)
        self.assertIn("function SecretField", component)
        self.assertIn("type={visible ? 'text' : 'password'}", component)
        self.assertIn("navigator.clipboard.writeText(value)", component)
        self.assertEqual(component.count("<SecretField"), 3)
        for field in ("push_url", "verify_tls", "encryption", "key", "iv",
                      "group", "sound", "level"):
            self.assertIn(field, component)
        self.assertIn("api.testBark({ ...config, _test_event: event })", component)
        self.assertIn("api.testBark(config)", component)
        self.assertIn("Plaintext Bark pushes expose", component)

    def test_parent_only_registers_and_renders_the_card(self):
        self.assertIn("import BarkNotificationCard", PARENT)
        self.assertIn("<BarkNotificationCard", PARENT)
        self.assertIn("MessageTemplateEditor={MessageTemplateEditor}", PARENT)
        self.assertIn("renderEventOptions=", PARENT)
        self.assertNotIn("bark.push_url", PARENT)

    def test_api_and_bilingual_page_subtitle_include_bark(self):
        self.assertIn("testBark: (config)", API)
        self.assertIn("/api/notifications/bark/test", API)
        self.assertGreaterEqual(I18N.count("Webhook, Telegram, PushPlus, Bark"), 1)
        self.assertIn("Webhook、Telegram、PushPlus、Bark", I18N)


if __name__ == "__main__":
    unittest.main()
