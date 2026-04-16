/**
 * Cloudflare Worker — Instant bet cancellation
 *
 * Deploy steps:
 *   1. Go to https://workers.cloudflare.com → Create Worker → paste this file
 *   2. Settings → Variables → add:
 *        GH_BOT_TOKEN = <your GitHub Actions token (same as GH_TOKEN secret)>  ← mark as Secret
 *   3. Copy the worker URL and set it as CANCEL_WORKER_URL in your GitHub Actions secrets.
 *
 * What it does:
 *   - Verifies the user's GitHub token
 *   - Checks the bet belongs to them and deadline is >1h away
 *   - Updates docs/bets.json directly in the repo (instant refund)
 *   - Closes the bet issue
 */

const ALLOWED_ORIGINS = [
  'https://dev-scoreboard.firstlegoleague.win',
  'http://localhost',
  'http://127.0.0.1',
];

const OWNER     = 'polMarsol';
const REPO      = 'first-lego-league-scoreboard';
const BETS_PATH = 'docs/bets.json';
const GH_API    = 'https://api.github.com';
const UA        = 'FLL-Scoreboard-Worker';

export default {
  async fetch(request, env) {
    const origin  = request.headers.get('Origin') || '';
    const allowed = ALLOWED_ORIGINS.some(o => origin.startsWith(o));

    const corsHeaders = {
      'Access-Control-Allow-Origin':  allowed ? origin : ALLOWED_ORIGINS[0],
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders });
    if (!allowed)                      return new Response('Forbidden', { status: 403 });
    if (request.method !== 'POST')     return new Response('Method Not Allowed', { status: 405, headers: corsHeaders });

    let userToken, issueNumber;
    try {
      ({ token: userToken, issue_number: issueNumber } = await request.json());
    } catch {
      return json({ error: 'Invalid JSON' }, 400, corsHeaders);
    }
    if (!userToken || !issueNumber) {
      return json({ error: 'Missing token or issue_number' }, 400, corsHeaders);
    }

    // 1. Verify user identity with their token
    const userRes = await fetch(`${GH_API}/user`, {
      headers: { Authorization: `token ${userToken}`, 'User-Agent': UA },
    });
    if (!userRes.ok) return json({ error: 'Invalid GitHub token' }, 401, corsHeaders);
    const { login } = await userRes.json();

    // 2. Fetch current bets.json (bot token for repo read access)
    const fileRes = await fetch(`${GH_API}/repos/${OWNER}/${REPO}/contents/${BETS_PATH}`, {
      headers: { Authorization: `token ${env.GH_BOT_TOKEN}`, 'User-Agent': UA },
    });
    if (!fileRes.ok) return json({ error: 'Could not fetch bets.json' }, 500, corsHeaders);
    const fileData = await fileRes.json();

    let bets;
    try {
      bets = JSON.parse(atob(fileData.content.replace(/\n/g, '')));
    } catch {
      return json({ error: 'Could not parse bets.json' }, 500, corsHeaders);
    }

    // 3. Find the active bet owned by this user
    const betIdx = bets.active_bets.findIndex(
      b => b.issue_number === issueNumber && b.placed_by.toLowerCase() === login.toLowerCase()
    );
    if (betIdx === -1) return json({ error: 'Bet not found or not yours' }, 404, corsHeaders);
    const bet = bets.active_bets[betIdx];

    // 4. Enforce 1-hour deadline guard
    // Treat close time as 23:00 UTC on the deadline date (1h before midnight)
    const closeTime = new Date(bet.deadline + 'T23:00:00Z');
    if (new Date() >= closeTime) {
      return json({ error: 'Too close to the deadline — cancellation not allowed' }, 400, corsHeaders);
    }

    // 5. Apply cancellation in memory
    bets.active_bets.splice(betIdx, 1);
    const oldBal = bets.member_balances[login] || 0;
    bets.member_balances[login] = Math.round((oldBal + bet.stake) * 100) / 100;
    bets.resolved_bets.push({
      ...bet,
      won:         false,
      payout:      0.0,
      cancelled:   true,
      resolved_at: new Date().toISOString(),
    });

    // 6. Commit updated bets.json to the repo
    const newContent = btoa(unescape(encodeURIComponent(JSON.stringify(bets, null, 2))));
    const putRes = await fetch(`${GH_API}/repos/${OWNER}/${REPO}/contents/${BETS_PATH}`, {
      method: 'PUT',
      headers: {
        Authorization:   `token ${env.GH_BOT_TOKEN}`,
        'Content-Type':  'application/json',
        'User-Agent':    UA,
      },
      body: JSON.stringify({
        message: `chore: cancel bet #${issueNumber} by ${login} [skip ci]`,
        content: newContent,
        sha:     fileData.sha,
      }),
    });
    if (!putRes.ok) {
      const err = await putRes.json().catch(() => ({}));
      return json({ error: 'Failed to save bets.json: ' + (err.message || putRes.status) }, 500, corsHeaders);
    }

    // 7. Post resolution comment + close issue (best-effort)
    const issueBase = `${GH_API}/repos/${OWNER}/${REPO}/issues/${issueNumber}`;
    const commentBody = `\u21a9\ufe0f **Cancelled** \u2014 Stake refunded: **+${bet.stake.toFixed(2)} BRK**`;
    await Promise.allSettled([
      fetch(`${issueBase}/comments`, {
        method: 'POST',
        headers: { Authorization: `token ${env.GH_BOT_TOKEN}`, 'Content-Type': 'application/json', 'User-Agent': UA },
        body: JSON.stringify({ body: commentBody }),
      }),
      fetch(issueBase, {
        method: 'PATCH',
        headers: { Authorization: `token ${env.GH_BOT_TOKEN}`, 'Content-Type': 'application/json', 'User-Agent': UA },
        body: JSON.stringify({ state: 'closed' }),
      }),
    ]);

    return json({
      ok:          true,
      refund:      bet.stake,
      new_balance: bets.member_balances[login],
    }, 200, corsHeaders);
  },
};

function json(body, status, headers) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...headers, 'Content-Type': 'application/json' },
  });
}
