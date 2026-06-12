export default {
  async scheduled(event, env) {
    const twTime = () => new Date().toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' });
    const notify = async (text) => {
      await fetch('https://pomodoro-bot.juria-orch.workers.dev', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: '8786691885', text }),
      }).catch(() => {});
    };

    try {
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

      if (resp.status === 204) {
        await notify(`✅ Stock cron trigger 成功 (${twTime()})`);
      } else {
        const body = await resp.text();
        console.error(`Trigger failed: ${resp.status} ${body}`);
        await notify(`⚠️ Stock cron trigger 失敗!\nStatus: ${resp.status}\n${body}\n時間: ${twTime()}\n可能原因: GITHUB_TOKEN 過期`);
      }
    } catch (err) {
      console.error(`Worker crashed: ${err.message}`);
      await notify(`❌ Stock cron Worker 崩潰!\n${err.message}\n時間: ${twTime()}`);
    }
  },

  async fetch(request, env) {
    return new Response('Stock cron trigger is running. Use Cloudflare cron to trigger.');
  },
};
