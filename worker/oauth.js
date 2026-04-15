/**
 * Cloudflare Worker — GitHub OAuth token exchange proxy
 *
 * Deploy steps:
 *   1. Go to https://workers.cloudflare.com → Create Worker → paste this file
 *   2. Settings → Variables → add:
 *        GH_CLIENT_ID     = <your OAuth App client id>
 *        GH_CLIENT_SECRET = <your OAuth App client secret>  ← mark as Secret
 *   3. Copy the worker URL (e.g. https://fll-oauth.your-name.workers.dev)
 *      and set it as OAUTH_WORKER_URL in your GitHub Actions secrets.
 *
 * Allowed origins: update ALLOWED_ORIGINS if your domain changes.
 */

const ALLOWED_ORIGINS = [
  'https://dev-scoreboard.firstlegoleague.win',
  'http://localhost',
  'http://127.0.0.1',
];

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const allowed = ALLOWED_ORIGINS.some(o => origin.startsWith(o));

    const corsHeaders = {
      'Access-Control-Allow-Origin': allowed ? origin : ALLOWED_ORIGINS[0],
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    if (!allowed) {
      return new Response('Forbidden', { status: 403 });
    }

    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405, headers: corsHeaders });
    }

    let code;
    try {
      ({ code } = await request.json());
    } catch {
      return json({ error: 'Invalid JSON' }, 400, corsHeaders);
    }

    if (!code) {
      return json({ error: 'Missing code' }, 400, corsHeaders);
    }

    const ghRes = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({
        client_id:     env.GH_CLIENT_ID,
        client_secret: env.GH_CLIENT_SECRET,
        code,
      }),
    });

    const data = await ghRes.json();
    return json(data, ghRes.status, corsHeaders);
  },
};

function json(body, status, headers) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...headers, 'Content-Type': 'application/json' },
  });
}
