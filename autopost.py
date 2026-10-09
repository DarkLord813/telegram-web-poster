import os
import logging
import sqlite3
import asyncio
import feedparser
import hashlib
import json
import random
import re
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from contextlib import contextmanager
from urllib.parse import urlparse, urljoin
import pytz
from pytz import all_timezones, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from bs4 import BeautifulSoup
import aiohttp
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ======================== CONFIGURATION ========================
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# Admin IDs
ADMIN_IDS = [
    7713987088,  # Add your admin IDs here
]

# Bot settings
BOT_NAME = "WebAutoPoster™"
CHECK_INTERVAL = 300  # 5 minutes

# Database file
DB_FILE = 'web_auto_poster.db'

# Conversation states
ADD_WEBSITE_URL = 1
ADD_CHANNEL_SELECT_WEBSITE = 2
ADD_CHANNEL_METHOD = 3
ADD_CHANNEL_FORWARD = 4
ADD_CHANNEL_MANUAL = 5
SCHEDULE_WEBSITE = 6
SET_SCHEDULE_TIME = 7
SET_POSTS_PER_DAY = 8
RESCHEDULE_POST = 9
BROADCAST_IMAGE = 10
BROADCAST_CAPTION = 11
BROADCAST_BUTTONS = 12
BROADCAST_CONFIRM = 13
AWAITING_POST_ID = 14
AWAITING_SCHEDULE_TIME = 15
AWAITING_RESCHEDULE_ID = 16
AWAITING_NEW_TIME = 17
AWAITING_CHANNEL_FOR_POST = 18
AWAITING_POST_ACTION = 19
AWAITING_WEBSITE_SELECTION = 20
AWAITING_WEBSITE_SCHEDULE = 21
AWAITING_SCHEDULE_ACTION = 22
AWAITING_SCHEDULE_TIME_SET = 23
AWAITING_POSTS_COUNT = 24
AWAITING_WEBSITE_DELETE = 25
AWAITING_TIMEZONE = 26

# Button constants
CANCEL_BUTTON = '❌ Cancel'
BACK_BUTTON = '🔙 Back'
BACK_TO_MENU = '🔙 Back to Menu'

BTN_MY_WEBSITES = '🌐 My Websites'
BTN_MY_CHANNELS = '📋 My Channels'
BTN_ADD_WEBSITE = '➕ Add Website'
BTN_ADD_CHANNEL = '📤 Add Channel'
BTN_DELETE_WEBSITE = '🗑 Delete Website'
BTN_SET_TIMEZONE = '⏰ Set Timezone'
BTN_VIEW_POSTS = '📊 View Posts'
BTN_MANAGE_POSTS = '📤 Manage Posts'
BTN_SCHEDULE_SETTINGS = '⏰ Schedule Settings'
BTN_HELP = 'ℹ️ Help'
BTN_ADMIN_PANEL = '🔧 Admin Panel'
BTN_SEND_NOW = '📤 Send Now'
BTN_SCHEDULE = '⏰ Schedule'
BTN_SET_TIME = '⏰ Set Time'
BTN_YES_DELETE = '✅ Yes, Delete'

# ======================== LOGGING ========================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================== HEALTH CHECK SERVER ========================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health' or self.path == '/' or self.path == '/healthz':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Silence health check logs

def run_health_server():
    port = int(os.environ.get('PORT', 8080))
    try:
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"✅ Health server listening on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health server error: {e}")

# ======================== TIMEZONE HELPERS ========================

def get_user_timezone(user_id: int) -> str:
    user = db.get_user(user_id)
    return user.get('timezone', 'UTC') if user else 'UTC'

def get_user_timezone_obj(user_id: int):
    user_tz = get_user_timezone(user_id)
    try:
        return pytz.timezone(user_tz)
    except:
        return pytz.UTC

# ======================== HTML HELPERS ========================

async def send_html(update_or_context, text: str, parse_mode: str = 'HTML', **kwargs):
    try:
        if hasattr(update_or_context, 'message'):
            return await update_or_context.message.reply_text(text, parse_mode=parse_mode, **kwargs)
        else:
            return await update_or_context.reply_text(text, parse_mode=parse_mode, **kwargs)
    except Exception as e:
        logger.warning(f"HTML failed: {e}")
        if hasattr(update_or_context, 'message'):
            return await update_or_context.message.reply_text(text, parse_mode=None, **kwargs)
        else:
            return await update_or_context.reply_text(text, parse_mode=None, **kwargs)

async def send_html_photo(update_or_context, photo: str, caption: str = None, **kwargs):
    try:
        if hasattr(update_or_context, 'message'):
            return await update_or_context.message.reply_photo(photo, caption=caption, parse_mode='HTML', **kwargs)
        else:
            return await update_or_context.reply_photo(photo, caption=caption, parse_mode='HTML', **kwargs)
    except Exception as e:
        logger.warning(f"Photo failed: {e}")
        if caption:
            return await send_html(update_or_context, caption, **kwargs)
        return None

# ======================== DATABASE ========================

