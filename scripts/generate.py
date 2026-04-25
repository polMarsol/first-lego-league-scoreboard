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
import math
import os
import re
import sys
import requests
from datetime import datetime, timezone, timedelta

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
SCOREBOARD_OWNER = "polMarsol"                    # owner of the scoreboard repo
SCOREBOARD_REPO  = "first-lego-league-scoreboard"  # repo where bet issues are filed
BRICKS_START = 100.0  # starting Bricks per member

# Lego brick SVG icon (from Downloads/brick.svg — white bg removed, fill→currentColor)
_BRICK_PATH = "M 934.355469 754.019531 C 952.269531 754.019531 969.730469 755.171875 986.484375 757.339844 L 1188.871094 646.980469 C 1191.320312 609.410156 1218.898438 576.738281 1262.25 553.910156 C 1302.898438 532.5 1358.460938 519.25 1419.289062 519.25 C 1480.121094 519.25 1535.679688 532.5 1576.328125 553.910156 C 1620.148438 576.988281 1647.851562 610.109375 1649.769531 648.199219 L 1849.929688 757.339844 C 1866.679688 755.171875 1884.140625 754.019531 1902.050781 754.019531 C 1962.890625 754.019531 2018.449219 767.269531 2059.101562 788.679688 C 2104.539062 812.609375 2132.648438 847.359375 2132.648438 887.230469 C 2132.648438 888.710938 2132.601562 890.191406 2132.53125 891.660156 L 2132.539062 911.441406 L 2368.941406 1040.339844 C 2377.710938 1044.171875 2383.828125 1052.910156 2383.828125 1063.089844 L 2383.828125 1778.519531 L 2383.75 1778.519531 C 2383.738281 1787.28125 2379.070312 1795.75 2370.851562 1800.230469 L 1431.910156 2312.210938 L 1431.730469 2312.332031 L 1431.710938 2312.34375 L 1431.539062 2312.453125 L 1431.359375 2312.570312 L 1431.171875 2312.6875 L 1430.789062 2312.914062 L 1430.410156 2313.136719 L 1430.398438 2313.136719 L 1430.210938 2313.242188 L 1430.191406 2313.253906 L 1430.019531 2313.351562 L 1429.820312 2313.457031 L 1429.621094 2313.558594 L 1429.601562 2313.574219 L 1429.429688 2313.660156 L 1429.230469 2313.761719 L 1429.03125 2313.859375 L 1428.828125 2313.953125 L 1428.628906 2314.050781 L 1428.570312 2314.074219 L 1428.269531 2314.210938 L 1428.21875 2314.234375 L 1428.011719 2314.324219 L 1427.808594 2314.410156 L 1427.601562 2314.496094 L 1427.390625 2314.578125 L 1427.191406 2314.660156 L 1426.980469 2314.742188 L 1426.769531 2314.820312 L 1426.570312 2314.890625 L 1426.550781 2314.898438 L 1426.339844 2314.972656 L 1426.160156 2315.035156 L 1426.128906 2315.046875 L 1425.921875 2315.113281 L 1425.699219 2315.183594 L 1425.578125 2315.222656 L 1425.558594 2315.226562 L 1425.269531 2315.316406 L 1425.050781 2315.378906 L 1425 2315.394531 L 1424.828125 2315.441406 L 1424.621094 2315.5 L 1424.578125 2315.511719 L 1424.28125 2315.589844 L 1423.921875 2315.675781 L 1423.289062 2315.816406 L 1423.210938 2315.835938 L 1423.058594 2315.863281 L 1422.609375 2315.945312 L 1422.601562 2315.949219 L 1422.160156 2316.023438 L 1421.980469 2316.050781 L 1421.929688 2316.058594 L 1421.378906 2316.136719 L 1421.351562 2316.140625 L 1420.78125 2316.203125 L 1420.738281 2316.210938 L 1420.550781 2316.226562 L 1420.121094 2316.265625 L 1420.089844 2316.269531 L 1419.488281 2316.304688 L 1419.480469 2316.304688 L 1419.390625 2316.308594 L 1418.921875 2316.328125 L 1418.851562 2316.328125 L 1418.800781 2316.332031 L 1418.210938 2316.339844 L 1417.621094 2316.332031 L 1417.570312 2316.328125 L 1417.5 2316.328125 L 1417.03125 2316.308594 L 1416.929688 2316.304688 L 1416.921875 2316.304688 L 1416.320312 2316.269531 L 1416.300781 2316.265625 L 1415.859375 2316.226562 L 1415.671875 2316.210938 L 1415.628906 2316.203125 L 1415.058594 2316.140625 L 1415.03125 2316.136719 L 1414.480469 2316.058594 L 1414.429688 2316.050781 L 1414.25 2316.023438 L 1413.808594 2315.949219 L 1413.800781 2315.945312 L 1413.351562 2315.863281 L 1413.210938 2315.835938 L 1413.121094 2315.816406 L 1412.699219 2315.722656 L 1412.5 2315.675781 L 1412.128906 2315.589844 L 1411.828125 2315.511719 L 1411.800781 2315.5 L 1411.578125 2315.441406 L 1411.410156 2315.394531 L 1411.359375 2315.378906 L 1411.140625 2315.316406 L 1410.929688 2315.253906 L 1410.828125 2315.222656 L 1410.5 2315.113281 L 1410.28125 2315.046875 L 1410.25 2315.035156 L 1410.070312 2314.972656 L 1409.859375 2314.898438 L 1409.839844 2314.890625 L 1409.648438 2314.820312 L 1409.441406 2314.742188 L 1408.808594 2314.496094 L 1408.601562 2314.410156 L 1408.398438 2314.324219 L 1408.191406 2314.234375 L 1408.140625 2314.210938 L 1407.839844 2314.074219 L 1407.789062 2314.050781 L 1407.589844 2313.953125 L 1407.378906 2313.859375 L 1407.191406 2313.761719 L 1406.988281 2313.660156 L 1406.820312 2313.574219 L 1406.789062 2313.558594 L 1406.589844 2313.457031 L 1406.398438 2313.351562 L 1406.21875 2313.253906 L 1406.199219 2313.242188 L 1406.011719 2313.136719 L 1405.628906 2312.914062 L 1405.429688 2312.800781 L 1405.25 2312.6875 L 1405.058594 2312.570312 L 1404.871094 2312.453125 L 1404.699219 2312.34375 L 1404.691406 2312.332031 L 1404.5 2312.210938 L 465.566406 1800.230469 C 457.339844 1795.75 452.671875 1787.28125 452.664062 1778.519531 L 452.578125 1778.519531 L 452.578125 1063.089844 C 452.578125 1052.910156 458.707031 1044.171875 467.472656 1040.339844 L 703.875 911.441406 L 703.886719 891.679688 C 703.808594 890.210938 703.761719 888.71875 703.761719 887.230469 C 703.761719 847.359375 731.871094 812.609375 777.3125 788.679688 C 817.964844 767.269531 873.523438 754.019531 934.355469 754.019531 Z M 2334.210938 1104.78125 L 1443.019531 1590.71875 L 1443.019531 2249.835938 L 2334.210938 1763.890625 Z M 1418.210938 1547.929688 L 2307.378906 1063.089844 L 2132.570312 967.769531 L 2132.601562 1028.5 L 2132.691406 1028.5 C 2132.691406 1068.378906 2104.578125 1103.121094 2059.128906 1127.058594 C 2018.46875 1148.46875 1962.898438 1161.710938 1902.050781 1161.710938 C 1841.210938 1161.710938 1785.628906 1148.46875 1744.980469 1127.050781 C 1699.53125 1103.121094 1671.410156 1068.371094 1671.410156 1028.5 L 1671.511719 1028.5 L 1671.578125 891.679688 C 1671.5 890.210938 1671.460938 888.71875 1671.460938 887.230469 C 1671.460938 847.359375 1699.570312 812.609375 1745.011719 788.679688 C 1755.078125 783.371094 1766.070312 778.570312 1777.828125 774.339844 L 1649.789062 704.519531 L 1649.828125 793.730469 L 1649.929688 793.730469 C 1649.929688 833.609375 1621.820312 868.351562 1576.371094 892.289062 C 1535.710938 913.699219 1480.128906 926.941406 1419.289062 926.941406 C 1358.441406 926.941406 1302.871094 913.699219 1262.210938 892.289062 C 1216.761719 868.351562 1188.648438 833.609375 1188.648438 793.730469 L 1188.75 793.730469 L 1188.789062 703.339844 L 1058.578125 774.339844 C 1070.339844 778.570312 1081.328125 783.371094 1091.398438 788.679688 C 1136.839844 812.609375 1164.949219 847.359375 1164.949219 887.230469 C 1164.949219 888.710938 1164.910156 890.191406 1164.828125 891.660156 L 1164.898438 1028.5 L 1165 1028.5 C 1165 1068.378906 1136.878906 1103.121094 1091.429688 1127.058594 C 1050.769531 1148.46875 995.199219 1161.710938 934.355469 1161.710938 C 873.515625 1161.710938 817.9375 1148.46875 777.28125 1127.050781 C 731.828125 1103.121094 703.714844 1068.371094 703.714844 1028.5 L 703.8125 1028.5 L 703.84375 967.769531 L 529.035156 1063.089844 Z M 1393.390625 1590.71875 L 502.203125 1104.78125 L 502.203125 1763.890625 L 1393.390625 2249.835938 Z M 1649.761719 1163.988281 L 1649.828125 1300.828125 L 1649.929688 1300.828125 C 1649.929688 1340.699219 1621.820312 1375.441406 1576.371094 1399.378906 C 1535.710938 1420.789062 1480.128906 1434.039062 1419.289062 1434.039062 C 1358.441406 1434.039062 1302.871094 1420.789062 1262.210938 1399.378906 C 1216.761719 1375.441406 1188.648438 1340.699219 1188.648438 1300.828125 L 1188.75 1300.828125 L 1188.820312 1164.011719 C 1188.738281 1162.53125 1188.691406 1161.039062 1188.691406 1159.550781 C 1188.691406 1119.679688 1216.800781 1084.941406 1262.25 1061 C 1302.890625 1039.589844 1358.460938 1026.339844 1419.289062 1026.339844 C 1480.121094 1026.339844 1535.679688 1039.589844 1576.328125 1061 C 1621.78125 1084.941406 1649.878906 1119.679688 1649.878906 1159.550781 C 1649.878906 1161.039062 1649.839844 1162.519531 1649.761719 1163.988281 Z M 1238.210938 1243.261719 L 1238.179688 1300.828125 L 1238.28125 1300.828125 C 1238.28125 1320.820312 1256.238281 1340.28125 1285.28125 1355.570312 C 1319.121094 1373.390625 1366.460938 1384.410156 1419.289062 1384.410156 C 1472.121094 1384.410156 1519.460938 1373.390625 1553.300781 1355.570312 C 1582.339844 1340.28125 1600.300781 1320.820312 1600.300781 1300.828125 L 1600.398438 1300.828125 L 1600.371094 1243.261719 C 1593.039062 1248.578125 1585 1253.539062 1576.328125 1258.109375 C 1535.679688 1279.519531 1480.121094 1292.761719 1419.289062 1292.761719 C 1358.460938 1292.761719 1302.898438 1279.519531 1262.25 1258.109375 C 1253.578125 1253.539062 1245.539062 1248.578125 1238.210938 1243.261719 Z M 1553.269531 1104.808594 C 1519.441406 1086.988281 1472.109375 1075.96875 1419.289062 1075.96875 C 1366.46875 1075.96875 1319.140625 1086.988281 1285.308594 1104.808594 C 1256.28125 1120.101562 1238.320312 1139.558594 1238.320312 1159.550781 C 1238.320312 1179.550781 1256.28125 1199 1285.308594 1214.300781 C 1319.140625 1232.121094 1366.46875 1243.140625 1419.289062 1243.140625 C 1472.109375 1243.140625 1519.441406 1232.121094 1553.261719 1214.300781 C 1582.300781 1199 1600.261719 1179.550781 1600.261719 1159.550781 C 1600.261719 1139.558594 1582.300781 1120.101562 1553.269531 1104.808594 Z M 1238.210938 736.171875 L 1238.179688 793.730469 L 1238.28125 793.730469 C 1238.28125 813.730469 1256.238281 833.179688 1285.28125 848.480469 C 1319.121094 866.300781 1366.460938 877.320312 1419.289062 877.320312 C 1472.121094 877.320312 1519.460938 866.289062 1553.300781 848.480469 C 1582.339844 833.179688 1600.300781 813.730469 1600.300781 793.730469 L 1600.398438 793.730469 L 1600.371094 736.171875 C 1593.039062 741.488281 1585 746.449219 1576.328125 751.011719 C 1535.679688 772.429688 1480.121094 785.671875 1419.289062 785.671875 C 1358.460938 785.671875 1302.890625 772.429688 1262.25 751.011719 C 1253.578125 746.449219 1245.539062 741.488281 1238.210938 736.171875 Z M 1553.261719 597.71875 C 1519.441406 579.898438 1472.109375 568.878906 1419.289062 568.878906 C 1366.46875 568.878906 1319.140625 579.898438 1285.308594 597.71875 C 1256.28125 613.011719 1238.320312 632.46875 1238.320312 652.460938 C 1238.320312 672.449219 1256.28125 691.910156 1285.308594 707.199219 C 1319.140625 725.019531 1366.46875 736.039062 1419.289062 736.039062 C 1472.109375 736.039062 1519.441406 725.019531 1553.269531 707.210938 C 1582.300781 691.910156 1600.261719 672.449219 1600.261719 652.460938 C 1600.261719 632.46875 1582.300781 613.011719 1553.261719 597.71875 Z M 1720.96875 970.941406 L 1720.941406 1028.5 L 1721.039062 1028.5 C 1721.039062 1048.488281 1739 1067.949219 1768.039062 1083.238281 C 1801.878906 1101.058594 1849.21875 1112.089844 1902.050781 1112.089844 C 1954.878906 1112.089844 2002.230469 1101.058594 2036.058594 1083.25 C 2065.101562 1067.949219 2083.070312 1048.488281 2083.070312 1028.5 L 2083.171875 1028.5 L 2083.140625 970.941406 C 2075.800781 976.261719 2067.769531 981.21875 2059.101562 985.78125 C 2018.449219 1007.191406 1962.890625 1020.441406 1902.050781 1020.441406 C 1841.21875 1020.441406 1785.660156 1007.191406 1745.011719 985.78125 C 1736.339844 981.21875 1728.300781 976.25 1720.96875 970.941406 Z M 2036.03125 832.488281 C 2002.199219 814.671875 1954.871094 803.648438 1902.050781 803.648438 C 1849.238281 803.648438 1801.910156 814.671875 1768.078125 832.488281 C 1739.039062 847.78125 1721.089844 867.238281 1721.089844 887.230469 C 1721.089844 907.21875 1739.039062 926.679688 1768.078125 941.96875 C 1801.898438 959.789062 1849.238281 970.808594 1902.050781 970.808594 C 1954.871094 970.808594 2002.199219 959.789062 2036.03125 941.96875 C 2065.058594 926.679688 2083.019531 907.21875 2083.019531 887.230469 C 2083.019531 867.238281 2065.058594 847.78125 2036.03125 832.488281 Z M 1115.441406 970.941406 C 1108.109375 976.261719 1100.070312 981.21875 1091.398438 985.78125 C 1050.75 1007.191406 995.191406 1020.441406 934.355469 1020.441406 C 873.523438 1020.441406 817.964844 1007.191406 777.3125 985.78125 C 768.644531 981.21875 760.609375 976.25 753.277344 970.941406 L 753.246094 1028.5 L 753.34375 1028.5 C 753.34375 1048.488281 771.308594 1067.949219 800.347656 1083.238281 C 834.183594 1101.058594 881.527344 1112.089844 934.355469 1112.089844 C 987.1875 1112.089844 1034.53125 1101.058594 1068.371094 1083.25 C 1097.410156 1067.949219 1115.371094 1048.488281 1115.371094 1028.5 L 1115.46875 1028.5 Z M 1068.328125 832.488281 C 1034.511719 814.671875 987.171875 803.648438 934.355469 803.648438 C 881.539062 803.648438 834.210938 814.671875 800.382812 832.488281 C 771.347656 847.78125 753.390625 867.238281 753.390625 887.230469 C 753.390625 907.21875 771.347656 926.679688 800.382812 941.96875 C 834.207031 959.789062 881.539062 970.808594 934.355469 970.808594 C 987.171875 970.808594 1034.511719 959.789062 1068.328125 941.96875 C 1097.371094 926.679688 1115.328125 907.21875 1115.328125 887.230469 C 1115.328125 867.238281 1097.371094 847.78125 1068.328125 832.488281"
BRICK_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2836 2836"'
    ' width="16" height="16" style="flex-shrink:0;display:block">'
    f'<path fill-rule="nonzero" fill="currentColor" d="{_BRICK_PATH}"/>'
    '</svg>'
)

