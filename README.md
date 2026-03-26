# 🎬 YouTube Shorts SEO Agent

> Fully automated pipeline: **Google Drive → AI SEO → YouTube Upload → Email Notification**
> Powered by **GitHub Actions + Cron-job.org** — Most Reliable Free 24/7 System

Runs every 5 minutes via GitHub Actions. Zero manual steps after the one-time setup.

---

## 📋 What It Does

1. **Scans** your Google Drive folder for video files (picks the oldest one)
2. **Downloads** the video temporarily
3. **Generates** SEO-optimized title, description, and 15+ tags using Claude AI
4. **Uploads** the video to YouTube as a Short (public)
5. **Deletes** the Drive file after confirmed upload
6. **Emails** you a notification with the video link and timestamp (IST)

---

## 🗂️ Project Structure

```
youtube-seo-agent/
├── .github/workflows/agent.yml   ← Auto-runs every 5 minutes + external trigger support
├── src/
│   ├── main.py                   ← Orchestrator
│   ├── drive_handler.py          ← Google Drive operations
│   ├── seo_generator.py          ← AI metadata generation
│   ├── youtube_uploader.py       ← YouTube Data API
│   ├── scheduler.py              ← Upload scheduling (US peak hours)
│   └── telegram_notifier.py      ← Telegram notifications
├── config/settings.py            ← Environment variable loader
├── get_youtube_token.py          ← One-time token generator (run locally)
├── requirements.txt
└── .env.example                  ← Copy to .env for local dev
```

---

## 🚀 Setup Guide (10 minutes)

