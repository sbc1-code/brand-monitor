import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import report
import scan
import score


class BrandMonitorPipelineTests(unittest.TestCase):
    def test_brand_terms_filter_loose_results(self):
        brand = {
            "id": "acme",
            "name": "Acme Robotics",
            "keywords": ['"Acme Robotics"', '"Acme Pilot"'],
            "core_terms": ["acme robotics", "acme pilot"],
        }

        self.assertTrue(scan.verify_brand_mention("Acme Robotics launches", "", brand))
        self.assertTrue(scan.verify_brand_mention("", "Acme Pilot is mentioned here.", brand))
        self.assertFalse(scan.verify_brand_mention("Robotics market roundup", "No target term.", brand))

    def test_product_classification_uses_config(self):
        product = scan.classify_product(
            "Developers compare the OpenAI API and alternatives",
            "Responses API examples are included.",
            "openai",
        )

        self.assertEqual(product, "OpenAI API")

    def test_scoring_uses_configured_product_terms(self):
        mention = {
            "brand_id": "github",
            "source_type": "news_article",
            "title": "GitHub Copilot ships new enterprise controls",
            "snippet": "The update covers policy management for engineering teams.",
            "published_date": "2026-06-01",
            "is_first_party": "False",
            "is_partner_or_reseller": "False",
        }

        signal_score, sentiment = score.score_mention(mention)

        self.assertGreaterEqual(signal_score, 35)
        self.assertEqual(sentiment, "neutral")

    def test_report_environment_escapes_external_content(self):
        env = report.create_template_environment()
        rendered = env.from_string("{{ value }}").render(value="<script>alert(1)</script>")

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_report_template_explains_monitor_without_mock_language(self):
        env = report.create_template_environment()
        rendered = env.get_template("report.html").render(
            scan_date="June 05, 2026",
            scan_period="Daily Scan",
            summary={
                "total_new": 0,
                "total_cumulative": 0,
                "highlights": 0,
                "worthy": 0,
                "brands_mentioned": 0,
                "top_score": 0,
            },
            brand_stats=[],
            type_stats=[],
            brands_with_mentions={},
            highlights=[],
            worthy=[],
            all_new_mentions=[],
            all_cumulative=[],
            thresholds={"highlight": 70, "notify": 40},
        )

        self.assertIn("Know where your brand is showing up", rendered)
        self.assertIn("scans configured sources, dedupes mentions, scores signal", rendered)
        self.assertIn("Live sample configuration", rendered)
        lowered = rendered.lower()
        self.assertNotIn("fictional", lowered)
        self.assertNotIn("mock", lowered)
        self.assertNotIn("demonstration", lowered)

    def test_mention_id_is_stable_by_url_and_brand(self):
        first = scan.generate_mention_id("https://unit.test/Post", "brand")
        second = scan.generate_mention_id("https://unit.test/Post", "brand")
        third = scan.generate_mention_id("https://unit.test/Post", "other")

        self.assertEqual(first, second)
        self.assertNotEqual(first, third)


if __name__ == "__main__":
    unittest.main()