CHART_COLORS = [
    "#2F81F7", "#3FB950", "#D4A017", "#F78166",
    "#A371F7", "#FFA657", "#79C0FF", "#FF7B72",
    "#56D364", "#E5C07B", "#58A6FF", "#F0883E",
]

# ── OAuth (GitHub OAuth App + Cloudflare Worker proxy) ─────────────────────────
# Set these as GitHub Actions secrets: OAUTH_CLIENT_ID, OAUTH_WORKER_URL, CANCEL_WORKER_URL
OAUTH_CLIENT_ID   = os.environ.get("OAUTH_CLIENT_ID", "")
OAUTH_WORKER_URL  = os.environ.get("OAUTH_WORKER_URL", "")
CANCEL_WORKER_URL = os.environ.get("CANCEL_WORKER_URL", "")

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
              timelineItems(itemTypes: [CLOSED_EVENT], last: 1) {
                nodes {
                  ... on ClosedEvent {
                    closer {
                      ... on PullRequest {
                        author { login }
                      }
                    }
                  }
                }
              }
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
        open_issues  — Status!='Done' + has SP label  (shown in Reserve modal)
    """
    done = []
    coin = []
    open_issues = []
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

            status = (item.get("status") or {}).get("name", "")

            # Extract PR author who closed the issue
            tl_nodes = content.get("timelineItems", {}).get("nodes", [])
            closer = ""
            if tl_nodes:
                closer_obj    = (tl_nodes[0].get("closer") or {})
                closer_author = (closer_obj.get("author") or {})
                closer        = closer_author.get("login", "") or ""

            repo = (content.get("repository") or {}).get("name", "")
            issue = {
                "number":       content["number"],
                "title":        content["title"],
                "repo":         repo,
                "creator":      (content.get("author") or {}).get("login"),
                "assignees":    [a["login"] for a in content.get("assignees", {}).get("nodes", [])],
                "story_points": sp,
                "closed_at":    content.get("closedAt", "") or "",
                "closer":       closer,
            }

            if "done" in status.lower():
                done.append(issue)
            else:
                open_issues.append({
                    "number":    content["number"],
                    "title":     content["title"],
                    "repo":      repo,
                    "sp":        sp,
                    "status":    status,
                    "assignees": [a["login"] for a in content.get("assignees", {}).get("nodes", [])],
                    "creator":   (content.get("author") or {}).get("login") or "",
                })

            if COIN_LABEL in labels:
                coin.append(issue)

        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]

    # Sort open issues: unassigned first, then by SP descending
    open_issues.sort(key=lambda i: (len(i["assignees"]) > 0, -i["sp"]))
    return done, coin, open_issues

# ── Scoring ─────────────────────────────────────────────────────────────────────

def find_implementer(issue, user_to_team):
    """Return (team_id, login) for the person who implemented this issue.

    Priority:
      1. Author of the PR that closed the issue (most accurate)
      2. First assignee that belongs to a known team (fallback)
    """
    closer = issue.get("closer", "")
    if closer:
        t = user_to_team.get(closer.lower())
        if t is not None:
            return t, closer

    for a in issue["assignees"]:
        t = user_to_team.get(a.lower())
        if t is not None:
            return t, a

    return None, None

def calculate_scores(teams, user_to_team, all_issues, coin_issues, open_issues=None):
    scores = {i: {"creation": 0.0, "implementation": 0.0, "issues_created": 0, "issues_implemented": 0,
                  "balance": 0.0, "coin_issues": 0, "expected_sp": 0.0, "expected_issues": 0}
              for i in range(len(teams))}

    for issue in all_issues:
        creator  = issue["creator"]
        sp       = issue["story_points"]

        creator_team_id          = user_to_team.get(creator.lower()) if creator else None
        impl_team_id, _implementer = find_implementer(issue, user_to_team)

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

    # Expected SP: sum SP of open issues assigned to each team
    for issue in (open_issues or []):
        seen_teams = set()
        for assignee in issue.get("assignees", []):
            tid = user_to_team.get(assignee.lower())
            if tid is not None and tid not in seen_teams:
                seen_teams.add(tid)
                scores[tid]["expected_sp"] += issue["sp"]
                scores[tid]["expected_issues"] += 1

    return scores

# ── Issues Detail ───────────────────────────────────────────────────────────────

def build_issues_detail(teams, user_to_team, all_issues):
    """Build rich per-issue data used by both the score chart and team detail panel."""
    details = []
    for issue in all_issues:
        creator     = issue["creator"]
        creator_tid = user_to_team.get(creator.lower()) if creator else None
        impl_tid, implementer = find_implementer(issue, user_to_team)
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

def load_daily_positions(out_dir):
    """Load start-of-day positions. Returns {} if file missing or date stale."""
    path = os.path.join(out_dir, "positions_daily.json")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") == today:
            return data.get("positions", {})
    return {}

def save_daily_positions(positions, out_dir):
    """Save daily baseline — only writes once per UTC day."""
    path = os.path.join(out_dir, "positions_daily.json")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") == today:
            return
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": today, "positions": positions}, f, indent=2)

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

# ── Betting ──────────────────────────────────────────────────────────────────────

def load_bets(out_dir, teams):
    """Load docs/bets.json; initialize missing members at BRICKS_START."""
    path = os.path.join(out_dir, "bets.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"member_balances": {}, "active_bets": [], "resolved_bets": []}

    for team in teams:
        for member in team["members"]:
            if member not in data["member_balances"]:
                data["member_balances"][member] = BRICKS_START

    return data


MAX_ACTIVE_BETS_PER_USER = 5  # spam guard


def fetch_bet_issues():
    """Fetch open issues labeled 'bet' from the scoreboard repo."""
    url = f"https://api.github.com/repos/{SCOREBOARD_OWNER}/{SCOREBOARD_REPO}/issues"
    bets = []
    page = 1
    while True:
        resp = requests.get(
            url, headers=HEADERS,
            params={"labels": "bet", "state": "open", "per_page": 100, "page": page},
            timeout=15,
        )
        if resp.status_code == 404:
            print("  Note: scoreboard repo or 'bet' label not found — skipping bets")
            return bets
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break
        for issue in items:
            body = issue.get("body") or ""
            bet_data = None
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
            if m:
                try:
                    bet_data = json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
            if bet_data is None:
                try:
                    bet_data = json.loads(body.strip())
                except json.JSONDecodeError:
                    continue
            bet_data["_issue_number"] = issue["number"]
            bet_data["_issue_url"]    = issue["html_url"]
            # Always use the GitHub issue author — never trust the JSON field
            bet_data["_author"]       = issue["user"]["login"]
            # Check if the author posted a "cancel" comment
            bet_data["_cancel_by"]    = None
            if issue.get("comments", 0) > 0:
                try:
                    c_resp = requests.get(issue["comments_url"], headers=HEADERS, timeout=10)
                    if c_resp.ok:
                        for c in c_resp.json():
                            if (c.get("body", "").strip().lower() == "cancel"
                                    and c["user"]["login"] == issue["user"]["login"]):
                                bet_data["_cancel_by"] = c["user"]["login"]
                                break
                except Exception:
                    pass
            bets.append(bet_data)
        if len(items) < 100:
            break
        page += 1
    return bets


def _sigmoid(x):
    """Standard logistic function, clamped to avoid overflow."""
    return 1.0 / (1.0 + math.exp(-max(-500, min(500, x))))


def _calc_odds_server(bet_type, params, teams, scores, ranked):
    """Recalculate odds server-side using sigmoid curves (mirrors JS calcOdds)."""
    HOUSE_EDGE = 0.10
    K_SCORE    = 5.0   # sigmoid steepness for score-based bets
    K_RANK     = 4.0   # sigmoid steepness for rank bets
    p = 0.5

    name_to_id = {t["name"]: t["id"] for t in teams}
    n_teams    = max(len(teams), 1)

    def metric(tid, key):
        if key == "total":
            return scores[tid]["creation"] + scores[tid]["implementation"]
        return scores[tid].get(key, 0)

    if bet_type == "over_under":
        tid = name_to_id.get(params.get("subject_team"))
        if tid is None:
            return 2.0
        current   = metric(tid, params.get("metric", "total"))
        threshold = float(params.get("threshold") or 1)
        ratio     = current / threshold if threshold > 0 else 1.0
        p_over    = _sigmoid(K_SCORE * (ratio - 1))
        p = p_over if params.get("direction") == "over" else (1 - p_over)

    elif bet_type == "rank":
        tid = name_to_id.get(params.get("subject_team"))
        if tid is None:
            return 2.0
        cur = (ranked.index(tid) + 1) if tid in ranked else n_teams + 1
        tgt = int(params.get("target_rank") or 1)
        # positive gap = needs to improve, negative = already ahead of target
        gap = (cur - tgt) if params.get("direction") == "at_or_better" else (tgt - cur)
        p   = _sigmoid(-K_RANK * gap / n_teams)

    elif bet_type == "milestone":
        tid = name_to_id.get(params.get("subject_team"))
        if tid is None:
            return 2.0
        current = scores[tid].get(params.get("metric", "issues_created"), 0)
        target  = int(params.get("target") or 1)
        ratio   = current / target if target > 0 else 1.0
        p       = _sigmoid(K_SCORE * (ratio - 1))

    elif bet_type == "head_to_head":
        id_a = name_to_id.get(params.get("team_a"))
        id_b = name_to_id.get(params.get("team_b"))
        if id_a is None or id_b is None:
            return 2.0
        sc_a   = metric(id_a, params.get("metric", "total"))
        sc_b   = metric(id_b, params.get("metric", "total"))
        total_ = sc_a + sc_b
        p_a    = (sc_a / total_) if total_ > 0 else 0.5
        p      = p_a if params.get("pick") == "team_a" else (1 - p_a)

    p   = max(0.05, min(0.95, p))
    raw = (1 / p) * (1 - HOUSE_EDGE)
    return round(max(1.05, min(9.0, raw)), 2)


def _close_bet_issue_cancelled(issue_number, stake):
    """Post a cancellation comment and close the bet issue (best-effort)."""
    base = f"https://api.github.com/repos/{SCOREBOARD_OWNER}/{SCOREBOARD_REPO}/issues/{issue_number}"
    body = f"\u21a9\ufe0f **Cancelled** \u2014 Stake refunded: **+{stake:.2f} BRK**"
    try:
        requests.post(base + "/comments", headers=HEADERS, json={"body": body}, timeout=10)
        requests.patch(base, headers=HEADERS, json={"state": "closed"}, timeout=10)
    except Exception as exc:
        print(f"  Warning: could not close cancelled bet #{issue_number}: {exc}")


def process_cancellations(bets_data, bet_issues):
    """Refund and close bets where the owner posted 'cancel' with >1h before deadline."""
    cancel_map = {
        b["_issue_number"]: b["_cancel_by"]
        for b in bet_issues if b.get("_cancel_by")
    }
    now = datetime.now(timezone.utc)
    still_active = []

    for bet in bets_data["active_bets"]:
        cancel_by = cancel_map.get(bet["issue_number"])
        if not cancel_by or cancel_by.lower() != bet["placed_by"].lower():
            still_active.append(bet)
            continue

        try:
            deadline_date = datetime.strptime(bet["deadline"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            still_active.append(bet)
            continue

        # Close time = midnight UTC at end of deadline day; cancel window closes 1 h before
        close_time = datetime(deadline_date.year, deadline_date.month, deadline_date.day,
                              tzinfo=timezone.utc) + timedelta(days=1)
        if now >= close_time - timedelta(hours=1):
            print(f"  Bet #{bet['issue_number']}: cancel request too close to deadline, ignored")
            still_active.append(bet)
            continue

        # Refund stake
        old_bal = bets_data["member_balances"].get(bet["placed_by"], 0)
        bets_data["member_balances"][bet["placed_by"]] = round(old_bal + bet["stake"], 2)
        _close_bet_issue_cancelled(bet["issue_number"], bet["stake"])
        print(f"  Bet #{bet['issue_number']} cancelled by {bet['placed_by']}: +{bet['stake']:.2f} BRK refunded")

        resolved_bet = dict(bet)
        resolved_bet["won"]         = False
        resolved_bet["payout"]      = 0.0
        resolved_bet["cancelled"]   = True
        resolved_bet["resolved_at"] = now.isoformat()
        bets_data["resolved_bets"].append(resolved_bet)

    bets_data["active_bets"] = still_active
    return bets_data


def _reject_bet_issue(issue_number, reason):
    """Post a rejection comment and close the bet issue (best-effort)."""
    base = f"https://api.github.com/repos/{SCOREBOARD_OWNER}/{SCOREBOARD_REPO}/issues/{issue_number}"
    body = f"\u274c **Bet rejected:** {reason}"
    try:
        requests.post(base + "/comments", headers=HEADERS, json={"body": body}, timeout=10)
        requests.patch(base, headers=HEADERS, json={"state": "closed"}, timeout=10)
    except Exception as exc:
        print(f"  Warning: could not reject bet #{issue_number}: {exc}")


def sync_new_bets(bets_data, bet_issues, teams, scores, ranked):
    """Register new bet issues, deducting stake from placer's balance."""
    existing_ids = {b["issue_number"] for b in bets_data["active_bets"]}
    existing_ids |= {b["issue_number"] for b in bets_data["resolved_bets"]}

    # Build team-name → set-of-members for own-team check
    name_to_members = {t["name"]: set(m.lower() for m in t["members"]) for t in teams}

    today = datetime.now(timezone.utc).date()

    for issue in bet_issues:
        issue_num = issue.get("_issue_number")
        if issue_num in existing_ids:
            continue

        # Always use the GitHub issue author — never the JSON field
        placed_by = issue.get("_author", "").strip()
        if not placed_by:
            continue

        try:
            stake = float(issue.get("stake", 0))
        except (TypeError, ValueError):
            continue

        if stake <= 0:
            _reject_bet_issue(issue_num, "stake must be greater than 0")
            existing_ids.add(issue_num)
            continue

        # Minimum deadline: must be at least tomorrow
        deadline_str = issue.get("deadline", "")
        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            _reject_bet_issue(issue_num, "missing or invalid deadline (use YYYY-MM-DD)")
            existing_ids.add(issue_num)
            continue
        if deadline <= today:
            _reject_bet_issue(issue_num, "deadline must be at least tomorrow")
            existing_ids.add(issue_num)
            continue

        bet_type = issue.get("bet_type", "")
        params   = issue.get("params", {})

        # H2H same team → reject
        if bet_type == "head_to_head" and params.get("team_a") == params.get("team_b"):
            _reject_bet_issue(issue_num, "head-to-head bet cannot use the same team on both sides")
            existing_ids.add(issue_num)
            continue

        # Block betting on own team
        placed_by_lower = placed_by.lower()
        if bet_type in ("over_under", "rank", "milestone"):
            subject = params.get("subject_team", "")
            if placed_by_lower in name_to_members.get(subject, set()):
                _reject_bet_issue(issue_num, "you cannot bet on your own team")
                existing_ids.add(issue_num)
                continue
        elif bet_type == "head_to_head":
            for side in ("team_a", "team_b"):
                if placed_by_lower in name_to_members.get(params.get(side, ""), set()):
                    _reject_bet_issue(issue_num, "you cannot bet on a head-to-head that includes your own team")
                    existing_ids.add(issue_num)
                    break
            else:
                pass  # no own-team violation, continue normally
            if issue_num in existing_ids:
                continue

        # Spam guard: max active bets per user
        active_count = sum(1 for b in bets_data["active_bets"] if b["placed_by"] == placed_by)
        if active_count >= MAX_ACTIVE_BETS_PER_USER:
            _reject_bet_issue(issue_num, f"maximum of {MAX_ACTIVE_BETS_PER_USER} active bets per user reached")
            existing_ids.add(issue_num)
            continue

        # Recalculate odds server-side — never trust the client value
        odds = _calc_odds_server(bet_type, params, teams, scores, ranked)

        balance = bets_data["member_balances"].get(placed_by, 0)
        if balance < stake:
            print(f"  Bet #{issue_num} by {placed_by}: insufficient balance ({balance:.2f} < {stake:.2f}), skipping")
            continue

        bets_data["member_balances"][placed_by] = round(balance - stake, 2)
        bets_data["active_bets"].append({
            "issue_number":    issue_num,
            "issue_url":       issue.get("_issue_url", ""),
            "bet_type":        bet_type,
            "placed_by":       placed_by,
            "stake":           stake,
            "odds":            odds,
            "potential_payout": round(stake * odds, 2),
            "deadline":        deadline_str,
            "params":          params,
            "placed_at":       issue.get("placed_at", datetime.now(timezone.utc).isoformat()),
        })
        existing_ids.add(issue_num)
        print(f"  New bet #{issue_num} by {placed_by}: {stake:.2f} BRK @ {odds:.2f}x")

    return bets_data


