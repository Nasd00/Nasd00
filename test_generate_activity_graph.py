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
        activity = graph.Activity(counts, (
            ("psu-nittanyaiadvance/26-S-Lockheed-1", "https://github.com/psu-nittanyaiadvance/26-S-Lockheed-1"),
            ("acmpsu/acm-website", "https://github.com/acmpsu/acm-website"),
            ("Nasd00/iris", "https://github.com/Nasd00/iris"),
        ))
        svg = graph.render_svg(activity, datetime(2026, 10, 6, tzinfo=timezone.utc), preview=True)
        root = ElementTree.fromstring(svg)
        polygon = root.find("{http://www.w3.org/2000/svg}polygon")
        self.assertEqual(polygon.attrib["points"], "754.0,203.4 754.0,242.0 754.0,264.8 640.0,242.0")
        self.assertIn("Preview from supplied reference", svg)
        self.assertIn("acmpsu/acm-website", svg)
        self.assertIn("psu-nittanyaiadvance/26-S-Lockheed-1", svg)
        self.assertIn("Nasd00/iris", svg)
        self.assertIn('href="https://github.com/Nasd00/iris"', svg)
        self.assertNotIn("accessible private repositories", svg)

    @patch("generate_activity_graph.urlopen")
    def test_fetch_activity_uses_authenticated_viewer_and_aggregate_counts(self, urlopen):
        response = {
            "data": {
                "viewer": {"login": "Nasd00"},
                "user": {
                    "contributionsCollection": {
                        "restrictedContributionsCount": 0,
                        "totalCommitContributions": 65,
                        "totalIssueContributions": 0,
                        "totalPullRequestContributions": 13,
                        "totalPullRequestReviewContributions": 22,
                    },
                },
            }
        }
        urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
        activity = graph.fetch_activity("test-token", datetime(2026, 10, 6, tzinfo=timezone.utc))
        self.assertEqual(activity.counts, {"reviews": 22, "issues": 0, "pull_requests": 13, "commits": 65})
        self.assertEqual(activity.featured_repositories, graph.FEATURED_REPOSITORIES)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertIn("2025-10-06", request.data.decode())
        self.assertNotIn("nameWithOwner", request.data.decode())

    @patch("generate_activity_graph.urlopen")
    def test_rejects_totals_when_private_contributions_are_restricted(self, urlopen):
        response = {
            "data": {
                "viewer": {"login": "Nasd00"},
                "user": {"contributionsCollection": {"restrictedContributionsCount": 125}},
            }
        }
        urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
        with self.assertRaisesRegex(graph.RestrictedContributionsError, "125 restricted contributions"):
            graph.fetch_activity("test-token")

    def test_missing_reviews_get_a_one_percent_minimum(self):
        activity = graph.Activity(
            {"reviews": 0, "issues": 8, "pull_requests": 8, "commits": 84},
            (("Nasd00/Nasd00", "https://github.com/Nasd00/Nasd00"),),
        )
        svg = graph.render_svg(activity, datetime(2026, 10, 6, tzinfo=timezone.utc))
        root = ElementTree.fromstring(svg)
        self.assertIn("Code reviews: 1%", svg)
        self.assertIn(">1%+</text>", svg)
        self.assertEqual(graph.display_percentages(activity.counts)[0], {
            "reviews": 1, "issues": 8, "pull_requests": 8, "commits": 83,
        })
        self.assertEqual(len(root.findall("{http://www.w3.org/2000/svg}circle")), 4)

if __name__ == "__main__":
    unittest.main()
