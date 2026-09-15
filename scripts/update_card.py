import os
import re
import requests

# Set to your exact GitHub username
USERNAME = "Sufal-kc"
TOKEN = os.getenv("GH_TOKEN")
headers = {"Authorization": f"token {TOKEN}"} if TOKEN else {}

# 1. Fetch User Stats
user_res = requests.get(f"https://api.github.com/users/{USERNAME}", headers=headers).json()
public_repos = str(user_res.get("public_repos", "--"))
followers = str(user_res.get("followers", "--"))

# 2. Fetch Stars Across Public Repos
repos_res = requests.get(f"https://api.github.com/users/{USERNAME}/repos?per_page=100", headers=headers).json()
stars_count = sum(repo.get("stargazers_count", 0) for repo in repos_res if isinstance(repo, dict))

# 3. Fetch Latest Public Push Event
events_res = requests.get(f"https://api.github.com/users/{USERNAME}/events/public", headers=headers).json()
latest_repo = "N/A"
latest_msg = "No recent commits"
event_type = "PushEvent"

if isinstance(events_res, list):
    for event in events_res:
        if event.get("type") == "PushEvent":
            latest_repo = event.get("repo", {}).get("name", "Sufal-kc/repo")
            commits = event.get("payload", {}).get("commits", [])
            if commits:
                latest_msg = commits[-1].get("message", "").split("\n")[0][:22]
            break

# Helper function to replace text inside <tspan id="X">...</tspan>
def replace_tspan(content, elem_id, new_val):
    pattern = rf'(<tspan[^>]*id="{elem_id}"[^>]*>)(.*?)(</tspan>)'
    return re.sub(pattern, rf'\g<1>{new_val}\g<3>', content)

# Read and update SVG
with open("profile-card.svg", "r", encoding="utf-8") as f:
    svg = f.read()

svg = replace_tspan(svg, "feed-repo", latest_repo)
svg = replace_tspan(svg, "feed-msg", latest_msg)
svg = replace_tspan(svg, "feed-event", event_type)
svg = replace_tspan(svg, "stat-repos", public_repos)
svg = replace_tspan(svg, "stat-stars", str(stars_count))
svg = replace_tspan(svg, "stat-followers", followers)

with open("profile-card.svg", "w", encoding="utf-8") as f:
    f.write(svg)

print("Successfully updated profile-card.svg for user Sufal-kc!")