def _check_bet_condition(bet, teams, scores, ranked):
    """Return True (win) / False (loss) / None (unknown team) for a bet."""
    name_to_id = {t["name"]: t["id"] for t in teams}

    def metric(team_id, key):
        s = scores[team_id]
        if key == "total":
            return s["creation"] + s["implementation"]
        return s.get(key, 0)

    bt     = bet.get("bet_type")
    params = bet.get("params", {})

    if bt == "over_under":
        tid = name_to_id.get(params.get("subject_team"))
        if tid is None: return None
        current   = metric(tid, params.get("metric", "total"))
        threshold = float(params.get("threshold", 0))
        return current > threshold if params.get("direction") == "over" else current < threshold

    if bt == "rank":
        tid = name_to_id.get(params.get("subject_team"))
        if tid is None: return None
        cur_rank    = (ranked.index(tid) + 1) if tid in ranked else len(ranked) + 1
        target_rank = int(params.get("target_rank", 1))
        return cur_rank <= target_rank if params.get("direction") == "at_or_better" else cur_rank >= target_rank

    if bt == "milestone":
        tid = name_to_id.get(params.get("subject_team"))
        if tid is None: return None
        current = scores[tid].get(params.get("metric", "issues_created"), 0)
        return current >= int(params.get("target", 0))

    if bt == "head_to_head":
        id_a = name_to_id.get(params.get("team_a"))
        id_b = name_to_id.get(params.get("team_b"))
        if id_a is None or id_b is None: return None
        key    = params.get("metric", "total")
        sc_a   = metric(id_a, key)
        sc_b   = metric(id_b, key)
        return sc_a > sc_b if params.get("pick") == "team_a" else sc_b > sc_a

    return None


def _close_bet_issue(issue_number, won, payout, odds):
    """Post a resolution comment and close the bet issue (best-effort)."""
    if won:
        body = f"**WIN** \U0001f3c6 — Payout: **+{payout:.2f} BRK** (\u00d7{odds:.2f} odds)"
    else:
        body = "**LOSS** \U0001f534 — Stake lost."

    base = f"https://api.github.com/repos/{SCOREBOARD_OWNER}/{SCOREBOARD_REPO}/issues/{issue_number}"
    try:
        requests.post(base + "/comments", headers=HEADERS, json={"body": body}, timeout=10)
        requests.patch(base, headers=HEADERS, json={"state": "closed"}, timeout=10)
    except Exception as exc:
        print(f"  Warning: could not close bet #{issue_number}: {exc}")


def resolve_bets(bets_data, teams, scores, ranked):
    """Resolve all active bets whose deadline has passed."""
    today = datetime.now(timezone.utc).date()
    still_active = []

    for bet in bets_data["active_bets"]:
        deadline_str = bet.get("deadline", "")
        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            still_active.append(bet)
            continue

        if deadline > today:
            still_active.append(bet)
            continue

        won = _check_bet_condition(bet, teams, scores, ranked)
        if won is None:
            won = False  # unknown condition → loss

        payout = bet["potential_payout"] if won else 0.0
        if won:
            old_bal = bets_data["member_balances"].get(bet["placed_by"], 0)
            bets_data["member_balances"][bet["placed_by"]] = round(old_bal + payout, 2)

        resolved_bet = dict(bet)
        resolved_bet["won"]         = won
        resolved_bet["payout"]      = payout
        resolved_bet["resolved_at"] = datetime.now(timezone.utc).isoformat()
        bets_data["resolved_bets"].append(resolved_bet)

        _close_bet_issue(bet["issue_number"], won, payout, bet["odds"])
        print(f"  Resolved bet #{bet['issue_number']}: {'WIN' if won else 'LOSS'} for {bet['placed_by']}")

    bets_data["active_bets"] = still_active
    return bets_data


