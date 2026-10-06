# Activity graph setup

The graph uses the four `contributionsCollection` totals from GitHub's GraphQL API for the past 365 days. It publishes only category counts and percentages, never private repository names or URLs.

To include private contributions, create a classic personal access token for **Nasd00** with the `read:user` scope. Add it to this repository's Actions secrets as `GH_PROFILE_TOKEN`. Then run **Update activity graph** from the Actions tab once. The scheduled workflow refreshes the image daily after this branch is merged into the default branch.

The workflow fails if the token is missing, belongs to another account, or GitHub reports restricted contributions that the token cannot access. Fine-grained tokens without private repository access can return partial totals. Organization activity may require SSO authorization. The profile's **Private contributions** setting also controls what GitHub shows publicly.

For a local refresh, set `GH_PROFILE_TOKEN` in the environment and run `python3 generate_activity_graph.py`. To render the reference preview without API access, run `python3 generate_activity_graph.py --preview`.
