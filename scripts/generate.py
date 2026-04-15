#!/usr/bin/env python3
"""
FLL Scoreboard Generator
Fetches issues from GitHub Projects, calculates team scores, generates HTML.

Scoring rules:
  - Each Done issue: creator's team gets +0.25 pts
  - Each Done issue: implementer's team gets +SP (full story points)
      EXCEPT if implementer == creator team: only +SP/2
"""

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

# ── HTML ────────────────────────────────────────────────────────────────────────

def generate_html(teams, scores, all_issues, generated_at):
    ranked = sorted(
        range(len(teams)),
        key=lambda i: scores[i]["creation"] + scores[i]["implementation"],
        reverse=True,
    )

    rows = ""
    for pos, team_id in enumerate(ranked):
        team      = teams[team_id]
        s         = scores[team_id]
        total     = s["creation"] + s["implementation"]
        rank_num  = pos + 1
        rank_cls  = f"rank-{rank_num}" if rank_num <= 3 else ""
        row_cls   = f"row-top-{rank_num}" if rank_num <= 3 else ""

        members_html = "".join(
            f'<a href="https://github.com/{m}" target="_blank" class="member" aria-label="{m}">'
            f'<img src="https://github.com/{m}.png?size=56" alt="{m}" class="avatar" width="28" height="28">'
            f'<span>{m}</span>'
            f'</a>'
            for m in team["members"]
        )

        rows += f"""
            <tr class="{row_cls}">
              <td class="col-rank"><span class="rank-badge {rank_cls}">{rank_num}</span></td>
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
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FLL Scoreboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
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
      --gold:          #D4A017;
      --silver:        #A0AEC0;
      --bronze:        #B87333;
    }}

    body {{
      font-family: 'Barlow', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text-primary);
      min-height: 100vh;
      font-size: 16px;
      line-height: 1.5;
    }}

    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 20px 32px;
    }}
    .header-inner {{
      max-width: 900px;
      margin: 0 auto;
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

    .container {{
      max-width: 900px;
      margin: 32px auto;
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

    /* Rank */
    .col-rank {{ width: 56px; text-align: center; }}
    .rank-badge {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1.05rem;
      font-weight: 700;
      color: var(--text-muted);
    }}
    .rank-badge.rank-1 {{ color: var(--gold); }}
    .rank-badge.rank-2 {{ color: var(--silver); }}
    .rank-badge.rank-3 {{ color: var(--bronze); }}

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
      header {{ padding: 16px; }}
      .header-inner {{ flex-direction: column; gap: 4px; }}
      .container {{ padding: 0 12px; margin: 20px auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <h1>FLL Scoreboard</h1>
      <span class="org">UdL EPS SoftArch Igualada</span>
    </div>
  </header>
  <div class="container">
    <div class="stats">
      <div class="stat">
        <div class="value">{len(teams)}</div>
        <div class="label">Equipos</div>
      </div>
      <div class="stat">
        <div class="value">{total_done}</div>
        <div class="label">Issues en Done</div>
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
            <th>Equipo</th>
            <th class="align-right">Pts Creacion</th>
            <th class="align-right">Pts Implementacion</th>
            <th class="align-right">Total</th>
          </tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>
    </div>

    <div class="rules">
      <h2>Reglas de puntuacion</h2>
      <ul>
        <li>Crear una issue (que acabe en Done): <strong>+0.25 pts</strong> al equipo creador</li>
        <li>Implementar una issue de otro equipo: <strong>+SP completos</strong> al equipo implementador</li>
        <li>Implementar una issue propia: <strong>+SP/2</strong> al equipo (mitad de los story points)</li>
        <li>Solo cuentan las issues en estado <strong>Done</strong> (cerradas por PR mergeado)</li>
      </ul>
    </div>

    <p class="updated">Ultima actualizacion: {generated_at}</p>
  </div>
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

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = generate_html(teams, scores, all_issues, generated_at)

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Written to {out_path}")

if __name__ == "__main__":
    main()
