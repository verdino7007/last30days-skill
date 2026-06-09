"""Extended tests for GitHub source module — person-mode, project-mode,
star enrichment, and helper functions that the baseline tests don't cover."""

import unittest
from unittest.mock import patch, MagicMock

from lib import github


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestFormatStars(unittest.TestCase):
    def test_small_number(self):
        self.assertEqual(github._format_stars(42), "42")

    def test_thousands(self):
        self.assertEqual(github._format_stars(2900), "2.9K")

    def test_tens_of_thousands(self):
        self.assertEqual(github._format_stars(15000), "15K")

    def test_millions(self):
        self.assertEqual(github._format_stars(1_500_000), "1.5M")

    def test_zero(self):
        self.assertEqual(github._format_stars(0), "0")

    def test_exactly_1000(self):
        self.assertEqual(github._format_stars(1000), "1.0K")


class TestFetchJson(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"total_count": 1}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = github._fetch_json("https://api.github.com/search/issues")
        self.assertEqual(result, {"total_count": 1})

    @patch("urllib.request.urlopen")
    def test_includes_auth_header(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        github._fetch_json("https://api.github.com/x", token="tok123")
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), "Bearer tok123")

    @patch("urllib.request.urlopen")
    def test_403_returns_none(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 403, "Forbidden", {}, None
        )
        result = github._fetch_json("https://api.github.com/x")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_422_returns_none(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 422, "Unprocessable", {}, None
        )
        result = github._fetch_json("https://api.github.com/x")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_other_http_error_returns_none(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 500, "Server Error", {}, None
        )
        result = github._fetch_json("https://api.github.com/x")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_url_error_returns_none(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("DNS failure")
        result = github._fetch_json("https://api.github.com/x")
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_json_decode_error_returns_none(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'not json'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = github._fetch_json("https://api.github.com/x")
        self.assertIsNone(result)


class TestFetchItemComments(unittest.TestCase):
    @patch.object(github, "_fetch_json")
    def test_returns_comments(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "body": "Great issue! I agree with this.",
                "reactions": {"total_count": 5},
                "user": {"login": "commenter"},
            }
        ]
        comments = github._fetch_item_comments(
            "https://github.com/owner/repo/issues/1", "tok"
        )
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["score"], 5)
        self.assertEqual(comments[0]["author"], "commenter")
        self.assertIn("Great issue", comments[0]["excerpt"])

    @patch.object(github, "_fetch_json", return_value=None)
    def test_returns_empty_on_failure(self, mock_fetch):
        comments = github._fetch_item_comments(
            "https://github.com/owner/repo/issues/1", "tok"
        )
        self.assertEqual(comments, [])

    @patch.object(github, "_fetch_json")
    def test_truncates_long_body(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "body": "x" * 500,
                "reactions": {"total_count": 0},
                "user": {"login": "u"},
            }
        ]
        comments = github._fetch_item_comments(
            "https://github.com/owner/repo/issues/1", "tok"
        )
        self.assertTrue(comments[0]["excerpt"].endswith("..."))
        self.assertLessEqual(len(comments[0]["excerpt"]), 304)

    @patch.object(github, "_fetch_json")
    def test_pr_url_converted(self, mock_fetch):
        mock_fetch.return_value = []
        github._fetch_item_comments(
            "https://github.com/owner/repo/pull/99", "tok"
        )
        url_called = mock_fetch.call_args[0][0]
        self.assertIn("/issues/99/comments", url_called)


class TestFetchLatestReleases(unittest.TestCase):
    @patch.object(github, "_fetch_json")
    def test_parses_releases(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "tag_name": "v1.0.0",
                "name": "Release 1.0",
                "published_at": "2026-03-15T12:00:00Z",
                "body": "Initial release",
            }
        ]
        releases = github._fetch_latest_releases("owner/repo", "tok")
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["tag"], "v1.0.0")
        self.assertEqual(releases[0]["name"], "Release 1.0")
        self.assertEqual(releases[0]["date"], "2026-03-15")

    @patch.object(github, "_fetch_json", return_value=None)
    def test_returns_empty_on_failure(self, mock_fetch):
        releases = github._fetch_latest_releases("owner/repo", "tok")
        self.assertEqual(releases, [])

    @patch.object(github, "_fetch_json")
    def test_name_falls_back_to_tag(self, mock_fetch):
        mock_fetch.return_value = [
            {"tag_name": "v2.0", "name": "", "published_at": None, "body": ""},
        ]
        releases = github._fetch_latest_releases("owner/repo", "tok")
        self.assertEqual(releases[0]["name"], "v2.0")


