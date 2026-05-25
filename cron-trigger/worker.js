export default {
  async scheduled(event, env) {
    // 先檢查今天是否已有成功的 workflow run，有就跳過
    const today = new Date().toISOString().slice(0, 10); // UTC date
    const checkResp = await fetch(
      `https://api.github.com/repos/Amati-Lee/stock-system/actions/workflows/daily-stock-update.yml/runs?created=${today}&status=success&per_page=1`,
      {
        headers: {
          'Authorization': `token ${env.GITHUB_TOKEN}`,
          'Accept': 'application/vnd.github.v3+json',
          'User-Agent': 'stock-cron-trigger',
        },
      }
    );

    if (checkResp.ok) {
      const data = await checkResp.json();
      if (data.total_count > 0) {
        console.log(`Already ran successfully today (${today}), skipping.`);
        return;
      }
    }

    // 今天還沒成功跑過，觸發 workflow
    const resp = await fetch(
      'https://api.github.com/repos/Amati-Lee/stock-system/actions/workflows/daily-stock-update.yml/dispatches',
      {
        method: 'POST',
        headers: {
          'Authorization': `token ${env.GITHUB_TOKEN}`,
          'Accept': 'application/vnd.github.v3+json',
          'User-Agent': 'stock-cron-trigger',
        },
        body: JSON.stringify({ ref: 'master' }),
      }
    );

    console.log(`Triggered workflow: ${resp.status}`);

    // 204 = 成功，其他都是異常
    if (resp.status !== 204) {
      const body = await resp.text();
      console.error(`Trigger failed: ${resp.status} ${body}`);
      const twTime = new Date().toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' });
      await fetch('https://pomodoro-bot.juria-orch.workers.dev', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: '8786691885',
          text: `⚠️ Stock cron trigger 失敗!\nStatus: ${resp.status}\n${body}\n時間: ${twTime}\n可能原因: GITHUB_TOKEN 過期`,
        }),
      });
    }
  },

  async fetch(request, env) {
    return new Response('Stock cron trigger is running. Use Cloudflare cron to trigger.');
  },
};
