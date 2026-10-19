# Activity graph setup

The graph uses the four `contributionsCollection` totals from GitHub's GraphQL API for the past 365 days. The featured repositories are curated as `(name, url)` pairs in `FEATURED_REPOSITORIES` inside `generate_activity_graph.py` and render on the left as clickable links; the GraphQL request does not fetch repository names.

The account owner reports code reviews that GitHub's contribution API currently returns as zero. When the calculated code review share would display as 0%, the graph shows a 1% minimum and subtracts one point from the largest displayed category. The SVG description records this display rule.

To include private contributions, create a classic personal access token for **Nasd00** with the `read:user` scope and provide it through the `GH_PROFILE_TOKEN` environment variable when generating the graph locally.

Generation fails if the token is missing, belongs to another account, or GitHub reports restricted contributions that the token cannot access. Fine-grained tokens without private repository access can return partial totals. Organization activity may require SSO authorization. The profile's **Private contributions** setting also controls what GitHub shows publicly.

The graph is not updated automatically. For a local refresh, set `GH_PROFILE_TOKEN` in the environment and run `python3 generate_activity_graph.py`. To render the reference preview without API access, run `python3 generate_activity_graph.py --preview`.
