"""Refresh the live values (stats and latest push) in the profile card SVGs.

Every profile*.svg in the repository root is scanned; a value is written into
each <tspan id="..."> placeholder that exists. Values that could not be fetched
are left as they were, so an API hiccup never blanks the card.
"""
import datetime
import glob
import html
import os
import re
import sys

import requests

USERNAME = os.getenv("GITHUB_REPOSITORY_OWNER") or "Sufal-kc"
TOKEN = os.getenv("GH_TOKEN")
API = "https://api.github.com"
MAX_MSG_LEN = 22

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

session = requests.Session()
session.headers["Accept"] = "application/vnd.github+json"
if TOKEN:
    session.headers["Authorization"] = f"Bearer {TOKEN}"


def get(path, **params):
    """GET a GitHub API path; return the parsed JSON, or None on any failure."""
    try:
        res = session.get(f"{API}{path}", params=params, timeout=15)
        res.raise_for_status()
        return res.json()
    except (requests.RequestException, ValueError) as err:
        print(f"warning: GET {path} failed: {err}", file=sys.stderr)
        return None


CALENDAR_QUERY = (
    "query($login:String!,$from:DateTime,$to:DateTime){user(login:$login){"
    "contributionsCollection(from:$from,to:$to){contributionCalendar{"
    "totalContributions weeks{contributionDays{date contributionCount}}}}}}"
)
MAX_STREAK_YEARS = 15


def fetch_calendar(start=None, end=None):
    """Return (total, [(date, count), ...] oldest first) for a window of up to
    a year (the last year by default), or None on any failure."""
    variables = {"login": USERNAME}
    if start and end:
        variables["from"] = f"{start.isoformat()}T00:00:00Z"
        variables["to"] = f"{end.isoformat()}T23:59:59Z"
    try:
        res = session.post(
            f"{API}/graphql",
            json={"query": CALENDAR_QUERY, "variables": variables},
            timeout=15,
        )
        res.raise_for_status()
        calendar = res.json()["data"]["user"]["contributionsCollection"][
            "contributionCalendar"
        ]
        days = [
            (datetime.date.fromisoformat(day["date"]), day["contributionCount"])
            for week in calendar["weeks"]
            for day in week["contributionDays"]
        ]
        return calendar["totalContributions"], sorted(days)
    except (requests.RequestException, ValueError, KeyError, TypeError) as err:
        print(f"warning: contributions query failed: {err}", file=sys.stderr)
        return None


def current_streak(days):
    """Count consecutive contribution days ending today (or yesterday, if there
    is nothing yet today). Returns None if an older window could not be fetched."""
    days = list(days)
    # A day that is still in progress does not break the streak
    if days and days[-1][1] == 0:
        days.pop()
    streak = 0
    for _ in range(MAX_STREAK_YEARS):
        if not days:
            return streak
        for _, count in reversed(days):
            if count == 0:
                return streak
            streak += 1
        # The streak fills the whole window, so keep counting in the year before
        end = days[0][0] - datetime.timedelta(days=1)
        earlier = fetch_calendar(end - datetime.timedelta(days=364), end)
        if earlier is None:
            return None
        days = earlier[1]
    return streak


def fetch_values():
    """Return {tspan id: text} for everything that could be fetched."""
    values = {}

    user = get(f"/users/{USERNAME}")
    if isinstance(user, dict):
        values["stat-repos"] = str(user.get("public_repos", 0))
        values["stat-followers"] = str(user.get("followers", 0))

    # Stars across all public repos (paginated)
    stars, page, complete = 0, 1, True
    while True:
        repos = get(f"/users/{USERNAME}/repos", per_page=100, page=page, type="owner")
        if not isinstance(repos, list):
            complete = False
            break
        stars += sum(repo.get("stargazers_count", 0) for repo in repos)
        if len(repos) < 100:
            break
        page += 1
    if complete:
        values["stat-stars"] = str(stars)

    # Contributions in the last year and the current streak (GraphQL needs a token)
    if TOKEN:
        calendar = fetch_calendar()
        if calendar:
            total, days = calendar
            values["stat-contribs"] = str(total)
            streak = current_streak(days)
            if streak is not None:
                values["stat-streak"] = f"{streak} day{'' if streak == 1 else 's'}"

    # Latest public push
    events = get(f"/users/{USERNAME}/events/public", per_page=100)
    if isinstance(events, list):
        push = next((e for e in events if e.get("type") == "PushEvent"), None)
        if push:
            repo = push.get("repo", {}).get("name", "")
            payload = push.get("payload", {})
            values["feed-event"] = "PushEvent"
            if repo:
                values["feed-repo"] = repo
            # Push events no longer carry the commit list, so look the head commit up
            commits = payload.get("commits") or []
            message = commits[-1].get("message", "") if commits else ""
            if not message and repo and payload.get("head"):
                commit = get(f"/repos/{repo}/commits/{payload['head']}")
                if isinstance(commit, dict):
                    message = commit.get("commit", {}).get("message", "")
            first_line = message.strip().split("\n")[0]
            if first_line:
                if len(first_line) > MAX_MSG_LEN:
                    first_line = first_line[: MAX_MSG_LEN - 1].rstrip() + "…"
                values["feed-msg"] = first_line

    if values:
        now = datetime.datetime.now(datetime.timezone.utc)
        values["feed-updated"] = now.strftime("%d %b %Y %H:%M UTC")

    return values


def replace_tspan(content, elem_id, new_val):
    """Set the text of <tspan id=elem_id>; return (content, replaced?)."""
    pattern = rf'(<tspan[^>]*\bid="{re.escape(elem_id)}"[^>]*>)(.*?)(</tspan>)'
    escaped = html.escape(new_val, quote=False)
    # A function replacement keeps backslashes in the value literal
    new_content, count = re.subn(
        pattern, lambda m: m.group(1) + escaped + m.group(3), content, flags=re.S
    )
    return new_content, count > 0


def main():
    values = fetch_values()
    if not values:
        print("error: no data could be fetched from the GitHub API", file=sys.stderr)
        return 1

    updated = 0
    for path in sorted(glob.glob(os.path.join(BASE_DIR, "profile*.svg"))):
        with open(path, encoding="utf-8") as f:
            original = f.read()
        svg, hits = original, []
        for elem_id, value in values.items():
            svg, replaced = replace_tspan(svg, elem_id, value)
            if replaced:
                hits.append(elem_id)
        name = os.path.basename(path)
        if not hits:
            print(f"{name}: no live placeholders, skipped")
            continue
        updated += 1
        if svg != original:
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg)
        print(f"{name}: set {', '.join(hits)}")

    if not updated:
        print("warning: no profile*.svg contains live placeholders", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
