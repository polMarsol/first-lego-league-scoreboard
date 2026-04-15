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

COIN_LABEL = "\U0001fa99"  # 🪙 — professor's budget label

CHART_COLORS = [
    "#2F81F7", "#3FB950", "#D4A017", "#F78166",
    "#A371F7", "#FFA657", "#79C0FF", "#FF7B72",
    "#56D364", "#E5C07B", "#58A6FF", "#F0883E",
]

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
              closedAt
            }
          }
        }
      }
    }
  }
}
"""

def fetch_project_issues():
    """Fetch all project items in a single pass.

    Returns:
        done_issues  — Status='Done' + has SP label  (used for scoring)
        coin_issues  — has 🪙 label + has SP label, any status  (used for balance)
    """
    done = []
    coin = []
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
            content = item.get("content") or {}
            if not content.get("number"):
                continue  # Skip non-issue items (e.g. draft notes)

            labels = [l["name"] for l in content.get("labels", {}).get("nodes", [])]
            sp = next((STORY_POINTS_MAP[lb] for lb in labels if lb in STORY_POINTS_MAP), None)
            if sp is None:
                continue  # No SP label → irrelevant for both scoring and balance

            issue = {
                "number":       content["number"],
                "title":        content["title"],
                "repo":         (content.get("repository") or {}).get("name", ""),
                "creator":      (content.get("author") or {}).get("login"),
                "assignees":    [a["login"] for a in content.get("assignees", {}).get("nodes", [])],
                "story_points": sp,
                "closed_at":    content.get("closedAt", "") or "",
            }

            status = (item.get("status") or {}).get("name", "")
            if "done" in status.lower():
                done.append(issue)

            if COIN_LABEL in labels:
                coin.append(issue)

        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]

    return done, coin

# ── Scoring ─────────────────────────────────────────────────────────────────────

def calculate_scores(teams, user_to_team, all_issues, coin_issues):
    scores = {i: {"creation": 0.0, "implementation": 0.0, "issues_created": 0, "issues_implemented": 0,
                  "balance": 0.0, "coin_issues": 0}
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

    # Balance: SP still available in 🪙-labeled issues created by each team
    for issue in coin_issues:
        creator = issue["creator"]
        creator_team_id = user_to_team.get(creator.lower()) if creator else None
        if creator_team_id is not None:
            scores[creator_team_id]["balance"] += issue["story_points"]
            scores[creator_team_id]["coin_issues"] += 1

    return scores

# ── Issues Detail ───────────────────────────────────────────────────────────────

def build_issues_detail(teams, user_to_team, all_issues):
    """Build rich per-issue data used by both the score chart and team detail panel."""
    details = []
    for issue in all_issues:
        creator     = issue["creator"]
        creator_tid = user_to_team.get(creator.lower()) if creator else None
        impl_tid    = None
        implementer = None
        for a in issue["assignees"]:
            t = user_to_team.get(a.lower())
            if t is not None:
                impl_tid    = t
                implementer = a
                break
        if impl_tid is None:
            continue
        sp    = issue["story_points"]
        score = sp / 2 if impl_tid == creator_tid else sp
        date  = issue.get("closed_at", "")[:10]
        details.append({
            "number":       issue["number"],
            "title":        issue["title"],
            "repo":         issue.get("repo", ""),
            "sp":           sp,
            "score":        score,
            "own":          impl_tid == creator_tid,
            "creator":      creator or "",
            "creator_team": teams[creator_tid]["name"] if creator_tid is not None else "",
            "implementer":  implementer or "",
            "impl_team":    teams[impl_tid]["name"],
            "date":         date,
        })
    return details

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

def generate_html(teams, scores, all_issues, coin_issues, generated_at, ranked, prev_positions, issues_detail):
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

        balance     = s["balance"]
        balance_cls = "balance-ok" if balance >= 0 else "balance-debt"
        balance_str = f"+{balance:.2f}" if balance >= 0 else f"{balance:.2f}"

        team_name_js = team["name"].replace("'", "\\'")
        rows += f"""
            <tr class="{row_cls}" onclick="openTeamDetail('{team_name_js}')" style="cursor:pointer">
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
              <td class="col-balance">
                <span class="balance-value {balance_cls}">{balance_str}</span>
                <span class="pts-sub">{s["coin_issues"]} open</span>
              </td>
            </tr>"""

    total_done    = len(all_issues)
    total_sp      = sum(i["story_points"] for i in all_issues)
    teams_in_debt = sum(1 for i in range(len(teams)) if scores[i]["balance"] < 0)

    team_names_json   = json.dumps([t["name"] for t in teams])
    team_members_json = json.dumps({t["name"]: t["members"] for t in teams})
    team_colors_json  = json.dumps(CHART_COLORS[:len(teams)])
    issues_detail_json = json.dumps(issues_detail)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FLL Scoreboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
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
      grid-template-columns: repeat(5, 1fr);
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

    /* Balance */
    .col-balance {{ text-align: right; }}
    .balance-value {{
      display: block;
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1rem;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }}
    .balance-ok   {{ color: var(--green); }}
    .balance-debt {{ color: var(--red); }}

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

    /* Chart button */
    .chart-btn {{
      display: flex; align-items: center; gap: 6px;
      padding: 6px 12px;
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text-secondary);
      font-family: 'Barlow', sans-serif;
      font-size: 0.78rem; font-weight: 500;
      cursor: pointer;
      transition: border-color 150ms ease, color 150ms ease, background 150ms ease;
      white-space: nowrap;
    }}
    .chart-btn:hover {{ border-color: var(--accent); color: var(--accent); background: var(--surface-hover); }}
    .chart-btn svg {{ width: 14px; height: 14px; flex-shrink: 0; }}

    /* Modal overlay */
    .modal-overlay {{
      position: fixed; inset: 0;
      background: rgba(0,0,0,0.65);
      z-index: 200;
      display: none;
      align-items: center; justify-content: center;
      padding: 20px;
    }}
    .modal-overlay.open {{ display: flex; }}
    .modal-box {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      width: 100%; max-width: 880px;
      max-height: 90vh;
      display: flex; flex-direction: column;
      overflow: hidden;
    }}
    .modal-header {{
      display: flex; align-items: center; justify-content: space-between;
      padding: 14px 20px;
      border-bottom: 1px solid var(--border);
    }}
    .modal-title {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1rem; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--text-primary);
    }}
    .modal-close {{
      background: transparent; border: none;
      color: var(--text-muted); cursor: pointer;
      font-size: 1.2rem; line-height: 1;
      padding: 4px 8px; border-radius: 4px;
      transition: color 150ms ease, background 150ms ease;
    }}
    .modal-close:hover {{ color: var(--text-primary); background: var(--surface-hover); }}
    .modal-controls {{
      display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
      padding: 12px 20px;
      border-bottom: 1px solid var(--border-subtle);
    }}
    .ctrl-label {{
      font-size: 0.68rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--text-muted);
    }}
    .ctrl-group {{ display: flex; gap: 4px; }}
    .ctrl-btn {{
      padding: 4px 12px;
      border: 1px solid var(--border);
      border-radius: 4px;
      background: transparent;
      color: var(--text-secondary);
      font-family: 'Barlow', sans-serif;
      font-size: 0.78rem; cursor: pointer;
      transition: all 150ms ease;
    }}
    .ctrl-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
    .ctrl-btn.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
    .team-toggles {{
      display: flex; gap: 8px; flex-wrap: wrap;
      padding: 10px 20px;
      border-bottom: 1px solid var(--border-subtle);
    }}
    .team-pill {{
      padding: 3px 12px;
      border-radius: 20px;
      border: 2px solid transparent;
      font-family: 'Barlow', sans-serif;
      font-size: 0.75rem; font-weight: 600;
      cursor: pointer;
      transition: opacity 150ms ease, filter 150ms ease;
    }}
    .team-pill.off {{ opacity: 0.3; filter: grayscale(0.6); }}
    .chart-area {{
      padding: 16px 20px;
      flex: 1;
      overflow-y: auto;
      min-height: 280px;
      position: relative;
    }}

    /* Team detail modal */
    .member-breakdown {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      padding: 14px 20px;
      border-bottom: 1px solid var(--border-subtle);
    }}
    .member-card {{
      background: var(--surface-hover);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 12px 14px;
    }}
    .member-card-header {{
      display: flex; align-items: center; gap: 8px;
      margin-bottom: 10px;
    }}
    .member-card-header .avatar {{ width: 32px; height: 32px; }}
    .member-card-header a {{
      text-decoration: none; color: var(--text-primary);
      font-weight: 600; font-size: 0.88rem;
      transition: color 150ms ease;
    }}
    .member-card-header a:hover {{ color: var(--accent); }}
    .member-stat {{
      font-size: 0.78rem; color: var(--text-secondary);
      display: flex; justify-content: space-between;
      padding: 2px 0;
    }}
    .member-stat strong {{ color: var(--text-primary); font-variant-numeric: tabular-nums; }}
    .detail-tabs {{
      display: flex; gap: 0;
      border-bottom: 1px solid var(--border);
      padding: 0 20px;
    }}
    .tab-btn {{
      padding: 10px 16px;
      background: transparent; border: none;
      border-bottom: 2px solid transparent;
      color: var(--text-muted);
      font-family: 'Barlow', sans-serif;
      font-size: 0.82rem; font-weight: 600;
      cursor: pointer;
      transition: color 150ms ease, border-color 150ms ease;
      margin-bottom: -1px;
    }}
    .tab-btn:hover {{ color: var(--text-primary); }}
    .tab-btn.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
    .detail-table-area {{
      flex: 1; overflow-y: auto;
      padding: 0 20px 16px;
    }}
    .detail-table {{
      width: 100%; border-collapse: collapse;
      font-size: 0.82rem; margin-top: 12px;
    }}
    .detail-table th {{
      text-align: left; padding: 6px 10px;
      font-size: 0.65rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border-subtle);
    }}
    .detail-table th.tr {{ text-align: right; }}
    .detail-table td {{
      padding: 9px 10px;
      border-bottom: 1px solid var(--border-subtle);
      vertical-align: middle;
      color: var(--text-secondary);
    }}
    .detail-table tr:last-child td {{ border-bottom: none; }}
    .detail-table a {{ color: var(--text-primary); text-decoration: none; }}
    .detail-table a:hover {{ color: var(--accent); text-decoration: underline; }}
    .detail-table .tr {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .badge-own {{
      display: inline-block; padding: 1px 7px;
      border-radius: 10px; font-size: 0.65rem; font-weight: 600;
      background: color-mix(in srgb, var(--text-muted) 15%, transparent);
      color: var(--text-muted);
    }}
    .badge-cross {{
      display: inline-block; padding: 1px 7px;
      border-radius: 10px; font-size: 0.65rem; font-weight: 600;
      background: color-mix(in srgb, var(--green) 15%, transparent);
      color: var(--green);
    }}
    .implementer-pill {{
      display: inline-flex; align-items: center; gap: 5px;
      font-size: 0.78rem; color: var(--text-secondary);
    }}
    .implementer-pill img {{
      width: 20px; height: 20px; border-radius: 50%;
      border: 1px solid var(--border);
    }}
    .no-issues {{
      text-align: center; padding: 32px 0;
      color: var(--text-muted); font-size: 0.82rem;
    }}

    @media (max-width: 900px) {{
      .stats {{ grid-template-columns: repeat(3, 1fr); }}
    }}
    @media (max-width: 600px) {{
      .stats {{ grid-template-columns: 1fr 1fr; }}
      header {{ padding: 12px 16px; }}
      .header-left {{ flex-direction: column; gap: 2px; }}
      .container {{ padding: 0 12px; margin: 20px auto; }}
      .modal-controls {{ gap: 10px; }}
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
      <button class="chart-btn" onclick="openChart()" aria-label="Score evolution chart">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
        </svg>
        Chart
      </button>
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
      <div class="stat">
        <div class="value">{sum(scores[i]["balance"] for i in range(len(teams))):.1f}</div>
        <div class="label">Budget Available (SP)</div>
      </div>
      <div class="stat">
        <div class="value" style="color: {'var(--red)' if teams_in_debt > 0 else 'var(--green)'}">{teams_in_debt}</div>
        <div class="label">Teams in Debt</div>
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
            <th class="align-right">Budget</th>
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
        <li><strong>Budget</strong>: SP available in open issues tagged with the budget label — must be &gt;= SP of the PR you want to close</li>
      </ul>
    </div>

    <p class="updated">Last updated: {generated_at}</p>
  </div>
  <!-- Team detail modal -->
  <div id="team-modal" class="modal-overlay" onclick="handleTeamOverlayClick(event)">
    <div class="modal-box" style="max-width:800px">
      <div class="modal-header">
        <div id="team-modal-title" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap"></div>
        <button class="modal-close" onclick="closeTeamModal()" aria-label="Close">&times;</button>
      </div>
      <div id="member-breakdown" class="member-breakdown"></div>
      <div class="detail-tabs">
        <button class="tab-btn active" onclick="switchTab(this,'implemented')">Implemented</button>
        <button class="tab-btn" onclick="switchTab(this,'created')">Created</button>
      </div>
      <div class="detail-table-area">
        <div id="detail-content"></div>
      </div>
    </div>
  </div>

  <!-- Chart modal -->
  <div id="chart-modal" class="modal-overlay" onclick="handleOverlayClick(event)">
    <div class="modal-box">
      <div class="modal-header">
        <span class="modal-title">Score Evolution</span>
        <button class="modal-close" onclick="closeChart()" aria-label="Close">&times;</button>
      </div>
      <div class="modal-controls">
        <span class="ctrl-label">Metric</span>
        <div class="ctrl-group" id="metric-group">
          <button class="ctrl-btn active" data-metric="score" onclick="setMetric(this)">Total Score</button>
          <button class="ctrl-btn" data-metric="sp" onclick="setMetric(this)">Story Points</button>
        </div>
        <span class="ctrl-label" style="margin-left:8px">Period</span>
        <div class="ctrl-group" id="gran-group">
          <button class="ctrl-btn" data-gran="day" onclick="setGran(this)">Day</button>
          <button class="ctrl-btn active" data-gran="week" onclick="setGran(this)">Week</button>
          <button class="ctrl-btn" data-gran="month" onclick="setGran(this)">Month</button>
        </div>
      </div>
      <div class="team-toggles" id="team-toggles"></div>
      <div class="chart-area">
        <canvas id="scoreChart"></canvas>
      </div>
    </div>
  </div>

  <script>
    // ── Data injected by Python ───────────────────────────────────────────────
    const ISSUES  = {issues_detail_json};
    const TEAMS   = {team_names_json};
    const MEMBERS = {team_members_json};
    const COLORS  = {team_colors_json};
    // Derive flat chart events from rich issue data
    const RAW = ISSUES.map(e => ({{ date: e.date, team: e.impl_team, score: e.score, sp: e.sp }}));

    // ── State ─────────────────────────────────────────────────────────────────
    let chart       = null;
    let activeMetric = 'score';
    let activeGran   = 'week';
    const activeTeams = new Set(TEAMS);

    // ── Helpers ───────────────────────────────────────────────────────────────
    function periodKey(dateStr, gran) {{
      const d = new Date(dateStr + 'T12:00:00Z');
      if (gran === 'day')   return dateStr;
      if (gran === 'month') return dateStr.slice(0, 7);
      // week: Monday of that week
      const day  = d.getUTCDay() || 7;
      const mon  = new Date(d);
      mon.setUTCDate(d.getUTCDate() - day + 1);
      return mon.toISOString().slice(0, 10);
    }}

    function fmtLabel(key, gran) {{
      if (gran === 'month') {{
        const [y, m] = key.split('-');
        return new Date(y, m - 1, 1).toLocaleString('en', {{ month: 'short', year: '2-digit' }});
      }}
      if (gran === 'week') {{
        const d   = new Date(key + 'T12:00:00Z');
        const jan4 = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
        const wk1Mon = new Date(jan4);
        wk1Mon.setUTCDate(jan4.getUTCDate() - ((jan4.getUTCDay() || 7) - 1));
        const wn = Math.round((d - wk1Mon) / 604800000) + 1;
        return 'W' + wn + " '" + String(d.getUTCFullYear()).slice(2);
      }}
      return key.slice(5); // MM-DD
    }}

    function themeColors() {{
      const dark = document.documentElement.getAttribute('data-theme') !== 'light';
      return {{
        grid:    dark ? '#30363D' : '#E1E4E8',
        tick:    dark ? '#6E7681' : '#9198A1',
        tooltip: dark ? '#161B22' : '#FFFFFF',
        border:  dark ? '#30363D' : '#D0D7DE',
      }};
    }}

    // ── Build & render ────────────────────────────────────────────────────────
    function buildChart() {{
      const keySet = new Set(RAW.map(e => periodKey(e.date, activeGran)));
      const keys   = Array.from(keySet).sort();
      const labels = keys.map(k => fmtLabel(k, activeGran));

      const datasets = TEAMS.map((team, idx) => {{
        if (!activeTeams.has(team)) return null;
        let cum = 0;
        const data = keys.map(k => {{
          RAW.filter(e => e.team === team && periodKey(e.date, activeGran) === k)
             .forEach(e => {{ cum += activeMetric === 'score' ? e.score : e.sp; }});
          return parseFloat(cum.toFixed(2));
        }});
        const color = COLORS[idx % COLORS.length];
        return {{
          label: team, data,
          borderColor: color,
          backgroundColor: color + '18',
          fill: false,
          tension: 0.35,
          pointRadius: 4,
          pointHoverRadius: 6,
          borderWidth: 2.5,
        }};
      }}).filter(Boolean);

      const tc = themeColors();
      const yLabel = activeMetric === 'score' ? 'Cumulative Score' : 'Cumulative Story Points';

      if (chart) chart.destroy();
      chart = new Chart(document.getElementById('scoreChart').getContext('2d'), {{
        type: 'line',
        data: {{ labels, datasets }},
        options: {{
          responsive: true,
          maintainAspectRatio: true,
          interaction: {{ mode: 'index', intersect: false }},
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              backgroundColor: tc.tooltip,
              borderColor: tc.border,
              borderWidth: 1,
              titleColor: tc.tick,
              bodyColor: '#E6EDF3',
              padding: 10,
              callbacks: {{
                title: items => fmtLabel(keys[items[0].dataIndex], activeGran),
              }},
            }},
          }},
          scales: {{
            x: {{
              grid: {{ color: tc.grid }},
              ticks: {{ color: tc.tick, font: {{ family: 'Barlow', size: 11 }} }},
            }},
            y: {{
              beginAtZero: true,
              grid: {{ color: tc.grid }},
              ticks: {{ color: tc.tick, font: {{ family: 'Barlow', size: 11 }} }},
              title: {{ display: true, text: yLabel, color: tc.tick, font: {{ family: 'Barlow', size: 11 }} }},
            }},
          }},
        }},
      }});
    }}

    function buildTeamToggles() {{
      const container = document.getElementById('team-toggles');
      container.innerHTML = '';
      TEAMS.forEach((team, idx) => {{
        const btn = document.createElement('button');
        btn.className = 'team-pill';
        btn.textContent = team;
        btn.style.borderColor = COLORS[idx % COLORS.length];
        btn.style.color = COLORS[idx % COLORS.length];
        btn.dataset.team = team;
        btn.onclick = () => toggleTeam(team, btn);
        container.appendChild(btn);
      }});
    }}

    function toggleTeam(team, btn) {{
      if (activeTeams.has(team)) {{
        activeTeams.delete(team);
        btn.classList.add('off');
      }} else {{
        activeTeams.add(team);
        btn.classList.remove('off');
      }}
      buildChart();
    }}

    function setMetric(btn) {{
      activeMetric = btn.dataset.metric;
      document.querySelectorAll('#metric-group .ctrl-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      buildChart();
    }}

    function setGran(btn) {{
      activeGran = btn.dataset.gran;
      document.querySelectorAll('#gran-group .ctrl-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      buildChart();
    }}

    // ── Team detail modal ─────────────────────────────────────────────────────
    let currentTeam = null;
    let currentTab  = 'implemented';

    function openTeamDetail(teamName) {{
      currentTeam = teamName;
      currentTab  = 'implemented';
      document.querySelectorAll('#team-modal .tab-btn').forEach((b, i) => {{
        b.classList.toggle('active', i === 0);
      }});
      renderTeamModal();
      document.getElementById('team-modal').classList.add('open');
      document.body.style.overflow = 'hidden';
    }}

    function closeTeamModal() {{
      document.getElementById('team-modal').classList.remove('open');
      document.body.style.overflow = '';
    }}

    function handleTeamOverlayClick(e) {{
      if (e.target === document.getElementById('team-modal')) closeTeamModal();
    }}

    function switchTab(btn, tab) {{
      currentTab = tab;
      document.querySelectorAll('#team-modal .tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderDetailTable();
    }}

    function renderTeamModal() {{
      const members = MEMBERS[currentTeam] || [];
      const teamIdx = TEAMS.indexOf(currentTeam);
      const color   = COLORS[teamIdx % COLORS.length];

      // Header: avatars + names
      const titleEl = document.getElementById('team-modal-title');
      titleEl.innerHTML = members.map(m =>
        `<a href="https://github.com/${{m}}" target="_blank" style="display:flex;align-items:center;gap:6px;text-decoration:none;color:inherit">
          <img src="https://github.com/${{m}}.png?size=56" width="28" height="28"
               style="border-radius:50%;border:2px solid ${{color}}">
          <span style="font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:1rem;letter-spacing:.04em">${{m}}</span>
        </a>`
      ).join('<span style="color:var(--text-muted);font-size:0.8rem">&</span>');

      // Per-member breakdown
      const implIssues = ISSUES.filter(e => e.impl_team === currentTeam);
      const creaIssues = ISSUES.filter(e => e.creator_team === currentTeam);
      const breakdown  = document.getElementById('member-breakdown');
      breakdown.innerHTML = members.map(m => {{
        const mImpl  = implIssues.filter(e => e.implementer === m);
        const mCrea  = creaIssues.filter(e => e.creator === m);
        const mScore = mImpl.reduce((s, e) => s + e.score, 0);
        const mSP    = mImpl.reduce((s, e) => s + e.sp, 0);
        return `<div class="member-card">
          <div class="member-card-header">
            <img src="https://github.com/${{m}}.png?size=56" alt="${{m}}" class="avatar"
                 style="border-color:${{color}}">
            <a href="https://github.com/${{m}}" target="_blank">${{m}}</a>
          </div>
          <div class="member-stat">
            <span>Implemented</span>
            <strong>${{mImpl.length}} issues &middot; ${{mScore.toFixed(2)}} pts</strong>
          </div>
          <div class="member-stat">
            <span>SP done</span>
            <strong>${{mSP.toFixed(2)}} SP</strong>
          </div>
          <div class="member-stat">
            <span>Created (done)</span>
            <strong>${{mCrea.length}} issues</strong>
          </div>
        </div>`;
      }}).join('');

      renderDetailTable();
    }}

    function fmtDate(d) {{
      if (!d) return '—';
      const dt = new Date(d + 'T12:00:00Z');
      return dt.toLocaleString('en', {{ month: 'short', day: 'numeric', year: '2-digit' }});
    }}

    function renderDetailTable() {{
      const el = document.getElementById('detail-content');
      if (currentTab === 'implemented') {{
        const rows = ISSUES.filter(e => e.impl_team === currentTeam)
          .sort((a, b) => b.date.localeCompare(a.date));
        if (!rows.length) {{
          el.innerHTML = '<p class="no-issues">No implemented issues yet.</p>';
          return;
        }}
        el.innerHTML = `<table class="detail-table">
          <thead><tr>
            <th>#</th><th>Title</th><th>Repo</th>
            <th class="tr">SP</th><th class="tr">Earned</th>
            <th>By</th><th>Type</th><th>Date</th>
          </tr></thead>
          <tbody>${{rows.map(e => `
            <tr>
              <td style="color:var(--text-muted)">#${{e.number}}</td>
              <td><a href="https://github.com/${{e.repo ? 'UdL-EPS-SoftArch-Igualada/' + e.repo + '/issues/' + e.number : '#'}}" target="_blank">${{e.title}}</a></td>
              <td style="color:var(--text-muted)">${{e.repo || '—'}}</td>
              <td class="tr">${{e.sp.toFixed(2)}}</td>
              <td class="tr" style="color:var(--green);font-weight:700">+${{e.score.toFixed(2)}}</td>
              <td>
                <span class="implementer-pill">
                  <img src="https://github.com/${{e.implementer}}.png?size=40" alt="${{e.implementer}}">
                  ${{e.implementer}}
                </span>
              </td>
              <td>${{e.own
                ? '<span class="badge-own">own</span>'
                : '<span class="badge-cross">cross</span>'}}</td>
              <td style="color:var(--text-muted);white-space:nowrap">${{fmtDate(e.date)}}</td>
            </tr>`).join('')}}
          </tbody>
        </table>`;
      }} else {{
        const rows = ISSUES.filter(e => e.creator_team === currentTeam)
          .sort((a, b) => b.date.localeCompare(a.date));
        if (!rows.length) {{
          el.innerHTML = '<p class="no-issues">No created issues in Done yet.</p>';
          return;
        }}
        el.innerHTML = `<table class="detail-table">
          <thead><tr>
            <th>#</th><th>Title</th><th>Repo</th>
            <th class="tr">SP</th><th>Creator</th>
            <th>Implemented by</th><th>Date</th>
          </tr></thead>
          <tbody>${{rows.map(e => `
            <tr>
              <td style="color:var(--text-muted)">#${{e.number}}</td>
              <td><a href="https://github.com/${{e.repo ? 'UdL-EPS-SoftArch-Igualada/' + e.repo + '/issues/' + e.number : '#'}}" target="_blank">${{e.title}}</a></td>
              <td style="color:var(--text-muted)">${{e.repo || '—'}}</td>
              <td class="tr">${{e.sp.toFixed(2)}}</td>
              <td>
                <span class="implementer-pill">
                  <img src="https://github.com/${{e.creator}}.png?size=40" alt="${{e.creator}}">
                  ${{e.creator}}
                </span>
              </td>
              <td>
                <span class="implementer-pill">
                  <img src="https://github.com/${{e.implementer}}.png?size=40" alt="${{e.implementer}}">
                  ${{e.implementer}}
                  <span style="color:var(--text-muted);font-size:0.72rem">(${{e.impl_team}})</span>
                </span>
              </td>
              <td style="color:var(--text-muted);white-space:nowrap">${{fmtDate(e.date)}}</td>
            </tr>`).join('')}}
          </tbody>
        </table>`;
      }}
    }}

    // ── Modal ─────────────────────────────────────────────────────────────────
    function openChart() {{
      document.getElementById('chart-modal').classList.add('open');
      document.body.style.overflow = 'hidden';
      buildTeamToggles();
      buildChart();
    }}

    function closeChart() {{
      document.getElementById('chart-modal').classList.remove('open');
      document.body.style.overflow = '';
    }}

    function handleOverlayClick(e) {{
      if (e.target === document.getElementById('chart-modal')) closeChart();
    }}

    document.addEventListener('keydown', e => {{
      if (e.key === 'Escape') {{ closeChart(); closeTeamModal(); }}
    }});
  </script>

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

    print("Fetching project issues...")
    all_issues, coin_issues = fetch_project_issues()
    print(f"  {len(all_issues)} Done issues found")
    print(f"  {len(coin_issues)} budget-labeled issues found")

    scores = calculate_scores(teams, user_to_team, all_issues, coin_issues)

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    os.makedirs(out_dir, exist_ok=True)

    ranked = rank_teams(teams, scores)
    prev_positions = load_previous_positions(out_dir)
    current_positions = {teams[team_id]["name"]: pos + 1 for pos, team_id in enumerate(ranked)}
    save_positions(current_positions, out_dir)

    issues_detail = build_issues_detail(teams, user_to_team, all_issues)
    generated_at  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = generate_html(teams, scores, all_issues, coin_issues, generated_at, ranked, prev_positions, issues_detail)

    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Written to {out_path}")

if __name__ == "__main__":
    main()
