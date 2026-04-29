/**
 * stock-watchlist Worker
 * KV-backed watchlist CRUD API
 *
 * GET  /watchlist         -> 取得全部觀察清單
 * POST /watchlist         -> 新增/更新一支股票 (body: {code, ...})
 * DELETE /watchlist/:code -> 刪除一支股票
 *
 * Auth: Bearer token in Authorization header
 */

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
  });
}

function checkAuth(request, env) {
  const auth = request.headers.get('Authorization') || '';
  const token = auth.replace('Bearer ', '');
  return token === env.API_TOKEN;
}

export default {
  async fetch(request, env) {
    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const path = url.pathname;

    // GET /watchlist - public read (PWA and GitHub Actions both need it)
    if (request.method === 'GET' && path === '/watchlist') {
      const data = await env.WATCHLIST_KV.get('watchlist', 'json');
      return json(data || {});
    }

    // Write operations require auth
    if (!checkAuth(request, env)) {
      return json({ error: 'Unauthorized' }, 401);
    }

    // POST /watchlist - add/update a stock
    if (request.method === 'POST' && path === '/watchlist') {
      const body = await request.json();
      const code = body.code;
      if (!code) {
        return json({ error: 'Missing code' }, 400);
      }

      // Get existing data
      const data = (await env.WATCHLIST_KV.get('watchlist', 'json')) || {};

      // Build entry
      data[code] = {
        name: body.name || code,
        added: body.added || new Date().toISOString().slice(0, 10),
        source: body.source || 'PWA',
        targets: body.targets || {},
        key_dates: body.key_dates || [],
        watch: body.watch || [],
        stop_loss: body.stop_loss || null,
      };

      await env.WATCHLIST_KV.put('watchlist', JSON.stringify(data));
      return json({ ok: true, count: Object.keys(data).length });
    }

    // DELETE /watchlist/:code
    if (request.method === 'DELETE' && path.startsWith('/watchlist/')) {
      const code = path.split('/')[2];
      if (!code) {
        return json({ error: 'Missing code' }, 400);
      }

      const data = (await env.WATCHLIST_KV.get('watchlist', 'json')) || {};
      if (data[code]) {
        delete data[code];
        await env.WATCHLIST_KV.put('watchlist', JSON.stringify(data));
      }
      return json({ ok: true, count: Object.keys(data).length });
    }

    return json({ error: 'Not found' }, 404);
  },
};
