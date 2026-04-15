#!/usr/bin/env python3
"""
FLL Scoreboard Generator
Fetches issues from GitHub Projects, calculates team scores, generates HTML.

Scoring rules:
  - Each Done issue: creator's team gets +0.25 pts
  - Each Done issue: implementer's team gets +SP (full story points)
      EXCEPT if implementer == creator team: only +SP/2
"""

import json
import os
import sys
import requests
from datetime import datetime, timezone

# ── Config ─────────────────────────────────────────────────────────────────────
ORG = "UdL-EPS-SoftArch-Igualada"
PROJECT_NUMBER = 8          # https://github.com/orgs/UdL-EPS-SoftArch-Igualada/projects/8
TEAMS_REPO = "first-lego-league-backend"
TEAMS_FILE_PATH = ".github/teams.txt"
TOKEN = os.environ.get("GH_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
GRAPHQL_URL = "https://api.github.com/graphql"

STORY_POINTS_MAP = {
    "story-points-0_25": 0.25,
    "story-points-0_5":  0.50,
    "story-points-0_75": 0.75,
    "story-points-1":    1.00,
    "story-points-2":    2.00,
    "story-points-3":    3.00,
    "story-points-4":    4.00,
}

# ── Teams ───────────────────────────────────────────────────────────────────────

def fetch_teams():
    """Read teams.txt from the repo and build lookup structures."""
    url = f"https://raw.githubusercontent.com/{ORG}/{TEAMS_REPO}/main/{TEAMS_FILE_PATH}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=15)
    resp.raise_for_status()

    teams = []
    user_to_team = {}

    for line in resp.text.strip().splitlines():
        members = [m.strip() for m in line.strip().split() if m.strip()]
        if len(members) < 2:
            # Solo member (professor) — skip
            continue
        team_id = len(teams)
        teams.append({
            "id":      team_id,
            "name":    f"{members[0]} & {members[1]}",
            "members": members,
        })
        for m in members:
            user_to_team[m.lower()] = team_id

    return teams, user_to_team

# ── GitHub GraphQL ──────────────────────────────────────────────────────────────

def graphql(query, variables=None):
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        print("GraphQL errors:", payload["errors"], file=sys.stderr)
    return payload.get("data", {})

# ── Issues from Project ─────────────────────────────────────────────────────────

PROJECT_QUERY = """
query($org: String!, $projectNumber: Int!, $cursor: String) {
  organization(login: $org) {
    projectV2(number: $projectNumber) {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          status: fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          content {
            ... on Issue {
              number
              title
              author { login }
              assignees(first: 10) { nodes { login } }
              labels(first: 15) { nodes { name } }
              repository { name }
            }
          }
        }
      }
    }
  }
}
"""

def fetch_done_issues():
    """Fetch all project items with Status='Done' that have story points."""
    done = []
    cursor = None

    while True:
        data = graphql(PROJECT_QUERY, {"org": ORG, "projectNumber": PROJECT_NUMBER, "cursor": cursor})
        project = (data.get("organization") or {}).get("projectV2")
        if not project:
            print(
                "ERROR: Cannot access project. Make sure GH_TOKEN has 'project' scope.\n"
                "  Go to https://github.com/settings/tokens and regenerate with scope: project",
                file=sys.stderr,
            )
            sys.exit(1)

        items_data = project.get("items", {})
        nodes = items_data.get("nodes", [])
        page_info = items_data.get("pageInfo", {})

        for item in nodes:
            # Only items with Status == "Done"
            status = (item.get("status") or {}).get("name", "")
            if "done" not in status.lower():
                continue

            content = item.get("content") or {}
            if not content.get("number"):
                continue  # Skip non-issue items (e.g. draft notes)

            # Story points from labels
            labels = [l["name"] for l in content.get("labels", {}).get("nodes", [])]
            sp = next((STORY_POINTS_MAP[lb] for lb in labels if lb in STORY_POINTS_MAP), None)
            if sp is None:
                continue  # No valid story-points label → skip

            done.append({
                "number":       content["number"],
                "title":        content["title"],
                "repo":         (content.get("repository") or {}).get("name", ""),
                "creator":      (content.get("author") or {}).get("login"),
                "assignees":    [a["login"] for a in content.get("assignees", {}).get("nodes", [])],
                "story_points": sp,
            })

        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]

    return done

# ── Scoring ─────────────────────────────────────────────────────────────────────

