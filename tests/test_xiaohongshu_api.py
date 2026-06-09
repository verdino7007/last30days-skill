"""Tests for Xiaohongshu API search client."""

import unittest
from unittest.mock import patch, MagicMock

from lib import xiaohongshu_api
from lib.http import HTTPError


class TestToInt(unittest.TestCase):
    def test_none(self):
        self.assertEqual(xiaohongshu_api._to_int(None), 0)

    def test_int(self):
        self.assertEqual(xiaohongshu_api._to_int(42), 42)

    def test_float(self):
        self.assertEqual(xiaohongshu_api._to_int(3.7), 3)

    def test_string_int(self):
        self.assertEqual(xiaohongshu_api._to_int("100"), 100)

    def test_string_float(self):
        self.assertEqual(xiaohongshu_api._to_int("3.5"), 3)

    def test_empty_string(self):
        self.assertEqual(xiaohongshu_api._to_int(""), 0)

    def test_wan_suffix(self):
        self.assertEqual(xiaohongshu_api._to_int("1.2万"), 12000)

    def test_yi_suffix(self):
        self.assertEqual(xiaohongshu_api._to_int("3亿"), 300000000)

    def test_comma_separated(self):
        self.assertEqual(xiaohongshu_api._to_int("1,234"), 1234)

    def test_garbage(self):
        self.assertEqual(xiaohongshu_api._to_int("abc"), 0)


class TestTimestampToDateMs(unittest.TestCase):
    def test_valid_ms_timestamp(self):
        # 2026-01-01 00:00:00 UTC in ms
        self.assertEqual(
            xiaohongshu_api._timestamp_to_date_ms(1767225600000),
            "2026-01-01",
        )

    def test_zero(self):
        self.assertIsNone(xiaohongshu_api._timestamp_to_date_ms(0))

    def test_negative(self):
        self.assertIsNone(xiaohongshu_api._timestamp_to_date_ms(-1000))

    def test_none(self):
        self.assertIsNone(xiaohongshu_api._timestamp_to_date_ms(None))

    def test_garbage_string(self):
        self.assertIsNone(xiaohongshu_api._timestamp_to_date_ms("not-a-number"))


class TestRelevanceFromInteractions(unittest.TestCase):
    def test_zero_engagement(self):
        score = xiaohongshu_api._relevance_from_interactions(0, 0, 0)
        self.assertEqual(score, 0.05)

    def test_moderate_engagement(self):
        score = xiaohongshu_api._relevance_from_interactions(100, 50, 30)
        self.assertGreater(score, 0.05)
        self.assertLessEqual(score, 1.0)

    def test_high_engagement_caps_at_one(self):
        score = xiaohongshu_api._relevance_from_interactions(10000, 5000, 3000)
        self.assertEqual(score, 1.0)

    def test_rounding(self):
        score = xiaohongshu_api._relevance_from_interactions(10, 5, 3)
        self.assertEqual(score, round(score, 3))


class TestBuildNoteUrl(unittest.TestCase):
    def test_with_token(self):
        url = xiaohongshu_api._build_note_url("abc123", "tok456")
        self.assertEqual(
            url, "https://www.xiaohongshu.com/explore/abc123?xsec_token=tok456"
        )

    def test_without_token(self):
        url = xiaohongshu_api._build_note_url("abc123", "")
        self.assertEqual(url, "https://www.xiaohongshu.com/explore/abc123")