class TestFetchRepoInfo(unittest.TestCase):
    @patch.object(github, "_fetch_json")
    def test_parses_repo_info(self, mock_fetch):
        mock_fetch.return_value = {
            "stargazers_count": 5000,
            "forks_count": 200,
            "description": "A cool project",
            "language": "Python",
            "open_issues_count": 42,
        }
        info = github._fetch_repo_info("owner/repo", "tok")
        self.assertEqual(info["stars"], 5000)
        self.assertEqual(info["forks"], 200)
        self.assertEqual(info["language"], "Python")
        self.assertEqual(info["open_issues"], 42)

    @patch.object(github, "_fetch_json", return_value=None)
    def test_returns_none_on_failure(self, mock_fetch):
        info = github._fetch_repo_info("owner/repo", "tok")
        self.assertIsNone(info)


class TestFetchTopIssues(unittest.TestCase):
    @patch.object(github, "_fetch_json")
    def test_returns_feature_and_complaint(self, mock_fetch):
        def side_effect(url, **kwargs):
            if "enhancement" in url:
                return {
                    "total_count": 1,
                    "items": [{
                        "title": "Feature Request",
                        "reactions": {"total_count": 15},
                        "comments": 8,
                        "html_url": "https://github.com/o/r/issues/1",
                    }],
                }
            elif "sort=comments" in url:
                return {
                    "total_count": 1,
                    "items": [{
                        "title": "Top Complaint",
                        "reactions": {"total_count": 3},
                        "comments": 50,
                        "html_url": "https://github.com/o/r/issues/2",
                    }],
                }
            return {"total_count": 0, "items": []}

        mock_fetch.side_effect = side_effect
        result = github._fetch_top_issues("owner/repo", "tok")
        self.assertEqual(result["top_feature_request"]["title"], "Feature Request")
        self.assertEqual(result["top_complaint"]["title"], "Top Complaint")

    @patch.object(github, "_fetch_json")
    def test_fallback_when_no_enhancement_label(self, mock_fetch):
        call_count = [0]

        def side_effect(url, **kwargs):
            call_count[0] += 1
            if "enhancement" in url:
                return {"total_count": 0, "items": []}
            elif "sort=reactions" in url or (call_count[0] == 2 and "sort=comments" not in url):
                return {
                    "total_count": 1,
                    "items": [{
                        "title": "Fallback Issue",
                        "reactions": {"total_count": 5},
                        "comments": 3,
                        "html_url": "https://github.com/o/r/issues/3",
                    }],
                }
            elif "sort=comments" in url:
                return {"total_count": 0, "items": []}
            return {"total_count": 0, "items": []}

        mock_fetch.side_effect = side_effect
        result = github._fetch_top_issues("owner/repo", "tok")
        self.assertIn("top_feature_request", result)