class Database:
    def __init__(self, db_file: str):
        self.db_file = db_file
        self._init_database()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    full_name TEXT,
                    language_code TEXT,
                    timezone TEXT DEFAULT 'UTC',
                    joined_date TEXT,
                    last_active TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS websites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    website_url TEXT,
                    feed_url TEXT,
                    name TEXT,
                    added_at TEXT,
                    last_checked TEXT,
                    status TEXT DEFAULT 'active',
                    schedule_time TEXT DEFAULT '12:00',
                    posts_per_day INTEGER DEFAULT 3,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    channel_name TEXT,
                    added_by INTEGER,
                    website_id INTEGER,
                    added_at TEXT,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (added_by) REFERENCES users(user_id),
                    FOREIGN KEY (website_id) REFERENCES websites(id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS blog_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_post_id INTEGER,
                    user_id INTEGER,
                    website_id INTEGER,
                    post_id TEXT UNIQUE,
                    title TEXT,
                    link TEXT,
                    description TEXT,
                    content TEXT,
                    thumbnail_url TEXT,
                    image_urls TEXT,
                    published_at TEXT,
                    created_at TEXT,
                    post_hash TEXT UNIQUE,
                    notified INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    sent_count INTEGER DEFAULT 0,
                    auto_sent INTEGER DEFAULT 0,
                    notified_user INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (website_id) REFERENCES websites(id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posted_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT,
                    channel_id TEXT,
                    posted_at TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT,
                    channel_id TEXT,
                    scheduled_time TEXT,
                    priority INTEGER DEFAULT 0,
                    notified INTEGER DEFAULT 0
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    image_id TEXT,
                    caption TEXT,
                    buttons TEXT,
                    total_sent INTEGER DEFAULT 0,
                    total_failed INTEGER DEFAULT 0,
                    sent_at TEXT
                )
            ''')
            
            # Indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_websites_user ON websites(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_channels_website ON channels(website_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_website ON blog_posts(website_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_user ON blog_posts(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_hash ON blog_posts(post_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_pending_time ON pending_posts(scheduled_time)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_user_id ON blog_posts(user_post_id, user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_auto_sent ON blog_posts(auto_sent)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_notified_user ON blog_posts(notified_user)')
            
            conn.commit()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def create_user(self, user_id: int, username: str = '', first_name: str = '', 
                   last_name: str = '', language_code: str = 'en') -> Dict:
        now = datetime.now(pytz.UTC).isoformat()
        full_name = f"{first_name} {last_name}".strip() or first_name or username or str(user_id)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users 
                (user_id, username, first_name, last_name, full_name, language_code, 
                 timezone, joined_date, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'UTC', ?, ?, ?)
            ''', (user_id, username, first_name, last_name, full_name, language_code,
                  now, now, now))
            conn.commit()
            return self.get_user(user_id)
    
    def update_user_timezone(self, user_id: int, timezone: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET timezone = ?, updated_at = ? WHERE user_id = ?',
                         (timezone, datetime.now(pytz.UTC).isoformat(), user_id))
            conn.commit()
    
    def get_user_timezone(self, user_id: int) -> str:
        user = self.get_user(user_id)
        return user.get('timezone', 'UTC') if user else 'UTC'
    
    def get_all_users(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_total_users(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM users')
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def add_website(self, user_id: int, website_url: str, feed_url: str, name: str) -> int:
        now = datetime.now(pytz.UTC).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO websites (user_id, website_url, feed_url, name, added_at, last_checked, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active')
            ''', (user_id, website_url, feed_url, name, now, now))
            conn.commit()
            return cursor.lastrowid
    
    def get_user_websites(self, user_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM websites 
                WHERE user_id = ? AND status = 'active'
                ORDER BY id
            ''', (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_all_websites(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM websites WHERE status = "active"')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_website(self, website_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM websites WHERE id = ?', (website_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_website_by_url(self, user_id: int, url: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM websites WHERE user_id = ? AND website_url = ? AND status = "active"',
                         (user_id, url))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def delete_website(self, website_id: int, user_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE websites SET status = "deleted" WHERE id = ? AND user_id = ?',
                         (website_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def update_website_schedule(self, website_id: int, schedule_time: str, posts_per_day: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE websites SET schedule_time = ?, posts_per_day = ? WHERE id = ?',
                         (schedule_time, posts_per_day, website_id))
            conn.commit()
    
    def update_website_last_checked(self, website_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE websites SET last_checked = ? WHERE id = ?',
                         (datetime.now(pytz.UTC).isoformat(), website_id))
            conn.commit()
    
    def get_websites_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM websites WHERE status = "active"')
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def add_channel(self, channel_id: str, channel_name: str, user_id: int, website_id: int):
        now = datetime.now(pytz.UTC).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO channels (channel_id, channel_name, added_by, website_id, added_at, status)
                VALUES (?, ?, ?, ?, ?, 'active')
            ''', (channel_id, channel_name, user_id, website_id, now))
            conn.commit()
    
    def get_user_channels(self, user_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.*, w.name as website_name, w.schedule_time, w.posts_per_day
                FROM channels c
                JOIN websites w ON c.website_id = w.id
                WHERE c.added_by = ? AND c.status = 'active'
            ''', (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_website_channels(self, website_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM channels WHERE website_id = ? AND status = "active"',
                         (website_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_all_channels(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM channels WHERE status = "active"')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_channels_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM channels WHERE status = "active"')
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def get_next_user_post_id(self, user_id: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT MAX(user_post_id) as max_id FROM blog_posts WHERE user_id = ?',
                         (user_id,))
            row = cursor.fetchone()
            max_id = row['max_id'] if row and row['max_id'] else 0
            return max_id + 1
    
    def save_blog_post(self, post_data: Dict, user_id: int, website_id: int) -> Dict:
        next_id = self.get_next_user_post_id(user_id)
        
        post_id = post_data.get('post_id', f"post_{int(datetime.now(pytz.UTC).timestamp())}")
        title = post_data.get('title', '')
        link = post_data.get('link', '')
        description = post_data.get('description', '')[:500]
        content = post_data.get('content', '')[:2000]
        thumbnail = post_data.get('thumbnail', '')
        images = json.dumps(post_data.get('images', []))
        published_at = post_data.get('published', datetime.now(pytz.UTC).isoformat())
        
        hash_string = f"{title}{link}{content[:500]}"
        post_hash = hashlib.md5(hash_string.encode()).hexdigest()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO blog_posts 
                (user_post_id, user_id, website_id, post_id, title, link, description, content, 
                 thumbnail_url, image_urls, published_at, created_at, post_hash, notified, status, sent_count, auto_sent, notified_user)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', 0, 0, 0)
            ''', (next_id, user_id, website_id, post_id, title, link, description, content,
                  thumbnail, images, published_at, datetime.now(pytz.UTC).isoformat(), post_hash))
            conn.commit()
            
            cursor.execute('SELECT * FROM blog_posts WHERE post_id = ? AND user_id = ?',
                         (post_id, user_id))
            saved_post = cursor.fetchone()
            return dict(saved_post) if saved_post else None
    
    def get_posts_for_user(self, user_id: int, limit: int = 50) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT bp.*, w.name as website_name
                FROM blog_posts bp
                JOIN websites w ON bp.website_id = w.id
                WHERE bp.user_id = ?
                ORDER BY bp.user_post_id DESC LIMIT ?
            ''', (user_id, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_post(self, user_id: int, user_post_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT bp.*, w.name as website_name
                FROM blog_posts bp
                JOIN websites w ON bp.website_id = w.id
                WHERE bp.user_id = ? AND bp.user_post_id = ?
            ''', (user_id, user_post_id))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_post_by_post_id(self, post_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM blog_posts WHERE post_id = ?', (post_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_post_status(self, user_id: int, user_post_id: int, status: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE blog_posts SET status = ? WHERE user_id = ? AND user_post_id = ?',
                         (status, user_id, user_post_id))
            conn.commit()
    
    def increment_post_sent_count(self, user_id: int, user_post_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE blog_posts SET sent_count = sent_count + 1 WHERE user_id = ? AND user_post_id = ?',
                         (user_id, user_post_id))
            conn.commit()
    
    def mark_auto_sent(self, post_id: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE blog_posts SET auto_sent = 1 WHERE post_id = ?', (post_id,))
            conn.commit()
    
    def mark_post_notified_user(self, post_id: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE blog_posts SET notified_user = 1 WHERE post_id = ?', (post_id,))
            conn.commit()
    
    def get_posts_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM blog_posts')
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def get_sent_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM posted_history')
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def schedule_post(self, post_id: str, channel_id: str, scheduled_time: str, priority: int = 0):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO pending_posts (post_id, channel_id, scheduled_time, priority, notified)
                VALUES (?, ?, ?, ?, 0)
            ''', (post_id, channel_id, scheduled_time, priority))
            conn.commit()
    
    def get_pending_posts(self) -> List[Dict]:
        now_utc = datetime.now(pytz.UTC).isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pp.*, bp.title, bp.link, bp.description, bp.thumbnail_url, 
                       c.channel_name, w.name as website_name, bp.user_id, bp.user_post_id
                FROM pending_posts pp
                JOIN blog_posts bp ON pp.post_id = bp.post_id
                JOIN channels c ON pp.channel_id = c.channel_id
                JOIN websites w ON bp.website_id = w.id
                WHERE pp.scheduled_time <= ?
                ORDER BY pp.priority DESC, pp.scheduled_time ASC
            ''', (now_utc,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_all_pending_posts(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pp.*, bp.title, bp.link, c.channel_name, w.name as website_name,
                       bp.user_id, bp.user_post_id
                FROM pending_posts pp
                JOIN blog_posts bp ON pp.post_id = bp.post_id
                JOIN channels c ON pp.channel_id = c.channel_id
                JOIN websites w ON bp.website_id = w.id
                ORDER BY pp.scheduled_time ASC
                LIMIT 50
            ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def mark_as_posted(self, post_id: str, channel_id: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO posted_history (post_id, channel_id, posted_at) VALUES (?, ?, ?)',
                         (post_id, channel_id, datetime.now(pytz.UTC).isoformat()))
            cursor.execute('DELETE FROM pending_posts WHERE post_id = ? AND channel_id = ?',
                         (post_id, channel_id))
            conn.commit()
    
    def reschedule_post(self, pending_id: int, new_time: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE pending_posts SET scheduled_time = ?, notified = 0 WHERE id = ?',
                         (new_time, pending_id))
            conn.commit()
    
    def get_pending_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM pending_posts')
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def save_broadcast(self, admin_id: int, image_id: str, caption: str, buttons: str, sent: int, failed: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO broadcasts (admin_id, image_id, caption, buttons, total_sent, total_failed, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (admin_id, image_id, caption, buttons, sent, failed, datetime.now(pytz.UTC).isoformat()))
            conn.commit()

db = Database(DB_FILE)

# ======================== WEBSITE DETECTOR ========================

class WebsiteDetector:
    @staticmethod
    async def find_feed_url(url: str) -> Optional[str]:
        if not url.startswith('http'):
            url = 'https://' + url
        
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        feed_paths = [
            '/feed', '/rss', '/rss.xml', '/feed.xml', '/atom.xml',
            '/rss/', '/feed/', '/index.xml', '/?feed=rss2',
            '/?feed=atom', '/posts?format=rss', '/blog?format=rss'
        ]
        
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for path in feed_paths:
                    try:
                        test_url = urljoin(base_url, path)
                        async with session.get(test_url) as response:
                            if response.status == 200:
                                content_type = response.headers.get('content-type', '')
                                if 'xml' in content_type or 'rss' in content_type or 'atom' in content_type:
                                    return test_url
                                try:
                                    text = await response.text()
                                    if '<rss' in text.lower() or '<feed' in text.lower() or '<channel' in text.lower():
                                        return test_url
                                except:
                                    pass
                    except:
                        continue
                
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            feed_links = soup.find_all('link', type=re.compile(r'application/(rss|atom)\+xml'))
                            for link in feed_links:
                                href = link.get('href')
                                if href:
                                    return urljoin(base_url, href)
                except:
                    pass
        except Exception as e:
            logger.error(f"Feed detection error: {e}")
        
        return None
    
    @staticmethod
    async def extract_post_data(entry) -> Dict:
        content = entry.get('summary', entry.get('content', entry.get('description', '')))
        if isinstance(content, list):
            content = content[0].value if content and hasattr(content[0], 'value') else ''
        
        if isinstance(content, str):
            soup = BeautifulSoup(content, 'html.parser')
        else:
            soup = BeautifulSoup(str(content), 'html.parser')
        
        thumbnail = None
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            thumbnail = og_image.get('content')
        
        if not thumbnail:
            img = soup.find('img')
            if img and img.get('src'):
                thumbnail = img.get('src')
                if not thumbnail.startswith('http') and entry.get('link'):
                    thumbnail = urljoin(entry.get('link'), thumbnail)
        
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        paragraphs = soup.find_all('p')
        description = ""
        if paragraphs:
            description = paragraphs[0].get_text().strip()
        if not description or len(description) < 50:
            description = text[:300]
        description = re.sub(r'\s+', ' ', description).strip()
        
        images = []
        for img in soup.find_all('img'):
            src = img.get('src')
            if src and src.startswith('http'):
                images.append(src)
        
        return {
            'title': entry.get('title', 'Untitled'),
            'link': entry.get('link', ''),
            'content': text[:2000],
            'description': description[:500],
            'thumbnail': thumbnail,
            'images': images[:5],
            'published': entry.get('published', entry.get('updated', datetime.now(pytz.UTC).isoformat()))
        }

detector = WebsiteDetector()

# ======================== HELPER FUNCTIONS ========================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_or_create_user(update: Update) -> Dict:
    try:
        user = update.effective_user
        existing = db.get_user(user.id)
        if not existing:
            db.create_user(user.id, user.username or '', user.first_name or '',
                          user.last_name or '', user.language_code or 'en')
            existing = db.get_user(user.id)
        return existing
    except Exception as e:
        logger.error(f"Error in get_or_create_user: {e}")
        return None

def get_website_name(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain.startswith('www.'):
        domain = domain[4:]
    name = domain.split('.')[0] if '.' in domain else domain
    return name.capitalize()

def format_post_preview(post: Dict) -> str:
    text = f"📝 <b>{post['title']}</b>\n\n"
    text += f"{post['description'][:300]}...\n\n"
    text += f"🔗 <a href='{post['link']}'>Read More</a>\n"
    text += f"🆔 <b>Post #{post['user_post_id']}</b>\n"
    text += f"🌐 {post['website_name']}\n"
    text += f"📊 Status: {post['status']}\n"
    text += f"📤 Sent: {post['sent_count']} times"
    return text

# ======================== KEYBOARDS ========================

def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    keyboard = [
        [BTN_MY_WEBSITES, BTN_MY_CHANNELS],
        [BTN_ADD_WEBSITE, BTN_ADD_CHANNEL],
        [BTN_DELETE_WEBSITE, BTN_SET_TIMEZONE],
        [BTN_VIEW_POSTS, BTN_MANAGE_POSTS],
        [BTN_SCHEDULE_SETTINGS, BTN_HELP]
    ]
    if is_admin(user_id):
        keyboard.insert(0, [BTN_ADMIN_PANEL])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ['📊 Statistics', '⏰ Pending Posts'],
        ['🔄 Reschedule Post', '📢 Broadcast'],
        [BACK_TO_MENU]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_post_action_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [BTN_SEND_NOW, BTN_SCHEDULE],
        [BACK_TO_MENU]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ======================== CANCEL FUNCTIONS ========================

async def cancel_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_add_website(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_reschedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await send_html(update, "❌ Cancelled.", reply_markup=get_admin_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await send_html(update, "❌ Broadcast cancelled.", reply_markup=get_admin_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_schedule_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_manage_posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
    context.user_data.clear()
    return ConversationHandler.END

# ======================== START COMMAND ========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        user_id = user.id
        
        logger.info(f"Start command from user {user_id}")
        
        user_data = get_or_create_user(update)
        if not user_data:
            await send_html(update, "❌ Error creating user. Please try again later.")
            return
        
        user_tz = get_user_timezone(user_id)
        try:
            user_timezone = pytz.timezone(user_tz)
            current_time = datetime.now(user_timezone)
            time_str = current_time.strftime('%I:%M %p')
        except:
            time_str = datetime.now().strftime('%I:%M %p')
        
        welcome_text = f"""
<b>🌐 Welcome to {BOT_NAME}!</b>

👋 Hello {user.first_name or 'User'}! (🕐 {time_str})

I automatically post new articles from websites to your Telegram channels.

━━━━━━━━━━━━━━━━━━━
<b>📌 How it works:</b>
1️⃣ <b>Add Website</b> - Send any website URL
2️⃣ <b>Add Channel</b> - Link your Telegram channel
3️⃣ <b>Auto-Post</b> - New posts are sent immediately!

<b>⚡ Instant Auto-Post:</b>
• When new posts are detected in your website
• They are sent to your channel <b>immediately</b>
• You get a notification when new posts are found

<b>📤 Post Management:</b>
• View all posts with unique IDs (1, 2, 3...)
• See preview with image + title + description
• Send posts immediately to any channel
• Schedule posts for later

<b>⏰ Timezone:</b> <code>{user_tz}</code>
━━━━━━━━━━━━━━━━━━━

👇 Use the buttons below to get started:
"""
        
        await send_html(update, welcome_text, reply_markup=get_main_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await send_html(update, "❌ An error occurred. Please try again later.")

# ======================== HELP ========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        user_tz = get_user_timezone(user_id)
        
        help_text = f"""
<b>📖 {BOT_NAME} Help</b>

<b>🌐 Adding a Website:</b>
1. Click 'Add Website'
2. Send the website URL
3. I'll auto-detect the RSS feed

<b>📤 Adding a Channel:</b>
1. Click 'Add Channel'
2. Select which website it's for
3. Choose method:
   • Forward - Forward any message from your channel
   • @username - Enter @channelname
   • ID - Enter channel ID

<b>⚡ Auto-Post (Immediate):</b>
• New posts are detected and sent to your channel <b>immediately</b>
• You get a notification when new posts are found

<b>📤 Post Preview:</b>
• Select any post by ID
• See image + title + description preview
• Choose to send now or schedule

<b>🗑 Deleting a Website:</b>
1. Click 'Delete Website'
2. Select the website to delete
3. Confirm deletion

<b>⏰ Setting Timezone:</b>
1. Click 'Set Timezone'
2. Select your region and timezone

<b>📊 View Posts:</b>
• See all posts from your websites

<b>⏰ Your Timezone:</b> <code>{user_tz}</code>
"""
        await send_html(update, help_text)
    except Exception as e:
        logger.error(f"Error in help_command: {e}")
        await send_html(update, "❌ An error occurred. Please try again later.")

# ======================== TIMEZONE ========================

async def set_timezone_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        text = "⏰ <b>Set Your Timezone</b>\n\n"
        text += "Select your region:\n\n"
        
        keyboard = [
            ['🌍 Africa', '🌎 Americas'],
            ['🌏 Asia', '🌏 Asia/Pacific'],
            ['🌍 Europe', '🌐 Other'],
            [CANCEL_BUTTON]
        ]
        
        context.user_data['awaiting_timezone_region'] = True
        
        await send_html(update, text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    except Exception as e:
        logger.error(f"Error in set_timezone_start: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def handle_timezone_region(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text
        
        if text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
            context.user_data.clear()
            return
        
        region_map = {
            '🌍 Africa': ['Africa/Lagos', 'Africa/Cairo', 'Africa/Johannesburg', 'Africa/Nairobi', 'Africa/Casablanca'],
            '🌎 Americas': ['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles', 'America/Toronto', 'America/Sao_Paulo', 'America/Mexico_City'],
            '🌏 Asia': ['Asia/Dubai', 'Asia/Kolkata', 'Asia/Bangkok', 'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Singapore', 'Asia/Jerusalem'],
            '🌏 Asia/Pacific': ['Australia/Sydney', 'Australia/Melbourne', 'Pacific/Auckland'],
            '🌍 Europe': ['Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow', 'Europe/Rome', 'Europe/Madrid'],
            '🌐 Other': ['UTC', 'Etc/GMT+0', 'Etc/GMT-0']
        }
        
        if text in region_map:
            context.user_data['timezone_region'] = text
            context.user_data['awaiting_timezone_region'] = False
            context.user_data['awaiting_timezone_selection'] = True
            
            timezones = region_map[text]
            keyboard = []
            for tz in timezones:
                try:
                    tz_obj = pytz.timezone(tz)
                    now = datetime.now(pytz.UTC)
                    offset = tz_obj.utcoffset(now)
                    if offset:
                        hours = offset.total_seconds() / 3600
                        offset_str = f"{'+' if hours >= 0 else ''}{int(hours)}"
                        if hours % 1 != 0:
                            offset_str = f"{'+' if hours >= 0 else ''}{int(hours)}:{int((hours % 1) * 60):02d}"
                        display = f"{tz} (UTC{offset_str})"
                    else:
                        display = tz
                except:
                    display = tz
                keyboard.append([display])
            keyboard.append([CANCEL_BUTTON])
            
            await send_html(update, "⏰ <b>Select your timezone:</b>",
                          reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        else:
            await send_html(update, "❌ Please select a valid region.",
                          reply_markup=ReplyKeyboardMarkup([
                              ['🌍 Africa', '🌎 Americas'],
                              ['🌏 Asia', '🌏 Asia/Pacific'],
                              ['🌍 Europe', '🌐 Other'],
                              [CANCEL_BUTTON]
                          ], resize_keyboard=True))
    except Exception as e:
        logger.error(f"Error in handle_timezone_region: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def handle_timezone_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text
        
        if text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
            context.user_data.clear()
            return
        
        selected_tz = text.split(' (UTC')[0] if ' (UTC' in text else text
        
        if selected_tz in pytz.all_timezones:
            db.update_user_timezone(user_id, selected_tz)
            context.user_data.clear()
            
            user_tz = pytz.timezone(selected_tz)
            current_time = datetime.now(user_tz)
            time_str = current_time.strftime('%I:%M %p')
            date_str = current_time.strftime('%B %d, %Y')
            
            await send_html(
                update,
                f"✅ <b>Timezone Set!</b>\n\n"
                f"🕐 Timezone: <code>{selected_tz}</code>\n"
                f"📅 Date: {date_str}\n"
                f"⏰ Time: {time_str}",
                reply_markup=get_main_keyboard(user_id)
            )
        else:
            await send_html(update, "❌ Invalid timezone. Please try again.",
                          reply_markup=ReplyKeyboardMarkup([['🌍 Africa', '🌎 Americas'], ['🌏 Asia', '🌏 Asia/Pacific'], ['🌍 Europe', '🌐 Other'], [CANCEL_BUTTON]], resize_keyboard=True))
    except Exception as e:
        logger.error(f"Error in handle_timezone_selection: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== WEBSITES ========================

async def websites_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        websites = db.get_user_websites(user_id)
        
        if not websites:
            await send_html(update, "🌐 No websites added yet.\n\nClick 'Add Website' to get started!")
            return
        
        user_tz = get_user_timezone(user_id)
        text = "🌐 <b>Your Websites</b>\n\n"
        for site in websites:
            text += f"✅ <b>{site['name']}</b>\n"
            text += f"   🔗 {site['website_url']}\n"
            text += f"   🆔 ID: <code>{site['id']}</code>\n"
            text += f"   🕐 {site['schedule_time']} | 📊 {site['posts_per_day']}/day\n\n"
        
        text += f"\n⏰ Your Timezone: <code>{user_tz}</code>"
        await send_html(update, text)
    except Exception as e:
        logger.error(f"Error in websites_command: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== CHANNELS ========================

async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        channels = db.get_user_channels(user_id)
        
        if not channels:
            await send_html(update, "📭 No channels added yet.\n\nAdd a website first, then add channels!")
            return
        
        user_tz = get_user_timezone(user_id)
        text = "📋 <b>Your Channels</b>\n\n"
        for channel in channels:
            text += f"✅ <b>{channel['channel_name']}</b>\n"
            text += f"   🌐 {channel['website_name']}\n"
            text += f"   🕐 {channel['schedule_time']} | 📊 {channel['posts_per_day']}/day\n"
            text += f"   🆔 <code>{channel['channel_id']}</code>\n\n"
        
        text += f"\n⏰ Your Timezone: <code>{user_tz}</code>"
        await send_html(update, text)
    except Exception as e:
        logger.error(f"Error in channels_command: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== DELETE WEBSITE ========================

async def delete_website_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        websites = db.get_user_websites(user_id)
        
        if not websites:
            await send_html(update, "🌐 No websites to delete.", reply_markup=get_main_keyboard(user_id))
            return
        
        text = "🗑 <b>Delete Website</b>\n\n"
        text += "Select website to delete by entering its number:\n\n"
        
        for i, site in enumerate(websites, 1):
            text += f"{i}. <b>{site['name']}</b>\n"
            text += f"   🔗 {site['website_url']}\n\n"
        
        text += f"\n📝 Send the website number or click {CANCEL_BUTTON}"
        
        context.user_data['awaiting_website_delete'] = True
        context.user_data['websites_list'] = websites
        
        await send_html(update, text, reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
    except Exception as e:
        logger.error(f"Error in delete_website_start: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def handle_website_delete_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        if text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
            context.user_data.clear()
            return
        
        if not text.isdigit():
            await send_html(update, f"❌ Invalid. Click {CANCEL_BUTTON} to cancel")
            return
        
        website_index = int(text) - 1
        websites = context.user_data.get('websites_list', [])
        
        if website_index < 0 or website_index >= len(websites):
            await send_html(update, f"❌ Invalid number. Click {CANCEL_BUTTON} to cancel")
            return
        
        selected_website = websites[website_index]
        context.user_data['selected_website_delete'] = selected_website['id']
        context.user_data['awaiting_website_delete'] = False
        context.user_data['awaiting_website_delete_confirm'] = True
        
        keyboard = [[BTN_YES_DELETE], [CANCEL_BUTTON]]
        
        await send_html(
            update,
            f"🗑 <b>Delete Website</b>\n\n"
            f"Are you sure you want to delete <b>{selected_website['name']}</b>?\n\n"
            f"⚠️ This will stop all auto-posts from this website!",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
    except Exception as e:
        logger.error(f"Error in handle_website_delete_selection: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def handle_website_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        if text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
            context.user_data.clear()
            return
        
        if text == BTN_YES_DELETE:
            website_id = context.user_data.get('selected_website_delete')
            if not website_id:
                await send_html(update, "❌ No website selected.", reply_markup=get_main_keyboard(user_id))
                return
            
            success = db.delete_website(website_id, user_id)
            context.user_data.clear()
            
            if success:
                await send_html(update, "✅ Website deleted successfully!", reply_markup=get_main_keyboard(user_id))
            else:
                await send_html(update, "❌ Failed to delete.", reply_markup=get_main_keyboard(user_id))
        else:
            await send_html(update, "❌ Please select Yes or Cancel", reply_markup=ReplyKeyboardMarkup([[BTN_YES_DELETE], [CANCEL_BUTTON]], resize_keyboard=True))
    except Exception as e:
        logger.error(f"Error in handle_website_delete_confirm: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== VIEW POSTS ========================

async def view_posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        posts = db.get_posts_for_user(user_id, 50)
        
        if not posts:
            await send_html(update, "📝 No posts found yet.\n\nAdd websites and wait for new content!",
                          reply_markup=get_main_keyboard(user_id))
            return
        
        user_tz = get_user_timezone(user_id)
        text = "📝 <b>Your Posts</b>\n\n"
        for post in posts:
            date = post['published_at'][:10] if post['published_at'] else "Unknown"
            status = "📌" if post['status'] == 'pending' else "✅"
            auto_sent = " 🤖 Auto" if post.get('auto_sent', 0) == 1 else ""
            sent_count = f" 📤 Sent: {post['sent_count']}" if post['sent_count'] > 0 else ""
            text += f"{status} <b>#{post['user_post_id']}</b>{auto_sent}{sent_count}\n"
            text += f"📌 {post['title'][:40]}\n"
            text += f"   🌐 {post['website_name']}\n"
            text += f"   📅 {date}\n\n"
        
        text += f"\n⏰ Your Timezone: <code>{user_tz}</code>"
        await send_html(update, text[:4000], reply_markup=get_main_keyboard(user_id))
    except Exception as e:
        logger.error(f"Error in view_posts: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== MANAGE POSTS ========================

async def manage_posts_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        posts = db.get_posts_for_user(user_id, 30)
        
        if not posts:
            await send_html(update, "📭 No posts available.\n\nAdd websites and wait for content!",
                          reply_markup=get_main_keyboard(user_id))
            return
        
        text = "📤 <b>Manage Posts</b>\n\n"
        text += "Enter the <b>Post ID</b> you want to manage:\n\n"
        text += "📋 <b>Available Posts:</b>\n"
        
        for post in posts[:15]:
            status_icon = "📌" if post['status'] == 'pending' else "✅"
            text += f"{status_icon} <b>#{post['user_post_id']}</b> - {post['title'][:40]}\n"
        
        text += f"\n\n📝 Send the <b>Post ID number</b> or click {CANCEL_BUTTON}"
        
        context.user_data['awaiting_post_id'] = True
        await send_html(update, text, reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
    except Exception as e:
        logger.error(f"Error in manage_posts_start: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def handle_post_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        logger.info(f"Handling post ID input: {text} from user {user_id}")
        
        if text == CANCEL_BUTTON:
            await cancel_manage_posts(update, context)
            return
        
        if not text.isdigit():
            await send_html(update, f"❌ Invalid Post ID. Click {CANCEL_BUTTON} to cancel",
                          reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
            return
        
        post_id = int(text)
        post = db.get_post(user_id, post_id)
        
        if not post:
            await send_html(update, f"❌ Post #{post_id} not found. Click {CANCEL_BUTTON} to cancel",
                          reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
            return
        
        context.user_data['selected_post_id'] = post_id
        context.user_data['selected_post'] = post
        context.user_data['awaiting_post_id'] = False
        
        preview_text = format_post_preview(post)
        
        if post['thumbnail_url']:
            await send_html_photo(update, photo=post['thumbnail_url'], caption=preview_text,
                                reply_markup=get_post_action_keyboard())
        else:
            await send_html(update, preview_text, reply_markup=get_post_action_keyboard())
    except Exception as e:
        logger.error(f"Error in handle_post_id_input: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== SEND NOW / SCHEDULE ========================

async def handle_send_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        post_id = context.user_data.get('selected_post_id')
        post = context.user_data.get('selected_post')
        
        if not post:
            await send_html(update, "❌ No post selected.", reply_markup=get_main_keyboard(user_id))
            return
        
        channels = db.get_user_channels(user_id)
        
        if not channels:
            await send_html(update, "❌ No channels found. Add a channel first!",
                          reply_markup=get_post_action_keyboard())
            return
        
        text = f"📤 <b>Send Post #{post_id} to Channel</b>\n\n"
        text += f"📌 {post['title'][:50]}\n\n"
        text += "Select a channel:"
        
        context.user_data['awaiting_channel_for_post'] = True
        context.user_data['post_action'] = 'send'
        context.user_data['channels_list'] = channels
        
        keyboard = []
        for channel in channels:
            keyboard.append([f"📢 {channel['channel_name'][:30]}"])
        keyboard.append(['🔙 Back'])
        
        await send_html(update, text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    except Exception as e:
        logger.error(f"Error in handle_send_now: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def handle_schedule_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        post_id = context.user_data.get('selected_post_id')
        post = context.user_data.get('selected_post')
        
        if not post:
            await send_html(update, "❌ No post selected.", reply_markup=get_main_keyboard(user_id))
            return
        
        channels = db.get_user_channels(user_id)
        
        if not channels:
            await send_html(update, "❌ No channels found.", reply_markup=get_post_action_keyboard())
            return
        
        text = f"⏰ <b>Schedule Post #{post_id}</b>\n\n"
        text += f"📌 {post['title'][:50]}\n\n"
        text += "Select a channel:"
        
        context.user_data['awaiting_channel_for_post'] = True
        context.user_data['post_action'] = 'schedule'
        context.user_data['channels_list'] = channels
        
        keyboard = []
        for channel in channels:
            keyboard.append([f"📢 {channel['channel_name'][:30]}"])
        keyboard.append(['🔙 Back'])
        
        await send_html(update, text, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    except Exception as e:
        logger.error(f"Error in handle_schedule_post: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== CHANNEL SELECTION ========================

async def handle_channel_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_display: str) -> None:
    try:
        user_id = update.effective_user.id
        post_id = context.user_data.get('selected_post_id')
        post = context.user_data.get('selected_post')
        action = context.user_data.get('post_action')
        channels = context.user_data.get('channels_list', [])
        
        if not post:
            await send_html(update, "❌ No post selected.", reply_markup=get_main_keyboard(user_id))
            return
        
        if channel_display.startswith('📢 '):
            channel_display = channel_display[2:].strip()
        
        selected_channel = None
        for channel in channels:
            if channel['channel_name'][:30] == channel_display or channel['channel_name'] == channel_display:
                selected_channel = channel
                break
        
        if not selected_channel:
            for channel in channels:
                if channel_display in channel['channel_name']:
                    selected_channel = channel
                    break
        
        if not selected_channel:
            keyboard = []
            for channel in channels:
                keyboard.append([f"📢 {channel['channel_name'][:30]}"])
            keyboard.append(['🔙 Back'])
            await send_html(update, "❌ Channel not found. Select from list:",
                          reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return
        
        channel_id = selected_channel['channel_id']
        
        if action == 'send':
            try:
                message = f"📝 <b>{post['title']}</b>\n\n"
                message += f"{post['description'][:300]}...\n\n"
                message += f"🔗 <a href='{post['link']}'>Read More</a>"
                
                if post['thumbnail_url']:
                    await context.bot.send_photo(chat_id=channel_id, photo=post['thumbnail_url'],
                                                caption=message, parse_mode='HTML')
                else:
                    await context.bot.send_message(chat_id=channel_id, text=message, parse_mode='HTML')
                
                db.update_post_status(user_id, post_id, 'sent')
                db.increment_post_sent_count(user_id, post_id)
                db.mark_as_posted(post['post_id'], channel_id)
                db.mark_auto_sent(post['post_id'])
                
                context.user_data.clear()
                await send_html(update, f"✅ Post #{post_id} sent to {selected_channel['channel_name']}!",
                              reply_markup=get_main_keyboard(user_id))
            except Exception as e:
                logger.error(f"Error sending post: {e}")
                await send_html(update, f"❌ Error: {str(e)[:100]}", reply_markup=get_main_keyboard(user_id))
        
        elif action == 'schedule':
            context.user_data['schedule_channel_id'] = channel_id
            context.user_data['awaiting_channel_for_post'] = False
            context.user_data['awaiting_schedule_time'] = True
            context.user_data['channels_list'] = None
            
            user_tz = get_user_timezone(user_id)
            
            await send_html(
                update,
                f"⏰ <b>Schedule Post #{post_id}</b>\n\n"
                f"📢 Channel: <code>{selected_channel['channel_name']}</code>\n\n"
                f"Send the time (24h format) in your timezone:\n"
                f"⏰ Timezone: <code>{user_tz}</code>\n"
                f"Example: <code>14:30</code>\n\n"
                f"Or click {CANCEL_BUTTON}",
                reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True)
            )
    except Exception as e:
        logger.error(f"Error in handle_channel_selection: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== SCHEDULE TIME ========================

async def handle_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        if text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
            context.user_data.clear()
            return
        
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', text):
            await send_html(update, f"❌ Invalid time. Use HH:MM. Click {CANCEL_BUTTON} to cancel",
                          reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
            return
        
        post_id = context.user_data.get('selected_post_id')
        channel_id = context.user_data.get('schedule_channel_id')
        post = context.user_data.get('selected_post')
        
        if not post_id or not channel_id or not post:
            await send_html(update, "❌ Missing data. Start over.", reply_markup=get_main_keyboard(user_id))
            return
        
        user_tz = get_user_timezone(user_id)
        hour, minute = map(int, text.split(':'))
        
        try:
            user_timezone = pytz.timezone(user_tz)
            now_user = datetime.now(user_timezone)
            scheduled_user = now_user.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if scheduled_user < now_user:
                scheduled_user += timedelta(days=1)
            
            scheduled_utc = scheduled_user.astimezone(pytz.UTC)
            scheduled_time_str = scheduled_utc.isoformat()
            display_time = scheduled_user.strftime('%Y-%m-%d %H:%M')
        except Exception as e:
            logger.error(f"Timezone error: {e}")
            now_utc = datetime.now(pytz.UTC)
            scheduled_utc = now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if scheduled_utc < now_utc:
                scheduled_utc += timedelta(days=1)
            scheduled_time_str = scheduled_utc.isoformat()
            display_time = scheduled_utc.strftime('%Y-%m-%d %H:%M')
        
        db.schedule_post(post['post_id'], channel_id, scheduled_time_str, priority=0)
        db.update_post_status(user_id, post_id, 'scheduled')
        
        context.user_data.clear()
        
        await send_html(
            update,
            f"✅ <b>Post #{post_id} Scheduled!</b>\n\n"
            f"📌 {post['title'][:50]}\n"
            f"📢 Channel: <code>{channel_id}</code>\n"
            f"🕐 Time: {text} ({user_tz})\n"
            f"📅 Date: {display_time}",
            reply_markup=get_main_keyboard(user_id)
        )
    except Exception as e:
        logger.error(f"Error in handle_schedule_time: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== ADD WEBSITE ========================

async def add_website_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await send_html(
        update,
        "🌐 <b>Add Website</b>\n\n"
        "Send me the website URL:\n"
        "• <code>https://example.com</code>\n"
        "• <code>pspgamers5.blogspot.com</code>\n\n"
        "I'll auto-detect the RSS feed!",
        reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True)
    )
    return ADD_WEBSITE_URL

async def add_website_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message.text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
            return ConversationHandler.END
        
        website_url = update.message.text.strip()
        
        if not website_url.startswith('http'):
            website_url = 'https://' + website_url
        
        await send_html(update, "🔍 Detecting feed...")
        
        existing = db.get_website_by_url(update.effective_user.id, website_url)
        if existing:
            await send_html(update, f"⚠️ Already added!\n🌐 {existing['name']}",
                          reply_markup=get_main_keyboard(update.effective_user.id))
            return ConversationHandler.END
        
        feed_url = await detector.find_feed_url(website_url)
        
        if feed_url:
            name = get_website_name(website_url)
            website_id = db.add_website(update.effective_user.id, website_url, feed_url, name)
            
            await send_html(
                update,
                f"✅ <b>Website Added!</b>\n\n"
                f"🌐 <b>{name}</b>\n"
                f"🔗 {website_url}\n"
                f"📡 Feed: <code>{feed_url}</code>\n"
                f"🆔 Website ID: <code>{website_id}</code>\n\n"
                f"Now add a channel! 📤",
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
            
            await check_website_feed(website_id, update.effective_user.id)
            return ConversationHandler.END
        else:
            await send_html(
                update,
                "❌ <b>Could not find RSS feed</b>\n\n"
                "Try:\n"
                "• Add <code>/feed</code> to URL\n"
                "• Or send the feed URL directly\n\n"
                f"Send another URL or click {CANCEL_BUTTON}",
                reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True)
            )
            return ADD_WEBSITE_URL
    except Exception as e:
        logger.error(f"Error in add_website_url: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")
        return ConversationHandler.END

# ======================== ADD CHANNEL ========================

async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        user_id = update.effective_user.id
        websites = db.get_user_websites(user_id)
        
        if not websites:
            await send_html(update, "❌ Add a website first!", reply_markup=get_main_keyboard(user_id))
            return ConversationHandler.END
        
        text = "🌐 <b>Select website for this channel:</b>\n\n"
        for i, site in enumerate(websites, 1):
            text += f"{i}. {site['name']} (ID: {site['id']})\n"
        
        text += f"\n📝 Send the website number or click {CANCEL_BUTTON}"
        
        context.user_data['awaiting_website_selection'] = True
        context.user_data['websites_list'] = websites
        
        await send_html(update, text, reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
        return ADD_CHANNEL_SELECT_WEBSITE
    except Exception as e:
        logger.error(f"Error in add_channel_start: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")
        return ConversationHandler.END

async def select_website_for_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        text = update.message.text.strip()
        
        if text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
            context.user_data.clear()
            return ConversationHandler.END
        
        if not text.isdigit():
            await send_html(update, f"❌ Invalid. Click {CANCEL_BUTTON} to cancel",
                          reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
            return ADD_CHANNEL_SELECT_WEBSITE
        
        website_index = int(text) - 1
        websites = context.user_data.get('websites_list', [])
        
        if website_index < 0 or website_index >= len(websites):
            await send_html(update, f"❌ Invalid. Click {CANCEL_BUTTON} to cancel",
                          reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
            return ADD_CHANNEL_SELECT_WEBSITE
        
        website = websites[website_index]
        context.user_data['website_for_channel'] = website['id']
        context.user_data['awaiting_website_selection'] = False
        
        keyboard = [
            ['📤 Add via Forward'],
            ['✏️ Enter @username'],
            ['🔢 Enter Channel ID'],
            [CANCEL_BUTTON]
        ]
        
        await send_html(
            update,
            f"📤 <b>Add Channel</b>\n\n"
            f"Website: <b>{website['name']}</b>\n\n"
            f"Choose method:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return ADD_CHANNEL_METHOD
    except Exception as e:
        logger.error(f"Error in select_website_for_channel: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")
        return ConversationHandler.END

async def add_channel_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message.text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
            context.user_data.clear()
            return ConversationHandler.END
        
        context.user_data['add_channel_method'] = 'forward'
        
        await send_html(
            update,
            "📤 <b>Add Channel via Forward</b>\n\n"
            "Forward any message from your channel to me.\n\n"
            f"⚠️ Make sure I'm in the channel!\n\nClick {CANCEL_BUTTON} to cancel",
            reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True)
        )
        return ADD_CHANNEL_FORWARD
    except Exception as e:
        logger.error(f"Error in add_channel_forward: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")
        return ConversationHandler.END

async def add_channel_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message.text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
            context.user_data.clear()
            return ConversationHandler.END
        
        context.user_data['add_channel_method'] = 'username'
        
        await send_html(
            update,
            "✏️ <b>Add Channel via @username</b>\n\n"
            "Send me the channel username:\n"
            "Example: <code>@channel_name</code>\n\n"
            f"Click {CANCEL_BUTTON} to cancel",
            reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True)
        )
        return ADD_CHANNEL_MANUAL
    except Exception as e:
        logger.error(f"Error in add_channel_username: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")
        return ConversationHandler.END

async def add_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message.text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
            context.user_data.clear()
            return ConversationHandler.END
        
        context.user_data['add_channel_method'] = 'id'
        
        await send_html(
            update,
            "🔢 <b>Add Channel via ID</b>\n\n"
            "Send me the channel ID:\n"
            "Example: <code>-1001234567890</code>\n\n"
            f"Click {CANCEL_BUTTON} to cancel",
            reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True)
        )
        return ADD_CHANNEL_MANUAL
    except Exception as e:
        logger.error(f"Error in add_channel_id: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")
        return ConversationHandler.END

async def process_channel_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message.text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
            context.user_data.clear()
            return ConversationHandler.END
        
        website_id = context.user_data.get('website_for_channel')
        
        if not website_id:
            await send_html(update, "❌ No website selected.", reply_markup=get_main_keyboard(update.effective_user.id))
            return ConversationHandler.END
        
        if not update.message.forward_origin:
            await send_html(update, "❌ Please forward a message from your channel.")
            return ADD_CHANNEL_FORWARD
        
        try:
            chat = update.message.forward_origin.chat
            channel_id = str(chat.id)
            channel_name = chat.title or "Unknown Channel"
            
            db.add_channel(channel_id, channel_name, update.effective_user.id, website_id)
            
            website = db.get_website(website_id)
            await send_html(
                update,
                f"✅ <b>Channel Added!</b>\n\n"
                f"📢 {channel_name}\n"
                f"🌐 {website['name'] if website else 'Unknown'}\n"
                f"🆔 <code>{channel_id}</code>\n\n"
                f"Auto-posts will start immediately when new posts are detected!",
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
            context.user_data.clear()
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Error processing forward: {e}")
            await send_html(update, f"❌ Failed: {str(e)[:100]}",
                          reply_markup=get_main_keyboard(update.effective_user.id))
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in process_channel_forward: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")
        return ConversationHandler.END

async def process_channel_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        if update.message.text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))
            context.user_data.clear()
            return ConversationHandler.END
        
        website_id = context.user_data.get('website_for_channel')
        channel_input = update.message.text.strip()
        
        if not website_id:
            await send_html(update, "❌ No website selected.", reply_markup=get_main_keyboard(update.effective_user.id))
            return ConversationHandler.END
        
        try:
            if channel_input.startswith('@'):
                try:
                    chat = await context.bot.get_chat(channel_input)
                    channel_id = str(chat.id)
                    channel_name = chat.title or channel_input
                except Exception as e:
                    await send_html(update, f"❌ Could not find {channel_input}. Make sure I'm in it.",
                                  reply_markup=get_main_keyboard(update.effective_user.id))
                    return ConversationHandler.END
            else:
                try:
                    chat = await context.bot.get_chat(int(channel_input))
                    channel_id = str(chat.id)
                    channel_name = chat.title or channel_input
                except:
                    chat = await context.bot.get_chat(channel_input)
                    channel_id = str(chat.id)
                    channel_name = chat.title or channel_input
            
            db.add_channel(channel_id, channel_name, update.effective_user.id, website_id)
            
            website = db.get_website(website_id)
            await send_html(
                update,
                f"✅ <b>Channel Added!</b>\n\n"
                f"📢 {channel_name}\n"
                f"🌐 {website['name'] if website else 'Unknown'}\n"
                f"🆔 <code>{channel_id}</code>\n\n"
                f"Auto-posts will start immediately when new posts are detected!",
                reply_markup=get_main_keyboard(update.effective_user.id)
            )
            context.user_data.clear()
            return ConversationHandler.END
        except Exception as e:
            await send_html(update, f"❌ Error: {str(e)[:100]}",
                          reply_markup=get_main_keyboard(update.effective_user.id))
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in process_channel_manual: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")
        return ConversationHandler.END

# ======================== SCHEDULE SETTINGS ========================

async def schedule_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        websites = db.get_user_websites(user_id)
        
        if not websites:
            await send_html(update, "🌐 No websites found. Add one first!", reply_markup=get_main_keyboard(user_id))
            return
        
        user_tz = get_user_timezone(user_id)
        text = "⏰ <b>Select website to adjust schedule:</b>\n\n"
        for i, site in enumerate(websites, 1):
            text += f"{i}. {site['name']} - 🕐 {site['schedule_time']} | 📊 {site['posts_per_day']}/day\n"
        
        text += f"\n📝 Send website number or click {CANCEL_BUTTON}"
        text += f"\n\n⏰ Your Timezone: <code>{user_tz}</code>"
        
        context.user_data['awaiting_website_schedule'] = True
        context.user_data['websites_list'] = websites
        
        await send_html(update, text, reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
    except Exception as e:
        logger.error(f"Error in schedule_settings: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def handle_website_schedule_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        if text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
            context.user_data.clear()
            return
        
        if not text.isdigit():
            await send_html(update, f"❌ Invalid. Click {CANCEL_BUTTON} to cancel")
            return
        
        website_index = int(text) - 1
        websites = context.user_data.get('websites_list', [])
        
        if website_index < 0 or website_index >= len(websites):
            await send_html(update, f"❌ Invalid. Click {CANCEL_BUTTON} to cancel")
            return
        
        website = websites[website_index]
        context.user_data['schedule_website_id'] = website['id']
        context.user_data['awaiting_website_schedule'] = False
        
        user_tz = get_user_timezone(user_id)
        
        keyboard = [
            [BTN_SET_TIME],
            [f'📊 Posts/Day: {website["posts_per_day"]}'],
            ['🔙 Back']
        ]
        
        await send_html(
            update,
            f"⏰ <b>Schedule Settings</b>\n\n"
            f"🌐 {website['name']}\n"
            f"🕐 Time: {website['schedule_time']}\n"
            f"📊 Posts/Day: {website['posts_per_day']}\n\n"
            f"⏰ Your Timezone: <code>{user_tz}</code>",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        context.user_data['awaiting_schedule_action'] = True
    except Exception as e:
        logger.error(f"Error in handle_website_schedule_selection: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def handle_schedule_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text
        website_id = context.user_data.get('schedule_website_id')
        
        if text == '🔙 Back':
            context.user_data.clear()
            await schedule_settings(update, context)
            return
        
        if text == BTN_SET_TIME:
            user_tz = get_user_timezone(user_id)
            context.user_data['awaiting_schedule_time_set'] = True
            await send_html(
                update,
                f"⌚️ <b>Set Posting Time</b>\n\n"
                f"Send new time (24h format) in your timezone:\n"
                f"⏰ Timezone: <code>{user_tz}</code>\n"
                f"Example: <code>14:30</code>\n\n"
                f"Or click {CANCEL_BUTTON}",
                reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True)
            )
            return
        
        if text.startswith('📊 Posts/Day:'):
            keyboard = [
                ['1/day', '2/day', '3/day'],
                ['5/day', '10/day'],
                ['🔙 Back']
            ]
            context.user_data['awaiting_posts_count'] = True
            await send_html(update, "📊 <b>Select posts per day:</b>",
                          reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
            return
        
        if context.user_data.get('awaiting_schedule_time_set'):
            if text == CANCEL_BUTTON:
                await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
                context.user_data.clear()
                return
            
            if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', text):
                await send_html(update, "❌ Invalid time format. Use HH:MM")
                return
            
            website = db.get_website(website_id)
            if website:
                db.update_website_schedule(website_id, text, website['posts_per_day'])
                context.user_data['awaiting_schedule_time_set'] = False
                await send_html(update, f"✅ Schedule updated to {text}!",
                              reply_markup=get_main_keyboard(user_id))
            return
        
        if context.user_data.get('awaiting_posts_count'):
            if text == CANCEL_BUTTON:
                await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
                context.user_data.clear()
                return
            
            count_text = text.replace('/day', '').strip()
            if count_text.isdigit():
                count = int(count_text)
                website = db.get_website(website_id)
                if website:
                    db.update_website_schedule(website_id, website['schedule_time'], count)
                    context.user_data['awaiting_posts_count'] = False
                    await send_html(update, f"✅ Updated! {count} posts per day",
                                  reply_markup=get_main_keyboard(user_id))
            return
    except Exception as e:
        logger.error(f"Error in handle_schedule_action: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== ADMIN FUNCTIONS ========================

async def admin_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        total_users = db.get_total_users()
        total_websites = db.get_websites_count()
        total_channels = db.get_channels_count()
        total_posts = db.get_posts_count()
        pending_posts = db.get_pending_count()
        total_sent = db.get_sent_count()
        
        text = f"""
<b>📊 {BOT_NAME} Statistics</b>

👥 Total Users: {total_users}
🌐 Active Websites: {total_websites}
📢 Active Channels: {total_channels}

📝 Total Posts: {total_posts}
⏳ Pending: {pending_posts}
✅ Sent: {total_sent}

⏰ Check Interval: {CHECK_INTERVAL//60} minutes
⚡ Auto-Post: IMMEDIATE
"""
        await send_html(update, text, reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"Error in admin_statistics: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def view_pending_posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        pending = db.get_all_pending_posts()
        
        if not pending:
            await send_html(update, "✅ No pending posts.", reply_markup=get_admin_keyboard())
            return
        
        text = "⏰ <b>Pending Posts</b>\n\n"
        for p in pending[:20]:
            try:
                user_tz = get_user_timezone(p['user_id'])
                user_timezone = pytz.timezone(user_tz)
                scheduled_dt = datetime.fromisoformat(p['scheduled_time'])
                if scheduled_dt.tzinfo is None:
                    scheduled_dt = pytz.UTC.localize(scheduled_dt)
                user_dt = scheduled_dt.astimezone(user_timezone)
                time_display = user_dt.strftime('%Y-%m-%d %H:%M')
            except:
                time_display = p['scheduled_time'][:16]
            
            text += f"📌 {p['title'][:30]}\n"
            text += f"   📢 {p['channel_name']}\n"
            text += f"   🕐 {time_display}\n"
            text += f"   🆔 ID: <code>{p['id']}</code>\n\n"
        
        await send_html(update, text[:4000], reply_markup=get_admin_keyboard())
    except Exception as e:
        logger.error(f"Error in view_pending_posts: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def reschedule_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        pending = db.get_all_pending_posts()
        
        if not pending:
            await send_html(update, "✅ No pending posts.", reply_markup=get_admin_keyboard())
            return
        
        text = "🔄 <b>Reschedule Post</b>\n\n"
        text += "Enter the <b>Pending ID</b>:\n\n"
        
        for p in pending[:15]:
            text += f"🆔 <b>{p['id']}</b> - {p['title'][:40]}\n"
            text += f"   📢 {p['channel_name']}\n\n"
        
        text += f"\n📝 Send the ID or click {CANCEL_BUTTON}"
        
        context.user_data['awaiting_reschedule_id'] = True
        await send_html(update, text, reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
    except Exception as e:
        logger.error(f"Error in reschedule_post_start: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def handle_reschedule_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        if text == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_admin_keyboard())
            context.user_data.clear()
            return
        
        if not text.isdigit():
            await send_html(update, f"❌ Invalid. Click {CANCEL_BUTTON} to cancel",
                          reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
            return
        
        pending_id = int(text)
        pending = db.get_all_pending_posts()
        selected = None
        for p in pending:
            if p['id'] == pending_id:
                selected = p
                break
        
        if not selected:
            await send_html(update, f"❌ ID {pending_id} not found. Click {CANCEL_BUTTON} to cancel",
                          reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
            return
        
        context.user_data['reschedule_pending_id'] = pending_id
        user_tz = get_user_timezone(user_id)
        
        await send_html(
            update,
            f"🔄 <b>Reschedule Post</b>\n\n"
            f"📌 {selected['title']}\n"
            f"📢 {selected['channel_name']}\n"
            f"🕐 Current: {selected['scheduled_time'][:16]}\n\n"
            f"Send new time (24h format) in your timezone:\n"
            f"⏰ Timezone: <code>{user_tz}</code>\n"
            f"Example: <code>14:30</code>\n\n"
            f"Or click {CANCEL_BUTTON}",
            reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True)
        )
        
        context.user_data['awaiting_new_time'] = True
        context.user_data['awaiting_reschedule_id'] = False
    except Exception as e:
        logger.error(f"Error in handle_reschedule_id_input: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

async def process_reschedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        pending_id = context.user_data.get('reschedule_pending_id')
        
        if not pending_id:
            await send_html(update, "❌ No post selected.", reply_markup=get_admin_keyboard())
            context.user_data.clear()
            return
        
        new_time = update.message.text.strip()
        
        if new_time == CANCEL_BUTTON:
            await send_html(update, "❌ Cancelled.", reply_markup=get_admin_keyboard())
            context.user_data.clear()
            return
        
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', new_time):
            await send_html(update, f"❌ Invalid time. Use HH:MM",
                          reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
            return
        
        user_tz = get_user_timezone(user_id)
        hour, minute = map(int, new_time.split(':'))
        
        try:
            user_timezone = pytz.timezone(user_tz)
            now_user = datetime.now(user_timezone)
            scheduled_user = now_user.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if scheduled_user < now_user:
                scheduled_user += timedelta(days=1)
            
            scheduled_utc = scheduled_user.astimezone(pytz.UTC)
            scheduled_time_str = scheduled_utc.isoformat()
        except Exception as e:
            logger.error(f"Timezone error: {e}")
            now_utc = datetime.now(pytz.UTC)
            scheduled_utc = now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if scheduled_utc < now_utc:
                scheduled_utc += timedelta(days=1)
            scheduled_time_str = scheduled_utc.isoformat()
        
        db.reschedule_post(pending_id, scheduled_time_str)
        await send_html(update, f"✅ Post rescheduled to {new_time}!", reply_markup=get_admin_keyboard())
        context.user_data.clear()
    except Exception as e:
        logger.error(f"Error in process_reschedule_time: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== BROADCAST ========================

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    await send_html(
        update,
        "📢 <b>Broadcast Message</b>\n\n"
        "Send image or /skip to continue without image.\n\n"
        f"Click {CANCEL_BUTTON} to cancel.",
        reply_markup=ReplyKeyboardMarkup([['/skip', CANCEL_BUTTON]], resize_keyboard=True)
    )
    return BROADCAST_IMAGE

async def broadcast_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    if update.message.photo:
        photo = update.message.photo[-1]
        context.user_data['broadcast_image'] = photo.file_id
    elif update.message.text == '/skip':
        context.user_data['broadcast_image'] = None
    elif update.message.text == CANCEL_BUTTON:
        await send_html(update, "❌ Cancelled.", reply_markup=get_admin_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await send_html(update, "Send photo or /skip:")
        return BROADCAST_IMAGE
    
    await send_html(update, "Now send the caption:",
                  reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
    return BROADCAST_CAPTION

async def broadcast_caption(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    if update.message.text == CANCEL_BUTTON:
        await send_html(update, "❌ Cancelled.", reply_markup=get_admin_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    
    context.user_data['broadcast_caption'] = update.message.text
    await send_html(update, "Send the final message text:",
                  reply_markup=ReplyKeyboardMarkup([[CANCEL_BUTTON]], resize_keyboard=True))
    return BROADCAST_CONFIRM

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    
    if update.message.text == CANCEL_BUTTON:
        await send_html(update, "❌ Cancelled.", reply_markup=get_admin_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    
    users = db.get_all_users()
    total_users = len(users)
    sent_count = 0
    failed_count = 0
    
    image = context.user_data.get('broadcast_image')
    caption = context.user_data.get('broadcast_caption', '')
    
    await send_html(update, f"📢 Sending to {total_users} users...")
    
    for i, user in enumerate(users):
        try:
            if image:
                await context.bot.send_photo(chat_id=user['user_id'], photo=image,
                                            caption=caption, parse_mode='HTML')
            else:
                await context.bot.send_message(chat_id=user['user_id'], text=caption, parse_mode='HTML')
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to send to {user['user_id']}: {e}")
        await asyncio.sleep(0.05)
    
    db.save_broadcast(update.effective_user.id, image or '', caption, '', sent_count, failed_count)
    await send_html(update, f"✅ Sent: {sent_count}, Failed: {failed_count}",
                  reply_markup=get_admin_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

# ======================== MENU HANDLER ========================

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        text = update.message.text
        
        # Skip if in conversation state
        if any(context.user_data.get(k) for k in [
            'awaiting_post_id', 'awaiting_schedule_time', 'awaiting_reschedule_id',
            'awaiting_new_time', 'awaiting_website_selection', 'awaiting_website_schedule',
            'awaiting_schedule_action', 'awaiting_schedule_time_set', 'awaiting_posts_count',
            'add_channel_method', 'awaiting_website_delete', 'awaiting_website_delete_confirm',
            'awaiting_timezone_region', 'awaiting_timezone_selection', 'awaiting_channel_for_post'
        ]):
            logger.info(f"Skipping menu handling for state text: {text}")
            return
        
        logger.info(f"Menu button: {text} by user {user_id}")
        
        # Post actions
        if text == BTN_SEND_NOW:
            if context.user_data.get('selected_post_id'):
                await handle_send_now(update, context)
            else:
                await send_html(update, "❌ No post selected.", reply_markup=get_main_keyboard(user_id))
            return
        
        if text == BTN_SCHEDULE:
            if context.user_data.get('selected_post_id'):
                await handle_schedule_post(update, context)
            else:
                await send_html(update, "❌ No post selected.", reply_markup=get_main_keyboard(user_id))
            return
        
        if text == BACK_TO_MENU or text == '🔙 Back':
            context.user_data.clear()
            await send_html(update, "🌐 <b>Main Menu</b>", reply_markup=get_main_keyboard(user_id))
            return
        
        # Channel selection
        if text.startswith('📢 ') and context.user_data.get('awaiting_channel_for_post'):
            channel_display = text.replace('📢 ', '').strip()
            await handle_channel_selection(update, context, channel_display)
            return
        
        # Main menu
        if text == BTN_ADMIN_PANEL and is_admin(user_id):
            await send_html(update, "🔧 <b>Admin Panel</b>", reply_markup=get_admin_keyboard())
            return
        
        if text == BTN_MY_WEBSITES:
            await websites_command(update, context)
            return
        
        if text == BTN_MY_CHANNELS:
            await channels_command(update, context)
            return
        
        if text == BTN_ADD_WEBSITE:
            await add_website_start(update, context)
            return
        
        if text == BTN_ADD_CHANNEL:
            await add_channel_start(update, context)
            return
        
        if text == BTN_DELETE_WEBSITE:
            await delete_website_start(update, context)
            return
        
        if text == BTN_SET_TIMEZONE:
            await set_timezone_start(update, context)
            return
        
        if text == BTN_VIEW_POSTS:
            await view_posts(update, context)
            return
        
        if text == BTN_MANAGE_POSTS:
            await manage_posts_start(update, context)
            return
        
        if text == BTN_SCHEDULE_SETTINGS:
            await schedule_settings(update, context)
            return
        
        if text == BTN_HELP:
            await help_command(update, context)
            return
        
        # Admin actions
        if text == '📊 Statistics' and is_admin(user_id):
            await admin_statistics(update, context)
            return
        
        if text == '⏰ Pending Posts' and is_admin(user_id):
            await view_pending_posts(update, context)
            return
        
        if text == '🔄 Reschedule Post' and is_admin(user_id):
            await reschedule_post_start(update, context)
            return
        
        if text == '📢 Broadcast' and is_admin(user_id):
            await broadcast_start(update, context)
            return
    except Exception as e:
        logger.error(f"Error in handle_menu: {e}")
        await send_html(update, "❌ An error occurred. Please try again.")

# ======================== AUTO-POST ENGINE ========================

async def check_website_feed(website_id: int, user_id: int):
    """Check feed and IMMEDIATELY auto-post new posts"""
    website = db.get_website(website_id)
    if not website:
        return
    
    try:
        logger.info(f"Checking feed for {website['name']} (User: {user_id})")
        
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, lambda: feedparser.parse(website['feed_url']))
        
        if feed.bozo:
            logger.error(f"Feed error for {website['name']}: {feed.bozo_exception}")
            return
        
        entries = feed.entries[:10]
        new_posts = []
        
        for entry in entries:
            post_data = await detector.extract_post_data(entry)
            post_id = f"post_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}"
            post_data['post_id'] = post_id
            
            existing = db.get_post_by_post_id(post_id)
            if not existing:
                saved_post = db.save_blog_post(post_data, user_id, website_id)
                if saved_post:
                    new_posts.append(saved_post)
                    logger.info(f"🔔 NEW POST: {post_data['title']} (User: {user_id})")
        
        db.update_website_last_checked(website_id)
        
        if new_posts:
            channels = db.get_website_channels(website_id)
            
            if channels:
                for post in new_posts:
                    for channel in channels:
                        await auto_send_post_to_channel(post, channel, user_id)
                    db.mark_auto_sent(post['post_id'])
                
                logger.info(f"✅ Auto-posted {len(new_posts)} posts to {len(channels)} channels")
            else:
                logger.info(f"⚠️ No channels for {website['name']} - posts saved only")
            
            await notify_user_new_posts(user_id, new_posts, website)
    except Exception as e:
        logger.error(f"Error checking feed: {e}")

async def auto_send_post_to_channel(post: Dict, channel: Dict, user_id: int):
    """Send post IMMEDIATELY to channel"""
    try:
        message = f"📝 <b>{post['title']}</b>\n\n"
        message += f"{post['description'][:300]}...\n\n"
        message += f"🔗 <a href='{post['link']}'>Read More</a>"
        
        if post['thumbnail_url']:
            await context.bot.send_photo(chat_id=channel['channel_id'], photo=post['thumbnail_url'],
                                        caption=message, parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=channel['channel_id'], text=message, parse_mode='HTML')
        
        db.update_post_status(user_id, post['user_post_id'], 'sent')
        db.increment_post_sent_count(user_id, post['user_post_id'])
        db.mark_as_posted(post['post_id'], channel['channel_id'])
        
        logger.info(f"📤 Auto-posted: {post['title']} to {channel['channel_name']}")
    except Exception as e:
        logger.error(f"Error auto-sending to {channel['channel_name']}: {e}")

async def notify_user_new_posts(user_id: int, posts: List, website: Dict):
    """Notify user about new posts"""
    try:
        user_tz = get_user_timezone(user_id)
        try:
            user_timezone = pytz.timezone(user_tz)
            current_time = datetime.now(user_timezone)
            time_str = current_time.strftime('%I:%M %p')
        except:
            time_str = datetime.now().strftime('%I:%M %p')
        
        for post in posts[:3]:
            text = f"🔔 <b>New Post Detected & Auto-Posted!</b>\n\n"
            text += f"🌐 <b>{website['name']}</b>\n"
            text += f"📝 <b>{post['title']}</b>\n\n"
            text += f"{post['description'][:200]}...\n\n"
            text += f"🆔 Post #{post['user_post_id']}\n"
            text += f"📤 Sent to all channels\n"
            text += f"🕐 {time_str}\n\n"
            text += f"🔗 <a href='{post['link']}'>Read Full Post</a>"
            
            try:
                if post['thumbnail_url']:
                    await context.bot.send_photo(chat_id=user_id, photo=post['thumbnail_url'],
                                                caption=text, parse_mode='HTML')
                else:
                    await context.bot.send_message(chat_id=user_id, text=text, parse_mode='HTML')
                
                db.mark_post_notified_user(post['post_id'])
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
    except Exception as e:
        logger.error(f"Error in notify_user_new_posts: {e}")

async def check_all_feeds():
    websites = db.get_all_websites()
    for website in websites:
        await check_website_feed(website['id'], website['user_id'])
        await asyncio.sleep(2)

# ======================== BACKGROUND TASKS ========================

async def auto_check_all_feeds():
    while True:
        try:
            logger.info("🔄 Scanning feeds...")
            await check_all_feeds()
        except Exception as e:
            logger.error(f"Auto-check error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

async def pending_posts_loop():
    while True:
        try:
            pending = db.get_pending_posts()
            for post in pending:
                try:
                    message = f"📝 <b>{post['title']}</b>\n\n"
                    message += f"{post['description'][:300]}...\n\n"
                    message += f"🔗 <a href='{post['link']}'>Read More</a>"
                    
                    if post['thumbnail_url']:
                        await context.bot.send_photo(chat_id=post['channel_id'], photo=post['thumbnail_url'],
                                                    caption=message, parse_mode='HTML')
                    else:
                        await context.bot.send_message(chat_id=post['channel_id'], text=message, parse_mode='HTML')
                    
                    user_id = post['user_id']
                    db.update_post_status(user_id, post['user_post_id'], 'sent')
                    db.increment_post_sent_count(user_id, post['user_post_id'])
                    db.mark_as_posted(post['post_id'], post['channel_id'])
                    db.mark_auto_sent(post['post_id'])
                    
                    logger.info(f"📤 Scheduled post sent: {post['title']}")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Failed to send scheduled post: {e}")
        except Exception as e:
            logger.error(f"Pending posts error: {e}")
        await asyncio.sleep(60)

# ======================== MESSAGE HANDLER ========================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    user_id = update.effective_user.id
    
    logger.info(f"Text handler: {text} from user {user_id}")
    
    if text == CANCEL_BUTTON:
        if context.user_data.get('awaiting_post_id'):
            await cancel_manage_posts(update, context)
            return
        elif context.user_data.get('awaiting_schedule_time'):
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
            context.user_data.clear()
            return
        elif context.user_data.get('awaiting_reschedule_id') or context.user_data.get('awaiting_new_time'):
            await cancel_reschedule(update, context)
            return
        elif any(context.user_data.get(k) for k in ['awaiting_website_selection', 'awaiting_website_schedule', 'awaiting_schedule_action', 'awaiting_schedule_time_set', 'awaiting_posts_count']):
            await cancel_schedule_settings(update, context)
            return
        elif context.user_data.get('add_channel_method'):
            await cancel_add_channel(update, context)
            return
        elif context.user_data.get('awaiting_channel_for_post'):
            context.user_data.clear()
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
            return
        else:
            await send_html(update, "❌ Cancelled.", reply_markup=get_main_keyboard(user_id))
            context.user_data.clear()
            return
    
    # Route based on state
    if context.user_data.get('awaiting_timezone_region'):
        await handle_timezone_region(update, context)
        return
    
    if context.user_data.get('awaiting_timezone_selection'):
        await handle_timezone_selection(update, context)
        return
    
    if context.user_data.get('awaiting_post_id'):
        await handle_post_id_input(update, context)
        return
    
    if context.user_data.get('awaiting_schedule_time'):
        await handle_schedule_time(update, context)
        return
    
    if context.user_data.get('awaiting_reschedule_id'):
        await handle_reschedule_id_input(update, context)
        return
    
    if context.user_data.get('awaiting_new_time'):
        await process_reschedule_time(update, context)
        return
    
    if context.user_data.get('awaiting_website_selection'):
        await select_website_for_channel(update, context)
        return
    
    if context.user_data.get('awaiting_website_schedule'):
        await handle_website_schedule_selection(update, context)
        return
    
    if context.user_data.get('awaiting_schedule_action'):
        await handle_schedule_action(update, context)
        return
    
    if context.user_data.get('awaiting_website_delete'):
        await handle_website_delete_selection(update, context)
        return
    
    if context.user_data.get('awaiting_website_delete_confirm'):
        await handle_website_delete_confirm(update, context)
        return
    
    if text in ['📤 Add via Forward', '✏️ Enter @username', '🔢 Enter Channel ID']:
        if context.user_data.get('add_channel_method') is None:
            if text == '📤 Add via Forward':
                await add_channel_forward(update, context)
            elif text == '✏️ Enter @username':
                await add_channel_username(update, context)
            elif text == '🔢 Enter Channel ID':
                await add_channel_id(update, context)
            return
    
    if context.user_data.get('add_channel_method') == 'forward':
        await process_channel_forward(update, context)
        return
    
    if context.user_data.get('add_channel_method') in ['username', 'id']:
        await process_channel_manual(update, context)
        return
    
    await handle_menu(update, context)

# ======================== MAIN FUNCTION ========================

async def post_init(application: Application) -> None:
    """Start background tasks after bot initialization"""
    asyncio.create_task(auto_check_all_feeds())
    asyncio.create_task(pending_posts_loop())
    logger.info("✅ Background tasks started")

def main():
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("❌ ERROR: Please set your BOT_TOKEN in env vars")
        return
    
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Start health server in background thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    logger.info("🏥 Health server thread started")
    
    # Build application with LONG timeouts for Render
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .get_updates_connect_timeout(30.0)
        .get_updates_read_timeout(30.0)
        .post_init(post_init)
        .build()
    )
    
    global context
    context = application
    
    application.add_handler(CommandHandler("start", start_command))
    
    # Add Website conversation
    add_website_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{BTN_ADD_WEBSITE}$'), add_website_start)],
        states={
            ADD_WEBSITE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_website_url)],
        },
        fallbacks=[
            MessageHandler(filters.Regex(f'^{CANCEL_BUTTON}$'), cancel_add_website),
            CommandHandler("cancel", cancel_add_website)
        ]
    )
    application.add_handler(add_website_conv)
    
    # Add Channel conversation
    add_channel_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{BTN_ADD_CHANNEL}$'), add_channel_start)],
        states={
            ADD_CHANNEL_SELECT_WEBSITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_website_for_channel)],
            ADD_CHANNEL_METHOD: [
                MessageHandler(filters.Regex('^📤 Add via Forward$'), add_channel_forward),
                MessageHandler(filters.Regex('^✏️ Enter @username$'), add_channel_username),
                MessageHandler(filters.Regex('^🔢 Enter Channel ID$'), add_channel_id),
                MessageHandler(filters.Regex(f'^{CANCEL_BUTTON}$'), add_channel_forward)
            ],
            ADD_CHANNEL_FORWARD: [
                MessageHandler(filters.FORWARDED, process_channel_forward),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_channel_forward)
            ],
            ADD_CHANNEL_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_channel_manual)]
        },
        fallbacks=[
            MessageHandler(filters.Regex(f'^{CANCEL_BUTTON}$'), cancel_add_channel),
            CommandHandler("cancel", cancel_add_channel)
        ]
    )
    application.add_handler(add_channel_conv)
    
    # Broadcast conversation
    broadcast_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📢 Broadcast$'), broadcast_start)],
        states={
            BROADCAST_IMAGE: [
                MessageHandler(filters.PHOTO, broadcast_image),
                MessageHandler(filters.Regex('^/skip$'), broadcast_image),
                MessageHandler(filters.Regex(f'^{CANCEL_BUTTON}$'), broadcast_image)
            ],
            BROADCAST_CAPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_caption),
                MessageHandler(filters.Regex(f'^{CANCEL_BUTTON}$'), broadcast_caption)
            ],
            BROADCAST_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_confirm),
                MessageHandler(filters.Regex(f'^{CANCEL_BUTTON}$'), broadcast_confirm)
            ]
        },
        fallbacks=[]
    )
    application.add_handler(broadcast_conv)
    
    # Main text handler (must be last)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print(f"🌐 {BOT_NAME} starting...")
    print(f"👥 Admins: {ADMIN_IDS}")
    print(f"⏰ Check interval: {CHECK_INTERVAL} seconds")
    print(f"⚡ Auto-Post: IMMEDIATE")
    
    # Retry loop for network errors
    while True:
        try:
            application.run_polling(
                allowed_updates=['message', 'callback_query'],
                drop_pending_updates=True
            )
            break
        except Exception as e:
            logger.error(f"⚠️ Bot crashed: {e}. Restarting in 10 seconds...")
            time.sleep(10)

if __name__ == '__main__':
    main()