import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from xml.etree import ElementTree

import generate_activity_graph as graph


class GraphTests(unittest.TestCase):
    def test_percentages_total_100_with_equal_counts(self):
        counts = {"reviews": 1, "issues": 1, "pull_requests": 1, "commits": 0}
        self.assertEqual(sum(graph.percentages(counts).values()), 100)
        zeros = {kind: 0 for kind in counts}
        self.assertEqual(graph.percentages(zeros), zeros)

    def test_svg_matches_reference_proportions(self):
        counts = {"reviews": 22, "issues": 0, "pull_requests": 13, "commits": 65}
        svg = graph.render_svg(counts, datetime(2026, 10, 6, tzinfo=timezone.utc), preview=True)
        root = ElementTree.fromstring(svg)
        polygon = root.find("{http://www.w3.org/2000/svg}polygon")
        self.assertEqual(polygon.attrib["points"], "310.0,157.6 310.0,205.0 310.0,233.0 170.0,205.0")
        self.assertIn("Preview from supplied reference", svg)
        self.assertNotIn("accessible private repositories", svg)

    @patch("generate_activity_graph.urlopen")
    def test_fetch_counts_uses_authenticated_viewer_and_all_categories(self, urlopen):
        response = {
            "data": {
                "viewer": {"login": "Nasd00"},
                "user": {"contributionsCollection": {
                    "restrictedContributionsCount": 0,
                    "totalCommitContributions": 65,
                    "totalIssueContributions": 0,
                    "totalPullRequestContributions": 13,
                    "totalPullRequestReviewContributions": 22,
                }},
            }
        }
        urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
        counts = graph.fetch_counts("test-token", datetime(2026, 10, 6, tzinfo=timezone.utc))
        self.assertEqual(counts, {"reviews": 22, "issues": 0, "pull_requests": 13, "commits": 65})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertIn("2025-10-06", request.data.decode())

    @patch("generate_activity_graph.urlopen")
    def test_rejects_totals_when_private_contributions_are_restricted(self, urlopen):
        response = {
            "data": {
                "viewer": {"login": "Nasd00"},
                "user": {"contributionsCollection": {"restrictedContributionsCount": 125}},
            }
        }
        urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
        with self.assertRaisesRegex(ValueError, "125 restricted contributions"):
            graph.fetch_counts("test-token")


if __name__ == "__main__":
    unittest.main()