class TestSearchFeeds(unittest.TestCase):
    def test_missing_base_url_raises(self):
        with self.assertRaises(ValueError):
            xiaohongshu_api.search_feeds("test", "2026-01-01", "2026-01-31", "")

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_not_logged_in_raises(self, mock_get, mock_post):
        mock_get.return_value = {"data": {"is_logged_in": False}}
        with self.assertRaises(HTTPError):
            xiaohongshu_api.search_feeds(
                "test", "2026-01-01", "2026-01-31", "http://localhost:8080"
            )

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_non_dict_login_response_raises(self, mock_get, mock_post):
        mock_get.return_value = "unexpected string"
        with self.assertRaises(HTTPError):
            xiaohongshu_api.search_feeds(
                "test", "2026-01-01", "2026-01-31", "http://localhost:8080"
            )

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_successful_search(self, mock_get, mock_post):
        mock_get.return_value = {"data": {"is_logged_in": True}}
        mock_post.return_value = {
            "data": {
                "feeds": [
                    {
                        "id": "feed1",
                        "xsecToken": "xtoken",
                        "noteCard": {
                            "displayTitle": "Test Note",
                            "desc": "A test note description",
                            "time": 1767225600000,
                            "interactInfo": {
                                "likedCount": 100,
                                "commentCount": 20,
                                "collectedCount": 50,
                            },
                        },
                    }
                ]
            }
        }
        items = xiaohongshu_api.search_feeds(
            "test", "2026-01-01", "2026-01-31", "http://localhost:8080"
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "XHS1")
        self.assertEqual(items[0]["title"], "Test Note")
        self.assertEqual(items[0]["source_domain"], "xiaohongshu.com")
        self.assertIn("xsec_token=xtoken", items[0]["url"])
        self.assertEqual(items[0]["date"], "2026-01-01")
        self.assertGreater(items[0]["relevance"], 0)

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_empty_feeds(self, mock_get, mock_post):
        mock_get.return_value = {"data": {"is_logged_in": True}}
        mock_post.return_value = {"data": {"feeds": []}}
        items = xiaohongshu_api.search_feeds(
            "test", "2026-01-01", "2026-01-31", "http://localhost:8080"
        )
        self.assertEqual(items, [])

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_non_dict_feed_skipped(self, mock_get, mock_post):
        mock_get.return_value = {"data": {"is_logged_in": True}}
        mock_post.return_value = {"data": {"feeds": ["not-a-dict", None]}}
        items = xiaohongshu_api.search_feeds(
            "test", "2026-01-01", "2026-01-31", "http://localhost:8080"
        )
        self.assertEqual(items, [])

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_feed_without_id_skipped(self, mock_get, mock_post):
        mock_get.return_value = {"data": {"is_logged_in": True}}
        mock_post.return_value = {
            "data": {"feeds": [{"noteCard": {"displayTitle": "No ID"}}]}
        }
        items = xiaohongshu_api.search_feeds(
            "test", "2026-01-01", "2026-01-31", "http://localhost:8080"
        )
        self.assertEqual(items, [])

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_depth_quick(self, mock_get, mock_post):
        mock_get.return_value = {"data": {"is_logged_in": True}}
        mock_post.return_value = {"data": {"feeds": []}}
        xiaohongshu_api.search_feeds(
            "test", "2026-01-01", "2026-01-31", "http://localhost:8080", depth="quick"
        )
        payload = mock_post.call_args[0][1]
        self.assertEqual(payload["filters"]["publish_time"], "一天内")

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_depth_deep(self, mock_get, mock_post):
        mock_get.return_value = {"data": {"is_logged_in": True}}
        mock_post.return_value = {"data": {"feeds": []}}
        xiaohongshu_api.search_feeds(
            "test", "2026-01-01", "2026-01-31", "http://localhost:8080", depth="deep"
        )
        payload = mock_post.call_args[0][1]
        self.assertEqual(payload["filters"]["publish_time"], "半年内")

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_non_dict_notecard_treated_as_empty(self, mock_get, mock_post):
        mock_get.return_value = {"data": {"is_logged_in": True}}
        mock_post.return_value = {
            "data": {
                "feeds": [
                    {
                        "id": "f1",
                        "noteCard": "bad",
                    }
                ]
            }
        }
        items = xiaohongshu_api.search_feeds(
            "test", "2026-01-01", "2026-01-31", "http://localhost:8080"
        )
        self.assertEqual(len(items), 1)
        self.assertIn("Xiaohongshu note f1", items[0]["title"])

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_non_dict_interact_treated_as_empty(self, mock_get, mock_post):
        mock_get.return_value = {"data": {"is_logged_in": True}}
        mock_post.return_value = {
            "data": {
                "feeds": [
                    {
                        "id": "f2",
                        "noteCard": {
                            "displayTitle": "Title",
                            "interactInfo": "bad",
                        },
                    }
                ]
            }
        }
        items = xiaohongshu_api.search_feeds(
            "test", "2026-01-01", "2026-01-31", "http://localhost:8080"
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Title")

    @patch("lib.http.post")
    @patch("lib.http.get")
    def test_non_list_feeds_treated_as_empty(self, mock_get, mock_post):
        mock_get.return_value = {"data": {"is_logged_in": True}}
        mock_post.return_value = {"data": {"feeds": "not-a-list"}}
        items = xiaohongshu_api.search_feeds(
            "test", "2026-01-01", "2026-01-31", "http://localhost:8080"
        )
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
