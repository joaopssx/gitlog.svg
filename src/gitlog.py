#!/usr/bin/env python3
"""
gitlog.svg - generates assets/gitlog.svg with lines added, lines removed and
commits, summed across all of the user's repositories.

Standard library only.

Environment variables:
  GH_TOKEN       GitHub read token (required, except with --demo)
  GH_USER        GitHub username (default: joaopssx)
  INCLUDE_FORKS  "true" to also count forks (default: false)

Usage:
  python src/gitlog.py          # real data
  python src/gitlog.py --demo   # sample data
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

API = "https://api.github.com"
USER = os.environ.get("GH_USER", "joaopssx")
TOKEN = os.environ.get("GH_TOKEN", "")
INCLUDE_FORKS = os.environ.get("INCLUDE_FORKS", "false").lower() == "true"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG_PATH = os.path.join(ROOT, "assets", "gitlog.svg")
JSON_PATH = os.path.join(ROOT, "assets", "stats.json")


def api_get(url):
    """GET a URL from the API. Returns (status, json); never raises on HTTP errors."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gitlog-svg",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as err:
        return err.code, None
    except urllib.error.URLError:
        return 0, None


def list_repos():
    """List the user's repositories (private ones too if the token allows it)."""
    repos, page = [], 1
    while True:
        url = f"{API}/user/repos?per_page=100&page={page}&affiliation=owner"
        status, data = api_get(url)
        if status != 200:
            url = f"{API}/users/{USER}/repos?per_page=100&page={page}&type=owner"
            status, data = api_get(url)
        if status != 200 or not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return [
        r for r in repos
        if r["owner"]["login"].lower() == USER.lower()
        and (INCLUDE_FORKS or not r["fork"])
    ]


def repo_totals(full_name):
    """Sum the user's additions, deletions and commits in one repository."""
    url = f"{API}/repos/{full_name}/stats/contributors"
    for attempt in range(6):
        status, data = api_get(url)
        if status == 200 and isinstance(data, list):
            for contributor in data:
                author = (contributor.get("author") or {}).get("login", "")
                if author.lower() == USER.lower():
                    adds = sum(w["a"] for w in contributor["weeks"])
                    dels = sum(w["d"] for w in contributor["weeks"])
                    return full_name, adds, dels, contributor["total"]
            return full_name, 0, 0, 0
        if status == 202:  # GitHub is still computing the stats
            time.sleep(3 + attempt * 2)
            continue
        break
    return full_name, 0, 0, 0


def collect():
    repos = list_repos()
    names = [r["full_name"] for r in repos]
    total_a = total_d = total_c = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for name, a, d, c in pool.map(repo_totals, names):
            print(f"{name:<45} +{a:<8} -{d:<8} commits={c}")
            total_a += a
            total_d += d
            total_c += c
    return total_a, total_d, total_c, len(repos)


def fmt(n):
    return f"{n:,}"


def ratio_bar(added, removed):
    """760px bar: green is the share of added lines, red the share of removed."""
    total = added + removed
    width = 760
    green = round(width * added / total) if total else 0
    red = width - green if total else 0
    return (
        '<clipPath id="barclip"><rect x="30" y="172" width="760" height="8" rx="4"/></clipPath>\n'
        '  <g clip-path="url(#barclip)">\n'
        '    <rect x="30" y="172" width="760" height="8" fill="#21262d"/>\n'
        f'    <rect x="30" y="172" width="{green}" height="8" fill="#3fb950"/>\n'
        f'    <rect x="{30 + green}" y="172" width="{red}" height="8" fill="#f85149"/>\n'
        '  </g>'
    )


def build_svg(added, removed, commits, repos):
    net = added - removed
    net_sign = "+" if net >= 0 else "-"
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="820" height="250" viewBox="0 0 820 250" role="img" aria-label="Git statistics for {USER}">
  <title>Git statistics for {USER}</title>
  <style>
    .mono {{ font-family: 'JetBrains Mono', 'Fira Code', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace; }}
    .muted {{ fill: #8b949e; font-size: 13px; }}
    .label {{ fill: #8b949e; font-size: 13px; letter-spacing: 1px; }}
    .num   {{ font-size: 34px; font-weight: 700; }}
    .prompt {{ fill: #e6edf3; font-size: 14px; }}
  </style>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0d1117"/>
      <stop offset="1" stop-color="#161b22"/>
    </linearGradient>
  </defs>

  <rect x="1" y="1" width="818" height="248" rx="12" fill="url(#bg)" stroke="#30363d" stroke-width="2"/>
  <rect x="1" y="1" width="818" height="36" rx="12" fill="#161b22"/>
  <rect x="1" y="24" width="818" height="13" fill="#161b22"/>
  <line x1="1" y1="37" x2="819" y2="37" stroke="#30363d"/>
  <circle cx="24" cy="19" r="6" fill="#ff5f56"/>
  <circle cx="44" cy="19" r="6" fill="#ffbd2e"/>
  <circle cx="64" cy="19" r="6" fill="#27c93f"/>
  <text x="410" y="24" text-anchor="middle" class="mono muted">{USER} — gitlog.svg</text>

  <text x="30" y="68" class="mono prompt"><tspan fill="#3fb950">$</tspan> git log --author="{USER}" --shortstat --all-repos</text>

  <text x="30" y="112" class="mono label">LINES ADDED</text>
  <text x="30" y="152" class="mono num" fill="#3fb950">+{fmt(added)}</text>

  <text x="300" y="112" class="mono label">LINES REMOVED</text>
  <text x="300" y="152" class="mono num" fill="#f85149">-{fmt(removed)}</text>

  <text x="570" y="112" class="mono label">COMMITS</text>
  <text x="570" y="152" class="mono num" fill="#58a6ff">{fmt(commits)}</text>

  {ratio_bar(added, removed)}

  <line x1="30" y1="200" x2="790" y2="200" stroke="#21262d"/>
  <text x="30" y="228" class="mono muted">net {net_sign}{fmt(abs(net))} lines  ·  {repos} repositories</text>
  <text x="790" y="228" text-anchor="end" class="mono muted">updated {updated}</text>
</svg>
"""


def unchanged(new):
    """True if the numbers match the last run and the SVG already exists."""
    try:
        with open(JSON_PATH, encoding="utf-8") as f:
            old = json.load(f)
    except (OSError, ValueError):
        return False
    return old == new and os.path.exists(SVG_PATH)


def main():
    demo = "--demo" in sys.argv
    if demo:
        added, removed, commits, repos = 184_320, 61_754, 1_482, 42
    else:
        if not TOKEN:
            sys.exit("Error: set the GH_TOKEN environment variable.")
        added, removed, commits, repos = collect()

    new = {"added": added, "removed": removed, "commits": commits, "repos": repos}

    # Skip rewriting so the bot doesn't push empty commits that only change the timestamp.
    if not demo and unchanged(new):
        print("\nNumbers unchanged. Nothing to update.")
        return

    os.makedirs(os.path.dirname(SVG_PATH), exist_ok=True)
    with open(SVG_PATH, "w", encoding="utf-8") as f:
        f.write(build_svg(added, removed, commits, repos))
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=2)
    print(f"\nSVG written: +{added} -{removed} commits={commits} repos={repos}")


if __name__ == "__main__":
    main()