def calculate_scores(teams, user_to_team, all_issues):
    scores = {i: {"creation": 0.0, "implementation": 0.0, "issues_created": 0, "issues_implemented": 0}
              for i in range(len(teams))}

    for issue in all_issues:
        creator   = issue["creator"]
        assignees = issue["assignees"]
        sp        = issue["story_points"]

        creator_team_id = user_to_team.get(creator.lower()) if creator else None

        # Implementer team = first assignee that belongs to a known team
        impl_team_id = None
        for a in assignees:
            t = user_to_team.get(a.lower())
            if t is not None:
                impl_team_id = t
                break

        # Creation points
        if creator_team_id is not None:
            scores[creator_team_id]["creation"] += 0.25
            scores[creator_team_id]["issues_created"] += 1

        # Implementation points
        if impl_team_id is not None:
            if impl_team_id == creator_team_id:
                scores[impl_team_id]["implementation"] += sp / 2
            else:
                scores[impl_team_id]["implementation"] += sp
            scores[impl_team_id]["issues_implemented"] += 1

    return scores

# ── Position Tracking ────────────────────────────────────────────────────────────

def load_previous_positions(out_dir):
    """Load previous team positions from positions.json. Returns {} if not found."""
    path = os.path.join(out_dir, "positions.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_positions(positions, out_dir):
    """Persist current team positions to positions.json."""
    path = os.path.join(out_dir, "positions.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(positions, f, indent=2)

def rank_teams(teams, scores):
    """Return team indices sorted by total score descending."""
    return sorted(
        range(len(teams)),
        key=lambda i: scores[i]["creation"] + scores[i]["implementation"],
        reverse=True,
    )

# ── HTML ────────────────────────────────────────────────────────────────────────

def generate_html(teams, scores, all_issues, generated_at, ranked, prev_positions):
    rows = ""
    for pos, team_id in enumerate(ranked):
        team     = teams[team_id]
        s        = scores[team_id]
        total    = s["creation"] + s["implementation"]
        rank_num = pos + 1
        rank_cls = f"rank-{rank_num}" if rank_num <= 3 else ""
        row_cls  = f"row-top-{rank_num}" if rank_num <= 3 else ""

        # Trend vs previous run
        prev_rank = prev_positions.get(team["name"])
        if prev_rank is None:
            trend_html = '<span class="trend trend-new" aria-label="new">&#x2022;</span>'
        elif prev_rank > rank_num:
            trend_html = '<span class="trend trend-up" aria-label="moved up">&#9650;</span>'
        elif prev_rank < rank_num:
            trend_html = '<span class="trend trend-down" aria-label="moved down">&#9660;</span>'
        else:
            trend_html = '<span class="trend trend-same" aria-label="no change">&mdash;</span>'

        members_html = "".join(
            f'<a href="https://github.com/{m}" target="_blank" class="member" aria-label="{m}">'
            f'<img src="https://github.com/{m}.png?size=56" alt="{m}" class="avatar" width="28" height="28">'
            f'<span>{m}</span>'
            f'</a>'
            for m in team["members"]
        )

        rows += f"""
            <tr class="{row_cls}">
              <td class="col-rank">
                <div class="rank-cell">
                  <span class="rank-badge {rank_cls}">{rank_num}</span>
                  {trend_html}
                </div>
              </td>
              <td class="col-team"><div class="team-members">{members_html}</div></td>
              <td class="col-pts">
                <span class="pts-value">{s["creation"]:.2f}</span>
                <span class="pts-sub">{s["issues_created"]} issues</span>
              </td>
              <td class="col-pts">
                <span class="pts-value">{s["implementation"]:.2f}</span>
                <span class="pts-sub">{s["issues_implemented"]} issues</span>
              </td>
              <td class="col-total">{total:.2f}</td>
            </tr>"""

    total_done = len(all_issues)
    total_sp   = sum(i["story_points"] for i in all_issues)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FLL Scoreboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    /* Dark theme (default) */
    :root, [data-theme="dark"] {{
      --bg:            #0D1117;
      --surface:       #161B22;
      --surface-hover: #1C2128;
      --border:        #30363D;
      --border-subtle: #21262D;
      --text-primary:  #E6EDF3;
      --text-secondary:#8B949E;
      --text-muted:    #6E7681;
      --accent:        #2F81F7;
      --green:         #3FB950;
      --red:           #F85149;
      --gold:          #D4A017;
      --silver:        #A0AEC0;
      --bronze:        #B87333;
    }}

    /* Light theme */
    [data-theme="light"] {{
      --bg:            #FFFFFF;
      --surface:       #F6F8FA;
      --surface-hover: #EFF2F5;
      --border:        #D0D7DE;
      --border-subtle: #EAEEF2;
      --text-primary:  #1F2328;
      --text-secondary:#656D76;
      --text-muted:    #9198A1;
      --accent:        #0969DA;
      --green:         #1A7F37;
      --red:           #CF222E;
      --gold:          #9A6700;
      --silver:        #57606A;
      --bronze:        #6E3B1A;
    }}

    body {{
      font-family: 'Barlow', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text-primary);
      min-height: 100vh;
      font-size: 16px;
      line-height: 1.5;
      transition: background 200ms ease, color 200ms ease;
    }}

    /* Header */
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 16px 32px;
    }}
    .header-inner {{
      max-width: 900px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    .header-left {{
      display: flex;
      align-items: baseline;
      gap: 14px;
    }}
    header h1 {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1.2rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--text-primary);
    }}
    header .org {{
      font-size: 0.78rem;
      color: var(--text-muted);
    }}

    /* Theme toggle */
    .theme-btn {{
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text-secondary);
      font-family: 'Barlow', sans-serif;
      font-size: 0.78rem;
      font-weight: 500;
      cursor: pointer;
      transition: border-color 150ms ease, color 150ms ease, background 150ms ease;
      white-space: nowrap;
    }}
    .theme-btn:hover {{
      border-color: var(--accent);
      color: var(--accent);
      background: var(--surface-hover);
    }}
    .theme-btn svg {{
      width: 14px;
      height: 14px;
      flex-shrink: 0;
    }}
    .icon-sun  {{ display: none; }}
    .icon-moon {{ display: block; }}
    [data-theme="light"] .icon-sun  {{ display: block; }}
    [data-theme="light"] .icon-moon {{ display: none; }}

    /* Layout */
    .container {{
      max-width: 900px;
      margin: 28px auto;
      padding: 0 20px;
    }}

    /* Stats */
    .stats {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 20px;
    }}
    .stat {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 16px 20px;
    }}
    .stat .value {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 2rem;
      font-weight: 700;
      color: var(--text-primary);
      font-variant-numeric: tabular-nums;
      line-height: 1;
    }}
    .stat .label {{
      font-size: 0.68rem;
      color: var(--text-muted);
      margin-top: 6px;
      text-transform: uppercase;
      letter-spacing: 0.09em;
    }}

    /* Table */
    .table-wrap {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 540px;
    }}
    thead tr {{
      background: var(--surface-hover);
      border-bottom: 1px solid var(--border);
    }}
    th {{
      padding: 10px 16px;
      text-align: left;
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 0.68rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-muted);
      white-space: nowrap;
    }}
    th.align-right {{ text-align: right; }}
    td {{
      padding: 13px 16px;
      border-bottom: 1px solid var(--border-subtle);
      font-size: 0.88rem;
      vertical-align: middle;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tbody tr {{ transition: background 150ms ease; }}
    tbody tr:hover td {{ background: var(--surface-hover); }}

    /* Top 3 left accent */
    .row-top-1 td:first-child {{ box-shadow: inset 3px 0 0 var(--gold); }}
    .row-top-2 td:first-child {{ box-shadow: inset 3px 0 0 var(--silver); }}
    .row-top-3 td:first-child {{ box-shadow: inset 3px 0 0 var(--bronze); }}

    /* Rank cell */
    .col-rank {{ width: 68px; }}
    .rank-cell {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
    }}
    .rank-badge {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--text-muted);
      min-width: 20px;
      text-align: right;
    }}
    .rank-badge.rank-1 {{ color: var(--gold); }}
    .rank-badge.rank-2 {{ color: var(--silver); }}
    .rank-badge.rank-3 {{ color: var(--bronze); }}

    /* Trend indicators */
    .trend {{
      font-size: 0.55rem;
      font-weight: 700;
      line-height: 1;
      width: 12px;
      text-align: center;
    }}
    .trend-up   {{ color: var(--green); }}
    .trend-down {{ color: var(--red); }}
    .trend-same {{ color: var(--text-muted); font-size: 0.7rem; }}
    .trend-new  {{ color: var(--accent); font-size: 0.5rem; }}

    /* Team */
    .col-team {{ font-weight: 500; }}
    .team-members {{
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .member {{
      display: flex;
      align-items: center;
      gap: 8px;
      text-decoration: none;
      color: var(--text-primary);
      font-size: 0.88rem;
      transition: color 150ms ease;
      cursor: pointer;
    }}
    .member:hover {{ color: var(--accent); }}
    .member:hover .avatar {{ border-color: var(--accent); }}
    .avatar {{
      width: 28px;
      height: 28px;
      border-radius: 50%;
      border: 1.5px solid var(--border);
      flex-shrink: 0;
      display: block;
    }}

    /* Points */
    .col-pts {{ text-align: right; }}
    .pts-value {{
      display: block;
      font-variant-numeric: tabular-nums;
      font-weight: 500;
      color: var(--text-secondary);
    }}
    .pts-sub {{
      display: block;
      font-size: 0.68rem;
      color: var(--text-muted);
      margin-top: 2px;
    }}

    /* Total */
    .col-total {{
      text-align: right;
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--green);
      font-variant-numeric: tabular-nums;
    }}

    /* Rules */
    .rules {{
      margin-top: 20px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 16px 20px;
      font-size: 0.8rem;
      color: var(--text-secondary);
      line-height: 1.6;
    }}
    .rules h2 {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 0.68rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-muted);
      margin-bottom: 10px;
    }}
    .rules ul {{ list-style: none; }}
    .rules li {{
      padding: 3px 0 3px 12px;
      position: relative;
    }}
    .rules li::before {{
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      width: 3px;
      height: 3px;
      border-radius: 50%;
      background: var(--border);
    }}

    .updated {{
      text-align: center;
      color: var(--text-muted);
      font-size: 0.7rem;
      margin-top: 12px;
    }}

    @media (max-width: 600px) {{
      .stats {{ grid-template-columns: 1fr 1fr; }}
      header {{ padding: 12px 16px; }}
      .header-left {{ flex-direction: column; gap: 2px; }}
      .container {{ padding: 0 12px; margin: 20px auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div class="header-left">
        <h1>FLL Scoreboard</h1>
        <span class="org">UdL EPS SoftArch Igualada</span>
      </div>
      <button class="theme-btn" onclick="toggleTheme()" aria-label="Toggle theme">
        <!-- Sun icon (shown in light mode) -->
        <svg class="icon-sun" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
        </svg>
        <!-- Moon icon (shown in dark mode) -->
        <svg class="icon-moon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
        <span class="btn-label">Light</span>
      </button>
    </div>
  </header>
  <div class="container">
    <div class="stats">
      <div class="stat">
        <div class="value">{len(teams)}</div>
        <div class="label">Teams</div>
      </div>
      <div class="stat">
        <div class="value">{total_done}</div>
        <div class="label">Done Issues</div>
      </div>
      <div class="stat">
        <div class="value">{total_sp:.1f}</div>
        <div class="label">Story Points</div>
      </div>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="col-rank">Pos</th>
            <th>Team</th>
            <th class="align-right">Creation Pts</th>
            <th class="align-right">Implementation Pts</th>
            <th class="align-right">Total</th>
          </tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>
    </div>

    <div class="rules">
      <h2>Scoring Rules</h2>
      <ul>
        <li>Creating an issue (that ends up Done): <strong>+0.25 pts</strong> to the creator's team</li>
        <li>Implementing another team's issue: <strong>+full SP</strong> to the implementer's team</li>
        <li>Implementing your own issue: <strong>+SP/2</strong> to your team (half story points)</li>
        <li>Only issues with status <strong>Done</strong> count (closed by merged PR)</li>
      </ul>
    </div>

    <p class="updated">Last updated: {generated_at}</p>
  </div>
  <script>
    (function () {{
      var saved = localStorage.getItem('fll-theme');
      if (saved) document.documentElement.setAttribute('data-theme', saved);
      var btn = document.querySelector('.btn-label');
      function updateLabel() {{
        var t = document.documentElement.getAttribute('data-theme');
        btn.textContent = t === 'dark' ? 'Light' : 'Dark';
      }}
      updateLabel();
      window.toggleTheme = function () {{
        var cur = document.documentElement.getAttribute('data-theme');
        var next = cur === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('fll-theme', next);
        updateLabel();
      }};
    }})();
  </script>
</body>
</html>"""

# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        print("ERROR: GH_TOKEN environment variable not set", file=sys.stderr)
        sys.exit(1)

    print("Fetching teams...")
    teams, user_to_team = fetch_teams()
    print(f"  {len(teams)} teams loaded")

    print("Fetching Done issues from project...")
    all_issues = fetch_done_issues()
    print(f"  {len(all_issues)} Done issues found")

    scores = calculate_scores(teams, user_to_team, all_issues)

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    os.makedirs(out_dir, exist_ok=True)

    ranked = rank_teams(teams, scores)
    prev_positions = load_previous_positions(out_dir)
    current_positions = {teams[team_id]["name"]: pos + 1 for pos, team_id in enumerate(ranked)}
    save_positions(current_positions, out_dir)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = generate_html(teams, scores, all_issues, generated_at, ranked, prev_positions)

    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Written to {out_path}")

if __name__ == "__main__":
    main()