def save_bets(bets_data, out_dir):
    """Write docs/bets.json."""
    path = os.path.join(out_dir, "bets.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bets_data, f, indent=2)

# ── HTML ────────────────────────────────────────────────────────────────────────

def generate_html(teams, scores, all_issues, coin_issues, generated_at, ranked, prev_positions, issues_detail, open_issues, bets_data=None):
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
                <span class="pts-sub">{s["issues_implemented"]} done</span>
                {"" if not s["expected_sp"] else f'<span class="pts-expected" title="Expected SP from assigned open issues">+{s["expected_sp"]:.2f} expected</span>'}
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

    team_names_json    = json.dumps([t["name"] for t in teams])
    team_members_json  = json.dumps({t["name"]: t["members"] for t in teams})
    team_colors_json   = json.dumps(CHART_COLORS[:len(teams)])
    issues_detail_json = json.dumps(issues_detail)
    open_issues_json   = json.dumps(open_issues)
    oauth_client_id    = json.dumps(OAUTH_CLIENT_ID)
    oauth_worker_url   = json.dumps(OAUTH_WORKER_URL)
    cancel_worker_url  = json.dumps(CANCEL_WORKER_URL)

    _bets = bets_data or {"member_balances": {}, "active_bets": [], "resolved_bets": []}
    member_bricks_json  = json.dumps(_bets["member_balances"])
    active_bets_json    = json.dumps(_bets["active_bets"])
    resolved_bets_json  = json.dumps(_bets["resolved_bets"])

    # Build team score snapshot for JS odds calculation
    team_scores_snapshot = {}
    for team in teams:
        s = scores[team["id"]]
        pos = ranked.index(team["id"]) + 1 if team["id"] in ranked else len(teams)
        team_scores_snapshot[team["name"]] = {
            "total": round(s["creation"] + s["implementation"], 2),
            "creation": round(s["creation"], 2),
            "implementation": round(s["implementation"], 2),
            "issues_created": s["issues_created"],
            "issues_implemented": s["issues_implemented"],
            "rank": pos,
        }
    team_scores_json = json.dumps(team_scores_snapshot)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FLL Scoreboard</title>
  <link rel="icon" type="image/svg+xml" href="fll.svg">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root, [data-theme="dark"] {{
      --bg:            #0A0A0A;
      --surface:       #111111;
      --surface-hover: #1A1A1A;
      --border:        #242424;
      --border-subtle: #191919;
      --text-primary:  #F0F0F0;
      --text-secondary:#8C8C8C;
      --text-muted:    #4A4A4A;
      --accent:        #C8873A;
      --accent-dim:    rgba(200,135,58,0.12);
      --green:         #4CC38A;
      --red:           #E5484D;
      --gold:          #D4A017;
      --silver:        #A0AEC0;
      --bronze:        #B87333;
    }}

    [data-theme="light"] {{
      --bg:            #FFFFFF;
      --surface:       #F6F8FA;
      --surface-hover: #EFF2F5;
      --border:        #D0D7DE;
      --border-subtle: #EAEEF2;
      --text-primary:  #1F2328;
      --text-secondary:#656D76;
      --text-muted:    #9198A1;
      --accent:        #A0620F;
      --accent-dim:    rgba(160,98,15,0.10);
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
    .site-link {{
      font-size: 0.75rem;
      color: var(--accent);
      text-decoration: none;
      opacity: 0.8;
      transition: opacity 150ms ease;
    }}
    .site-link:hover {{ opacity: 1; text-decoration: underline; }}

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
      transition: border-color 200ms ease, color 200ms ease, background 200ms ease, transform 120ms ease;
      white-space: nowrap;
      will-change: transform;
      user-select: none;
    }}
    .theme-btn:hover {{
      border-color: var(--accent);
      color: var(--accent);
      background: var(--accent-dim);
      transform: translateY(-1px);
    }}
    .theme-btn:active {{
      transform: translateY(0) scale(0.97);
      transition-duration: 60ms;
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
      position: relative;
      overflow: hidden;
    }}
    .stat::before {{
      content: '';
      position: absolute;
      top: 0; left: 20px; right: 20px;
      height: 2px;
      background: var(--stat-color, var(--border));
      border-radius: 0 0 2px 2px;
      opacity: 0.6;
    }}
    .stat .value {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 2rem;
      font-weight: 700;
      color: var(--stat-color, var(--text-primary));
      font-variant-numeric: tabular-nums;
      line-height: 1;
    }}
    .stat .label {{
      font-size: 0.68rem;
      color: var(--text-muted);
      margin-top: 7px;
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
      text-align: center;
      line-height: 1;
    }}
    .rank-badge.rank-1,
    .rank-badge.rank-2,
    .rank-badge.rank-3 {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 22px; height: 22px;
      border-radius: 50%;
      font-size: 0.78rem;
    }}
    .rank-badge.rank-1 {{ background: rgba(212,160,23,0.18); color: var(--gold); box-shadow: 0 0 0 1px rgba(212,160,23,0.35); }}
    .rank-badge.rank-2 {{ background: rgba(160,174,192,0.14); color: var(--silver); box-shadow: 0 0 0 1px rgba(160,174,192,0.30); }}
    .rank-badge.rank-3 {{ background: rgba(184,115,51,0.14); color: var(--bronze); box-shadow: 0 0 0 1px rgba(184,115,51,0.30); }}

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
    @keyframes rankUpGlow {{
      0%   {{ background-color: transparent; }}
      20%  {{ background-color: rgba(80,200,120,0.13); }}
      100% {{ background-color: transparent; }}
    }}
    .rank-up-flash > td {{ animation: rankUpGlow 2s ease-out forwards; }}

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
    .pts-expected {{
      display: block;
      font-size: 0.68rem;
      font-weight: 500;
      color: var(--accent);
      margin-top: 2px;
      opacity: 0.8;
      font-style: italic;
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
    .balance-ok   {{ color: var(--accent); }}
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

    /* ── Top 3 row tints — static gradient, no animation ───────── */
    .row-top-1 {{
      background: linear-gradient(90deg, rgba(212,160,23,0.14) 0%, rgba(212,160,23,0.04) 60%, transparent 100%);
    }}
    .row-top-2 {{
      background: linear-gradient(90deg, rgba(160,174,192,0.10) 0%, rgba(160,174,192,0.03) 60%, transparent 100%);
    }}
    .row-top-3 {{
      background: linear-gradient(90deg, rgba(184,115,51,0.10) 0%, rgba(184,115,51,0.03) 60%, transparent 100%);
    }}
    /* Hover: slide right + thicker accent — background is already taken by tint */
    .row-top-1, .row-top-2, .row-top-3 {{ transition: transform 150ms ease; }}
    .row-top-1:hover {{ transform: translateX(6px); }}
    .row-top-2:hover {{ transform: translateX(6px); }}
    .row-top-3:hover {{ transform: translateX(6px); }}
    .row-top-1:hover td {{ background: transparent !important; }}
    .row-top-2:hover td {{ background: transparent !important; }}
    .row-top-3:hover td {{ background: transparent !important; }}
    .row-top-1:hover td:first-child {{ box-shadow: inset 5px 0 0 var(--gold); }}
    .row-top-2:hover td:first-child {{ box-shadow: inset 5px 0 0 var(--silver); }}
    .row-top-3:hover td:first-child {{ box-shadow: inset 5px 0 0 var(--bronze); }}

    .updated {{
      text-align: center;
      color: var(--text-muted);
      font-size: 0.7rem;
      margin-top: 12px;
    }}
    .live-row {{
      display: flex; align-items: center; justify-content: center;
      gap: 16px; flex-wrap: wrap;
    }}
    .live-indicator {{
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 0.7rem; color: var(--text-muted);
    }}
    .live-dot {{
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--green);
      animation: livepulse 2s ease-in-out infinite;
      flex-shrink: 0;
    }}
    @keyframes livepulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50%       {{ opacity: 0.3; transform: scale(0.8); }}
    }}
    #countdown {{
      font-variant-numeric: tabular-nums;
      color: var(--text-secondary);
      font-weight: 600;
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
      transition: border-color 200ms ease, color 200ms ease, background 200ms ease, transform 120ms ease, box-shadow 200ms ease;
      white-space: nowrap;
      will-change: transform;
      user-select: none;
    }}
    .chart-btn:hover {{ border-color: var(--accent); color: var(--accent); background: var(--accent-dim); transform: translateY(-1px); box-shadow: 0 2px 8px rgba(0,0,0,0.25); }}
    .chart-btn:active {{ transform: translateY(0) scale(0.97); box-shadow: none; transition-duration: 60ms; }}
    .chart-btn svg {{ width: 14px; height: 14px; flex-shrink: 0; }}

    /* Modal overlay */
    .modal-overlay {{
      position: fixed; inset: 0;
      background: rgba(0,0,0,0);
      z-index: 200;
      display: flex;
      align-items: center; justify-content: center;
      padding: 20px;
      visibility: hidden;
      pointer-events: none;
      transition: background 280ms ease-out;
    }}
    .modal-overlay.open {{
      visibility: visible;
      pointer-events: auto;
      background: rgba(0,0,0,0.65);
    }}
    .modal-box {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      width: 100%; max-width: 880px;
      max-height: 90vh;
      display: flex; flex-direction: column;
      overflow: hidden;
      transform: translateY(16px) scale(0.98);
      opacity: 0;
      transition: transform 300ms cubic-bezier(0.16,1,0.3,1), opacity 280ms ease-out;
    }}
    .modal-overlay.open .modal-box {{
      transform: translateY(0) scale(1);
      opacity: 1;
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

    /* ── Reserve modal ──────────────────────────────────────────── */
    .auth-bar {{
      display: flex; align-items: center; gap: 8px;
      padding: 10px 20px;
      border-bottom: 1px solid var(--border-subtle);
      background: var(--surface-hover);
      font-size: 0.8rem;
    }}
    .gh-login-btn {{
      display: inline-flex; align-items: center; gap: 7px;
      padding: 6px 14px;
      background: var(--text-primary); color: var(--bg);
      border: none; border-radius: 6px;
      font-family: 'Barlow', sans-serif; font-size: 0.8rem; font-weight: 600;
      cursor: pointer; transition: opacity 150ms ease;
    }}
    .gh-login-btn:hover {{ opacity: 0.85; }}
    .gh-login-btn svg {{ width: 16px; height: 16px; }}
    .user-pill {{
      display: flex; align-items: center; gap: 8px;
      font-size: 0.82rem; color: var(--text-primary);
    }}
    .user-pill img {{
      width: 26px; height: 26px; border-radius: 50%;
      border: 1.5px solid var(--border);
    }}
    .logout-btn {{
      margin-left: auto;
      background: transparent; border: 1px solid var(--border);
      border-radius: 4px; padding: 3px 10px;
      color: var(--text-muted); font-family: 'Barlow', sans-serif;
      font-size: 0.72rem; cursor: pointer;
      transition: border-color 150ms ease, color 150ms ease;
    }}
    .logout-btn:hover {{ border-color: var(--red); color: var(--red); }}
    .reserve-filters {{
      display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
      padding: 10px 20px;
      border-bottom: 1px solid var(--border-subtle);
    }}
    .filter-select {{
      padding: 5px 10px;
      background: var(--surface-hover);
      border: 1px solid var(--border);
      border-radius: 5px;
      color: var(--text-primary);
      font-family: 'Barlow', sans-serif; font-size: 0.78rem;
      cursor: pointer;
    }}
    .filter-check {{
      display: flex; align-items: center; gap: 6px;
      font-size: 0.78rem; color: var(--text-secondary); cursor: pointer;
    }}
    .filter-count {{
      margin-left: auto;
      font-size: 0.72rem; color: var(--text-muted);
    }}
    .issue-scroll {{ flex: 1; overflow-y: auto; }}
    .issue-row {{
      display: flex; align-items: center; gap: 12px;
      padding: 11px 20px;
      border-bottom: 1px solid var(--border-subtle);
      transition: background 150ms ease, padding-left 150ms ease;
    }}
    .issue-row:last-child {{ border-bottom: none; }}
    .issue-row:hover {{ background: var(--surface-hover); padding-left: 24px; }}
    .issue-num {{ font-size: 0.72rem; color: var(--text-muted); min-width: 40px; flex-shrink: 0; font-variant-numeric: tabular-nums; }}
    .issue-title {{ flex: 1; min-width: 0; }}
    .issue-title a {{ color: var(--text-primary); text-decoration: none; font-size: 0.85rem; font-weight: 500; }}
    .issue-title a:hover {{ color: var(--accent); text-decoration: underline; }}
    .issue-meta {{ display: flex; gap: 5px; margin-top: 4px; flex-wrap: wrap; align-items: center; }}
    .chip {{
      display: inline-block; padding: 1px 7px;
      border-radius: 10px; font-size: 0.65rem; font-weight: 600;
      border: 1px solid var(--border);
      color: var(--text-muted); background: var(--surface-hover);
      white-space: nowrap;
    }}
    .chip-sp {{ color: var(--accent); border-color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, transparent); }}
    .chip-todo {{ color: var(--green); border-color: var(--green); background: color-mix(in srgb, var(--green) 10%, transparent); }}
    .chip-progress {{ color: #E5C07B; border-color: #E5C07B; background: color-mix(in srgb, #E5C07B 10%, transparent); }}
    .issue-assignees {{ display: flex; gap: -4px; flex-shrink: 0; }}
    .issue-assignees img {{ width: 22px; height: 22px; border-radius: 50%; border: 1.5px solid var(--border); margin-right: -5px; }}
    .claim-btn {{
      flex-shrink: 0;
      padding: 5px 14px;
      background: var(--accent); color: #fff;
      border: none; border-radius: 5px;
      font-family: 'Barlow', sans-serif; font-size: 0.78rem; font-weight: 600;
      cursor: pointer; white-space: nowrap;
      transition: background 200ms ease, transform 120ms ease, box-shadow 200ms ease;
      box-shadow: 0 1px 3px rgba(0,0,0,0.3);
      will-change: transform;
    }}
    .claim-btn:hover {{ background: color-mix(in srgb, var(--accent) 85%, white); transform: translateY(-1px); box-shadow: 0 3px 10px rgba(200,135,58,0.30); }}
    .claim-btn:active {{ transform: translateY(0) scale(0.97); box-shadow: 0 1px 3px rgba(0,0,0,0.3); transition-duration: 60ms; }}
    .claim-btn:disabled {{ background: var(--border); color: var(--text-muted); cursor: default; transform: none; box-shadow: none; }}
    .claim-btn.claimed {{ background: var(--green); cursor: default; transform: none; box-shadow: none; }}
    .reserve-empty {{
      text-align: center; padding: 40px 20px;
      color: var(--text-muted); font-size: 0.85rem;
    }}
    .auth-notice {{
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 0.78rem; color: var(--text-muted);
    }}
    /* ── Hall of Fame card ──────────────────────────────────────── */
    .hof-card {{
      background: var(--surface);
      border: 1px solid rgba(212,160,23,0.28);
      border-radius: 6px;
      padding: 14px 20px;
      margin-bottom: 20px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 16px;
      transition: border-color 200ms ease, background 150ms ease, transform 150ms ease, box-shadow 150ms ease;
      will-change: transform;
    }}
    .hof-card:hover {{ border-color: var(--gold); background: var(--surface-hover); transform: translateY(-2px); box-shadow: 0 4px 16px rgba(212,160,23,0.12); }}
    [data-theme="light"] .hof-card {{ border-color: rgba(154,103,0,0.2); }}
    [data-theme="light"] .hof-card:hover {{ border-color: var(--gold); }}
    .hof-label {{
      font-size: 0.65rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.1em;
      color: var(--gold); margin-bottom: 3px;
    }}
    .hof-winner-name {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1rem; font-weight: 700;
      color: var(--text-primary);
      display: flex; align-items: center; gap: 8px;
    }}
    .hof-week-sub {{ font-size: 0.72rem; color: var(--text-muted); margin-top: 2px; }}
    .hof-pts-badge {{ margin-left: auto; display: flex; flex-direction: column; align-items: flex-end; }}
    .hof-pts-num {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1.6rem; font-weight: 700; color: var(--gold); line-height: 1;
    }}
    .hof-pts-lbl {{ font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); margin-top: 3px; }}
    .hof-see-more {{
      font-size: 0.72rem; color: var(--text-muted);
      white-space: nowrap; display: flex; align-items: center; gap: 4px; flex-shrink: 0;
    }}
    /* Hall of Fame modal */
    .hof-scroll {{ flex: 1; overflow-y: auto; }}
    .hof-week-row {{
      display: flex; align-items: flex-start; gap: 14px;
      padding: 14px 20px;
      border-bottom: 1px solid var(--border-subtle);
      transition: background 150ms ease;
    }}
    .hof-week-row:last-child {{ border-bottom: none; }}
    .hof-week-row:hover {{ background: var(--surface-hover); }}
    .hof-wk-label {{
      font-size: 0.68rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--text-muted);
      min-width: 68px; padding-top: 3px; flex-shrink: 0;
    }}
    .hof-wk-label.current {{ color: var(--accent); }}
    .hof-wk-body {{ flex: 1; min-width: 0; }}
    .hof-wk-winner {{
      display: flex; align-items: center; gap: 8px; margin-bottom: 7px;
    }}
    .hof-wk-winner-name {{
      font-family: 'Barlow Condensed', sans-serif;
      font-weight: 700; font-size: 0.95rem; color: var(--text-primary);
    }}
    .hof-wk-pts {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1rem; font-weight: 700; color: var(--gold);
      margin-left: auto; white-space: nowrap;
    }}
    .hof-wk-others {{ display: flex; flex-wrap: wrap; gap: 4px; }}
    .hof-other-pill {{
      font-size: 0.7rem; color: var(--text-muted);
      background: var(--surface-hover); border: 1px solid var(--border-subtle);
      border-radius: 4px; padding: 2px 8px; font-variant-numeric: tabular-nums;
    }}

    /* ── Betting / Bricks ────────────────────────────────────────── */
    .bricks-table {{ width: 100%; border-collapse: collapse; font-size: 0.84rem; }}
    .bricks-table th {{
      text-align: left; padding: 8px 16px;
      font-size: 0.65rem; font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.09em; color: var(--text-muted);
      border-bottom: 1px solid var(--border);
    }}
    .bricks-table th.tr {{ text-align: right; }}
    .bricks-table td {{
      padding: 11px 16px; border-bottom: 1px solid var(--border-subtle);
      vertical-align: middle; color: var(--text-secondary);
    }}
    .bricks-table tr:last-child td {{ border-bottom: none; }}
    .bricks-table tbody tr {{ transition: background 150ms ease; }}
    .bricks-table tbody tr:hover td {{ background: var(--surface-hover); }}
    .bricks-table .tr {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .bricks-bal {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1.05rem; font-weight: 700;
      color: var(--gold);
      font-variant-numeric: tabular-nums;
    }}
    .bricks-bal.zero {{ color: var(--text-muted); }}
    .bricks-rank {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1rem; font-weight: 700; color: var(--text-muted);
      min-width: 28px; display: inline-block; text-align: right;
    }}
    .bricks-rank.r1 {{ color: var(--gold); }}
    .bricks-rank.r2 {{ color: var(--silver); }}
    .bricks-rank.r3 {{ color: var(--bronze); }}
    .bricks-win  {{ color: var(--green); font-weight: 600; }}
    .bricks-loss {{ color: var(--red); }}
    .bricks-scroll {{ flex: 1; overflow-y: auto; }}
    /* Bet form */
    .bet-form {{ padding: 16px 20px; flex: 1; overflow-y: auto; }}
    .bet-field {{
      margin-bottom: 14px;
    }}
    .bet-field label {{
      display: block; font-size: 0.72rem; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--text-muted); margin-bottom: 5px;
    }}
    .bet-input, .bet-select {{
      width: 100%; padding: 8px 12px;
      background: var(--surface-hover);
      border: 1px solid var(--border);
      border-radius: 6px;
      color: var(--text-primary);
      font-family: 'Barlow', sans-serif; font-size: 0.88rem;
      transition: border-color 150ms ease;
    }}
    .bet-input:focus, .bet-select:focus,
    .filter-select:focus {{
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-dim);
      transition: border-color 150ms ease, box-shadow 150ms ease;
    }}
    .bet-row {{ display: flex; gap: 12px; }}
    .bet-row .bet-field {{ flex: 1; }}
    .odds-preview {{
      background: var(--surface-hover);
      border: 1px solid var(--border);
      border-radius: 8px; padding: 14px 18px;
      margin-top: 4px; margin-bottom: 14px;
      display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
    }}
    .odds-item {{ display: flex; flex-direction: column; align-items: center; gap: 2px; }}
    .odds-num {{
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1.5rem; font-weight: 700;
      color: var(--gold); font-variant-numeric: tabular-nums;
    }}
    .odds-lbl {{
      font-size: 0.62rem; text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--text-muted);
    }}
    .bet-submit {{
      width: 100%; padding: 11px;
      background: var(--gold); color: #0A0A0A;
      border: none; border-radius: 7px;
      font-family: 'Barlow Condensed', sans-serif;
      font-size: 1rem; font-weight: 700; letter-spacing: 0.05em;
      cursor: pointer; text-transform: uppercase;
      transition: background 200ms ease, transform 120ms ease, box-shadow 200ms ease;
      box-shadow: 0 2px 0 rgba(0,0,0,0.35), 0 4px 12px rgba(212,160,23,0.20);
      will-change: transform;
    }}
    .bet-submit:hover {{ background: color-mix(in srgb, var(--gold) 90%, white); transform: translateY(-1px); box-shadow: 0 3px 0 rgba(0,0,0,0.35), 0 6px 16px rgba(212,160,23,0.30); }}
    .bet-submit:active {{ transform: translateY(1px); box-shadow: 0 1px 0 rgba(0,0,0,0.35), 0 2px 6px rgba(212,160,23,0.15); transition-duration: 60ms; }}
    .bet-submit:disabled {{ background: var(--border); color: var(--text-muted); cursor: default; transform: none; box-shadow: none; }}
    .bet-notice {{
      font-size: 0.75rem; color: var(--text-muted);
      margin-top: 8px; text-align: center;
    }}
    .bet-tabs {{
      display: flex; border-bottom: 1px solid var(--border); padding: 0 20px;
    }}
    .bet-tab-btn {{
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
    .bet-tab-btn:hover {{ color: var(--text-primary); }}
    .bet-tab-btn.active {{ color: var(--gold); border-bottom-color: var(--gold); }}
    .bets-history-scroll {{ flex: 1; overflow-y: auto; }}
    .bet-hist-row {{
      display: flex; align-items: flex-start; gap: 12px;
      padding: 11px 20px; border-bottom: 1px solid var(--border-subtle);
      font-size: 0.82rem;
    }}
    .bet-hist-row:last-child {{ border-bottom: none; }}
    .bet-status-pill {{
      flex-shrink: 0; padding: 2px 10px; border-radius: 10px;
      font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .pill-win       {{ background: color-mix(in srgb, var(--green) 18%, transparent); color: var(--green); }}
    .pill-loss      {{ background: color-mix(in srgb, var(--red)   18%, transparent); color: var(--red); }}
    .pill-open      {{ background: color-mix(in srgb, var(--gold)  18%, transparent); color: var(--gold); }}
    .pill-cancelled {{ background: color-mix(in srgb, var(--text-muted) 18%, transparent); color: var(--text-muted); }}
    .bet-cancel-btn {{
      flex-shrink: 0; padding: 3px 10px; border-radius: 6px;
      font-size: 0.70rem; font-weight: 600; cursor: pointer;
      border: 1px solid var(--red); color: var(--red);
      background: transparent; transition: background 120ms;
    }}
    .bet-cancel-btn:hover {{ background: color-mix(in srgb, var(--red) 12%, transparent); }}
    .bet-cancel-btn:disabled {{ opacity: 0.45; cursor: default; }}
    .bet-hist-body {{ flex: 1; min-width: 0; color: var(--text-secondary); }}
    .bet-hist-desc {{ color: var(--text-primary); font-weight: 500; margin-bottom: 3px; }}
    .bet-hist-meta {{ font-size: 0.72rem; color: var(--text-muted); }}

    @media (max-width: 900px) {{
      .stats {{ grid-template-columns: repeat(3, 1fr); }}  /* already 3, no change needed */
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
        <a href="https://firstlegoleague.win" target="_blank" class="site-link">firstlegoleague.win</a>
      </div>
      <button class="chart-btn" onclick="openBricksLeaderboard()" aria-label="Bricks betting leaderboard" style="color:var(--gold);border-color:var(--gold)">
        {BRICK_ICON} Bricks
      </button>
      <button class="chart-btn" onclick="openReserve()" aria-label="Reserve an issue">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/>
          <path d="M12 8v4l3 3"/>
        </svg>
        Reserve
      </button>
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
      <div class="stat" style="--stat-color:var(--text-secondary)">
        <div class="value">{len(teams)}</div>
        <div class="label">Teams</div>
      </div>
      <div class="stat" style="--stat-color:var(--green)">
        <div class="value">{total_done}</div>
        <div class="label">Done Issues</div>
      </div>
      <div class="stat" style="--stat-color:var(--accent)">
        <div class="value">{total_sp:.1f}</div>
        <div class="label">Story Points</div>
      </div>
    </div>

    <!-- Hall of Fame card -->
    <div class="hof-card" id="hof-card" onclick="openHallOfFame()" aria-label="Hall of Fame">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
           style="width:30px;height:30px;color:var(--gold);flex-shrink:0">
        <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/>
        <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/>
        <path d="M4 22h16"/>
        <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/>
        <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/>
        <path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>
      </svg>
      <div id="hof-card-body" style="min-width:0;flex:1">
        <div class="hof-label">Hall of Fame</div>
        <div class="hof-winner-name" style="color:var(--text-muted);font-size:0.82rem">Loading&hellip;</div>
      </div>
      <div class="hof-pts-badge" id="hof-card-pts" style="display:none">
        <div class="hof-pts-num" id="hof-pts-num">—</div>
        <div class="hof-pts-lbl" id="hof-pts-lbl">pts this week</div>
      </div>
      <div class="hof-see-more">
        All weeks
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:12px;height:12px">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
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

    <div class="live-row">
      <span class="updated">Last updated: {generated_at}</span>
      <span class="live-indicator">
        <span class="live-dot"></span>
        Next update in <span id="countdown">--:--</span>
      </span>
    </div>
  </div>
  <!-- Reserve Issue modal -->
  <div id="reserve-modal" class="modal-overlay" onclick="handleReserveOverlayClick(event)">
    <div class="modal-box" style="max-width:780px">
      <div class="modal-header">
        <span class="modal-title" style="display:flex;align-items:center;gap:8px">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
               style="width:16px;height:16px;color:var(--accent)">
            <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/>
            <path d="M12 8v4l3 3"/>
          </svg>
          Reserve Issue
        </span>
        <button class="modal-close" onclick="closeReserve()" aria-label="Close">&times;</button>
      </div>
      <div class="auth-bar" id="reserve-auth-bar">
        <span class="auth-notice">Sign in to claim issues directly from here</span>
        <button class="gh-login-btn" onclick="loginWithGitHub()">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.477 2 2 6.477 2 12c0 4.418 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.009-.868-.014-1.703-2.782.603-3.369-1.342-3.369-1.342-.454-1.155-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.268 2.75 1.026A9.578 9.578 0 0 1 12 6.836a9.59 9.59 0 0 1 2.504.337c1.909-1.294 2.747-1.026 2.747-1.026.546 1.377.202 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.741 0 .267.18.578.688.48C19.138 20.163 22 16.418 22 12c0-5.523-4.477-10-10-10z"/>
          </svg>
          Sign in with GitHub
        </button>
      </div>
      <div class="reserve-filters">
        <select class="filter-select" id="filter-repo" onchange="renderIssueList()">
          <option value="">All repos</option>
        </select>
        <select class="filter-select" id="filter-sp" onchange="renderIssueList()">
          <option value="">All SP</option>
          <option value="0.25">0.25</option>
          <option value="0.5">0.5</option>
          <option value="1">1</option>
          <option value="2">2</option>
          <option value="3">3</option>
          <option value="4">4</option>
        </select>
        <label class="filter-check">
          <input type="checkbox" id="filter-unassigned" onchange="renderIssueList()">
          Unassigned only
        </label>
        <span class="filter-count" id="filter-count"></span>
      </div>
      <div class="issue-scroll" id="issue-list"></div>
    </div>
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

  <!-- Hall of Fame modal -->
  <div id="hof-modal" class="modal-overlay" onclick="handleHofOverlayClick(event)">
    <div class="modal-box" style="max-width:640px">
      <div class="modal-header">
        <span class="modal-title" style="display:flex;align-items:center;gap:8px">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
               style="width:16px;height:16px;color:var(--gold)">
            <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/>
            <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/>
            <path d="M4 22h16"/>
            <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/>
            <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/>
            <path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>
          </svg>
          Hall of Fame
        </span>
        <button class="modal-close" onclick="closeHallOfFame()" aria-label="Close">&times;</button>
      </div>
      <div class="hof-scroll" id="hof-list"></div>
    </div>
  </div>

  <!-- Bricks Leaderboard modal -->
  <div id="bricks-modal" class="modal-overlay" onclick="handleBricksOverlayClick(event)">
    <div class="modal-box" style="max-width:700px">
      <div class="modal-header">
        <span class="modal-title" style="display:flex;align-items:center;gap:8px">
          {BRICK_ICON} Bricks Leaderboard
        </span>
        <div style="display:flex;gap:8px;align-items:center">
          <button class="chart-btn" onclick="openPlaceBet()" style="color:var(--gold);border-color:var(--gold);padding:5px 10px;font-size:0.78rem">
            + Place Bet
          </button>
          <button class="modal-close" onclick="closeBricksLeaderboard()" aria-label="Close">&times;</button>
        </div>
      </div>
      <div class="bet-tabs">
        <button class="bet-tab-btn active" onclick="switchBricksTab(this,'leaderboard')">Leaderboard</button>
        <button class="bet-tab-btn" onclick="switchBricksTab(this,'my-bets')">My Bets</button>
      </div>
      <div id="bricks-leaderboard-tab" class="bricks-scroll">
        <table class="bricks-table">
          <thead><tr>
            <th style="width:40px">Pos</th>
            <th>Member</th>
            <th>Team</th>
            <th class="tr">Bricks</th>
            <th class="tr">Bets</th>
            <th class="tr">Wins</th>
            <th class="tr">Win%</th>
            <th class="tr">Net P/L</th>
          </tr></thead>
          <tbody id="bricks-tbody"></tbody>
        </table>
      </div>
      <div id="bricks-mybets-tab" class="bets-history-scroll" style="display:none">
        <div id="my-bets-list"></div>
      </div>
    </div>
  </div>

  <!-- Place Bet modal -->
  <div id="bet-modal" class="modal-overlay" onclick="handleBetOverlayClick(event)">
    <div class="modal-box" style="max-width:520px">
      <div class="modal-header">
        <span class="modal-title">Place a Bet</span>
        <button class="modal-close" onclick="closePlaceBet()" aria-label="Close">&times;</button>
      </div>
      <div class="auth-bar" id="bet-auth-bar"></div>
      <div class="bet-form" id="bet-form-body">
        <div class="bet-field">
          <label>Bet Type</label>
          <select class="bet-select" id="bet-type" onchange="updateBetForm()">
            <option value="over_under">Over / Under (score threshold)</option>
            <option value="rank">Rank Prediction</option>
            <option value="milestone">Issue Milestone</option>
            <option value="head_to_head">Head-to-Head</option>
          </select>
        </div>

        <!-- over_under fields -->
        <div id="bf-over-under">
          <div class="bet-row">
            <div class="bet-field">
              <label>Subject Team</label>
              <select class="bet-select" id="bet-ou-team" onchange="updateOddsPreview()"></select>
            </div>
            <div class="bet-field">
              <label>Metric</label>
              <select class="bet-select" id="bet-ou-metric" onchange="updateOddsPreview()">
                <option value="total">Total Score</option>
                <option value="implementation">Implementation Pts</option>
                <option value="creation">Creation Pts</option>
                <option value="issues_implemented">Issues Done</option>
                <option value="issues_created">Issues Created</option>
              </select>
            </div>
          </div>
          <div class="bet-row">
            <div class="bet-field">
              <label>Direction</label>
              <select class="bet-select" id="bet-ou-dir" onchange="updateOddsPreview()">
                <option value="over">Over</option>
                <option value="under">Under</option>
              </select>
            </div>
            <div class="bet-field">
              <label>Threshold</label>
              <input type="number" class="bet-input" id="bet-ou-thresh" step="0.25" min="0" value="15" oninput="updateOddsPreview()">
            </div>
          </div>
        </div>

        <!-- rank fields -->
        <div id="bf-rank" style="display:none">
          <div class="bet-row">
            <div class="bet-field">
              <label>Subject Team</label>
              <select class="bet-select" id="bet-rk-team" onchange="updateOddsPreview()"></select>
            </div>
            <div class="bet-field">
              <label>Target Rank</label>
              <input type="number" class="bet-input" id="bet-rk-rank" min="1" value="1" oninput="updateOddsPreview()">
            </div>
          </div>
          <div class="bet-field">
            <label>Direction</label>
            <select class="bet-select" id="bet-rk-dir" onchange="updateOddsPreview()">
              <option value="at_or_better">At or Better</option>
              <option value="at_or_worse">At or Worse</option>
            </select>
          </div>
        </div>

        <!-- milestone fields -->
        <div id="bf-milestone" style="display:none">
          <div class="bet-row">
            <div class="bet-field">
              <label>Subject Team</label>
              <select class="bet-select" id="bet-ms-team" onchange="updateOddsPreview()"></select>
            </div>
            <div class="bet-field">
              <label>Metric</label>
              <select class="bet-select" id="bet-ms-metric" onchange="updateOddsPreview()">
                <option value="issues_created">Issues Created</option>
                <option value="issues_implemented">Issues Implemented</option>
              </select>
            </div>
          </div>
          <div class="bet-field">
            <label>Target Count</label>
            <input type="number" class="bet-input" id="bet-ms-target" min="1" value="10" oninput="updateOddsPreview()">
          </div>
        </div>

        <!-- head_to_head fields -->
        <div id="bf-h2h" style="display:none">
          <div class="bet-row">
            <div class="bet-field">
              <label>Team A</label>
              <select class="bet-select" id="bet-h2h-a" onchange="updateOddsPreview()"></select>
            </div>
            <div class="bet-field">
              <label>Team B</label>
              <select class="bet-select" id="bet-h2h-b" onchange="updateOddsPreview()"></select>
            </div>
          </div>
          <div class="bet-row">
            <div class="bet-field">
              <label>I Pick</label>
              <select class="bet-select" id="bet-h2h-pick">
                <option value="team_a">Team A wins</option>
                <option value="team_b">Team B wins</option>
              </select>
            </div>
            <div class="bet-field">
              <label>Metric</label>
              <select class="bet-select" id="bet-h2h-metric" onchange="updateOddsPreview()">
                <option value="total">Total Score</option>
                <option value="implementation">Implementation Pts</option>
              </select>
            </div>
          </div>
        </div>

        <div class="bet-field">
          <label>Deadline</label>
          <input type="date" class="bet-input" id="bet-deadline">
        </div>

        <div class="odds-preview" id="odds-preview">
          <div class="odds-item">
            <span class="odds-num" id="op-odds">—</span>
            <span class="odds-lbl">Odds</span>
          </div>
          <div class="odds-item">
            <span class="odds-num" id="op-payout">—</span>
            <span class="odds-lbl">Potential payout</span>
          </div>
          <div class="odds-item">
            <span class="odds-num" id="op-balance">—</span>
            <span class="odds-lbl">Your Bricks</span>
          </div>
        </div>

        <div class="bet-field">
          <label>Stake (Bricks)</label>
          <input type="number" class="bet-input" id="bet-stake" min="1" value="10" oninput="updateOddsPreview()">
        </div>

        <button class="bet-submit" id="bet-submit-btn" onclick="submitBet()" disabled>Sign in to place bet</button>
        <div class="bet-notice" id="bet-notice"></div>
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
    const ISSUES        = {issues_detail_json};
    const TEAMS         = {team_names_json};
    const MEMBERS       = {team_members_json};
    const COLORS        = {team_colors_json};
    const OPEN_ISSUES   = {open_issues_json};
    const ORG           = "UdL-EPS-SoftArch-Igualada";
    const CLIENT_ID     = {oauth_client_id};
    const WORKER_URL        = {oauth_worker_url};
    const CANCEL_WORKER_URL = {cancel_worker_url};
    // Betting data
    const MEMBER_BRICKS  = {member_bricks_json};
    const ACTIVE_BETS    = {active_bets_json};
    const RESOLVED_BETS  = {resolved_bets_json};
    const TEAM_SCORES    = {team_scores_json};
    const SCOREBOARD_OWNER = "{SCOREBOARD_OWNER}";
    const SCOREBOARD_REPO  = "{SCOREBOARD_REPO}";
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
      if (e.key === 'Escape') {{ closeChart(); closeTeamModal(); closeHallOfFame(); closeBricksLeaderboard(); closePlaceBet(); }}
    }});

    // ── Hall of Fame ──────────────────────────────────────────────────────────
    function computeHallOfFame() {{
      var weeks = {{}};
      ISSUES.forEach(function(e) {{
        if (!e.date) return;
        var wk = periodKey(e.date, 'week');
        if (!weeks[wk]) weeks[wk] = {{}};
        if (!weeks[wk][e.impl_team]) weeks[wk][e.impl_team] = 0;
        weeks[wk][e.impl_team] += e.score;
      }});
      return Object.keys(weeks).sort().reverse().map(function(wk) {{
        var entries = Object.entries(weeks[wk]).sort(function(a, b) {{ return b[1] - a[1]; }});
        return {{ week: wk, winner: entries[0][0], score: entries[0][1], all: entries }};
      }});
    }}

    function currentISOWeek() {{
      var now = new Date();
      var day = now.getUTCDay() || 7;
      var mon = new Date(now);
      mon.setUTCDate(now.getUTCDate() - day + 1);
      return mon.toISOString().slice(0, 10);
    }}

    function hofAvatars(teamName, size, overlap) {{
      return (MEMBERS[teamName] || []).slice(0, 2).map(function(m) {{
        return '<img src="https://github.com/' + m + '.png?size=56" width="' + size + '" height="' + size + '" ' +
               'alt="' + m + '" style="border-radius:50%;border:1.5px solid var(--border);margin-right:' + (-overlap) + 'px">';
      }}).join('');
    }}

    function renderHofCard() {{
      var hof = computeHallOfFame();
      if (!hof.length) return;
      var top = hof[0];
      var isCurrent = top.week === currentISOWeek();
      var weekLbl  = isCurrent ? 'This Week' : fmtLabel(top.week, 'week');
      var sub      = isCurrent ? 'Leading this week' : 'Best week so far';
      document.getElementById('hof-card-body').innerHTML =
        '<div class="hof-label">Hall of Fame &mdash; ' + weekLbl + '</div>' +
        '<div class="hof-winner-name">' +
          '<span style="display:flex;gap:2px">' + hofAvatars(top.winner, 24, 6) + '</span>' +
          '<span style="margin-left:8px">' + top.winner + '</span>' +
        '</div>' +
        '<div class="hof-week-sub">' + sub + '</div>';
      document.getElementById('hof-pts-num').textContent = top.score.toFixed(2);
      document.getElementById('hof-pts-lbl').textContent = isCurrent ? 'pts this week' : 'pts that week';
      document.getElementById('hof-card-pts').style.display = '';
    }}

    function openHallOfFame() {{
      var hof = computeHallOfFame();
      var thisWeek = currentISOWeek();
      var list = document.getElementById('hof-list');
      if (!hof.length) {{
        list.innerHTML = '<p class="no-issues">No data yet.</p>';
      }} else {{
        list.innerHTML = hof.map(function(entry, idx) {{
          var isCurrent = entry.week === thisWeek;
          var avatars = hofAvatars(entry.winner, 22, 5);
          var others  = entry.all.slice(1).map(function(e) {{
            return '<span class="hof-other-pill">' + e[0] + ' &middot; ' + e[1].toFixed(2) + ' pts</span>';
          }}).join('');
          return '<div class="hof-week-row">' +
            '<div class="hof-wk-label' + (isCurrent ? ' current' : '') + '">' +
              (isCurrent ? 'This week' : fmtLabel(entry.week, 'week')) +
            '</div>' +
            '<div class="hof-wk-body">' +
              '<div class="hof-wk-winner">' +
                '<span style="display:flex;gap:3px">' + avatars + '</span>' +
                '<span class="hof-wk-winner-name">' + entry.winner + '</span>' +
                '<span class="hof-wk-pts">' + entry.score.toFixed(2) + ' pts</span>' +
              '</div>' +
              (others ? '<div class="hof-wk-others">' + others + '</div>' : '') +
            '</div>' +
          '</div>';
        }}).join('');
      }}
      document.getElementById('hof-modal').classList.add('open');
      document.body.style.overflow = 'hidden';
    }}

    function closeHallOfFame() {{
      document.getElementById('hof-modal').classList.remove('open');
      document.body.style.overflow = '';
    }}

    function handleHofOverlayClick(e) {{
      if (e.target === document.getElementById('hof-modal')) closeHallOfFame();
    }}

    renderHofCard();

    // ── Reserve Issue ─────────────────────────────────────────────────────────
    var _claimedSet = new Set(); // issues claimed in this session

    function getGhUser()  {{ return JSON.parse(localStorage.getItem('gh_user')  || 'null'); }}
    function getGhToken() {{ return localStorage.getItem('gh_token') || ''; }}

    function updateAuthBar() {{
      var bar  = document.getElementById('reserve-auth-bar');
      var user = getGhUser();
      if (user) {{
        bar.innerHTML =
          '<div class="user-pill">' +
            '<img src="' + user.avatar_url + '" alt="' + user.login + '">' +
            '<span>Signed in as <strong>' + user.login + '</strong></span>' +
          '</div>' +
          '<button class="logout-btn" onclick="logoutGitHub()">Sign out</button>';
      }} else {{
        bar.innerHTML =
          '<span class="auth-notice">Sign in to claim issues directly from here</span>' +
          '<button class="gh-login-btn" onclick="loginWithGitHub()">' +
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" style="width:16px;height:16px">' +
              '<path d="M12 2C6.477 2 2 6.477 2 12c0 4.418 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.009-.868-.014-1.703-2.782.603-3.369-1.342-3.369-1.342-.454-1.155-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.268 2.75 1.026A9.578 9.578 0 0 1 12 6.836a9.59 9.59 0 0 1 2.504.337c1.909-1.294 2.747-1.026 2.747-1.026.546 1.377.202 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.741 0 .267.18.578.688.48C19.138 20.163 22 16.418 22 12c0-5.523-4.477-10-10-10z"/>' +
            '</svg>' +
            'Sign in with GitHub' +
          '</button>';
      }}
    }}

    function loginWithGitHub() {{
      if (!CLIENT_ID) {{
        alert('OAuth not configured yet. Set OAUTH_CLIENT_ID in GitHub Actions secrets.');
        return;
      }}
      var state = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
      localStorage.setItem('oauth_state', state);
      localStorage.setItem('oauth_return', 'reserve'); // reopen modal on return
      window.location.href = 'https://github.com/login/oauth/authorize' +
        '?client_id=' + CLIENT_ID +
        '&scope=public_repo' +
        '&state=' + state;
    }}

    function logoutGitHub() {{
      localStorage.removeItem('gh_token');
      localStorage.removeItem('gh_user');
      updateAuthBar();
      renderIssueList();
    }}

    async function exchangeOAuthCode(code) {{
      if (!WORKER_URL) return null;
      try {{
        var r = await fetch(WORKER_URL, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ code }})
        }});
        return await r.json();
      }} catch(e) {{ return null; }}
    }}

    async function handleOAuthCallback() {{
      var params = new URLSearchParams(window.location.search);
      var code  = params.get('code');
      var state = params.get('state');
      if (!code) return;
      if (state !== localStorage.getItem('oauth_state')) return;
      // Clean URL immediately
      window.history.replaceState({{}}, '', window.location.pathname);
      var data = await exchangeOAuthCode(code);
      if (data && data.access_token) {{
        localStorage.setItem('gh_token', data.access_token);
        try {{
          var userResp = await fetch('https://api.github.com/user', {{
            headers: {{ 'Authorization': 'token ' + data.access_token }}
          }});
          var user = await userResp.json();
          localStorage.setItem('gh_user', JSON.stringify(user));
        }} catch(e) {{}}
      }}
      // Reopen correct modal based on where login was triggered
      var ret = localStorage.getItem('oauth_return');
      localStorage.removeItem('oauth_return');
      if (ret === 'reserve') openReserve();
      else if (ret === 'bets') openPlaceBet();
    }}

    function openReserve() {{
      populateRepoFilter();
      updateAuthBar();
      renderIssueList();
      document.getElementById('reserve-modal').classList.add('open');
      document.body.style.overflow = 'hidden';
    }}

    function closeReserve() {{
      document.getElementById('reserve-modal').classList.remove('open');
      document.body.style.overflow = '';
    }}

    function handleReserveOverlayClick(e) {{
      if (e.target === document.getElementById('reserve-modal')) closeReserve();
    }}

    function populateRepoFilter() {{
      var repos = [...new Set(OPEN_ISSUES.map(i => i.repo).filter(Boolean))].sort();
      var sel = document.getElementById('filter-repo');
      var cur = sel.value;
      sel.innerHTML = '<option value="">All repos</option>' +
        repos.map(r => '<option value="' + r + '"' + (r === cur ? ' selected' : '') + '>' + r + '</option>').join('');
    }}

    function filteredIssues() {{
      var repo       = document.getElementById('filter-repo').value;
      var sp         = parseFloat(document.getElementById('filter-sp').value) || 0;
      var unassigned = document.getElementById('filter-unassigned').checked;
      return OPEN_ISSUES.filter(function(i) {{
        if (repo && i.repo !== repo) return false;
        if (sp && i.sp !== sp) return false;
        if (unassigned && i.assignees.length > 0) return false;
        return true;
      }});
    }}

    function renderIssueList() {{
      var issues = filteredIssues();
      var user   = getGhUser();
      var token  = getGhToken();
      document.getElementById('filter-count').textContent = issues.length + ' issue' + (issues.length !== 1 ? 's' : '');
      var el = document.getElementById('issue-list');
      if (!issues.length) {{
        el.innerHTML = '<div class="reserve-empty">No issues match the current filters.</div>';
        return;
      }}
      el.innerHTML = issues.map(function(issue) {{
        var statusClass = issue.status.toLowerCase().includes('progress') ? 'chip-progress'
                        : issue.status.toLowerCase().includes('todo') ? 'chip-todo' : '';
        var assigneeImgs = issue.assignees.map(function(a) {{
          return '<img src="https://github.com/' + a + '.png?size=40" title="' + a + '" alt="' + a + '">';
        }}).join('');
        var isClaimed = _claimedSet.has(issue.repo + '#' + issue.number);
        var isAssignedToMe = user && issue.assignees.map(function(a){{return a.toLowerCase();}}).includes(user.login.toLowerCase());
        var btnDisabled = !token ? '' : (isClaimed || isAssignedToMe ? ' disabled' : '');
        var btnClass    = isClaimed || isAssignedToMe ? ' claimed' : '';
        var btnText     = isClaimed ? '&#x2713; Requested' : isAssignedToMe ? 'Already yours' : 'Request';
        var issueUrl    = 'https://github.com/' + ORG + '/' + (issue.repo || '_') + '/issues/' + issue.number;
        return '<div class="issue-row" id="irow-' + issue.repo + '-' + issue.number + '">' +
          '<span class="issue-num">#' + issue.number + '</span>' +
          '<div class="issue-title">' +
            '<a href="' + issueUrl + '" target="_blank">' + issue.title + '</a>' +
            '<div class="issue-meta">' +
              (issue.repo ? '<span class="chip">' + issue.repo + '</span>' : '') +
              '<span class="chip chip-sp">' + issue.sp + ' SP</span>' +
              (issue.status ? '<span class="chip ' + statusClass + '">' + issue.status + '</span>' : '') +
            '</div>' +
          '</div>' +
          (assigneeImgs ? '<div class="issue-assignees">' + assigneeImgs + '</div>' : '') +
          (token
            ? '<button class="claim-btn' + btnClass + '"' + btnDisabled +
              ' onclick="claimIssue(&#39;' + issue.repo + '&#39;,' + issue.number + ',this)">'+btnText+'</button>'
            : '<button class="claim-btn" onclick="loginWithGitHub()">Sign in</button>'
          ) +
        '</div>';
      }}).join('');
    }}

    async function claimIssue(repo, number, btn) {{
      var token = getGhToken();
      var user  = getGhUser();
      if (!token || !user) {{ loginWithGitHub(); return; }}
      btn.disabled = true;
      btn.textContent = 'Sending\u2026';
      try {{
        // Post a comment claiming the issue (assigning requires write access the user may not have)
        var r = await fetch('https://api.github.com/repos/' + ORG + '/' + repo + '/issues/' + number + '/comments', {{
          method: 'POST',
          headers: {{ 'Authorization': 'token ' + token, 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ body: 'request' }})
        }});
        if (!r.ok) throw new Error('comment failed: ' + r.status);
        _claimedSet.add(repo + '#' + number);
        btn.textContent = '\u2713 Requested';
        btn.classList.add('claimed');
      }} catch(err) {{
        btn.disabled = false;
        btn.textContent = 'Retry';
        console.error(err);
      }}
    }}

    // ── Bricks / Betting ─────────────────────────────────────────────────────

    // Build per-member stats from resolved bets
    function buildMemberStats() {{
      var stats = {{}};
      Object.keys(MEMBER_BRICKS).forEach(function(m) {{
        stats[m] = {{ balance: MEMBER_BRICKS[m], bets: 0, wins: 0, net: 0 }};
      }});
      RESOLVED_BETS.forEach(function(b) {{
        var s = stats[b.placed_by];
        if (!s) return;
        s.bets++;
        s.net -= b.stake;
        if (b.won) {{ s.wins++; s.net += b.payout; }}
      }});
      ACTIVE_BETS.forEach(function(b) {{
        var s = stats[b.placed_by];
        if (!s) return;
        s.bets++;
      }});
      return stats;
    }}

    // Find team name for a member
    function memberTeam(member) {{
      return TEAMS.find(function(t) {{
        return (MEMBERS[t] || []).some(function(m) {{ return m.toLowerCase() === member.toLowerCase(); }});
      }}) || '—';
    }}

    var _bricksTab = 'leaderboard';

    function openBricksLeaderboard() {{
      _bricksTab = 'leaderboard';
      document.querySelectorAll('#bricks-modal .bet-tab-btn').forEach(function(b, i) {{
        b.classList.toggle('active', i === 0);
      }});
      renderBricksLeaderboard();
      document.getElementById('bricks-leaderboard-tab').style.display = '';
      document.getElementById('bricks-mybets-tab').style.display = 'none';
      document.getElementById('bricks-modal').classList.add('open');
      document.body.style.overflow = 'hidden';
    }}

    function closeBricksLeaderboard() {{
      document.getElementById('bricks-modal').classList.remove('open');
      document.body.style.overflow = '';
    }}

    function handleBricksOverlayClick(e) {{
      if (e.target === document.getElementById('bricks-modal')) closeBricksLeaderboard();
    }}

    function switchBricksTab(btn, tab) {{
      _bricksTab = tab;
      document.querySelectorAll('#bricks-modal .bet-tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
      if (tab === 'leaderboard') {{
        document.getElementById('bricks-leaderboard-tab').style.display = '';
        document.getElementById('bricks-mybets-tab').style.display = 'none';
        renderBricksLeaderboard();
      }} else {{
        document.getElementById('bricks-leaderboard-tab').style.display = 'none';
        document.getElementById('bricks-mybets-tab').style.display = '';
        renderMyBets();
      }}
    }}

    function renderBricksLeaderboard() {{
      var stats  = buildMemberStats();
      var sorted = Object.keys(stats).sort(function(a, b) {{ return stats[b].balance - stats[a].balance; }});
      var medals = ['\U0001f947','\U0001f948','\U0001f949'];
      var tbody = document.getElementById('bricks-tbody');
      tbody.innerHTML = sorted.map(function(member, idx) {{
        var s     = stats[member];
        var rank  = idx + 1;
        var rkCls = rank === 1 ? 'r1' : rank === 2 ? 'r2' : rank === 3 ? 'r3' : '';
        var team  = memberTeam(member);
        var winPct = s.bets > 0 ? Math.round(s.wins / s.bets * 100) : 0;
        var netStr = (s.net >= 0 ? '+' : '') + s.net.toFixed(2);
        var netCls = s.net > 0 ? 'bricks-win' : s.net < 0 ? 'bricks-loss' : '';
        return '<tr>' +
          '<td><span class="bricks-rank ' + rkCls + '">' + (medals[idx] || rank) + '</span></td>' +
          '<td><span style="display:flex;align-items:center;gap:8px">' +
            '<img src="https://github.com/' + member + '.png?size=40" width="24" height="24" style="border-radius:50%;border:1px solid var(--border)">' +
            '<a href="https://github.com/' + member + '" target="_blank" style="color:var(--text-primary);text-decoration:none;font-weight:500">' + member + '</a>' +
          '</span></td>' +
          '<td style="color:var(--text-muted);font-size:0.78rem">' + team + '</td>' +
          '<td class="tr"><span class="bricks-bal' + (s.balance === 0 ? ' zero' : '') + '">' + s.balance.toFixed(2) + ' BRK</span></td>' +
          '<td class="tr">' + s.bets + '</td>' +
          '<td class="tr">' + s.wins + '</td>' +
          '<td class="tr">' + (s.bets > 0 ? winPct + '%' : '—') + '</td>' +
          '<td class="tr ' + netCls + '">' + (s.bets > 0 ? netStr : '—') + '</td>' +
        '</tr>';
      }}).join('');
    }}

    function betDescription(bet) {{
      var p = bet.params || {{}};
      if (bet.bet_type === 'over_under') {{
        return (p.subject_team || '?') + ' ' + (p.metric || 'total') + ' ' + (p.direction || '') + ' ' + (p.threshold || '');
      }}
      if (bet.bet_type === 'rank') {{
        return (p.subject_team || '?') + ' ' + (p.direction === 'at_or_better' ? '≤' : '≥') + ' rank ' + (p.target_rank || '?');
      }}
      if (bet.bet_type === 'milestone') {{
        return (p.subject_team || '?') + ' ' + (p.metric || '') + ' ≥ ' + (p.target || '');
      }}
      if (bet.bet_type === 'head_to_head') {{
        return (p.pick === 'team_a' ? p.team_a : p.team_b) + ' beats ' + (p.pick === 'team_a' ? p.team_b : p.team_a);
      }}
      return bet.bet_type;
    }}

    function renderMyBets() {{
      var user = getGhUser();
      var el   = document.getElementById('my-bets-list');
      var mine = [];
      if (user) {{
        ACTIVE_BETS.forEach(function(b)   {{ if (b.placed_by === user.login) mine.push({{...b, status:'open'}}); }});
        RESOLVED_BETS.forEach(function(b) {{ if (b.placed_by === user.login) mine.push({{...b, status: b.won ? 'win' : 'loss'}}); }});
      }}
      if (!user) {{
        el.innerHTML = '<div class="reserve-empty">Sign in to see your bets.</div>';
        return;
      }}
      if (!mine.length) {{
        el.innerHTML = '<div class="reserve-empty">You have no bets yet. Place your first bet!</div>';
        return;
      }}
      mine.sort(function(a, b) {{ return (b.placed_at || '').localeCompare(a.placed_at || ''); }});
      el.innerHTML = mine.map(function(b) {{
        var isCancelled = !!b.cancelled;
        var pillCls = isCancelled ? 'pill-cancelled'
                    : b.status === 'open' ? 'pill-open'
                    : b.status === 'win'  ? 'pill-win' : 'pill-loss';
        var pillTxt = isCancelled ? 'Cancelled'
                    : b.status === 'open' ? 'Open'
                    : b.status === 'win'  ? 'Win' : 'Loss';
        var payoutStr = isCancelled         ? '\u21a9 ' + b.stake.toFixed(2) + ' BRK refunded'
                      : b.status === 'win'  ? '+' + b.payout.toFixed(2) + ' BRK'
                      : b.status === 'open' ? 'Potential: ' + b.potential_payout.toFixed(2) + ' BRK'
                      :                       '-' + b.stake.toFixed(2) + ' BRK';

        // Cancel button: only for open bets >1h before deadline
        var cancelBtn = '';
        if (b.status === 'open' && !isCancelled && b.issue_url) {{
          var closeTime = new Date((b.deadline || '2099-01-01') + 'T23:00:00Z');
          if (new Date() < closeTime) {{
            var btnId = 'cxl-' + b.issue_number;
            cancelBtn = '<button class="bet-cancel-btn" id="' + btnId + '" ' +
              'onclick="cancelBet(' + b.issue_number + ',&#39;' + b.issue_url + '&#39;,this)">Cancel</button>';
          }}
        }}

        return '<div class="bet-hist-row">' +
          '<span class="bet-status-pill ' + pillCls + '">' + pillTxt + '</span>' +
          '<div class="bet-hist-body">' +
            '<div class="bet-hist-desc">' + betDescription(b) + '</div>' +
            '<div class="bet-hist-meta">' +
              'Stake: ' + b.stake.toFixed(2) + ' BRK &middot; ' +
              'Odds: ' + b.odds.toFixed(2) + 'x &middot; ' +
              '<span style="color:var(--gold)">Closes: ' + (b.deadline || '?') + '</span>' +
              ' &middot; ' + payoutStr +
            '</div>' +
          '</div>' +
          cancelBtn +
          (b.issue_url ? '<a href="' + b.issue_url + '" target="_blank" style="font-size:0.72rem;color:var(--text-muted);text-decoration:none;flex-shrink:0">#' + b.issue_number + '</a>' : '') +
        '</div>';
      }}).join('');
    }}

    // ── Cancel Bet ───────────────────────────────────────────────────────────

    async function cancelBet(issueNumber, issueUrl, btn) {{
      var user  = getGhUser();
      var token = getGhToken();
      if (!user || !token) return;
      if (!confirm('Cancel this bet? Your stake will be refunded instantly.')) return;
      btn.disabled = true;
      btn.textContent = 'Cancelling\u2026';
      try {{
        if (!CANCEL_WORKER_URL) throw new Error('Cancel worker not configured');
        var r = await fetch(CANCEL_WORKER_URL, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ token: token, issue_number: issueNumber }})
        }});
        var data = await r.json();
        if (!r.ok) throw new Error(data.error || r.status);
        btn.textContent = '\u21a9 Cancelled';
        btn.style.borderColor = 'var(--green)';
        btn.style.color = 'var(--green)';
        // Update displayed balance instantly
        if (typeof data.new_balance === 'number') {{
          MEMBER_BRICKS[user.login] = data.new_balance;
          updateBetAuthBar();
        }}
        // Mark bet as cancelled in local data so re-renders reflect it
        ACTIVE_BETS.forEach(function(b) {{
          if (b.issue_number === issueNumber) {{ b._pendingCancel = true; }}
        }});
      }} catch(err) {{
        btn.disabled = false;
        btn.textContent = 'Retry';
        console.error(err);
        alert('Could not cancel: ' + err.message);
      }}
    }}

    // ── Place Bet modal ───────────────────────────────────────────────────────

    function openPlaceBet() {{
      // Populate team selects
      var opts = TEAMS.map(function(t) {{ return '<option value="' + t + '">' + t + '</option>'; }}).join('');
      ['bet-ou-team','bet-rk-team','bet-ms-team','bet-h2h-a','bet-h2h-b'].forEach(function(id) {{
        var el = document.getElementById(id);
        if (el) el.innerHTML = opts;
      }});
      // Set default deadline to 1 week from now
      var dl = new Date(); dl.setDate(dl.getDate() + 7);
      document.getElementById('bet-deadline').value = dl.toISOString().slice(0,10);
      updateBetForm();
      updateBetAuthBar();
      document.getElementById('bet-modal').classList.add('open');
      document.body.style.overflow = 'hidden';
    }}

    function closePlaceBet() {{
      document.getElementById('bet-modal').classList.remove('open');
      document.body.style.overflow = '';
    }}

    function handleBetOverlayClick(e) {{
      if (e.target === document.getElementById('bet-modal')) closePlaceBet();
    }}

    function updateBetAuthBar() {{
      var bar  = document.getElementById('bet-auth-bar');
      var user = getGhUser();
      if (user) {{
        var bal = (MEMBER_BRICKS[user.login] || 0);
        // Also subtract pending active bets
        ACTIVE_BETS.forEach(function(b) {{ if (b.placed_by === user.login) bal -= b.stake; }});
        bar.innerHTML =
          '<div class="user-pill">' +
            '<img src="' + user.avatar_url + '" alt="' + user.login + '">' +
            '<span>Signed in as <strong>' + user.login + '</strong></span>' +
          '</div>' +
          '<span style="margin-left:auto;font-size:0.82rem;color:var(--gold);font-weight:600">' + (MEMBER_BRICKS[user.login] || 0).toFixed(2) + ' BRK</span>';
        document.getElementById('bet-submit-btn').disabled = false;
        document.getElementById('bet-submit-btn').textContent = 'Place Bet';
      }} else {{
        bar.innerHTML =
          '<span class="auth-notice">Sign in to place bets</span>' +
          '<button class="gh-login-btn" onclick="loginForBets()" style="margin-left:auto">' +
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" style="width:16px;height:16px">' +
              '<path d="M12 2C6.477 2 2 6.477 2 12c0 4.418 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.009-.868-.014-1.703-2.782.603-3.369-1.342-3.369-1.342-.454-1.155-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.268 2.75 1.026A9.578 9.578 0 0 1 12 6.836a9.59 9.59 0 0 1 2.504.337c1.909-1.294 2.747-1.026 2.747-1.026.546 1.377.202 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.741 0 .267.18.578.688.48C19.138 20.163 22 16.418 22 12c0-5.523-4.477-10-10-10z"/>' +
            '</svg>' +
            'Sign in with GitHub' +
          '</button>';
        document.getElementById('bet-submit-btn').disabled = true;
        document.getElementById('bet-submit-btn').textContent = 'Sign in to place bet';
      }}
      updateOddsPreview();
    }}

    function loginForBets() {{
      if (!CLIENT_ID) {{ alert('OAuth not configured.'); return; }}
      var state = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
      localStorage.setItem('oauth_state', state);
      localStorage.setItem('oauth_return', 'bets');
      window.location.href = 'https://github.com/login/oauth/authorize?client_id=' + CLIENT_ID + '&scope=public_repo&state=' + state;
    }}

    function updateBetForm() {{
      var type = document.getElementById('bet-type').value;
      document.getElementById('bf-over-under').style.display = type === 'over_under' ? '' : 'none';
      document.getElementById('bf-rank').style.display       = type === 'rank'       ? '' : 'none';
      document.getElementById('bf-milestone').style.display  = type === 'milestone'  ? '' : 'none';
      document.getElementById('bf-h2h').style.display        = type === 'head_to_head' ? '' : 'none';
      updateOddsPreview();
    }}

    function calcOdds(betType, params) {{
      var HOUSE_EDGE = 0.10;
      var K_SCORE    = 5.0;
      var K_RANK     = 4.0;
      var p = 0.5;

      function sigmoid(x) {{ return 1 / (1 + Math.exp(-Math.max(-500, Math.min(500, x)))); }}

      if (betType === 'over_under') {{
        var ts = TEAM_SCORES[params.subject_team];
        if (!ts) return 2.0;
        var current   = ts[params.metric] || 0;
        var threshold = parseFloat(params.threshold) || 1;
        var ratio     = threshold > 0 ? current / threshold : 1;
        var pOver     = sigmoid(K_SCORE * (ratio - 1));
        p = params.direction === 'over' ? pOver : (1 - pOver);
      }}

      else if (betType === 'rank') {{
        var ts = TEAM_SCORES[params.subject_team];
        if (!ts) return 2.0;
        var cur = ts.rank || TEAMS.length;
        var tgt = parseInt(params.target_rank) || 1;
        var gap = params.direction === 'at_or_better' ? cur - tgt : tgt - cur;
        p = sigmoid(-K_RANK * gap / Math.max(TEAMS.length, 1));
      }}

      else if (betType === 'milestone') {{
        var ts = TEAM_SCORES[params.subject_team];
        if (!ts) return 2.0;
        var current = ts[params.metric] || 0;
        var target  = parseInt(params.target) || 1;
        var ratio   = target > 0 ? current / target : 1;
        p = sigmoid(K_SCORE * (ratio - 1));
      }}

      else if (betType === 'head_to_head') {{
        var tsA = TEAM_SCORES[params.team_a];
        var tsB = TEAM_SCORES[params.team_b];
        if (!tsA || !tsB) return 2.0;
        var key = params.metric || 'total';
        var scA = tsA[key] || 0;
        var scB = tsB[key] || 0;
        var total = scA + scB;
        var pA = total > 0 ? scA / total : 0.5;
        p = params.pick === 'team_a' ? pA : (1 - pA);
      }}

      p = Math.max(0.05, Math.min(0.95, p));
      var raw = (1 / p) * (1 - HOUSE_EDGE);
      return Math.round(Math.max(1.05, Math.min(9.0, raw)) * 100) / 100;
    }}

    function currentBetParams() {{
      var type = document.getElementById('bet-type').value;
      if (type === 'over_under') {{
        return {{
          subject_team: document.getElementById('bet-ou-team').value,
          metric:       document.getElementById('bet-ou-metric').value,
          direction:    document.getElementById('bet-ou-dir').value,
          threshold:    parseFloat(document.getElementById('bet-ou-thresh').value) || 0,
        }};
      }}
      if (type === 'rank') {{
        return {{
          subject_team: document.getElementById('bet-rk-team').value,
          target_rank:  parseInt(document.getElementById('bet-rk-rank').value) || 1,
          direction:    document.getElementById('bet-rk-dir').value,
        }};
      }}
      if (type === 'milestone') {{
        return {{
          subject_team: document.getElementById('bet-ms-team').value,
          metric:       document.getElementById('bet-ms-metric').value,
          target:       parseInt(document.getElementById('bet-ms-target').value) || 1,
        }};
      }}
      if (type === 'head_to_head') {{
        return {{
          team_a:  document.getElementById('bet-h2h-a').value,
          team_b:  document.getElementById('bet-h2h-b').value,
          pick:    document.getElementById('bet-h2h-pick').value,
          metric:  document.getElementById('bet-h2h-metric').value,
        }};
      }}
      return {{}};
    }}

    function updateOddsPreview() {{
      var type   = document.getElementById('bet-type').value;
      var params = currentBetParams();
      var odds   = calcOdds(type, params);
      var stake  = parseFloat(document.getElementById('bet-stake').value) || 0;
      var payout = Math.round(stake * odds * 100) / 100;
      document.getElementById('op-odds').textContent   = odds.toFixed(2) + 'x';
      document.getElementById('op-payout').textContent = payout.toFixed(2) + ' BRK';
      var user = getGhUser();
      var bal  = user ? (MEMBER_BRICKS[user.login] || 0) : 0;
      document.getElementById('op-balance').textContent = user ? bal.toFixed(2) + ' BRK' : '—';
    }}

    async function submitBet() {{
      var user  = getGhUser();
      var token = getGhToken();
      if (!user || !token) {{ loginForBets(); return; }}

      var type   = document.getElementById('bet-type').value;
      var params = currentBetParams();
      var odds   = calcOdds(type, params);
      var stake  = parseFloat(document.getElementById('bet-stake').value) || 0;
      var deadline = document.getElementById('bet-deadline').value;

      if (stake <= 0) {{ document.getElementById('bet-notice').textContent = 'Stake must be > 0.'; return; }}
      var bal = MEMBER_BRICKS[user.login] || 0;
      if (stake > bal) {{ document.getElementById('bet-notice').textContent = 'Insufficient Bricks (' + bal.toFixed(2) + ' available).'; return; }}
      if (!deadline) {{ document.getElementById('bet-notice').textContent = 'Set a deadline.'; return; }}

      // Deadline must be at least tomorrow
      var today = new Date(); today.setHours(0,0,0,0);
      var dlDate = new Date(deadline + 'T00:00:00');
      if (dlDate <= today) {{ document.getElementById('bet-notice').textContent = 'Deadline must be at least tomorrow.'; return; }}

      // Validate head_to_head: team_a != team_b
      if (type === 'head_to_head' && params.team_a === params.team_b) {{
        document.getElementById('bet-notice').textContent = 'Team A and Team B must be different.';
        return;
      }}

      // Cannot bet on your own team
      var myLogin = user.login.toLowerCase();
      var subjectTeams = [];
      if (type === 'head_to_head') {{
        subjectTeams = [params.team_a, params.team_b];
      }} else {{
        subjectTeams = [params.subject_team];
      }}
      for (var si = 0; si < subjectTeams.length; si++) {{
        var members = (MEMBERS[subjectTeams[si]] || []).map(function(m) {{ return m.toLowerCase(); }});
        if (members.indexOf(myLogin) !== -1) {{
          document.getElementById('bet-notice').textContent = 'You cannot bet on your own team.';
          return;
        }}
      }}

      var betPayload = {{
        version: 1,
        bet_type: type,
        placed_by: user.login,
        stake: stake,
        odds: odds,
        deadline: deadline,
        placed_at: new Date().toISOString(),
        params: params,
      }};

      var desc = betDescription({{bet_type: type, params: params}});
      var title = '[BET] ' + user.login + ': ' + desc + ' by ' + deadline;
      var body  = '```json\\n' + JSON.stringify(betPayload, null, 2) + '\\n```';

      var btn = document.getElementById('bet-submit-btn');
      btn.disabled = true;
      btn.textContent = 'Submitting\u2026';
      document.getElementById('bet-notice').textContent = '';

      try {{
        var r = await fetch('https://api.github.com/repos/' + SCOREBOARD_OWNER + '/' + SCOREBOARD_REPO + '/issues', {{
          method: 'POST',
          headers: {{ 'Authorization': 'token ' + token, 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ title: title, body: body, labels: ['bet'] }})
        }});
        if (!r.ok) {{
          var err = await r.json();
          throw new Error(err.message || r.status);
        }}
        var issue = await r.json();
        btn.textContent = '\u2713 Bet placed!';
        btn.style.background = 'var(--green)';
        document.getElementById('bet-notice').innerHTML = 'Bet #' + issue.number + ' submitted. ' +
          'Bricks will be deducted on next hourly update. ' +
          '<a href="' + issue.html_url + '" target="_blank" style="color:var(--accent)">View issue</a>';
      }} catch(err) {{
        btn.disabled = false;
        btn.textContent = 'Retry';
        document.getElementById('bet-notice').textContent = 'Error: ' + err.message;
        console.error(err);
      }}
    }}

    function escHtml(s) {{
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }}

    // Handle OAuth callback on page load
    handleOAuthCallback();
  </script>

  <script>
    (function () {{
      // Theme toggle
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

      // Countdown to next hourly workflow run (cron: '0 * * * *')
      var cdEl = document.getElementById('countdown');
      function tick() {{
        var now  = new Date();
        var next = new Date(now);
        next.setHours(next.getHours() + 1, 0, 0, 0);
        var diff = next - now;
        var m = Math.floor(diff / 60000);
        var s = Math.floor((diff % 60000) / 1000);
        cdEl.textContent = String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
      }}
      tick();
      setInterval(tick, 1000);
    }})();
  </script>
  <script>
    (function () {{
      // ── Cursor glow ───────────────────────────────────────────────────────
      var glow = document.createElement('div');
      glow.style.cssText = [
        'position:fixed', 'pointer-events:none', 'z-index:1',
        'width:520px', 'height:520px', 'border-radius:50%',
        'background:radial-gradient(circle,rgba(200,135,58,0.07) 0%,transparent 68%)',
        'transform:translate(-50%,-50%)', 'transition:opacity 400ms ease',
        'will-change:left,top', 'opacity:0'
      ].join(';');
      document.body.appendChild(glow);

      var mx = window.innerWidth / 2, my = window.innerHeight / 2;
      var gx = mx, gy = my;
      var inside = false;
      document.addEventListener('mousemove', function (e) {{ mx = e.clientX; my = e.clientY; inside = true; }});
      document.addEventListener('mouseleave', function () {{ inside = false; }});

      // ── Particles canvas ──────────────────────────────────────────────────
      var cvs = document.createElement('canvas');
      cvs.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:0;';
      document.body.prepend(cvs);
      var pc = cvs.getContext('2d');

      function resize() {{ cvs.width = window.innerWidth; cvs.height = window.innerHeight; }}
      resize();
      window.addEventListener('resize', resize);

      var starColors = ['255,255,255', '200,220,255', '255,240,180', '180,180,255', '220,255,220'];

      // 3 parallax layers: far (slow/small), mid, near (fast/large)
      var layerDefs = [
        {{ count: 80, baseSpeed: 0.22, sizeMin: 0.15, sizeMax: 0.55, opMax: 0.38, pFactor: 0.012 }},
        {{ count: 60, baseSpeed: 0.55, sizeMin: 0.45, sizeMax: 1.0,  opMax: 0.55, pFactor: 0.038 }},
        {{ count: 35, baseSpeed: 1.1,  sizeMin: 0.8,  sizeMax: 1.8,  opMax: 0.72, pFactor: 0.08  }},
      ];

      var pts = [];
      layerDefs.forEach(function (ld, li) {{
        for (var i = 0; i < ld.count; i++) {{
          var big = Math.random() < 0.1;
          var oBase = Math.random() * (ld.opMax * 0.55) + ld.opMax * 0.2;
          pts.push({{
            x: Math.random() * window.innerWidth,
            y: Math.random() * window.innerHeight,
            r: Math.random() * (ld.sizeMax - ld.sizeMin) + ld.sizeMin,
            speed: ld.baseSpeed * (0.7 + Math.random() * 0.6),
            oBase: oBase,
            oAmp:  big ? 0.18 : Math.random() * 0.11,
            oSpd:  Math.random() * 0.02 + 0.005,
            oPhase: Math.random() * Math.PI * 2,
            col: starColors[Math.floor(Math.random() * starColors.length)],
            pFactor: ld.pFactor,
          }});
        }}
      }});

      // ── Shooting stars ────────────────────────────────────────────────────
      var shoots = [];
      var nextShoot = Date.now() + 3000 + Math.random() * 4000;

      function spawnShoot () {{
        var angle = 0.38 + Math.random() * 0.35; // ~22–42° from horizontal
        var spd   = 9 + Math.random() * 7;
        shoots.push({{
          x:     Math.random() * cvs.width * 0.65,
          y:     Math.random() * cvs.height * 0.35,
          vx:    Math.cos(angle) * spd,
          vy:    Math.sin(angle) * spd,
          len:   70 + Math.random() * 70,
          life:  1.0,
          decay: 0.018 + Math.random() * 0.014,
        }});
      }}

      // ── Warp on click ─────────────────────────────────────────────────────
      var warp = 0;
      document.addEventListener('click', function () {{ warp = 1.0; }});

      // ── Animation loop ────────────────────────────────────────────────────
      function loop () {{
        var dark = document.documentElement.getAttribute('data-theme') !== 'light';

        var cx = cvs.width  / 2;
        var cy = cvs.height / 2;
        var dx = mx - cx, dy = my - cy;
        var dist = Math.sqrt(dx * dx + dy * dy) || 1;
        var influence = Math.min(dist / (Math.min(cvs.width, cvs.height) * 0.45), 1.0) * 0.65;
        var ndx = (dx / dist) * influence; // normalized steering X
        var ndy = (dy / dist) * influence; // normalized steering Y

        // Cursor glow
        gx += (mx - gx) * 0.07;
        gy += (my - gy) * 0.07;
        glow.style.left    = gx + 'px';
        glow.style.top     = gy + 'px';
        glow.style.opacity = dark && inside ? '1' : '0';

        if (warp > 0) warp = Math.max(0, warp - 0.028);

        pc.clearRect(0, 0, cvs.width, cvs.height);

        if (dark) {{
          var warpBoost = 1 + warp * 9;

          for (var j = 0; j < pts.length; j++) {{
            var p = pts[j];
            p.oPhase += p.oSpd;
            var alpha = p.oBase + Math.sin(p.oPhase) * p.oAmp;
            if (alpha < 0) alpha = 0;

            // Mouse steering: near layer reacts more than far
            var svx = ndx * p.speed * p.pFactor * 35;
            var svy = ndy * p.speed * p.pFactor * 35;
            var tvx = svx;
            var tvy = -p.speed + svy;

            if (warp > 0.05) {{
              var stretch = warp * 14;
              var sx = p.x - tvx * stretch;
              var sy = p.y - tvy * stretch;
              var grd = pc.createLinearGradient(p.x, p.y, sx, sy);
              grd.addColorStop(0, 'rgba(' + p.col + ',' + (alpha * (0.5 + warp * 0.5)) + ')');
              grd.addColorStop(1, 'rgba(' + p.col + ',0)');
              pc.beginPath();
              pc.moveTo(p.x, p.y);
              pc.lineTo(sx, sy);
              pc.strokeStyle = grd;
              pc.lineWidth = p.r * (1 + warp * 2.5);
              pc.stroke();
            }} else {{
              pc.beginPath();
              pc.arc(p.x, p.y, p.r, 0, Math.PI * 2);
              pc.fillStyle = 'rgba(' + p.col + ',' + alpha + ')';
              pc.fill();
            }}

            p.x += tvx * warpBoost;
            p.y += tvy * warpBoost;
            if (p.y < -4) {{ p.y = cvs.height + 4; p.x = Math.random() * cvs.width; }}
            if (p.x < -4) p.x = cvs.width  + 4;
            if (p.x > cvs.width + 4) p.x = -4;
          }}

          // Shooting stars
          var now = Date.now();
          if (now >= nextShoot) {{
            spawnShoot();
            nextShoot = now + 4000 + Math.random() * 5000;
          }}
          for (var s = shoots.length - 1; s >= 0; s--) {{
            var sh = shoots[s];
            sh.life -= sh.decay;
            if (sh.life <= 0) {{ shoots.splice(s, 1); continue; }}
            var spd2  = Math.sqrt(sh.vx * sh.vx + sh.vy * sh.vy) || 1;
            var tailX = sh.x - sh.vx / spd2 * sh.len;
            var tailY = sh.y - sh.vy / spd2 * sh.len;
            var sg = pc.createLinearGradient(sh.x, sh.y, tailX, tailY);
            sg.addColorStop(0, 'rgba(255,255,255,' + (sh.life * 0.95) + ')');
            sg.addColorStop(0.25, 'rgba(200,220,255,' + (sh.life * 0.55) + ')');
            sg.addColorStop(1, 'rgba(200,220,255,0)');
            pc.beginPath();
            pc.moveTo(sh.x, sh.y);
            pc.lineTo(tailX, tailY);
            pc.strokeStyle = sg;
            pc.lineWidth = 1.5;
            pc.stroke();
            sh.x += sh.vx;
            sh.y += sh.vy;
            if (sh.x > cvs.width + 120 || sh.y > cvs.height + 120) {{
              shoots.splice(s, 1);
            }}
          }}
        }}

        requestAnimationFrame(loop);
      }}
      loop();

      // ── Score counter animation ───────────────────────────────────────────
      setTimeout(function () {{
        var targets = document.querySelectorAll('.pts-value, td.col-total');
        targets.forEach(function (el) {{
          var raw = parseFloat(el.textContent);
          if (isNaN(raw) || raw === 0) return;
          var dur = 750, t0 = null;
          function step (ts) {{
            if (!t0) t0 = ts;
            var pct = Math.min((ts - t0) / dur, 1);
            var ease = 1 - Math.pow(1 - pct, 3);
            el.textContent = (raw * ease).toFixed(2);
            if (pct < 1) requestAnimationFrame(step);
            else el.textContent = raw.toFixed(2);
          }}
          requestAnimationFrame(step);
        }});
      }}, 120);

      // ── Rank-up glow ──────────────────────────────────────────────────────
      setTimeout(function () {{
        document.querySelectorAll('.trend-up').forEach(function (el) {{
          var row = el.closest('tr');
          if (row) row.classList.add('rank-up-flash');
        }});
      }}, 300);

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
    all_issues, coin_issues, open_issues = fetch_project_issues()
    print(f"  {len(all_issues)} Done issues found")
    print(f"  {len(coin_issues)} budget-labeled issues found")
    print(f"  {len(open_issues)} open issues found")

    scores = calculate_scores(teams, user_to_team, all_issues, coin_issues, open_issues)

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    os.makedirs(out_dir, exist_ok=True)

    ranked = rank_teams(teams, scores)
    prev_positions = load_daily_positions(out_dir)
    current_positions = {teams[team_id]["name"]: pos + 1 for pos, team_id in enumerate(ranked)}
    save_positions(current_positions, out_dir)
    save_daily_positions(current_positions, out_dir)

    print("Processing bets...")
    bets_data = load_bets(out_dir, teams)
    bet_issues = fetch_bet_issues()
    print(f"  {len(bet_issues)} pending bet issue(s) found")
    bets_data = process_cancellations(bets_data, bet_issues)
    bets_data = sync_new_bets(bets_data, bet_issues, teams, scores, ranked)
    bets_data = resolve_bets(bets_data, teams, scores, ranked)
    save_bets(bets_data, out_dir)

    issues_detail = build_issues_detail(teams, user_to_team, all_issues)
    generated_at  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = generate_html(teams, scores, all_issues, coin_issues, generated_at, ranked, prev_positions, issues_detail, open_issues, bets_data)

    out_path = os.path.join(out_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Written to {out_path}")

if __name__ == "__main__":
    main()
