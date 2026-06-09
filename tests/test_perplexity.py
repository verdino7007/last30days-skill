"""Tests for Perplexity Sonar Pro / Deep Research module."""

import unittest
from unittest.mock import patch, MagicMock

from lib import perplexity
from lib.http import HTTPError


class TestDomain(unittest.TestCase):
    def test_extracts_domain(self):
        self.assertEqual(perplexity._domain("https://example.com/path"), "example.com")

    def test_empty_url(self):
        self.assertEqual(perplexity._domain(""), "")

    def test_strips_and_lowercases(self):
        self.assertEqual(
            perplexity._domain("https://Example.COM/path"), "example.com"
        )


class TestSearch(unittest.TestCase):
    def test_no_api_key_returns_empty(self):
        items, artifact = perplexity.search(
            "test", ("2026-01-01", "2026-01-31"), config={}
        )
        self.assertEqual(items, [])
        self.assertEqual(artifact, {})

    @patch("lib.http.post")
    def test_successful_search(self, mock_post):
        mock_post.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Here is the synthesis about AI developments.",
                        "annotations": [
                            {
                                "url_citation": {
                                    "url": "https://example.com/article1",
                                    "title": "AI Article 1",
                                }
                            },
                            {
                                "url_citation": {
                                    "url": "https://other.com/article2",
                                    "title": "AI Article 2",
                                }
                            },
                        ],
                    }
                }
            ]
        }

        items, artifact = perplexity.search(
            "AI developments",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "test-key"},
        )

        self.assertEqual(len(items), 3)  # 1 synthesis + 2 citations
        self.assertEqual(items[0]["id"], "PX1")
        self.assertIn("Sonar Pro", items[0]["title"])
        self.assertEqual(items[0]["source_domain"], "perplexity.ai")
        self.assertEqual(items[0]["relevance"], 0.9)

        self.assertEqual(items[1]["id"], "PX2")
        self.assertEqual(items[1]["url"], "https://example.com/article1")
        self.assertEqual(items[1]["relevance"], 0.7)

        self.assertFalse(artifact["deep"])
        self.assertEqual(artifact["citationCount"], 2)

    @patch("lib.http.post")
    def test_deep_research_mode(self, mock_post):
        mock_post.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Deep research synthesis.",
                        "annotations": [],
                    }
                }
            ]
        }

        items, artifact = perplexity.search(
            "AI",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "test-key"},
            deep=True,
        )

        self.assertTrue(artifact["deep"])
        self.assertEqual(artifact["model"], perplexity.MODEL_DEEP_RESEARCH)
        self.assertIn("Deep Research", items[0]["title"])

    @patch("lib.http.post")
    def test_empty_choices_returns_empty(self, mock_post):
        mock_post.return_value = {"choices": []}
        items, artifact = perplexity.search(
            "test",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "test-key"},
        )
        self.assertEqual(items, [])
        self.assertEqual(artifact, {})

    @patch("lib.http.post")
    def test_empty_synthesis_returns_empty(self, mock_post):
        mock_post.return_value = {
            "choices": [{"message": {"content": ""}}]
        }
        items, artifact = perplexity.search(
            "test",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "test-key"},
        )
        self.assertEqual(items, [])
        self.assertEqual(artifact, {})

    @patch("lib.http.post")
    def test_deduplicates_citations(self, mock_post):
        mock_post.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Synthesis text here.",
                        "annotations": [
                            {"url_citation": {"url": "https://a.com", "title": "A"}},
                            {"url_citation": {"url": "https://a.com", "title": "A dup"}},
                            {"url_citation": {"url": "https://b.com", "title": "B"}},
                        ],
                    }
                }
            ]
        }
        items, artifact = perplexity.search(
            "test",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "key"},
        )
        # 1 synthesis + 2 unique citations
        self.assertEqual(len(items), 3)
        self.assertEqual(artifact["citationCount"], 2)

    @patch("lib.http.post", side_effect=HTTPError("401", status_code=401))
    def test_http_401_returns_empty(self, mock_post):
        items, artifact = perplexity.search(
            "test",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "bad-key"},
        )
        self.assertEqual(items, [])
        self.assertEqual(artifact, {})

    @patch("lib.http.post", side_effect=HTTPError("429", status_code=429))
    def test_http_429_returns_empty(self, mock_post):
        items, artifact = perplexity.search(
            "test",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "key"},
        )
        self.assertEqual(items, [])

    @patch("lib.http.post", side_effect=HTTPError("500", status_code=500))
    def test_http_other_error_returns_empty(self, mock_post):
        items, artifact = perplexity.search(
            "test",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "key"},
        )
        self.assertEqual(items, [])

    @patch("lib.http.post", side_effect=ConnectionError("network down"))
    def test_generic_exception_returns_empty(self, mock_post):
        items, artifact = perplexity.search(
            "test",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "key"},
        )
        self.assertEqual(items, [])
        self.assertEqual(artifact, {})

    @patch("lib.http.post")
    def test_no_annotations_key(self, mock_post):
        mock_post.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Synthesis without annotations field.",
                    }
                }
            ]
        }
        items, artifact = perplexity.search(
            "test",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "key"},
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(artifact["citationCount"], 0)

    @patch("lib.http.post")
    def test_citation_without_title_uses_domain(self, mock_post):
        mock_post.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Some synthesis.",
                        "annotations": [
                            {"url_citation": {"url": "https://nytimes.com/article", "title": ""}},
                        ],
                    }
                }
            ]
        }
        items, _ = perplexity.search(
            "test",
            ("2026-01-01", "2026-01-31"),
            config={"OPENROUTER_API_KEY": "key"},
        )
        self.assertEqual(items[1]["title"], "nytimes.com")


if __name__ == "__main__":
    unittest.main()
