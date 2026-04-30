# Stock System

台股篩選、警示與 AI 分析系統。

## 設定

### 環境變數

複製 `.env.example` 為 `.env`，填入真實金鑰：

```bash
cp .env.example .env
```

編輯 `.env`，將 `your-api-key-here` 替換為你的 Anthropic API Key：

```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxx
```

API Key 取得方式：https://console.anthropic.com/settings/keys

> `.env` 已被 `.gitignore` 排除，不會被提交到 Git。

### GitHub Actions

GitHub Actions 使用 Repository Secrets，在 Settings → Secrets and variables → Actions 設定 `ANTHROPIC_API_KEY`。

### 必要套件

本機執行 AI 分析需安裝 `python-dotenv`：

```bash
pip install python-dotenv anthropic
```
