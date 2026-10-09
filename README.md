# 🌐 Web Auto Poster - Telegram Bot

A powerful Telegram bot that automatically monitors websites for new posts and instantly publishes them to your Telegram channels. Built with Python and the `python-telegram-bot` library.

---

## ✨ Features

### 🚀 Core Features
- **🔍 Automatic Feed Detection** — Just send a website URL, and the bot automatically discovers the RSS/Atom feed
- **⚡ Instant Auto-Posting** — New articles are posted to your channels **immediately** upon detection
- **📢 Multi-Channel Support** — Post to multiple Telegram channels from a single website
- **🌐 Multi-Website Support** — Monitor unlimited websites simultaneously
- **⏰ Timezone-Aware Scheduling** — Schedule posts in your local timezone

### 📤 Post Management
- **Unique Post IDs** — Every post gets a sequential ID (1, 2, 3...) per user
- **Rich Previews** — View posts with thumbnail, title, and description before sending
- **Manual Send** — Send any post to any channel instantly
- **Schedule Posts** — Queue posts to be sent at a specific time in your timezone
- **Reschedule Posts** — Admins can reschedule any pending post

### 🛠 Channel Management
- **3 Ways to Add Channels:**
  - 📤 Forward a message from the channel
  - ✏️ Enter `@username`
  - 🔢 Enter channel ID
- **Per-Website Channels** — Each channel is linked to a specific website

### 🌍 Timezone Support
- Region-based timezone picker (Africa, Americas, Asia, Europe, etc.)
- All scheduling uses your local timezone
- Full `pytz` timezone database support

### 🔧 Admin Panel
- **📊 Statistics** — Users, websites, channels, posts, pending, sent counts
- **⏰ Pending Posts Viewer** — See all scheduled posts with local times
- **🔄 Reschedule Posts** — Change scheduled post times
- **📢 Broadcast** — Send image + caption messages to all users with progress tracking

---

## 📋 Requirements

- Python **3.8+**
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- SQLite (built-in with Python)

### Python Dependencies

```txt
python-telegram-bot>=20.0
feedparser
beautifulsoup4
aiohttp
python-dotenv
pytz
```

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/DarkLord813/telegram-web-poster.git
cd telegram-web-poster
```

### 2. Create a Virtual Environment (Recommended)

```bash
python -m venv venv

# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install python-telegram-bot feedparser beautifulsoup4 aiohttp python-dotenv pytz
```

### 4. Create the `.env` File

Create a `.env` file in the project root:

```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 5. Configure Admin IDs

Open `autopost.py` and update the `ADMIN_IDS` list:

```python
ADMIN_IDS = [
    12345678,  # Your Telegram user ID
    # Add more admin IDs here
]
```

> 💡 **Tip:** Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot)

### 6. Run the Bot

```bash
python autopost.py
```

---

## 📖 Usage Guide

### 🏁 Getting Started

1. **Start the bot** — Send `/start` to your bot on Telegram
2. **Set your timezone** — Click `⏰ Set Timezone` and pick your region
3. **Add a website** — Click `➕ Add Website` and send a URL
4. **Add a channel** — Click `📤 Add Channel`, select the website, and choose a method
5. **Done!** — New posts will be auto-posted immediately

### 🌐 Adding a Website

Send any of these formats:

- `https://example.com`
- `pspgamers5.blogspot.com`
- `https://news.site/feed`

**Supported platforms:** WordPress, Blogger, Medium, Ghost, and any RSS/Atom-enabled site.

If auto-detection fails, try these common feed paths:

| Platform | Feed Path |
|----------|-----------|
| WordPress | `/feed/` |
| Blogger | `/feeds/posts/default` |
| Medium | `/feed` |
| Ghost | `/rss/` |

### 📤 Adding a Channel

**Prerequisites:** The bot **must be an admin** in the channel.

1. Click `📤 Add Channel`
2. Select the website you want to link it to
3. Choose one of:
   - **📤 Forward** — Forward any message from the channel to the bot
   - **✏️ @username** — Enter `@your_channel`
   - **🔢 ID** — Enter the numeric channel ID (e.g., `-1001234567890`)

### 📝 Managing Posts

1. Click `📤 Manage Posts`
2. Enter the **Post ID** (shown as `#1`, `#2`, etc.)
3. View the preview (image + title + description)
4. Choose:
   - **📤 Send Now** — Pick a channel and send immediately
   - **⏰ Schedule** — Pick a channel and enter a time (HH:MM in your timezone)

### ⏰ Schedule Settings

Click `⏰ Schedule Settings` → Select a website → Adjust:

- **Set Time** — Change the daily posting time
- **Posts/Day** — Change the number of posts per day

### 🗑 Deleting a Website

