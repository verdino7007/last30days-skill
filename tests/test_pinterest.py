"""Tests for Pinterest search module."""

import unittest
from unittest.mock import patch

from lib import pinterest


class TestExtractCoreSubject(unittest.TestCase):
    def test_strips_noise_words(self):
        result = pinterest._extract_core_subject("best top AI recommendations trending")
        self.assertNotIn("best", result.lower().split())
        self.assertNotIn("trending", result.lower().split())
        self.assertIn("ai", result.lower())

    def test_plain_topic(self):
        result = pinterest._extract_core_subject("home decor")
        self.assertIn("home", result.lower())


class TestParseItems(unittest.TestCase):
    def _make_raw_pin(self, **overrides):
        base = {
            "id": "pin123",
            "description": "Beautiful AI art",
            "save_count": 500,
            "comment_count": 10,
            "link": "https://www.pinterest.com/pin/pin123/",
            "pinner": {"username": "artlover"},
            "board": {"name": "AI Art"},
        }
        base.update(overrides)
        return base

    def test_basic_parsing(self):
        items = pinterest._parse_items([self._make_raw_pin()], "AI art")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["pin_id"], "pin123")
        self.assertEqual(item["description"], "Beautiful AI art")
        self.assertEqual(item["author"], "artlover")
        self.assertEqual(item["board"], "AI Art")
        self.assertEqual(item["engagement"]["saves"], 500)
        self.assertEqual(item["engagement"]["comments"], 10)
        self.assertGreater(item["relevance"], 0)

    def test_non_dict_skipped(self):
        items = pinterest._parse_items(["not-a-dict", None, 42], "AI")
        self.assertEqual(items, [])

    def test_url_fallback_from_pin_id(self):
        items = pinterest._parse_items(
            [self._make_raw_pin(link="", url="")], "AI"
        )
        self.assertIn("/pin/pin123/", items[0]["url"])

    def test_pinner_as_string(self):
        items = pinterest._parse_items(
            [self._make_raw_pin(pinner="stringuser")], "AI"
        )
        self.assertEqual(items[0]["author"], "stringuser")

    def test_pinner_non_dict_non_string(self):
        items = pinterest._parse_items(
            [self._make_raw_pin(pinner=42)], "AI"
        )
        self.assertEqual(items[0]["author"], "")

    def test_board_non_dict(self):
        items = pinterest._parse_items(
            [self._make_raw_pin(board="not-a-dict")], "AI"
        )
        self.assertEqual(items[0]["board"], "")

    def test_engagement_fallback_fields(self):
        raw = self._make_raw_pin()
        del raw["save_count"]
        raw["saves"] = 999
        items = pinterest._parse_items([raw], "AI")
        self.assertEqual(items[0]["engagement"]["saves"], 999)

    def test_description_from_title_fallback(self):
        items = pinterest._parse_items(
            [self._make_raw_pin(description="", title="Title fallback")], "AI"
        )
        self.assertEqual(items[0]["description"], "Title fallback")

    def test_why_relevant_format(self):
        items = pinterest._parse_items([self._make_raw_pin()], "AI")
        self.assertTrue(items[0]["why_relevant"].startswith("Pinterest:"))

    def test_creator_fallback(self):
        items = pinterest._parse_items(
            [self._make_raw_pin(pinner=None, creator={"username": "creator1"})],
            "AI",
        )
        self.assertEqual(items[0]["author"], "creator1")


class TestParsePinterestResponse(unittest.TestCase):
    def test_extracts_items(self):
        resp = {"items": [{"id": 1}, {"id": 2}]}
        self.assertEqual(len(pinterest.parse_pinterest_response(resp)), 2)

    def test_empty_response(self):
        self.assertEqual(pinterest.parse_pinterest_response({}), [])


class TestSearchPinterest(unittest.TestCase):
    def test_no_token_returns_error(self):
        result = pinterest.search_pinterest("AI art", "2026-01-01", "2026-01-31")
        self.assertEqual(result["items"], [])
        self.assertIn("error", result)

    @patch("lib.http.get")
    def test_successful_search(self, mock_get):
        mock_get.return_value = {
            "pins": [
                {
                    "id": "p1",
                    "description": "AI art pin",
                    "save_count": 100,
                    "comment_count": 5,
                    "link": "https://pinterest.com/pin/p1/",
                    "pinner": {"username": "artist"},
                    "board": {"name": "Art"},
                }
            ]
        }
        result = pinterest.search_pinterest(
            "AI art", "2026-01-01", "2026-01-31", token="test-token"
        )
        self.assertGreater(len(result["items"]), 0)
        self.assertNotIn("error", result)

    @patch("lib.http.get")
    def test_sorted_by_saves(self, mock_get):
        mock_get.return_value = {
            "pins": [
                {
                    "id": "p1", "description": "low saves",
                    "save_count": 5, "comment_count": 0,
                    "pinner": {"username": "u"}, "board": {},
                },
                {
                    "id": "p2", "description": "high saves",
                    "save_count": 500, "comment_count": 0,
                    "pinner": {"username": "u"}, "board": {},
                },
            ]
        }
        result = pinterest.search_pinterest(
            "decor", "2026-01-01", "2026-01-31", token="tok"
        )
        self.assertGreaterEqual(
            result["items"][0]["engagement"]["saves"],
            result["items"][1]["engagement"]["saves"],
        )

    @patch("lib.http.get", side_effect=ConnectionError("fail"))
    def test_http_error_returns_error(self, mock_get):
        result = pinterest.search_pinterest(
            "AI", "2026-01-01", "2026-01-31", token="tok"
        )
        self.assertEqual(result["items"], [])
        self.assertIn("error", result)

    @patch("lib.http.get")
    def test_alternate_response_shape_results(self, mock_get):
        mock_get.return_value = {
            "results": [
                {
                    "id": "p1", "description": "from results key",
                    "save_count": 10, "comment_count": 0,
                    "pinner": {"username": "u"}, "board": {},
                }
            ]
        }
        result = pinterest.search_pinterest(
            "AI", "2026-01-01", "2026-01-31", token="tok"
        )
        self.assertEqual(len(result["items"]), 1)

    @patch("lib.http.get")
    def test_alternate_response_shape_data(self, mock_get):
        mock_get.return_value = {
            "data": [
                {
                    "id": "p1", "description": "from data key",
                    "save_count": 10, "comment_count": 0,
                    "pinner": {"username": "u"}, "board": {},
                }
            ]
        }
        result = pinterest.search_pinterest(
            "AI", "2026-01-01", "2026-01-31", token="tok"
        )
        self.assertEqual(len(result["items"]), 1)

    @patch("lib.http.get")
    def test_depth_quick_limits_results(self, mock_get):
        mock_get.return_value = {
            "pins": [{"id": f"p{i}", "description": "pin", "save_count": i,
                       "comment_count": 0, "pinner": {"username": "u"}, "board": {}}
                      for i in range(30)]
        }
        result = pinterest.search_pinterest(
            "AI", "2026-01-01", "2026-01-31", depth="quick", token="tok"
        )
        self.assertLessEqual(len(result["items"]), 10)


if __name__ == "__main__":
    unittest.main()
