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
REPOS = ["first-lego-league-backend", "first-lego-league-frontend"]
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
    url = f"https://raw.githubusercontent.com/{ORG}/{REPOS[0]}/main/{TEAMS_FILE_PATH}"
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

# ── Issues ──────────────────────────────────────────────────────────────────────

ISSUES_QUERY = """
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    issues(states: CLOSED, first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        author { login }
        assignees(first: 10) { nodes { login } }
        labels(first: 15) { nodes { name } }
        timelineItems(last: 1, itemTypes: CLOSED_EVENT) {
          nodes {
            ... on ClosedEvent {
              closer {
                __typename
                ... on PullRequest { merged }
              }
            }
          }
        }
      }
    }
  }
}
"""

def fetch_done_issues(repo):
    """Return all issues in 'Done' (closed by a merged PR) that have story points."""
    done = []
    cursor = None

    while True:
        data = graphql(ISSUES_QUERY, {"owner": ORG, "repo": repo, "cursor": cursor})
        issues_data = data.get("repository", {}).get("issues", {})
        nodes = issues_data.get("nodes", [])
        page_info = issues_data.get("pageInfo", {})

        for issue in nodes:
            # Extract story points from labels
            labels = [l["name"] for l in issue.get("labels", {}).get("nodes", [])]
            sp = next((STORY_POINTS_MAP[lb] for lb in labels if lb in STORY_POINTS_MAP), None)
            if sp is None:
                continue  # No valid story-points label → skip

            creator = (issue.get("author") or {}).get("login")
            assignees = [a["login"] for a in issue.get("assignees", {}).get("nodes", [])]

            done.append({
                "number":       issue["number"],
                "title":        issue["title"],
                "repo":         repo,
                "creator":      creator,
                "assignees":    assignees,
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

    medal = {0: "🥇", 1: "🥈", 2: "🥉"}

    rows = ""
    for pos, team_id in enumerate(ranked):
        team  = teams[team_id]
        s     = scores[team_id]
        total = s["creation"] + s["implementation"]
        rank_display = medal.get(pos, f"#{pos + 1}")
        rows += f"""
            <tr>
              <td class="rank">{rank_display}</td>
              <td class="team">{team["name"]}</td>
              <td class="pts">{s["creation"]:.2f}<span class="sub">({s["issues_created"]} issues)</span></td>
              <td class="pts">{s["implementation"]:.2f}<span class="sub">({s["issues_implemented"]} issues)</span></td>
              <td class="total">{total:.2f}</td>
            </tr>"""

    total_done = len(all_issues)
    total_sp   = sum(i["story_points"] for i in all_issues)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FLL Scoreboard</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #0d1117; color: #e6edf3; min-height: 100vh;
    }}
    header {{
      background: #161b22; border-bottom: 1px solid #30363d;
      padding: 24px 32px; display: flex; align-items: center; gap: 16px;
    }}
    header h1 {{ font-size: 1.4rem; font-weight: 700; color: #58a6ff; }}
    header p  {{ color: #8b949e; font-size: 0.8rem; margin-top: 2px; }}
    .container {{ max-width: 860px; margin: 32px auto; padding: 0 20px; }}
    .stats {{
      display: grid; grid-template-columns: repeat(3, 1fr);
      gap: 12px; margin-bottom: 24px;
    }}
    .stat {{
      background: #161b22; border: 1px solid #30363d;
      border-radius: 8px; padding: 16px 20px;
    }}
    .stat .value {{ font-size: 1.6rem; font-weight: 700; color: #58a6ff; }}
    .stat .label {{ font-size: 0.7rem; color: #8b949e; margin-top: 2px;
                    text-transform: uppercase; letter-spacing: .06em; }}
    table {{
      width: 100%; border-collapse: collapse;
      background: #161b22; border: 1px solid #30363d; border-radius: 8px;
      overflow: hidden;
    }}
    th {{
      padding: 10px 14px; text-align: left; font-size: 0.7rem;
      text-transform: uppercase; letter-spacing: .06em;
      color: #8b949e; background: #21262d; border-bottom: 1px solid #30363d;
    }}
    td {{ padding: 13px 14px; border-bottom: 1px solid #21262d; font-size: 0.88rem; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #1c2128; }}
    td.rank  {{ font-size: 1.1rem; width: 60px; text-align: center; }}
    td.team  {{ font-weight: 600; }}
    td.pts   {{ color: #8b949e; font-variant-numeric: tabular-nums; }}
    td.total {{ font-weight: 700; color: #3fb950;
                font-variant-numeric: tabular-nums; font-size: 1rem; }}
    .sub {{ display: block; font-size: 0.7rem; color: #6e7681; margin-top: 2px; }}
    .rules {{
      margin-top: 24px; background: #161b22; border: 1px solid #30363d;
      border-radius: 8px; padding: 16px 20px; font-size: 0.8rem; color: #8b949e;
    }}
    .rules h2 {{ color: #e6edf3; font-size: 0.85rem; margin-bottom: 8px; }}
    .rules li {{ margin-left: 16px; margin-top: 4px; line-height: 1.5; }}
    .updated {{ text-align: center; color: #6e7681; font-size: 0.72rem; margin-top: 12px; }}
    @media (max-width: 600px) {{
      .stats {{ grid-template-columns: 1fr 1fr; }}
      header {{ padding: 16px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>First Lego League — Scoreboard</h1>
      <p>UdL EPS SoftArch Igualada</p>
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
        <div class="label">Story Points totales</div>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Pos</th>
          <th>Equipo</th>
          <th>Pts Creación</th>
          <th>Pts Implementación</th>
          <th>Total</th>
        </tr>
      </thead>
      <tbody>{rows}
      </tbody>
    </table>

    <div class="rules">
      <h2>Reglas de puntuación</h2>
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

    all_issues = []
    for repo in REPOS:
        print(f"Fetching Done issues from {repo}...")
        issues = fetch_done_issues(repo)
        print(f"  {len(issues)} Done issues found")
        all_issues.extend(issues)

    print(f"Total Done issues: {len(all_issues)}")

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
