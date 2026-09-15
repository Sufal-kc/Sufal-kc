import os
import re
import requests

USERNAME = "kcsufal"  # Replace with your exact GitHub username
TOKEN = os.getenv("GH_TOKEN")

headers = {"Authorization": f"token {TOKEN}"} if TOKEN else {}

# Fetch recent user events from GitHub API
response = requests.get(f"https://api.github.com/users/{USERNAME}/events/public", headers=headers)

latest_repo = "N/A"
latest_msg = "No recent push"

if response.status_code == 200:
    events = response.json()
    for event in events:
        if event["type"] == "PushEvent":
            latest_repo = event["repo"]["name"].split("/")[-1]
            commits = event["payload"].get("commits", [])
            if commits:
                latest_msg = commits[-1]["message"].split("\n")[0][:25]
            break

# Read existing SVG
with open("profile-card.svg", "r", encoding="utf-8") as f:
    svg_content = f.read()

# Replace mock values in LIVE FEED with real metrics
svg_content = re.sub(
    r'<tspan class="link">.*?</tspan>',
    f'<tspan class="link">{latest_repo}: {latest_msg}</tspan>',
    svg_content,
    count=1
)

# Save updated SVG
with open("profile-card.svg", "w", encoding="utf-8") as f:
    f.write(svg_content)