### Prerequisites
- A Google account (for Drive + YouTube)
- A GitHub account (free tier is fine — **unlimited minutes for public repos**)
- An Anthropic API key (Claude) — get one at [console.anthropic.com](https://console.anthropic.com)
- Python 3.11+ installed locally (only needed for Step 3)

---

### Step 1 — Fork / Clone This Repository

```bash
git clone https://github.com/YOUR_USERNAME/youtube-seo-agent.git
cd youtube-seo-agent
```

---

### Step 2 — Set Up Google Drive Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → Create a new project (or use existing)
2. Enable **Google Drive API**:
   - `APIs & Services` → `Library` → search "Google Drive API" → Enable
3. Create a Service Account:
   - `APIs & Services` → `Credentials` → `Create Credentials` → `Service Account`
   - Name it anything, click Done
4. Generate a JSON key:
   - Click the service account → `Keys` tab → `Add Key` → `Create new key` → JSON
   - **Download** the JSON file (keep it safe!)
5. **Share your Drive folder** with the service account email:
   - Open Google Drive → Right-click your video folder → `Share`
   - Paste the service account email (looks like `xxx@yyyy.iam.gserviceaccount.com`)
   - Set permission to **Editor** → Click Share

> **Your Drive Folder ID**: Open the folder in Drive. The URL looks like:
> `https://drive.google.com/drive/folders/1ABC123XYZ`
> The `1ABC123XYZ` part is your Folder ID.

---

### Step 3 — Set Up YouTube API & Get Refresh Token

1. In Google Cloud Console → Enable **YouTube Data API v3**
2. Create OAuth2 credentials:
   - `Credentials` → `Create Credentials` → `OAuth client ID`
   - Application type: **Desktop app**
   - Download the credentials (you'll get a client ID and secret)
3. Add authorized redirect URIs:
   - In the OAuth client → `Add URI` → `http://localhost:8080`
4. Run the token generator **on your local machine**:

```bash
pip install google-auth-oauthlib python-dotenv
# Copy .env.example to .env and fill in YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET
cp .env.example .env
# Edit .env with your credentials
python get_youtube_token.py
```

5. A browser window will open → Sign in with your YouTube account → Allow access
6. Copy the `YOUTUBE_REFRESH_TOKEN` printed in the terminal

---

### Step 4 — Configure GitHub Secrets

Go to your GitHub repository → **Settings → Secrets and variables → Actions → New repository secret**

Add each secret:

| Secret Name | Value |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full contents of your service account JSON file (paste entire JSON) |
| `GOOGLE_DRIVE_FOLDER_ID` | Your Drive folder ID (e.g., `1ABC123XYZ`) |
| `YOUTUBE_CLIENT_ID` | Your YouTube OAuth2 Client ID |
| `YOUTUBE_CLIENT_SECRET` | Your YouTube OAuth2 Client Secret |
| `YOUTUBE_REFRESH_TOKEN` | Token from `get_youtube_token.py` |
| `ANTHROPIC_API_KEY` | Your Claude API key (starts with `sk-ant-`) |
| `NOTIFY_EMAIL` | Email address to receive notifications |
| `SMTP_EMAIL` | Gmail address to send notifications FROM |
| `SMTP_PASSWORD` | Gmail **App Password** (see below) |

#### How to get a Gmail App Password:
1. Go to your [Google Account](https://myaccount.google.com/)
2. Security → 2-Step Verification → enable it (required)
3. Security → `App passwords`
4. Select "Mail" and "Other (custom name)" → Generate
5. Copy the 16-character password

---

### Step 5 — Upload Videos to Google Drive

Drop any `.mp4`, `.mov`, or `.avi` files into your shared Drive folder.
The agent will pick the **oldest file** and process it every 30 minutes.

---

### Step 6 — Enable GitHub Actions

Go to your repo → **Actions** tab → click "I understand my workflows, go ahead and enable them"

The agent will now run automatically every 30 minutes. You can also trigger it manually:
- Actions → "YouTube SEO Agent" → "Run workflow"

---

## 📊 Monitoring

- **GitHub Actions logs**: `Actions` tab → Click any run → View step-by-step logs
- **Email**: You'll receive an email for every upload (success or failure)
- **Timestamps**: All logs and emails are in **IST (India Standard Time)**

---

## ⚙️ Configuration Options

| Setting | Default | How to Change |
|---|---|---|
| Run frequency | Every 5 min | Edit `cron` in `.github/workflows/agent.yml` |
| External trigger | Cron-job.org | Use `workflow_dispatch` or `repository_dispatch` |
| Privacy | `public` | Change `privacyStatus` in `youtube_uploader.py` |
| AI provider | Anthropic Claude | Set `OPENAI_API_KEY` instead of `ANTHROPIC_API_KEY` |
| Video category | `22` (People & Blogs) | AI adjusts based on filename |
| Default language | `hi` (Hindi) | AI adjusts based on filename |

---

## ⚡ GitHub Actions + Cron-job.org — Most Reliable Free 24/7 System

This project uses **GitHub Actions** for scheduling and **Cron-job.org** for external triggers.

### Option 1: GitHub Actions Only (Default)
- Runs every 5 minutes automatically
- No additional setup needed
- Free for public repos: **Unlimited minutes**

### Option 2: GitHub Actions + Cron-job.org (Recommended for reliability)
For minute-level precision, use Cron-job.org to trigger the workflow:

1. **Enable `workflow_dispatch`** — Already enabled in this repo ✅
2. **Create Cron-job.org job:**
   - **URL:** `https://api.github.com/repos/YOUR_USERNAME/YOUR_REPO/dispatches`
   - **Method:** POST
   - **Headers:**
     ```
     Authorization: token YOUR_GITHUB_TOKEN
     Accept: application/vnd.github+json
     ```
   - **Body:** `{"event_type": "cron-trigger"}`
   - **Schedule:** Up to 60x/hour (once per minute)

### Why This Combo?

| Feature | GitHub Actions | Cron-job.org |
|---------|---------------|--------------|
| Schedule | Every 5 min (free) | Every 1 min (free) |
| External API call | ❌ | ✅ |
| Cost | FREE | FREE |
| Public repo minutes | Unlimited | N/A |

**Best of both worlds:** Use GitHub Actions schedule as backup, Cron-job.org for precise triggering! |

---

## ❗ Error Handling

| Scenario | Behavior |
|---|---|
| No videos in Drive folder | Logs "No videos found" and exits cleanly |
| AI SEO generation fails | Retries once, then uses safe default metadata |
| YouTube upload fails | Drive file is **NOT deleted**; failure email sent |
| Email sending fails | Logged as warning; agent doesn't crash |
| API quota exceeded | Logged and exits; Drive file untouched |

---

## 🔒 Security Notes

- **Never commit** your `.env` file or `youtube_token.json` — they're in `.gitignore`
- The service account only has Drive access (no Gmail, no Sheets, etc.)
- YouTube credentials use OAuth2 with minimal scopes (upload only)
- Secrets are stored encrypted in GitHub Actions

---

## 📌 YouTube API Quota

YouTube's Data API allows **10,000 units/day** (free).
Each video upload costs **1,600 units**.
This means you can upload up to **6 videos per day** within the free quota.

The agent runs every 5 minutes but processes **one video per run**, so:
- 5-min interval = up to 288 runs/day → limited to 6 actual uploads by quota

---

## 🛠️ Local Development / Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill environment variables
cp .env.example .env
# Edit .env with your actual credentials

# Run the agent locally
python src/main.py
```

---

## 📬 Support

If you encounter issues:
1. Check the **GitHub Actions logs** (most detailed)
2. Check your email for the **failure notification** (includes error message)
3. Verify all secrets are set correctly (Settings → Secrets → Actions)

---

*Built with ❤️ using Python, Google APIs, Claude AI, and GitHub Actions*