1. Click `🗑 Delete Website`
2. Enter the website number
3. Confirm deletion

> ⚠️ Deleting a website stops all auto-posts and unlinks its channels.

---

## 🔧 Admin Panel

Admins see an extra `🔧 Admin Panel` button with:

| Feature | Description |
|---------|-------------|
| 📊 Statistics | User, website, channel, and post counts |
| ⏰ Pending Posts | View all scheduled posts with local times |
| 🔄 Reschedule Post | Change the send time of any pending post |
| 📢 Broadcast | Send image + caption to all users |

### Broadcast Format

1. Send a **photo** (or `/skip` for text-only)
2. Send the **caption** (image caption or message text)
3. Send the **message body** to broadcast
4. Bot sends to all users with live progress updates

---

## 🗂 Project Structure

```txt
website-auto-poster/
├── autopost.py            # Main bot script
├── web_auto_poster.db     # SQLite database (auto-created)
├── .env                   # Bot token (create this)
└── README.md              # This file
```

### Database Tables

| Table | Purpose |
|-------|---------|
| `users` | User profiles + timezones |
| `websites` | Monitored websites + schedules |
| `channels` | Telegram channels linked to websites |
| `blog_posts` | All fetched posts with metadata |
| `pending_posts` | Scheduled posts queue |
| `posted_history` | Record of sent posts |
| `broadcasts` | Broadcast history |

---

## ⚙️ Configuration

Edit these constants in `autopost.py`:

```python
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_IDS = [7713987088]
BOT_NAME = "WebAutoPoster™"
CHECK_INTERVAL = 300  # Feed check interval (seconds)
DB_FILE = 'web_auto_poster.db'
```

### `CHECK_INTERVAL`

How often the bot scans all websites for new posts.

- Default: `300` (5 minutes)
- Minimum recommended: `60` (1 minute)

---

## 🔄 How Auto-Posting Works

```txt
┌─────────────────┐
│ Background Loop │  Every CHECK_INTERVAL seconds
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Fetch RSS Feed │  For each active website
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Parse Entries  │  Extract title, content, images
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Deduplicate    │  Skip posts already saved (MD5 hash)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Auto-Post      │  Send to all linked channels immediately
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Notify User    │  Send preview to the website owner
└─────────────────┘
```

**Key behaviors:**

- ✅ New posts are sent **instantly** — no waiting for a schedule
- ✅ Deduplication via MD5 hash prevents duplicate posts
- ✅ Users receive a notification with a post preview when new content is found
- ✅ Scheduled posts are checked every **60 seconds**

---

## 🛡 Permissions Checklist

Before adding a channel, make sure:

- [x] The bot is a **member** of the channel
- [x] The bot is an **admin** in the channel
- [x] The bot has **Post Messages** permission
- [x] The bot has **Delete Messages** permission (optional)

---

## 🐛 Troubleshooting

### Bot doesn't respond

- Check that `BOT_TOKEN` is correct in `.env`
- Ensure the bot process is running
- Verify no other instance of the bot is polling

### "Could not find RSS/Atom feed"

- Try appending `/feed`, `/rss`, or `/rss.xml` to the URL
- For Blogger: use `/feeds/posts/default`
- For Medium: use `https://medium.com/@username/feed`

### Posts aren't being sent to channels

- Verify the bot is an admin in the channel
- Check that the channel is linked to the correct website
- Review logs for error messages

### Timezone issues

- Re-run `⏰ Set Timezone` and select your region
- The bot stores all times in UTC internally and converts for display

### Database errors

- Delete `web_auto_poster.db` and restart (⚠️ this erases all data)
- Ensure write permissions in the project directory

---

## 📊 Logging

The bot logs to `stdout` with the format:

```txt
2025-01-15 14:30:00,123 - __main__ - INFO - 🔔 NEW POST DETECTED: ...
2025-01-15 14:30:01,456 - __main__ - INFO - ✅ Auto-posted 2 new posts from Example to 3 channels
```

**Key log messages:**

- `🔄 Scanning all feeds...` — Background scan started
- `🔔 NEW POST DETECTED` — New content found
- `📤 Auto-posted` — Successfully sent to channel
- `⚠️ No channels found` — Website has no linked channels

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 📜 License

This project is licensed under the **MIT License** — see the `LICENSE` file for details.

---

## 🙏 Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — Telegram Bot API wrapper
- [feedparser](https://github.com/kurtmckee/feedparser) — RSS/Atom parsing
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) — HTML parsing
- [pytz](https://pythonhosted.org/pytz/) — Timezone handling

---

## 📞 Support

- 🐛 **Bug reports:** Open an issue on GitHub

---

<div align="center">

**Made with ❤️ for the Telegram automation community**

⭐ Star this repo if you find it useful!

</div>
