export default {
  async scheduled(event, env) {
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
      // 用 Telegram 通知（不依賴 GitHub token，token 過期時也能通知）
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
