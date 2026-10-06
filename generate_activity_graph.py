"""Render a profile activity overview from GitHub contribution totals."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


USERNAME = "Nasd00"
OUTPUT = Path("assets/activity-graph.svg")
FEATURED_REPOSITORIES = (
    ("psu-nittanyaiadvance/26-S-Lockheed-1", "https://github.com/psu-nittanyaiadvance/26-S-Lockheed-1"),
    ("acmpsu/acm-website", "https://github.com/acmpsu/acm-website"),
    ("Nasd00/iris", "https://github.com/Nasd00/iris"),
)
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


@dataclass(frozen=True)
class Activity:
    counts: dict[str, int]
    featured_repositories: tuple[tuple[str, str], ...] = FEATURED_REPOSITORIES


def fetch_activity(token: str, now: datetime | None = None) -> Activity:
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

    return Activity(counts=counts)


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


def display_percentages(counts: dict[str, int]) -> tuple[dict[str, int], bool]:
    """Keep a visible review minimum when the API omits reported reviews."""
    shares = percentages(counts)
    review_minimum = bool(sum(counts.values())) and shares["reviews"] == 0
    if review_minimum:
        donor = max((kind for kind in shares if kind != "reviews"), key=shares.get)
        shares[donor] -= 1
        shares["reviews"] = 1
    return shares, review_minimum


def render_svg(activity: Activity, generated_at: datetime, *, preview: bool = False) -> str:
    counts = activity.counts
    if set(counts) != {kind for kind, _ in KINDS} or any(
        type(value) is not int or value < 0 for value in counts.values()
    ):
        raise ValueError("Expected four nonnegative integer contribution counts")

    shares, review_minimum = display_percentages(counts)
    cx, cy, radius = 754, 242, 114
    largest = max(shares.values())
    review_radius = radius * shares["reviews"] / largest if largest else 0
    if review_minimum:
        review_radius = max(review_radius, 9)
    points = [
        (cx, cy - review_radius),
        (cx + radius * shares["issues"] / largest, cy),
        (cx, cy + radius * shares["pull_requests"] / largest),
        (cx - radius * shares["commits"] / largest, cy),
    ] if largest else [(cx, cy)] * 4
    polygon = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    markers = "\n".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" class="marker">'
        f'<title>{escape(label)}: {shares[kind]}%'
        f'{" minimum" if kind == "reviews" and review_minimum else ""}</title></circle>'
        for (kind, label), (x, y) in zip(KINDS, points)
    )
    repo_rows = "\n".join(
        f'<a href="{escape(url)}" target="_blank" rel="noopener">'
        f'<text class="repo" x="51" y="{177 + index * 30}">'
        f'{escape(name if len(name) <= 41 else name[:38] + "…")}'
        f'<title>{escape(name)}</title></text></a>'
        for index, (name, url) in enumerate(activity.featured_repositories)
    )
    generated = generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    summary = ", ".join(f"{label}: {shares[kind]}%" for kind, label in KINDS)
    review_note = ""
    if review_minimum:
        review_note = (
            " Code reviews use a 1% display minimum because the account owner reports reviews that the API omits."
            if counts["reviews"] == 0
            else " Code reviews use a 1% display minimum because the rounded share is below 1%."
        )
    description = (
        f"Illustrative preview based on the supplied screenshot. {summary}."
        if preview
        else f"{summary}. Updated {generated}. Counts include accessible private repositories.{review_note}"
    )
    preview_note = (
        '<text class="small" x="26" y="407">Preview from supplied reference</text>'
        if preview else ""
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="430" viewBox="0 0 1000 430" role="img" aria-labelledby="title description">
  <title id="title">GitHub activity mix{', preview' if preview else ', past 365 days'}</title>
  <desc id="description">{escape(description)}</desc>
  <style>
    .card {{ fill: #ffffff; stroke: #d0d7de; stroke-width: 1.5; }}
    .pill {{ fill: #f6f8fa; stroke: #d0d7de; }}
    .divider {{ stroke: #d0d7de; }}
    .axis {{ stroke: #176b2c; stroke-width: 2.5; }}
    .area {{ fill: #7dd787; fill-opacity: .72; }}
    .marker {{ fill: #ffffff; stroke: #176b2c; stroke-width: 2.5; }}
    .heading {{ fill: #1f2328; font: 20px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .body {{ fill: #1f2328; font: 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .repo {{ fill: #0969da; font: 600 18px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .label {{ fill: #57606a; font: 17px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .percent {{ fill: #57606a; font: 16px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .small {{ fill: #656d76; font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    @media (prefers-color-scheme: dark) {{
      .card {{ fill: #0d1117; stroke: #30363d; }}
      .pill {{ fill: #161b22; stroke: #30363d; }}
      .divider {{ stroke: #30363d; }}
      .heading, .body {{ fill: #e6edf3; }}
      .repo {{ fill: #2f81f7; }}
      .label {{ fill: #c9d1d9; }}
      .percent {{ fill: #8b949e; }}
      .small {{ fill: #8b949e; }}
      .marker {{ fill: #0d1117; }}
    }}
  </style>
  <rect class="card" x="1" y="1" width="998" height="428" rx="5"/>
  <rect class="pill" x="24" y="18" width="141" height="34" rx="8"/>
  <text class="small" x="40" y="40">Past 365 days</text>
  <rect class="pill" x="175" y="18" width="214" height="34" rx="8"/>
  <text class="small" x="191" y="40">Public + private activity</text>
  <text class="heading" x="25" y="94">Activity overview</text>
  <path class="divider" d="M495 80 V405"/>
  <path d="M27 131 h14 v13 h-3 v5 l-4 -3 -4 3 v-5 h-3 z" fill="none" stroke="#57606a" stroke-width="1.7" stroke-linejoin="round"/>
  <text class="body" x="51" y="145">Featured repositories</text>
  {repo_rows}
  <path class="axis" d="M754 127 V357 M639 242 H869"/>
  <polygon class="area" points="{polygon}"/>
  {markers}
  <text class="percent" x="754" y="88" text-anchor="middle">{shares['reviews']}%{'+' if review_minimum else ''}</text>
  <text class="label" x="754" y="109" text-anchor="middle">Code reviews</text>
  <text class="percent" x="754" y="385" text-anchor="middle">{shares['pull_requests']}%</text>
  <text class="label" x="754" y="407" text-anchor="middle">Pull requests</text>
  <text class="percent" x="598" y="235" text-anchor="middle">{shares['commits']}%</text>
  <text class="label" x="598" y="257" text-anchor="middle">Commits</text>
  <text class="percent" x="913" y="235" text-anchor="middle">{shares['issues']}%</text>
  <text class="label" x="913" y="257" text-anchor="middle">Issues</text>
  {preview_note}
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
        activity = Activity(
            counts={"reviews": 22, "issues": 0, "pull_requests": 13, "commits": 65},
        )
    else:
        token = os.environ.get("GH_PROFILE_TOKEN", "")
        if not token and os.environ.get("GITHUB_ACTIONS") == "true":
            print("::error title=Missing profile token::GH_PROFILE_TOKEN is not available", flush=True)
        try:
            activity = fetch_activity(token, now)
        except RestrictedContributionsError:
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(
                    "::error title=Incomplete private contribution access::"
                    "GH_PROFILE_TOKEN cannot read all contributions",
                    flush=True,
                )
            raise
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_svg(activity, now, preview=args.preview), encoding="utf-8")
    print(
        f"Wrote {args.output}"
        f"{' preview' if args.preview else f' from {sum(activity.counts.values())} contributions'}"
    )


if __name__ == "__main__":
    main()
