"""Tests for Threads keyword search module."""

import unittest
from unittest.mock import patch

from lib import threads


class TestExtractCoreSubject(unittest.TestCase):
    def test_strips_noise_words(self):
        result = threads._extract_core_subject("best latest AI updates trending")
        self.assertNotIn("best", result.lower().split())
        self.assertNotIn("latest", result.lower().split())
        self.assertIn("ai", result.lower())

    def test_plain_topic(self):
        result = threads._extract_core_subject("machine learning")
        self.assertIn("machine", result.lower())


class TestParseDate(unittest.TestCase):
    def test_unix_timestamp(self):
        result = threads._parse_date({"taken_at": 1767225600})
        self.assertEqual(result, "2026-01-01")

    def test_iso_date(self):
        result = threads._parse_date({"created_at": "2026-03-15T12:00:00Z"})
        self.assertEqual(result, "2026-03-15")

    def test_no_date_fields(self):
        result = threads._parse_date({})
        self.assertIsNone(result)

    def test_none_values_skipped(self):
        result = threads._parse_date({"taken_at": None, "created_at": "2026-05-01"})
        self.assertEqual(result, "2026-05-01")


class TestParseItems(unittest.TestCase):
    def _make_raw_item(self, **overrides):
        base = {
            "id": "thread123",
            "text": "This is a threads post about AI",
            "user": {"username": "testuser", "full_name": "Test User"},
            "like_count": 50,
            "reply_count": 10,
            "repost_count": 5,
            "quote_count": 2,
            "code": "abc123",
            "taken_at": 1767225600,
        }
        base.update(overrides)
        return base

    def test_basic_parsing(self):
        items = threads._parse_items([self._make_raw_item()], "AI")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], "thread123")
        self.assertEqual(item["handle"], "testuser")
        self.assertEqual(item["display_name"], "Test User")
        self.assertEqual(item["engagement"]["likes"], 50)
        self.assertEqual(item["engagement"]["replies"], 10)
        self.assertIn("threads.net", item["url"])
        self.assertGreater(item["relevance"], 0)

    def test_url_from_code(self):
        items = threads._parse_items(
            [self._make_raw_item(url="", share_url="")], "AI"
        )
        self.assertIn("/post/abc123", items[0]["url"])

    def test_url_from_handle_and_id(self):
        items = threads._parse_items(
            [self._make_raw_item(code="", shortcode="", url="", share_url="")], "AI"
        )
        self.assertIn("@testuser", items[0]["url"])

    def test_direct_url_preferred(self):
        items = threads._parse_items(
            [self._make_raw_item(url="https://custom.url/post")], "AI"
        )
        self.assertEqual(items[0]["url"], "https://custom.url/post")

    def test_text_from_caption_fallback(self):
        items = threads._parse_items(
            [self._make_raw_item(text="", caption="Caption text")], "AI"
        )
        self.assertEqual(items[0]["text"], "Caption text")

    def test_text_dict_extracted(self):
        items = threads._parse_items(
            [self._make_raw_item(text={"text": "Nested text"})], "AI"
        )
        self.assertEqual(items[0]["text"], "Nested text")

    def test_user_as_string(self):
        items = threads._parse_items(
            [self._make_raw_item(user="stringuser")], "AI"
        )
        self.assertEqual(items[0]["handle"], "stringuser")
        self.assertEqual(items[0]["display_name"], "stringuser")

    def test_user_non_dict_non_string(self):
        items = threads._parse_items(
            [self._make_raw_item(user=42)], "AI"
        )
        self.assertEqual(items[0]["handle"], "")

    def test_fallback_id_generation(self):
        raw = {"text": "post without id"}
        items = threads._parse_items([raw], "AI")
        self.assertEqual(items[0]["id"], "TH1")

    def test_engagement_fallback_fields(self):
        raw = self._make_raw_item()
        del raw["like_count"]
        raw["likes"] = 99
        items = threads._parse_items([raw], "AI")
        self.assertEqual(items[0]["engagement"]["likes"], 99)

    def test_relevance_decreases_with_rank(self):
        raw_items = [self._make_raw_item(id=f"t{i}") for i in range(5)]
        items = threads._parse_items(raw_items, "AI")
        # Higher rank (lower index) should have higher or equal relevance
        self.assertGreaterEqual(items[0]["relevance"], items[4]["relevance"])


