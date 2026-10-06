"""Render a profile activity overview from GitHub contribution totals."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


USERNAME = "Nasd00"
OUTPUT = Path("assets/activity-graph.svg")
KINDS = (
    ("reviews", "Code reviews"),
    ("issues", "Issues"),
    ("pull_requests", "Pull requests"),
    ("commits", "Commits"),
)
GRAPHQL = """
query Activity($login: String!, $from: DateTime!, $to: DateTime!) {
  viewer { login }
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      restrictedContributionsCount
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
    }
  }
}
"""


class RestrictedContributionsError(ValueError):
    """The supplied token cannot see every contribution in the time window."""


def fetch_counts(token: str, now: datetime | None = None) -> dict[str, int]:
    if not token:
        raise ValueError("GH_PROFILE_TOKEN is required (classic PAT with read:user scope)")

    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=365)
    payload = json.dumps(
        {
            "query": GRAPHQL,
            "variables": {
                "login": USERNAME,
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
        }
    ).encode("utf-8")
    request = Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "Nasd00-profile-activity-graph",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except (HTTPError, URLError) as error:
        raise RuntimeError(f"GitHub GraphQL request failed: {error}") from error

    if result.get("errors"):
        messages = "; ".join(error["message"] for error in result["errors"])
        raise RuntimeError(f"GitHub GraphQL error: {messages}")
    data = result.get("data") or {}
    viewer = (data.get("viewer") or {}).get("login", "")
    if viewer.lower() != USERNAME.lower():
        raise ValueError(f"GH_PROFILE_TOKEN must belong to {USERNAME}; got {viewer or 'unknown'}")
    user = data.get("user") or {}
    collection = user.get("contributionsCollection") or {}
    restricted = collection.get("restrictedContributionsCount")
    if type(restricted) is not int or restricted < 0:
        raise ValueError("GitHub returned an incomplete restricted contribution count")
    if restricted:
        raise RestrictedContributionsError(
            f"GitHub reports {restricted} restricted contributions that this token cannot access. "
            "Use a Nasd00 classic PAT with read:user scope and authorize any required organization SSO."
        )
    fields = {
        "reviews": "totalPullRequestReviewContributions",
        "issues": "totalIssueContributions",
        "pull_requests": "totalPullRequestContributions",
        "commits": "totalCommitContributions",
    }
    counts = {kind: collection.get(field) for kind, field in fields.items()}
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ValueError("GitHub returned incomplete contribution counts")
    return counts


def percentages(counts: dict[str, int]) -> dict[str, int]:
    """Round shares to whole percents that always total 100."""
    total = sum(counts.values())
    if total == 0:
        return {kind: 0 for kind, _ in KINDS}
    exact = {kind: 100 * counts[kind] / total for kind, _ in KINDS}
    rounded = {kind: int(exact[kind]) for kind, _ in KINDS}
    remaining = 100 - sum(rounded.values())
    order = sorted(rounded, key=lambda kind: exact[kind] - rounded[kind], reverse=True)
    for kind in order[:remaining]:
        rounded[kind] += 1
    return rounded


def render_svg(counts: dict[str, int], generated_at: datetime, *, preview: bool = False) -> str:
    if set(counts) != {kind for kind, _ in KINDS} or any(
        type(value) is not int or value < 0 for value in counts.values()
    ):
        raise ValueError("Expected four nonnegative integer contribution counts")

    shares = percentages(counts)
    total = sum(counts.values())
    cx, cy, radius = 310, 205, 140
    largest = max(counts.values())
    points = [
        (cx, cy - radius * counts["reviews"] / largest),
        (cx + radius * counts["issues"] / largest, cy),
        (cx, cy + radius * counts["pull_requests"] / largest),
        (cx - radius * counts["commits"] / largest, cy),
    ] if largest else [(cx, cy)] * 4
    polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    markers = "\n".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" class="marker">'
        f'<title>{escape(label)}: {shares[kind]}%'
        f'{"" if preview else f" ({counts[kind]} contributions)"}</title></circle>'
        for (kind, label), (x, y) in zip(KINDS, points)
        if counts[kind]
    )
    generated = generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    summary = ", ".join(f"{label}: {shares[kind]}%" for kind, label in KINDS)
    description = (
        f"Illustrative preview based on the supplied screenshot. {summary}."
        if preview
        else f"{summary}. Updated {generated}. Counts include accessible private repositories."
    )
    footer = (
        '<text class="preview" x="310" y="413" text-anchor="middle">'
        'Preview from supplied reference · live data pending</text>'
        if preview else ""
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="620" height="420" viewBox="0 0 620 420" role="img" aria-labelledby="title description">
  <title id="title">GitHub activity mix{', preview' if preview else ', past 365 days'}</title>
  <desc id="description">{escape(description)}</desc>
  <style>
    .card {{ fill: #ffffff; stroke: #d0d7de; stroke-width: 1.5; }}
    .axis {{ stroke: #40c463; stroke-width: 2.5; }}
    .area {{ fill: #40c463; fill-opacity: .82; }}
    .marker {{ fill: #ffffff; stroke: #40c463; stroke-width: 2.5; }}
    .label {{ fill: #57606a; font: 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .percent {{ fill: #8c959f; font: 14px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .preview {{ fill: #8c959f; font: 10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    @media (prefers-color-scheme: dark) {{
      .card {{ fill: #0d1117; stroke: #30363d; }}
      .label {{ fill: #c9d1d9; }}
      .percent {{ fill: #8b949e; }}
      .marker {{ fill: #0d1117; }}
    }}
  </style>
  <rect class="card" x="1" y="1" width="618" height="418" rx="4"/>
  <path class="axis" d="M310 63 V347 M170 205 H450"/>
  <polygon class="area" points="{polygon}"/>
  {markers}
  <text class="percent" x="310" y="28" text-anchor="middle">{shares['reviews']}%</text>
  <text class="label" x="310" y="49" text-anchor="middle">Code reviews</text>
  <text class="percent" x="310" y="375" text-anchor="middle">{shares['pull_requests']}%</text>
  <text class="label" x="310" y="397" text-anchor="middle">Pull requests</text>
  <text class="percent" x="125" y="197" text-anchor="middle">{shares['commits']}%</text>
  <text class="label" x="125" y="219" text-anchor="middle">Commits</text>
  <text class="percent" x="496" y="197" text-anchor="middle">{shares['issues']}%</text>
  <text class="label" x="496" y="219" text-anchor="middle">Issues</text>
  {footer}
</svg>
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--preview", action="store_true", help="render the supplied screenshot's example values"
    )
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.preview:
        counts = {"reviews": 22, "issues": 0, "pull_requests": 13, "commits": 65}
    else:
        token = os.environ.get("GH_PROFILE_TOKEN", "")
        if not token and os.environ.get("GITHUB_ACTIONS") == "true":
            print("::error title=Missing profile token::GH_PROFILE_TOKEN is not available", flush=True)
        try:
            counts = fetch_counts(token, now)
        except RestrictedContributionsError:
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(
                    "::error title=Incomplete private contribution access::"
                    "GH_PROFILE_TOKEN cannot read all contributions",
                    flush=True,
                )
            raise
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(counts, now, preview=args.preview), encoding="utf-8")
    print(f"Wrote {args.output}{' preview' if args.preview else f' from {sum(counts.values())} contributions'}")


if __name__ == "__main__":
    main()