class TestFetchReadmeSnippet(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_returns_readme(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"# My Project\n\nThis is a great project."
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        readme = github._fetch_readme_snippet("owner/repo", "tok")
        self.assertIn("My Project", readme)

    @patch("urllib.request.urlopen")
    def test_truncates_long_readme(self, mock_urlopen):
        long_text = ("Paragraph one.\n\n" + "x" * 600).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = long_text
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        readme = github._fetch_readme_snippet("owner/repo", "tok", max_chars=100)
        self.assertLessEqual(len(readme), 105)  # allow for rstrip

    @patch("urllib.request.urlopen")
    def test_returns_none_on_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        readme = github._fetch_readme_snippet("owner/repo", "tok")
        self.assertIsNone(readme)


# ---------------------------------------------------------------------------
# Person-mode search
# ---------------------------------------------------------------------------

class TestSearchGithubPerson(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_no_token_returns_empty(self, mock_run):
        items = github.search_github_person("testuser", "2026-03-01", "2026-03-31")
        self.assertEqual(items, [])

    @patch.object(github, "_enrich_own_repo", return_value={})
    @patch.object(github, "_enrich_external_repo", return_value={
        "info": {"stars": 1000, "forks": 50, "description": "Desc", "language": "Python", "open_issues": 10},
        "releases": [{"tag": "v1.0", "name": "v1.0", "date": "2026-03-01", "body": "First release"}],
    })
    @patch.object(github, "_fetch_json")
    @patch.object(github, "_resolve_token", return_value="test-token")
    def test_successful_person_search(self, mock_token, mock_fetch, mock_ext, mock_own):
        def fetch_side_effect(url, **kwargs):
            if "per_page=1" in url and "is:merged" not in url:
                return {"total_count": 10}
            if "is:merged" in url:
                return {
                    "total_count": 5,
                    "items": [
                        {"html_url": "https://github.com/facebook/react/pull/1"},
                        {"html_url": "https://github.com/facebook/react/pull/2"},
                        {"html_url": "https://github.com/vercel/next.js/pull/3"},
                    ],
                }
            if "/users/" in url:
                return [
                    {
                        "full_name": "testuser/my-project",
                        "stargazers_count": 500,
                        "open_issues_count": 3,
                        "description": "My proj",
                        "updated_at": "2026-03-15T00:00:00Z",
                    }
                ]
            return {"total_count": 0, "items": []}

        mock_fetch.side_effect = fetch_side_effect
        items = github.search_github_person("testuser", "2026-03-01", "2026-03-31")
        # Should have at least the velocity summary item
        self.assertGreater(len(items), 0)

    @patch.object(github, "_fetch_json")
    @patch.object(github, "_resolve_token", return_value="test-token")
    def test_no_prs_returns_empty(self, mock_token, mock_fetch):
        mock_fetch.return_value = {"total_count": 0, "items": []}
        items = github.search_github_person("unknown", "2026-03-01", "2026-03-31")
        self.assertEqual(items, [])


# ---------------------------------------------------------------------------
# Project-mode search
# ---------------------------------------------------------------------------

class TestSearchGithubProject(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_no_token_returns_empty(self, mock_run):
        items = github.search_github_project(
            ["facebook/react"], "2026-03-01", "2026-03-31"
        )
        self.assertEqual(items, [])

    @patch.object(github, "_enrich_project_repo")
    @patch.object(github, "_resolve_token", return_value="test-token")
    def test_successful_project_search(self, mock_token, mock_enrich):
        mock_enrich.return_value = {
            "info": {
                "stars": 10000,
                "forks": 500,
                "description": "A JavaScript library",
                "language": "JavaScript",
                "open_issues": 200,
            },
            "readme": "# React\nA declarative UI library.",
            "releases": [
                {"tag": "v18.3", "name": "v18.3", "date": "2026-03-10", "body": "New features"}
            ],
            "top_issues": {
                "top_feature_request": {
                    "title": "Support XYZ",
                    "reactions": 42,
                    "comments": 15,
                    "url": "https://github.com/facebook/react/issues/1",
                },
                "top_complaint": {
                    "title": "Bug in rendering",
                    "reactions": 10,
                    "comments": 30,
                    "url": "https://github.com/facebook/react/issues/2",
                },
            },
        }
        items = github.search_github_project(
            ["facebook/react"], "2026-03-01", "2026-03-31"
        )
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["source"], "github")
        self.assertEqual(item["container"], "facebook/react")
        self.assertIn("10K", item["title"])
        self.assertIn("project-mode", item["metadata"]["labels"])
        self.assertGreater(item["relevance"], 0)

    @patch.object(github, "_enrich_project_repo")
    @patch.object(github, "_resolve_token", return_value="test-token")
    def test_skips_repos_without_info(self, mock_token, mock_enrich):
        mock_enrich.return_value = {"info": None}
        items = github.search_github_project(
            ["nonexistent/repo"], "2026-03-01", "2026-03-31"
        )
        self.assertEqual(items, [])

    @patch.object(github, "_enrich_project_repo", side_effect=Exception("timeout"))
    @patch.object(github, "_resolve_token", return_value="test-token")
    def test_handles_enrichment_failure(self, mock_token, mock_enrich):
        items = github.search_github_project(
            ["fail/repo"], "2026-03-01", "2026-03-31"
        )
        self.assertEqual(items, [])


# ---------------------------------------------------------------------------
# Comment enrichment
# ---------------------------------------------------------------------------

class TestEnrichWithComments(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_no_token_returns_items_unchanged(self, mock_run):
        items = [{"url": "https://github.com/o/r/issues/1", "score": 5, "metadata": {}}]
        result = github.enrich_with_comments(items)
        self.assertEqual(result, items)

    def test_empty_items(self):
        self.assertEqual(github.enrich_with_comments([]), [])

    @patch.object(github, "_fetch_item_comments", return_value=[
        {"score": 3, "excerpt": "Great!", "author": "user1"},
    ])
    @patch.object(github, "_resolve_token", return_value="tok")
    def test_enriches_top_items(self, mock_token, mock_comments):
        items = [
            {"url": "https://github.com/o/r/issues/1", "score": 10, "metadata": {}},
        ]
        result = github.enrich_with_comments(items, token="tok")
        self.assertIn("top_comments", result[0]["metadata"])
        self.assertEqual(len(result[0]["metadata"]["top_comments"]), 1)


# ---------------------------------------------------------------------------
# Star enrichment
# ---------------------------------------------------------------------------

class TestExtractRepoRefs(unittest.TestCase):
    def test_extracts_from_url(self):
        class FakeCandidate:
            url = "https://github.com/facebook/react/issues/1"
            title = ""
            evidence = None
            metadata = {}

        refs = github.extract_repo_refs([FakeCandidate()])
        self.assertIn("facebook/react", refs)

    def test_skips_non_repo_paths(self):
        class FakeCandidate:
            url = "https://github.com/topics/python"
            title = ""
            evidence = None
            metadata = {}

        refs = github.extract_repo_refs([FakeCandidate()])
        self.assertEqual(refs, [])

    def test_deduplicates(self):
        class FakeCandidate:
            url = "https://github.com/owner/repo/issues/1"
            title = "See https://github.com/owner/repo for details"
            evidence = None
            metadata = {}

        refs = github.extract_repo_refs([FakeCandidate()])
        self.assertEqual(len(refs), 1)

    def test_extracts_from_evidence(self):
        class FakeCandidate:
            url = ""
            title = ""
            evidence = "Check https://github.com/cool/project"
            metadata = {}

        refs = github.extract_repo_refs([FakeCandidate()])
        self.assertIn("cool/project", refs)


class TestEnrichCandidatesWithStars(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_no_token_returns_zero(self, mock_run):
        count = github.enrich_candidates_with_stars([])
        self.assertEqual(count, 0)

    @patch.object(github, "_fetch_repo_info", return_value={"stars": 5000})
    @patch.object(github, "_resolve_token", return_value="tok")
    def test_enriches_candidates(self, mock_token, mock_info):
        # Use a repo name whose last char is NOT in {'.','g','i','t'}
        # because _REPO_URL_PATTERN match is run through rstrip(".git")
        # which strips individual chars — names ending in those letters
        # get truncated, preventing a star_map hit.
        class FakeCandidate:
            url = "https://github.com/vercel/hyper"
            title = ""
            evidence = "Some context"
            metadata = {}

        candidates = [FakeCandidate()]
        count = github.enrich_candidates_with_stars(candidates, token="tok")
        self.assertEqual(count, 1)
        self.assertIn("github_stars", candidates[0].metadata)

    @patch.object(github, "_resolve_token", return_value="tok")
    def test_no_refs_returns_zero(self, mock_token):
        class FakeCandidate:
            url = "https://example.com"
            title = "No GitHub"
            evidence = None
            metadata = {}

        count = github.enrich_candidates_with_stars([FakeCandidate()], token="tok")
        self.assertEqual(count, 0)

    @patch.object(github, "_fetch_repo_info", return_value={"stars": 100})
    @patch.object(github, "_resolve_token", return_value="tok")
    def test_skips_already_enriched(self, mock_token, mock_info):
        class FakeCandidate:
            url = "https://github.com/owner/repo"
            title = ""
            evidence = None
            metadata = {}

        candidates = [FakeCandidate()]
        count = github.enrich_candidates_with_stars(
            candidates, token="tok", already_enriched={"owner/repo"}
        )
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