class TestSearchThreads(unittest.TestCase):
    def test_no_token_returns_error(self):
        result = threads.search_threads("AI", "2026-01-01", "2026-01-31")
        self.assertEqual(result["items"], [])
        self.assertIn("error", result)

    @patch("lib.http.get")
    def test_successful_search(self, mock_get):
        mock_get.return_value = {
            "items": [
                {
                    "id": "t1",
                    "text": "AI thread post",
                    "user": {"username": "user1"},
                    "like_count": 100,
                    "reply_count": 20,
                    "repost_count": 5,
                    "quote_count": 1,
                    "code": "code1",
                    "taken_at": 1767225600,
                }
            ]
        }
        result = threads.search_threads(
            "AI", "2026-01-01", "2026-01-31", token="test-token"
        )
        self.assertEqual(len(result["items"]), 1)
        self.assertNotIn("error", result)

    @patch("lib.http.get")
    def test_date_filter_applied(self, mock_get):
        mock_get.return_value = {
            "items": [
                {
                    "id": "t1", "text": "in range",
                    "user": {"username": "u"},
                    "like_count": 10, "reply_count": 0,
                    "repost_count": 0, "quote_count": 0,
                    "created_at": "2026-01-15T00:00:00Z",
                },
                {
                    "id": "t2", "text": "out of range",
                    "user": {"username": "u"},
                    "like_count": 5, "reply_count": 0,
                    "repost_count": 0, "quote_count": 0,
                    "created_at": "2025-06-01T00:00:00Z",
                },
            ]
        }
        result = threads.search_threads(
            "AI", "2026-01-01", "2026-01-31", token="tok"
        )
        # Only the in-range item should be present
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["id"], "t1")

    @patch("lib.http.get")
    def test_no_items_in_range_keeps_all(self, mock_get):
        mock_get.return_value = {
            "items": [
                {
                    "id": "t1", "text": "out of range",
                    "user": {"username": "u"},
                    "like_count": 5, "reply_count": 0,
                    "repost_count": 0, "quote_count": 0,
                    "created_at": "2025-06-01T00:00:00Z",
                },
            ]
        }
        result = threads.search_threads(
            "AI", "2026-01-01", "2026-01-31", token="tok"
        )
        self.assertEqual(len(result["items"]), 1)

    @patch("lib.http.get", side_effect=ConnectionError("fail"))
    def test_http_error_returns_error(self, mock_get):
        result = threads.search_threads(
            "AI", "2026-01-01", "2026-01-31", token="tok"
        )
        self.assertEqual(result["items"], [])
        self.assertIn("error", result)

    @patch("lib.http.get")
    def test_sorted_by_likes(self, mock_get):
        mock_get.return_value = {
            "items": [
                {
                    "id": "t1", "text": "low likes",
                    "user": {"username": "u"},
                    "like_count": 5, "reply_count": 0,
                    "repost_count": 0, "quote_count": 0,
                },
                {
                    "id": "t2", "text": "high likes",
                    "user": {"username": "u"},
                    "like_count": 100, "reply_count": 0,
                    "repost_count": 0, "quote_count": 0,
                },
            ]
        }
        result = threads.search_threads(
            "AI", "2026-01-01", "2026-01-31", token="tok"
        )
        self.assertGreaterEqual(
            result["items"][0]["engagement"]["likes"],
            result["items"][1]["engagement"]["likes"],
        )

    @patch("lib.http.get")
    def test_response_shape_keys(self, mock_get):
        mock_get.return_value = {
            "data": [
                {
                    "id": "t1", "text": "post",
                    "user": {"username": "u"},
                    "like_count": 1, "reply_count": 0,
                    "repost_count": 0, "quote_count": 0,
                },
            ]
        }
        result = threads.search_threads(
            "AI", "2026-01-01", "2026-01-31", token="tok"
        )
        self.assertEqual(len(result["items"]), 1)


class TestParseThreadsResponse(unittest.TestCase):
    def test_extracts_items(self):
        resp = {"items": [{"id": 1}, {"id": 2}]}
        self.assertEqual(len(threads.parse_threads_response(resp)), 2)

    def test_empty_response(self):
        self.assertEqual(threads.parse_threads_response({}), [])


if __name__ == "__main__":
    unittest.main()
