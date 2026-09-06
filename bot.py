import os
import random
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from html import escape
import tempfile
from pathlib import Path

try:
    import edge_tts
except Exception:
    edge_tts = None

from yt_dlp import YoutubeDL

try:
    from openai import AsyncOpenAI
except Exception:
    AsyncOpenAI = None
from pytgcalls import PyTgCalls

from pymongo import MongoClient, UpdateOne
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import functions
from telegram import Update, ChatMember, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler,
    ContextTypes, CallbackQueryHandler, filters
)

# =========================
# ENVIRONMENT / CONFIG
# =========================
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
STRING_SESSION = os.environ["STRING_SESSION"]
MUSIC_SESSION = os.getenv("MUSIC_SESSION", "")
MONGO_URI = os.environ["MONGO_URI"]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")

IST = ZoneInfo("Asia/Kolkata")
DELETE_AFTER = int(os.getenv("DELETE_AFTER", "600"))  # 10 minutes for normal group bot messages
CALL_DELETE_AFTER = int(os.getenv("CALL_DELETE_AFTER", "86400"))  # 24 hours for call/tag messages
CALL_MIN = int(os.getenv("CALL_MIN", "2"))
CALL_MAX = int(os.getenv("CALL_MAX", "5"))
CALL_DELAY = float(os.getenv("CALL_DELAY", "1.2"))

mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = mongo["fun_in_shadows"]
users = db["users"]
groups = db["groups"]
activity = db["activity"]
giveaways = db["giveaways"]
stored_songs = db["stored_songs"]
dm_history = db["dm_history"]

ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if (AsyncOpenAI and OPENAI_API_KEY) else None

mt = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
music_mt = TelegramClient(StringSession(MUSIC_SESSION), API_ID, API_HASH) if MUSIC_SESSION else None
music_calls = PyTgCalls(music_mt) if music_mt else None

QUIZ = [
    ("What is the capital of India?", ["Delhi", "Mumbai", "Kolkata", "Chennai"], 0),
    ("Which planet is known as the Red Planet?", ["Earth", "Mars", "Jupiter", "Venus"], 1),
    ("2 + 2 × 2 = ?", ["6", "8", "4", "10"], 0),
    ("Which language is used by Telegram bots in this project?", ["Python", "Rust", "PHP", "Ruby"], 0),
    ("What is the largest ocean on Earth?", ["Atlantic Ocean", "Indian Ocean", "Pacific Ocean", "Arctic Ocean"], 2),
    ("How many continents are there on Earth?", ["5", "6", "7", "8"], 2),
    ("Which gas do humans need to breathe to survive?", ["Oxygen", "Helium", "Hydrogen", "Neon"], 0),
    ("Which is the fastest land animal?", ["Lion", "Cheetah", "Horse", "Tiger"], 1),
    ("What is H2O commonly called?", ["Salt", "Water", "Oxygen", "Hydrogen"], 1),
    ("Which country is famous for the pyramids of Giza?", ["India", "Egypt", "Mexico", "Greece"], 1),
    ("How many days are in a leap year?", ["365", "366", "364", "367"], 1),
    ("Which instrument has black and white keys?", ["Guitar", "Piano", "Violin", "Flute"], 1),
    ("Which metal is liquid at normal room temperature?", ["Iron", "Mercury", "Copper", "Aluminium"], 1),
    ("What is the largest planet in our solar system?", ["Earth", "Saturn", "Jupiter", "Neptune"], 2),
    ("Which organ pumps blood around the human body?", ["Lungs", "Brain", "Heart", "Liver"], 2),
    ("Which country is known as the Land of the Rising Sun?", ["China", "Japan", "Thailand", "South Korea"], 1),
    ("How many sides does a hexagon have?", ["5", "6", "7", "8"], 1),
    ("Which is the smallest prime number?", ["0", "1", "2", "3"], 2),
    ("What is the chemical symbol for gold?", ["Ag", "Au", "Fe", "Gd"], 1),
    ("Which planet is closest to the Sun?", ["Venus", "Earth", "Mercury", "Mars"], 2),
    ("Who wrote Romeo and Juliet?", ["William Shakespeare", "Charles Dickens", "Mark Twain", "Leo Tolstoy"], 0),
    ("What is 15 × 4?", ["45", "50", "60", "75"], 2),
    ("Which animal is known for having a long trunk?", ["Elephant", "Giraffe", "Zebra", "Rhino"], 0),
    ("Which is the largest mammal?", ["African Elephant", "Blue Whale", "Giraffe", "Hippopotamus"], 1),
    ("How many hours are in one day?", ["12", "18", "24", "36"], 2),
    ("Which vitamin is commonly produced in the skin through sunlight exposure?", ["Vitamin A", "Vitamin B12", "Vitamin C", "Vitamin D"], 3),
    ("Which Indian festival is widely known as the festival of lights?", ["Holi", "Diwali", "Eid", "Onam"], 1),
    ("What is the square root of 81?", ["7", "8", "9", "10"], 2),
    ("Which part of a plant usually absorbs water from the soil?", ["Flower", "Leaf", "Root", "Fruit"], 2),
    ("Which is the nearest star to Earth?", ["Sirius", "Polaris", "The Sun", "Betelgeuse"], 2),
    ("What is the currency of Japan?", ["Won", "Yuan", "Yen", "Ringgit"], 2),
    ("Which blood cells help fight infections?", ["Red blood cells", "White blood cells", "Platelets", "Plasma"], 1),
    ("How many degrees are in a right angle?", ["45°", "90°", "120°", "180°"], 1),
    ("Which ocean lies between Africa and Australia?", ["Atlantic Ocean", "Pacific Ocean", "Indian Ocean", "Arctic Ocean"], 2),
    ("Which device is primarily used to measure temperature?", ["Barometer", "Thermometer", "Altimeter", "Hygrometer"], 1),
    ("What is the freezing point of water at standard atmospheric pressure?", ["0°C", "10°C", "32°C", "100°C"], 0),
    ("Which planet is famous for its prominent rings?", ["Mars", "Venus", "Saturn", "Mercury"], 2),
    ("What is the main language spoken in Brazil?", ["Spanish", "Portuguese", "French", "Italian"], 1),
    ("Which number comes next: 2, 4, 6, 8, ?", ["9", "10", "11", "12"], 1),
    ("Which shape has three sides?", ["Square", "Circle", "Triangle", "Pentagon"], 2),
]
GAMES = ["🎲 Dice Duel", "🎯 Target Shot", "🪙 Coin Flip"]

# in-memory state is intentionally small; persistent balances/activity are MongoDB-backed.
active_calls = set()
pending_quizzes = {}
active_games = {}
pending_fights = {}
music_queues = {}
music_current = {}
music_volume = {}
awaiting_song_upload = set()

# =========================
# DB HELPERS
# =========================
def now():
    return datetime.now(IST)

def save_group(chat):
    if not chat:
        return
    groups.update_one(
        {"chat_id": chat.id},
        {"$set": {"title": chat.title or "", "type": chat.type}},
        upsert=True,
    )

def touch_user(chat_id, user):
    if not user or user.is_bot:
        return
    t = now()
    users.update_one(
        {"chat_id": chat_id, "user_id": user.id},
        {"$set": {
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "username": user.username or "",
            "last_seen": t,
        }, "$setOnInsert": {"coins": 0}},
        upsert=True,
    )

def add_activity(chat_id, user_id, messages=1):
    if not user_id:
        return
    t = now()
    day = t.strftime("%Y-%m-%d")
    activity.update_one(
        {"chat_id": chat_id, "user_id": user_id, "day": day},
        {"$inc": {"messages": messages}, "$set": {"updated_at": t}},
        upsert=True,
    )

def add_coins(chat_id, user_id, amount):
    users.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"coins": amount}},
        upsert=True,
    )

def get_coins(chat_id, user_id):
    row = users.find_one({"chat_id": chat_id, "user_id": user_id}, {"coins": 1})
    return int((row or {}).get("coins", 0))

def spend_coins(chat_id, user_id, amount):
    """Atomically spend coins; returns True only when the user had enough."""
    result = users.update_one(
        {"chat_id": chat_id, "user_id": user_id, "coins": {"$gte": amount}},
        {"$inc": {"coins": -amount}},
    )
    if result.modified_count:
        try:
            db.coin_events.insert_one({"chat_id": chat_id, "user_id": user_id, "amount": -amount, "at": now()})
        except Exception:
            pass
        return True
    return False

def mention(uid, name):
    return f'<a href="tg://user?id={uid}">{escape(name or "User")}</a>'

def user_label(u):
    return ((u.get("first_name") or "") + " " + (u.get("last_name") or "")).strip() or "User"

async def send_temp(update, text, **kwargs):
    """Send a bot response and schedule deletion after 5 minutes in groups."""
    chat = update.effective_chat
    msg = await update.effective_message.reply_text(text, **kwargs)
    if chat and chat.type in ("group", "supergroup"):
        context = kwargs.pop("_context", None)
    # Deletion scheduling is done by command handlers with context where needed.
    return msg

async def delete_later(context, chat_id, message_id, delay=DELETE_AFTER):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def schedule_delete(context, message):
    if message and message.chat and message.chat.type in ("group", "supergroup"):
        context.application.create_task(
            delete_later(context, message.chat.id, message.message_id)
        )

def schedule_call_delete(context, message):
    if message and message.chat and message.chat.type in ("group", "supergroup"):
        context.application.create_task(
            delete_later(context, message.chat.id, message.message_id, CALL_DELETE_AFTER)
        )

# =========================
# ADMIN
# =========================
async def is_owner(update):
    return bool(update.effective_user and update.effective_user.id == OWNER_ID)

async def is_admin(update, context):
    if not update.effective_chat or not update.effective_user:
        return False
    try:
        m = await context.bot.get_chat_member(
            update.effective_chat.id, update.effective_user.id
        )
        return m.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception:
        return False

# =========================
# PARTICIPANT SCAN
# =========================
async def sync_members(chat_id):
    entity = await mt.get_entity(chat_id)
    batch = []
    total = 0
    async for u in mt.iter_participants(entity):
        if getattr(u, "deleted", False):
            continue
        batch.append(u)
        total += 1
        if len(batch) >= 500:
            _write_members(chat_id, batch)
            batch.clear()
    if batch:
        _write_members(chat_id, batch)
    return total

def _write_members(chat_id, batch):
    ops = []
    for u in batch:
        ops.append(UpdateOne(
            {"chat_id": chat_id, "user_id": u.id},
            {"$set": {
                "first_name": u.first_name or "",
                "last_name": u.last_name or "",
                "username": u.username or "",
                "is_bot": bool(getattr(u, "bot", False)),
            }},
            upsert=True,
        ))
    if ops:
        db.members.bulk_write(ops)

# =========================
# MUSIC / VOICE CHAT
# =========================
def music_ready():
    return music_mt is not None and music_calls is not None

async def music_search(query):
    def _search():
        q = query.strip()
        # Never pass a bare song name to yt-dlp as if it were a URL.
        target = q if q.startswith(("http://", "https://")) else f"ytsearch1:{q}"
        opts = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": True,
            "noplaylist": True,
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)
            if info and "entries" in info:
                info = next((x for x in info["entries"] if x), None)
            return info
    return await asyncio.to_thread(_search)

async def music_direct_url(webpage_url):
    def _extract():
        opts = {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
            "format": "bestaudio/best",
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
            return info.get("url"), info.get("title") or "Unknown"
    return await asyncio.to_thread(_extract)

async def find_stored_song(query):
    q = query.strip()
    if not q:
        return None
    return stored_songs.find_one({"$or": [
        {"title": {"$regex": q, "$options": "i"}},
        {"caption": {"$regex": q, "$options": "i"}},
        {"keywords": {"$regex": q, "$options": "i"}},
    ]})

async def download_stored_song(item):
    file_id = item.get("file_id")
    if not file_id:
        raise RuntimeError("Stored MP3 file id missing")
    safe = "".join(c for c in str(file_id) if c.isalnum())[-24:] or "song"
    path = f"/tmp/fis_{safe}.mp3"
    if not os.path.exists(path) or os.path.getsize(path) < 1024:
        tgfile = await application_bot.get_file(file_id)
        await tgfile.download_to_drive(path)
    return path

async def vc_play(chat_id, source):
    return await music_calls.play(chat_id, source)

async def vc_pause(chat_id):
    for name in ("pause", "pause_stream"):
        fn = getattr(music_calls, name, None)
        if fn:
            return await fn(chat_id)
    raise RuntimeError("PyTgCalls pause API not available")

async def vc_resume(chat_id):
    for name in ("resume", "resume_stream"):
        fn = getattr(music_calls, name, None)
        if fn:
            return await fn(chat_id)
    raise RuntimeError("PyTgCalls resume API not available")

async def vc_leave(chat_id):
    for name in ("leave_call", "leave_group_call"):
        fn = getattr(music_calls, name, None)
        if fn:
            return await fn(chat_id)
    raise RuntimeError("PyTgCalls leave API not available")

async def vc_volume(chat_id, volume):
    for name in ("change_volume", "change_volume_call"):
        fn = getattr(music_calls, name, None)
        if fn:
            return await fn(chat_id, volume)
    raise RuntimeError("PyTgCalls volume API not available")

async def music_play_next(chat_id):
    if not music_ready():
        return False
    q = music_queues.get(chat_id, [])
    if not q:
        music_current.pop(chat_id, None)
        return False
    item = q.pop(0)
    music_queues[chat_id] = q
    try:
        if item.get("stored"):
            direct_url = await download_stored_song(item)
            title = item.get("title") or "Stored song"
        else:
            direct_url, title = await music_direct_url(item["webpage_url"])
        if not direct_url:
            raise RuntimeError("No playable audio URL")
        await vc_play(chat_id, direct_url)
        item["title"] = title or item.get("title") or "Unknown"
        music_current[chat_id] = item
        return True
    except Exception as e:
        music_current.pop(chat_id, None)
        if q:
            return await music_play_next(chat_id)
        raise e

async def music_stream_end(_, update):
    chat_id = getattr(update, "chat_id", None)
    if chat_id is None:
        return
    music_current.pop(chat_id, None)
    try:
        await music_play_next(chat_id)
    except Exception:
        pass

async def ensure_music_assistant_in_group(update, context):
    """Ensure the MUSIC_SESSION account is a group member.
    The main bot creates a one-use invite link, and the assistant user account
    joins through MTProto. No admin rights are required for the assistant.
    """
    chat = update.effective_chat
    if not music_mt:
        return False, "Music assistant session is not configured."
    try:
        me = await music_mt.get_me()
        try:
            await music_mt.get_permissions(chat.id, me.id)
            return True, None
        except Exception:
            pass

        # Main bot must have permission to create invite links.
        invite = await context.bot.create_chat_invite_link(
            chat.id, member_limit=1, name="Fun in Shadows Music Assistant"
        )
        link = invite.invite_link
        if "t.me/+" in link:
            invite_hash = link.rsplit("/", 1)[-1].lstrip("+")
            await music_mt(functions.messages.ImportChatInviteRequest(invite_hash))
        else:
            # Public invite links can be joined by username.
            username = chat.username
            if not username:
                return False, "I couldn't create a usable invite for the assistant."
            await music_mt(functions.channels.JoinChannelRequest(username))

        await asyncio.sleep(1.2)
        try:
            await music_mt.get_permissions(chat.id, me.id)
        except Exception:
            return False, "Assistant join could not be confirmed."

        return True, me.username or me.first_name or "Music Assistant"
    except Exception as e:
        return False, str(e)[:250]

async def play_cmd(update, context):
    if not music_ready():
        msg = await update.message.reply_text(
            "🎵 Music setup pending. Render mein MUSIC_SESSION add karo."
        )
        schedule_delete(context, msg)
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        msg = await update.message.reply_text("🎵 Music commands group voice chat mein use karo.")
        return
    if not context.args:
        msg = await update.message.reply_text("🎵 Usage: /play song name or YouTube URL")
        schedule_delete(context, msg)
        return
    query = " ".join(context.args).strip()
    try:
        # Auto-invite the normal Telegram music assistant only when /play is used.
        # The assistant stays a normal member; admin rights are not required.
        ok, assistant_info = await ensure_music_assistant_in_group(update, context)
        if not ok:
            msg = await update.message.reply_text(
                "🎵 <b>Music Assistant required</b>\n\n"
                "Assistant group mein member nahi hai aur auto-invite nahi ho saka.\n"
                "Main bot ko invite-link permission do, phir /play dobara use karo.",
                parse_mode=ParseMode.HTML,
            )
            schedule_delete(context, msg)
            return

        notice = await update.message.reply_text(
            f"🎵 <b>Assistant ready</b> — {escape(str(assistant_info))}\n"
            "Starting your song...",
            parse_mode=ParseMode.HTML,
        )
        schedule_delete(context, notice)

        stored = await find_stored_song(query)
        if stored:
            item = {
                "title": stored.get("title") or query,
                "stored": True,
                "file_id": stored.get("file_id"),
                "requested_by": update.effective_user.id,
            }
            queue = music_queues.setdefault(update.effective_chat.id, [])
            playing = update.effective_chat.id in music_current
            queue.append(item)
            if not playing:
                await music_play_next(update.effective_chat.id)
                text = f"🎵 <b>Now Playing</b>\n{escape(item['title'])}"
            else:
                text = f"🎵 <b>Added to Queue</b>\n{escape(item['title'])}\n📋 Position: <b>{len(queue)}</b>"
            msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
            schedule_delete(context, msg)
            return
        info = await music_search(query)
        if not info:
            raise RuntimeError("Song not found")
        webpage = info.get("webpage_url")
        if not webpage and isinstance(info.get("url"), str) and info["url"].startswith(("http://", "https://")):
            webpage = info["url"]
        title = info.get("title") or query
        if not webpage or not webpage.startswith(("http://", "https://")):
            raise RuntimeError("Song search did not return a valid URL")
        item = {
            "title": title,
            "webpage_url": webpage,
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "requested_by": update.effective_user.id,
        }
        queue = music_queues.setdefault(update.effective_chat.id, [])
        playing = update.effective_chat.id in music_current
        queue.append(item)
        if not playing:
            await music_play_next(update.effective_chat.id)
            current = music_current.get(update.effective_chat.id, item)
            mins = int(current.get("duration") or 0) // 60
            secs = int(current.get("duration") or 0) % 60
            dur = f"{mins}:{secs:02d}" if current.get("duration") else "Unknown"
            text = (f"🖤 <b>| sᴛᴀʀᴛᴇᴅ sᴛʀᴇᴀᴍɪɴɢ |</b>\n\n"
                    f"<b>ᴛɪᴛʟᴇ:</b> {escape(current.get('title', title))}\n\n"
                    f"<b>ᴅᴜʀᴀᴛɪᴏɴ:</b> {dur} ᴍɪɴ\n"
                    f"<b>ʀᴇǫᴜᴇsᴛᴇᴅ ʙʏ:</b> {mention(update.effective_user.id, update.effective_user.full_name)}")
        else:
            text = f"🎵 <b>Added to Queue</b>\n{escape(title)}\n📋 Position: <b>{len(queue)}</b>"
    except Exception as e:
        text = f"❌ Music error: <code>{escape(str(e)[:300])}</code>"
    thumb = music_current.get(update.effective_chat.id, {}).get("thumbnail")
    if thumb and text.startswith("🖤"):
        try:
            msg = await update.message.reply_photo(thumb, caption=text, parse_mode=ParseMode.HTML)
        except Exception:
            msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def pause_cmd(update, context):
    if not music_ready():
        return
    try:
        await vc_pause(update.effective_chat.id)
        text = "⏸️ Paused."
    except Exception as e:
        text = f"❌ {escape(str(e)[:250])}"
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def resume_cmd(update, context):
    if not music_ready():
        return
    try:
        await vc_resume(update.effective_chat.id)
        text = "▶️ Resumed."
    except Exception as e:
        text = f"❌ {escape(str(e)[:250])}"
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def skip_cmd(update, context):
    if not music_ready():
        return
    chat_id = update.effective_chat.id
    try:
        await vc_leave(chat_id)
    except Exception:
        pass
    music_current.pop(chat_id, None)
    try:
        ok = await music_play_next(chat_id)
        text = "⏭️ Skipped. Playing next." if ok else "⏭️ Skipped. Queue is empty."
    except Exception as e:
        text = f"❌ {escape(str(e)[:250])}"
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def stop_cmd(update, context):
    if not music_ready():
        return
    chat_id = update.effective_chat.id
    music_queues.pop(chat_id, None)
    music_current.pop(chat_id, None)
    try:
        await vc_leave(chat_id)
        text = "⏹️ Music stopped and queue cleared."
    except Exception:
        text = "⏹️ Music stopped and queue cleared."
    msg = await update.message.reply_text(text)
    schedule_delete(context, msg)

async def queue_cmd(update, context):
    chat_id = update.effective_chat.id
    current = music_current.get(chat_id)
    queue = music_queues.get(chat_id, [])
    lines = ["🎵 <b>Music Queue</b>"]
    if current:
        lines.append(f"\n▶️ {escape(current.get('title','Unknown'))}")
    if queue:
        for i, item in enumerate(queue[:10], 1):
            lines.append(f"{i}. {escape(item.get('title','Unknown'))}")
        if len(queue) > 10:
            lines.append(f"... +{len(queue)-10} more")
    elif not current:
        lines.append("\nQueue empty.")
    msg = await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def music_menu_cmd(update, context):
    if update.effective_chat.type != "private":
        msg = await update.message.reply_text("🎵 /music ko DM mein use karo.")
        schedule_delete(context, msg)
        return
    kb = [
        [InlineKeyboardButton("🎵 Save MP3", callback_data="music:save")],
        [InlineKeyboardButton("📚 My Songs", callback_data="music:list")],
    ]
    await update.message.reply_text(
        "🎵 <b>Music Vault</b>\n\nSave an MP3 here, then group mein uska title ya koi matching line likhkar <b>/play</b> se chala sakte ho.",
        parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb)
    )

async def music_menu_callback(update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "music:save":
        awaiting_song_upload.add(q.from_user.id)
        await q.edit_message_text("📥 Ab isi DM mein MP3/audio file bhejo. Main usse Music Vault mein save kar dunga.\n\n❌ Cancel: /music")
    elif q.data == "music:list":
        songs = list(stored_songs.find({"owner_id": q.from_user.id}, {"title":1}).sort("created_at", -1).limit(20))
        if not songs:
            text = "📚 Tumhare vault mein abhi koi song nahi hai."
        else:
            text = "📚 <b>My Songs</b>\n\n" + "\n".join(f"{i}. {escape(x.get('title','Untitled'))}" for i,x in enumerate(songs,1))
        await q.edit_message_text(text, parse_mode=ParseMode.HTML)

async def private_audio(update, context):
    if update.effective_chat.type != "private" or not update.message or not update.message.audio:
        return
    uid = update.effective_user.id
    if uid not in awaiting_song_upload:
        await update.message.reply_text("🎵 Pehle /music → 🎵 Save MP3 button dabao.")
        return
    audio = update.message.audio
    title = audio.title or audio.file_name or "Untitled Song"
    keywords = " ".join(filter(None, [audio.title, audio.file_name, audio.performer, update.message.caption]))
    stored_songs.update_one(
        {"owner_id": uid, "file_id": audio.file_id},
        {"$set": {"title": title, "performer": audio.performer or "", "caption": update.message.caption or "", "keywords": keywords, "file_id": audio.file_id, "owner_id": uid, "created_at": now()}},
        upsert=True,
    )
    awaiting_song_upload.discard(uid)
    await update.message.reply_text(f"✅ Saved: <b>{escape(title)}</b>\nAb group mein <code>/play {escape(title)}</code> ya song ki matching line se try kar sakte ho.", parse_mode=ParseMode.HTML)

async def ai_reply(user_id, user_name, user_text):
    """Natural DM conversation with short persistent context."""
    if not ai_client:
        return "Bhai 😅 AI chat abhi configured nahi hai. Render mein OPENAI_API_KEY add karna hoga."

    rows = list(dm_history.find({"user_id": user_id}).sort("created_at", -1).limit(12))
    rows.reverse()
    messages = [{
        "role": "system",
        "content": (
            "You are Fun in Shadows bot's friendly DM companion. "
            "Talk naturally like a close Indian friend. Use casual Hinglish/Hindi when the user does, "
            "otherwise use the user's language. Keep replies concise, warm, playful and contextual. "
            "Do not repeat generic greetings. Answer the actual message. You can use emojis naturally, "
            "but don't overdo them. Never claim to be a human."
            f"The user's display name is {user_name or 'bhai'}."
        )
    }]
    for r in rows:
        role = r.get("role")
        content = r.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})

    try:
        response = await ai_client.chat.completions.create(model=AI_MODEL, messages=messages, temperature=0.8)
        reply = (response.choices[0].message.content or "").strip()
        if not reply:
            reply = "Bhai, ek sec 😅 dobara bol."
    except Exception as e:
        print(f"AI DM error: {e}")
        reply = "Bhai 😅 abhi AI reply mein thoda issue aa gaya. Ek baar phir bhej."

    t = now()
    dm_history.insert_one({"user_id": user_id, "role": "user", "content": user_text, "created_at": t})
    dm_history.insert_one({"user_id": user_id, "role": "assistant", "content": reply, "created_at": t})
    # Keep the collection bounded per user.
    old = list(dm_history.find({"user_id": user_id}, {"_id": 1}).sort("created_at", -1).skip(24))
    if old:
        dm_history.delete_many({"_id": {"$in": [x["_id"] for x in old]}})
    return reply

async def send_voice_reply(message, text):
    if not edge_tts:
        await message.reply_text(text)
        return
    path = f"/tmp/fis_voice_{message.message_id}.mp3"
    try:
        communicate = edge_tts.Communicate(text, "hi-IN-MadhurNeural")
        await communicate.save(path)
        with open(path, "rb") as audio:
            await message.reply_voice(voice=audio)
    except Exception as e:
        print(f"TTS error: {e}")
        await message.reply_text(text)
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

async def voice_note_reply(update, context):
    if update.effective_chat.type != "private" or not update.message or not update.message.voice:
        return
    if not ai_client:
        await update.message.reply_text("🎙️ Voice chat ke liye Render mein OPENAI_API_KEY add karna hoga bhai.")
        return

    temp_path = f"/tmp/fis_in_{update.message.message_id}.ogg"
    try:
        tg_file = await context.bot.get_file(update.message.voice.file_id)
        await tg_file.download_to_drive(temp_path)
        with open(temp_path, "rb") as audio_file:
            transcript = await ai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        text = (getattr(transcript, "text", "") or "").strip()
        if not text:
            await update.message.reply_text("🎙️ Bhai voice clear nahi aa rahi 😅 ek baar phir bhej.")
            return
        reply = await ai_reply(update.effective_user.id, update.effective_user.full_name, text)
        await send_voice_reply(update.message, reply)
    except Exception as e:
        print(f"Voice AI error: {e}")
        await update.message.reply_text("🎙️ Voice samajhne mein issue aa gaya bhai 😅 ek baar phir try kar.")
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass

async def volume_cmd(update, context):
    if not music_ready():
        msg = await update.message.reply_text("🎵 Music setup pending. MUSIC_SESSION add karo.")
        schedule_delete(context, msg)
        return
    if not context.args:
        msg = await update.message.reply_text("🔊 Usage: /volume 0-200")
        schedule_delete(context, msg)
        return
    try:
        volume = max(0, min(200, int(context.args[0])))
    except ValueError:
        volume = -1
    if volume < 0:
        msg = await update.message.reply_text("🔊 Volume 0 se 200 ke beech do.")
        schedule_delete(context, msg)
        return
    try:
        await vc_volume(update.effective_chat.id, volume)
        text = f"🔊 Volume set to <b>{volume}%</b>."
    except Exception as e:
        text = f"❌ Volume change failed: <code>{escape(str(e)[:250])}</code>"
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

# =========================
# COMMANDS
# =========================
async def start(update, context):
    save_group(update.effective_chat)
    touch_user(update.effective_chat.id, update.effective_user)
    text = (
        "🖤 <b>FUN IN SHADOWS</b>\n\n"
        "/call — members ko 2–5 ke batches mein tag\n"
        "/stop_calling — active call stop\n"
        "/calladmins — admins ko tag\n"
        "/health — user ki activity health\n"
        "/coin_ballance — 🪙 balance\n"
        "/quiz — quiz\n"
        "/rost — funny roast\n"
        "/game — 3 random games\n"
        "/rank — coin ranking\n"
        "/participate — 8 PM IST giveaway entry\n"
        "/activity — group activity\n"
        "/fight — 2 🪙 quiz battle\n"
        "/groupinfo — group info (1 🪙)\n"
        "/play song — music in voice chat\n"
        "/music — DM Music Vault\n"
        "/pause /resume /skip /stop /queue /volume\n"
        "/help @shadow_atomic_21 — help"
    )
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def help_cmd(update, context):
    text = (
        "🖤 <b>Fun in Shadows Help</b>\n\n"
        "Tag: /call, /stop_calling, /calladmins\n"
        "Fun: /quiz, /rost, /game, /fight\n"
        "Coins: /coin_ballance, /rank\n"
        "Group: /health, /activity, /groupinfo (1 🪙), /userinfo (2 🪙)\n"
        "Music: /play, /pause, /resume, /skip, /stop, /queue, /volume\n"
        "Giveaway: /participate (result 8 PM IST)\n\n"
        "Support: @shadow_atomic_21"
    )
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def call_cmd(update, context):
    if not (await is_owner(update) or await is_admin(update, context)):
        msg = await update.message.reply_text("⛔ Admins only.")
        schedule_delete(context, msg)
        return

    chat_id = update.effective_chat.id
    if chat_id in active_calls:
        msg = await update.message.reply_text("🔔 /call already running. Use /stop_calling.")
        schedule_delete(context, msg)
        return

    active_calls.add(chat_id)
    status = await update.message.reply_text(
        "🔎 <b>Detecting group members...</b>",
        parse_mode=ParseMode.HTML,
    )
    schedule_call_delete(context, status)

    try:
        total = await sync_members(chat_id)
        await status.edit_text(
            f"🌑 <b>Calling...</b>\n👥 Detected: <b>{total}</b>",
            parse_mode=ParseMode.HTML,
        )
        rows = list(db.members.find(
            {"chat_id": chat_id, "is_bot": {"$ne": True}},
            {"user_id": 1, "first_name": 1, "last_name": 1}
        ))
        random.shuffle(rows)

        i = 0
        while i < len(rows) and chat_id in active_calls:
            remaining = len(rows) - i
            if remaining <= CALL_MAX:
                batch_size = remaining
            else:
                batch_size = random.randint(CALL_MIN, CALL_MAX)
                # Avoid leaving a one-person final batch when possible.
                if remaining - batch_size == 1:
                    batch_size = min(CALL_MAX, batch_size + 1)
            batch = rows[i:i + batch_size]
            text = " ".join(mention(r["user_id"], user_label(r)) for r in batch)
            if text:
                out = await context.bot.send_message(
                    chat_id,
                    "🔔 " + text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                schedule_call_delete(context, out)
            i += len(batch)
            await asyncio.sleep(CALL_DELAY)
    except Exception as e:
        out = await context.bot.send_message(
            chat_id, f"❌ Call failed: <code>{escape(str(e))}</code>",
            parse_mode=ParseMode.HTML
        )
        schedule_call_delete(context, out)
    finally:
        active_calls.discard(chat_id)

async def stop_calling_cmd(update, context):
    if not (await is_owner(update) or await is_admin(update, context)):
        msg = await update.message.reply_text("⛔ Admins only.")
        schedule_delete(context, msg)
        return
    active_calls.discard(update.effective_chat.id)
    msg = await update.message.reply_text("🛑 Calling stopped.")
    schedule_delete(context, msg)

async def calladmins_cmd(update, context):
    if not (await is_owner(update) or await is_admin(update, context)):
        msg = await update.message.reply_text("⛔ Admins only.")
        schedule_delete(context, msg)
        return
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    admins = [m.user for m in admins if not m.user.is_bot]
    text = " ".join(mention(u.id, u.full_name) for u in admins)
    msg = await update.message.reply_text(
        f"👑 <b>Admins:</b>\n{text or 'None'}",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    schedule_delete(context, msg)

async def health_cmd(update, context):
    chat_id = update.effective_chat.id
    if update.effective_chat.type not in ("group", "supergroup"):
        msg = await update.message.reply_text("❤️ Health check group mein 1 🪙 per check hai.")
        return
    target = update.effective_user
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    elif context.args:
        username = context.args[0].lstrip("@")
        found = users.find_one({
            "chat_id": update.effective_chat.id,
            "username": username
        })
        if found:
            target = type("Obj", (), {
                "id": found["user_id"],
                "first_name": found.get("first_name", ""),
                "last_name": found.get("last_name", ""),
                "username": username
            })()

    row = users.find_one({"chat_id": update.effective_chat.id, "user_id": target.id})
    last = row.get("last_seen") if row else None
    if not last:
        hearts = 0
        status = "💀 Dead / never detected"
    else:
        # PyMongo commonly returns BSON datetimes as naive UTC datetimes unless tz_aware is enabled.
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc).astimezone(IST)
        else:
            last = last.astimezone(IST)
        days = (now() - last).days
        if days <= 7:
            hearts = 5
            status = "🟢 Active"
        elif days <= 21:
            hearts = 3
            status = "🟡 Inactive"
        elif days <= 30:
            hearts = 1
            status = "🟠 Almost gone"
        else:
            hearts = 0
            status = "💀 Dead"

    heart = "❤️" * hearts + "🖤" * (5 - hearts)
    name = escape(target.full_name)
    text = (
        f"🩺 <b>Health Report</b>\n\n"
        f"👤 {name}\n"
        f"💗 {heart}\n"
        f"📌 {status}\n"
        f"🕒 Last seen: {escape(str(last) if last else 'Unknown')}"
    )
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def coin_balance_cmd(update, context):
    target = update.effective_user
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    balance = get_coins(update.effective_chat.id, target.id)
    msg = await update.message.reply_text(
        f"🪙 <b>{escape(target.full_name)}</b>: <b>{balance}</b> coins",
        parse_mode=ParseMode.HTML,
    )
    schedule_delete(context, msg)

async def quiz_cmd(update, context):
    chat_id = update.effective_chat.id
    old = pending_quizzes.get(chat_id)
    if old and old.get("expires", now()) >= now():
        msg = await update.message.reply_text("🧠 A quiz is already running. Answer the buttons first!")
        schedule_delete(context, msg)
        return

    q, options, answer = random.choice(QUIZ)
    pending_quizzes[chat_id] = {
        "answer": answer,
        "options": options,
        "question": q,
        "expires": now() + timedelta(minutes=2),
    }
    keyboard = [
        [InlineKeyboardButton(f"1️⃣ {options[0]}", callback_data="quiz:0"),
         InlineKeyboardButton(f"2️⃣ {options[1]}", callback_data="quiz:1")],
        [InlineKeyboardButton(f"3️⃣ {options[2]}", callback_data="quiz:2"),
         InlineKeyboardButton(f"4️⃣ {options[3]}", callback_data="quiz:3")],
    ]
    msg = await update.message.reply_text(
        f"🧠 <b>QUIZ</b>\n\n{escape(q)}\n\n"
        "👇 Choose the correct answer\n🏆 Winner gets <b>2 coins</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    pending_quizzes[chat_id]["message_id"] = msg.message_id
    schedule_delete(context, msg)

async def quiz_callback(update, context):
    query = update.callback_query
    if not query.message or not query.message.chat:
        return
    chat_id = query.message.chat.id
    quiz = pending_quizzes.get(chat_id)
    if not quiz:
        await query.answer("⌛ This quiz is already finished.", show_alert=True)
        return
    if quiz.get("expires", now()) < now():
        pending_quizzes.pop(chat_id, None)
        await query.edit_message_text("⌛ <b>Quiz expired.</b> Use /quiz for a new one.", parse_mode=ParseMode.HTML)
        return

    try:
        choice = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return

    if choice != quiz["answer"]:
        await query.answer("❌ Wrong answer! Try again.", show_alert=True)
        return

    winner = query.from_user
    await query.answer("✅ Correct! +2 coins")
    add_coins_logged(chat_id, winner.id, 2)
    pending_quizzes.pop(chat_id, None)
    await query.edit_message_text(
        f"🧠🏆 <b>Quiz Won!</b>\n\n"
        f"{mention(winner.id, winner.full_name)} got it right!\n"
        "🪙 Reward: <b>2 coins</b>\n\n"
        "Use /quiz for another question.",
        parse_mode=ParseMode.HTML,
    )

async def roast_cmd(update, context):
    target = update.effective_user
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    roasts = [
        f"😂 {escape(target.first_name)}, tera Wi‑Fi bhi tujhse zyada stable hai.",
        f"🔥 {escape(target.first_name)}, confidence 100%, logic loading...",
        f"🤣 {escape(target.first_name)}, Google bhi tujhe search karke thak gaya.",
        f"💀 {escape(target.first_name)}, tu online hai, par system offline.",
    ]
    msg = await update.message.reply_text(random.choice(roasts), parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def game_cmd(update, context):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    key = (chat_id, user_id)
    active_games.pop(key, None)
    keyboard = [
        [InlineKeyboardButton("🎲 Dice Duel — 2 🪙", callback_data="game:menu:dice")],
        [InlineKeyboardButton("🎯 Guess Number — 3 🪙", callback_data="game:menu:guess")],
        [InlineKeyboardButton("🪙 Coin Flip — 1 🪙", callback_data="game:menu:coin")],
    ]
    msg = await update.message.reply_text(
        "🎮 <b>FUN GAMES</b>\n\n"
        "Choose ONE game. Coins are given only after a real win — opening /game gives <b>0 coins</b>.\n\n"
        "🎲 Dice Duel: you roll vs bot; higher number wins.\n"
        "🎯 Guess Number: pick 1–3; guess the hidden number.\n"
        "🪙 Coin Flip: pick Heads or Tails.\n\n"
        "🪙 Rewards: 1–3 coins only on winning.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    schedule_delete(context, msg)

async def game_callback(update, context):
    query = update.callback_query
    await query.answer()
    if not query.message or not query.message.chat:
        return
    chat_id = query.message.chat.id
    user = query.from_user
    user_id = user.id
    key = (chat_id, user_id)
    data = query.data.split(":")

    if len(data) != 3 or data[0] != "game":
        return

    if data[1] == "menu":
        game = data[2]
        if game == "dice":
            active_games[key] = {"type": "dice"}
            kb = [[InlineKeyboardButton("🎲 ROLL DICE", callback_data="game:roll:dice")],
                  [InlineKeyboardButton("↩️ Games Menu", callback_data="game:back:menu")]]
            await query.edit_message_text(
                "🎲 <b>Dice Duel</b>\n\nPress <b>ROLL DICE</b>.\nYou and the bot each get 1–6. Higher roll wins.\n🏆 Winner: <b>2 coins</b>.\n❌ Draw/loss: <b>0 coins</b>.",
                parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
        elif game == "guess":
            active_games[key] = {"type": "guess"}
            kb = [[InlineKeyboardButton("1", callback_data="game:guess:1"),
                   InlineKeyboardButton("2", callback_data="game:guess:2"),
                   InlineKeyboardButton("3", callback_data="game:guess:3")],
                  [InlineKeyboardButton("↩️ Games Menu", callback_data="game:back:menu")]]
            await query.edit_message_text(
                "🎯 <b>Guess the Number</b>\n\nI picked a hidden number from <b>1 to 3</b>.\nTap your guess.\n🏆 Correct guess: <b>3 coins</b>.\n❌ Wrong guess: <b>0 coins</b>.",
                parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
        elif game == "coin":
            active_games[key] = {"type": "coin"}
            kb = [[InlineKeyboardButton("🙂 HEADS", callback_data="game:coin:heads"),
                   InlineKeyboardButton("🌑 TAILS", callback_data="game:coin:tails")],
                  [InlineKeyboardButton("↩️ Games Menu", callback_data="game:back:menu")]]
            await query.edit_message_text(
                "🪙 <b>Coin Flip</b>\n\nChoose Heads or Tails.\n🏆 Correct call: <b>1 coin</b>.\n❌ Wrong call: <b>0 coins</b>.",
                parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
        return

    if data[1] == "back" and data[2] == "menu":
        active_games.pop(key, None)
        kb = [
            [InlineKeyboardButton("🎲 Dice Duel — 2 🪙", callback_data="game:menu:dice")],
            [InlineKeyboardButton("🎯 Guess Number — 3 🪙", callback_data="game:menu:guess")],
            [InlineKeyboardButton("🪙 Coin Flip — 1 🪙", callback_data="game:menu:coin")],
        ]
        await query.edit_message_text("🎮 <b>FUN GAMES</b>\n\nChoose one game:", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
        return

    game = active_games.get(key)
    if not game:
        await query.answer("Start a game with /game first.", show_alert=True)
        return

    if data[1] == "roll" and data[2] == "dice" and game["type"] == "dice":
        player_roll = random.randint(1, 6)
        bot_roll = random.randint(1, 6)
        active_games.pop(key, None)
        if player_roll > bot_roll:
            add_coins_logged(chat_id, user_id, 2)
            result = f"🏆 <b>You win!</b>\n\nYou: 🎲 {player_roll}\nBot: 🎲 {bot_roll}\n\n🪙 <b>+2 coins</b>"
        elif player_roll < bot_roll:
            result = f"❌ <b>You lose!</b>\n\nYou: 🎲 {player_roll}\nBot: 🎲 {bot_roll}\n\n🪙 <b>+0 coins</b>"
        else:
            result = f"🤝 <b>Draw!</b>\n\nYou: 🎲 {player_roll}\nBot: 🎲 {bot_roll}\n\n🪙 <b>+0 coins</b>"
        await query.edit_message_text(result, parse_mode=ParseMode.HTML)
        return

    if data[1] == "guess" and data[2] in {"1", "2", "3"} and game["type"] == "guess":
        guess = int(data[2])
        hidden = random.randint(1, 3)
        active_games.pop(key, None)
        if guess == hidden:
            add_coins_logged(chat_id, user_id, 3)
            result = f"🎯 <b>Correct!</b> Hidden number was <b>{hidden}</b>.\n\n🪙 <b>+3 coins</b>"
        else:
            result = f"🎯 <b>Wrong!</b> Hidden number was <b>{hidden}</b>.\nYou picked <b>{guess}</b>.\n\n🪙 <b>+0 coins</b>"
        await query.edit_message_text(result, parse_mode=ParseMode.HTML)
        return

    if data[1] == "coin" and data[2] in {"heads", "tails"} and game["type"] == "coin":
        pick = data[2]
        flip = random.choice(["heads", "tails"])
        active_games.pop(key, None)
        if pick == flip:
            add_coins_logged(chat_id, user_id, 1)
            result = f"🪙 <b>{flip.upper()}!</b>\n\nYou picked {pick.title()}.\n🏆 <b>You win +1 coin!</b>"
        else:
            result = f"🪙 <b>{flip.upper()}!</b>\n\nYou picked {pick.title()}.\n❌ <b>You lose +0 coins.</b>"
        await query.edit_message_text(result, parse_mode=ParseMode.HTML)
        return

    await query.answer("This game action is no longer active.", show_alert=True)

async def rank_cmd(update, context):
    chat_id = update.effective_chat.id
    period = (context.args[0].lower() if context.args else "all")
    title = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly", "all": "All-time"}.get(period, "All-time")

    if period == "all":
        rows = list(users.find({"chat_id": chat_id}, {"user_id":1,"first_name":1,"last_name":1,"coins":1})
                   .sort("coins", -1).limit(10))
    else:
        days = {"daily": 1, "weekly": 7, "monthly": 30}[period]
        since = now() - timedelta(days=days)
        # Rank by coins earned during period using activity-like coin events.
        rows = list(db.coin_events.aggregate([
            {"$match": {"chat_id": chat_id, "at": {"$gte": since}}},
            {"$group": {"_id": "$user_id", "coins": {"$sum": "$amount"}}},
            {"$sort": {"coins": -1}}, {"$limit": 10},
        ]))
        for r in rows:
            u = users.find_one({"chat_id": chat_id, "user_id": r["_id"]}) or {}
            r.update({"first_name": u.get("first_name",""), "last_name": u.get("last_name","")})

    if not rows:
        text = f"🏆 <b>{title} Ranking</b>\n\nNo coin activity yet."
    else:
        text = f"🏆 <b>{title} Ranking</b>\n\n"
        for i, r in enumerate(rows, 1):
            uid = r.get("user_id", r.get("_id"))
            name = user_label(r)
            coins = r.get("coins", 0)
            text += f"{i}. {mention(uid, name)} — 🪙 {coins}\n"
    text += "\nUse /rank daily, /rank weekly, /rank monthly or /rank."
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

def add_coins_logged(chat_id, user_id, amount):
    add_coins(chat_id, user_id, amount)
    db.coin_events.insert_one({"chat_id": chat_id, "user_id": user_id, "amount": amount, "at": now()})

async def participate_cmd(update, context):
    chat_id = update.effective_chat.id
    doc = giveaways.find_one({"chat_id": chat_id, "date": now().date().isoformat()})
    if not doc:
        doc = {"chat_id": chat_id, "date": now().date().isoformat(), "participants": []}
        giveaways.insert_one(doc)
    giveaways.update_one(
        {"chat_id": chat_id, "date": doc["date"]},
        {"$addToSet": {"participants": update.effective_user.id}},
        upsert=True,
    )
    msg = await update.message.reply_text(
        "🎁 <b>Entered!</b>\nGiveaway result will be announced around <b>8:00 PM IST</b>.",
        parse_mode=ParseMode.HTML
    )
    schedule_delete(context, msg)

async def giveaway_job(context):
    date_str = now().date().isoformat()
    for doc in giveaways.find({"date": date_str, "result": {"$exists": False}}):
        p = doc.get("participants", [])
        if not p:
            giveaways.update_one({"_id": doc["_id"]}, {"$set": {"result": "no_participants"}})
            continue
        winner = random.choice(p)
        giveaways.update_one({"_id": doc["_id"]}, {"$set": {"result": winner}})
        try:
            msg = await context.bot.send_message(
                doc["chat_id"],
                f"🎁 <b>Giveaway Result!</b>\n\n🏆 Winner: {mention(winner, 'Winner')}\n🖤 Congratulations!",
                parse_mode=ParseMode.HTML
            )
            schedule_delete(context, msg)
        except Exception:
            pass

async def activity_cmd(update, context):
    chat_id = update.effective_chat.id
    since = now() - timedelta(days=1)
    rows = list(activity.find(
        {"chat_id": chat_id, "updated_at": {"$gte": since}},
        {"user_id":1,"messages":1}
    ).sort("messages",-1).limit(10))
    if not rows:
        text = "📈 <b>Activity</b>\n\nNo activity recorded in the last 24 hours."
    else:
        text = "📈 <b>Last 24h Activity</b>\n\n"
        for i, r in enumerate(rows, 1):
            u = users.find_one({"chat_id": chat_id, "user_id": r["user_id"]}) or {}
            text += f"{i}. {mention(r['user_id'], user_label(u))} — 💬 {r['messages']}\n"
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def fight_cmd(update, context):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    if not update.message.reply_to_message:
        msg = await update.message.reply_text("🧠😂 Reply to a friend's message and use /fight.")
        schedule_delete(context, msg)
        return
    opponent = update.message.reply_to_message.from_user
    if opponent.is_bot or opponent.id == uid:
        msg = await update.message.reply_text("❌ Choose a real opponent.")
        schedule_delete(context, msg)
        return

    pending_fights[chat_id] = {
        "a": uid, "b": opponent.id,
        "expires": now() + timedelta(minutes=2)
    }
    msg = await update.message.reply_text(
        f"🧠😂 <b>QUIZ BATTLE!</b>\n"
        f"{mention(uid, update.effective_user.full_name)} challenged "
        f"{mention(opponent.id, opponent.full_name)}\n\n"
        "Both players: reply <b>/accept</b> to enter. Winner gets 3 coins.",
        parse_mode=ParseMode.HTML
    )
    schedule_delete(context, msg)

async def accept_cmd(update, context):
    chat_id = update.effective_chat.id
    f = pending_fights.get(chat_id)
    if not f or f["expires"] < now():
        msg = await update.message.reply_text("⌛ No active fight.")
        schedule_delete(context, msg)
        return
    if update.effective_user.id not in (f["a"], f["b"]):
        return
    f.setdefault("accepted", set()).add(update.effective_user.id)
    if len(f["accepted"]) < 2:
        msg = await update.message.reply_text("✅ Accepted. Waiting for the other fighter.")
        schedule_delete(context, msg)
        return

    # Charge the 2-coin entry only after both players have accepted.
    if get_coins(chat_id, f["a"]) < 2 or get_coins(chat_id, f["b"]) < 2:
        pending_fights.pop(chat_id, None)
        msg = await update.message.reply_text("🪙 Dono fighters ko 2-2 coins chahiye. Fight cancelled.")
        schedule_delete(context, msg)
        return
    if not spend_coins(chat_id, f["a"], 2):
        pending_fights.pop(chat_id, None)
        msg = await update.message.reply_text("🪙 Challenger ke coins change ho gaye. Fight cancelled.")
        schedule_delete(context, msg)
        return
    if not spend_coins(chat_id, f["b"], 2):
        add_coins(chat_id, f["a"], 2)
        pending_fights.pop(chat_id, None)
        msg = await update.message.reply_text("🪙 Opponent ke paas 2 coins nahi bache. Fight cancelled; challenger refund ho gaya.")
        schedule_delete(context, msg)
        return

    q, options, ans = random.choice(QUIZ)
    f["answer"] = ans
    f["question"] = q
    f["started"] = now()
    f["accepted"] = set()
    opts = "\n".join(f"{i+1}. {escape(x)}" for i,x in enumerate(options))
    msg = await update.message.reply_text(
        f"🥊 <b>Battle Question</b>\n\n{escape(q)}\n\n{opts}\n\n"
        "First fighter to reply with the correct number wins 3 coins.",
        parse_mode=ParseMode.HTML
    )
    schedule_delete(context, msg)

async def userinfo_cmd(update, context):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        msg = await update.message.reply_text("👤 User info group mein 2 🪙 hai.")
        return
    if not spend_coins(chat.id, update.effective_user.id, 2):
        msg = await update.message.reply_text("🪙 User info ke liye 2 coins chahiye.")
        schedule_delete(context, msg)
        return
    target = update.effective_user
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    elif context.args:
        q = context.args[0].lstrip("@")
        found = users.find_one({"chat_id": chat.id, "username": q})
        if found:
            target = type("Obj", (), {
                "id": found["user_id"], "first_name": found.get("first_name", ""),
                "last_name": found.get("last_name", ""), "username": found.get("username", "")
            })()
    try:
        member = await context.bot.get_chat_member(chat.id, target.id)
        status = getattr(member, "status", "unknown")
    except Exception:
        status = "unavailable"
    row = users.find_one({"chat_id": chat.id, "user_id": target.id}) or {}
    coins = int(row.get("coins", 0))
    last = row.get("last_seen")
    if last and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc).astimezone(IST)
    username = getattr(target, "username", None) or row.get("username") or "Not available"
    name = escape(getattr(target, "full_name", None) or user_label(row))
    text = (
        "👤 <b>User Info</b>\n\n"
        f"Name: {name}\n"
        f"ID: <code>{target.id}</code>\n"
        f"Username: @{escape(username) if username != 'Not available' else username}\n"
        f"Group status: <b>{escape(str(status))}</b>\n"
        f"Coins: 🪙 <b>{coins}</b>\n"
        f"Last seen: {escape(str(last) if last else 'Not available')}\n"
        f"Bot account: {'Yes' if getattr(target, 'is_bot', False) else 'No'}"
    )
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def groupinfo_cmd(update, context):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return
    if not spend_coins(chat.id, update.effective_user.id, 1):
        msg = await update.message.reply_text("🪙 Group info dekhne ke liye 1 coin chahiye.")
        schedule_delete(context, msg)
        return
    save_group(chat)
    total = await context.bot.get_chat_member_count(chat.id)
    indexed = db.members.count_documents({"chat_id": chat.id})
    admins = await context.bot.get_chat_administrators(chat.id)
    msg = await update.message.reply_text(
        f"🖤 <b>Group Info</b>\n\n"
        f"🏷️ {escape(chat.title or 'Unknown')}\n"
        f"🆔 <code>{chat.id}</code>\n"
        f"👥 Telegram total: <b>{total}</b>\n"
        f"💾 Indexed: <b>{indexed}</b>\n"
        f"👑 Admins: <b>{len(admins)}</b>",
        parse_mode=ParseMode.HTML
    )
    schedule_delete(context, msg)

# =========================
# MESSAGE / MEMBER TRACKING
# =========================
async def message_tracker(update, context):
    if not update.effective_chat or not update.effective_user:
        return
    if update.effective_chat.type in ("group", "supergroup"):
        save_group(update.effective_chat)
        touch_user(update.effective_chat.id, update.effective_user)
        add_activity(update.effective_chat.id, update.effective_user.id)

        # Small random coin drop, intentionally rare.
        if random.random() < 0.008:
            amount = random.choice([1, 1, 1, 2])
            add_coins_logged(update.effective_chat.id, update.effective_user.id, amount)
            msg = await update.message.reply_text(
                f"🪙 Lucky drop! {mention(update.effective_user.id, update.effective_user.full_name)} "
                f"got <b>{amount}</b> coin(s)!",
                parse_mode=ParseMode.HTML
            )
            schedule_delete(context, msg)

        # Fight answer
        f = pending_fights.get(update.effective_chat.id)
        if f and f.get("started") and f["started"] + timedelta(minutes=2) >= now():
            if update.effective_user.id in (f["a"], f["b"]) and update.message.text:
                try:
                    ans = int(update.message.text.strip()) - 1
                except ValueError:
                    ans = -1
                if ans == f.get("answer"):
                    winner = update.effective_user
                    add_coins_logged(update.effective_chat.id, winner.id, 3)
                    pending_fights.pop(update.effective_chat.id, None)
                    msg = await update.message.reply_text(
                        f"🥊🏆 {mention(winner.id, winner.full_name)} wins the quiz battle!\n"
                        "Reward: <b>3 coins</b>",
                        parse_mode=ParseMode.HTML
                    )
                    schedule_delete(context, msg)

async def member_tracker(update, context):
    cm = update.chat_member
    if cm:
        save_group(update.effective_chat)
        touch_user(update.effective_chat.id, cm.new_chat_member.user)

async def private_chat(update, context):
    # Natural AI DM conversation. Commands, audio uploads and voice notes are handled separately.
    if update.effective_chat.type == "private" and update.message and update.message.text:
        reply = await ai_reply(
            update.effective_user.id,
            update.effective_user.full_name,
            update.message.text.strip(),
        )
        await update.message.reply_text(reply)
        # DMs are intentionally not auto-deleted.

# =========================
# STARTUP / SCHEDULER
# =========================
async def post_init(app):
    await mt.connect()
    if not await mt.is_user_authorized():
        raise RuntimeError("STRING_SESSION is not authorized.")

    if music_mt:
        await music_mt.connect()
        if not await music_mt.is_user_authorized():
            raise RuntimeError("MUSIC_SESSION is not authorized.")
        await music_calls.start()
        try:
            from pytgcalls import filters as pt_filters
            @music_calls.on_stream_end()
            async def _music_stream_end(client, update):
                await music_stream_end(client, update)
        except Exception:
            pass

    # Daily giveaway at 20:00 IST.
    if app.job_queue:
        app.job_queue.run_daily(
            giveaway_job,
            time=time(20, 0, tzinfo=IST),
            name="giveaway_8pm_ist",
        )

async def post_shutdown(app):
    if music_calls:
        try:
            await music_calls.stop()
        except Exception:
            pass
    if music_mt and music_mt is not mt:
        await music_mt.disconnect()
    if mt:
        await mt.disconnect()
    mongo.close()

application_bot = None

async def error_handler(update, context):
    err = context.error
    if err and "Message to be replied not found" in str(err):
        return
    print(f"Telegram handler error: {err!r}")

# Tiny HTTP server for Render Web Service + UptimeRobot.
# It runs independently of the Telegram polling loop and does not change bot features.
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b"Fun in Shadows is alive"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return

def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    print(f"🌐 Health server listening on 0.0.0.0:{port}")
    threading.Thread(target=server.serve_forever, daemon=True).start()

def main():
    global application_bot
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application_bot = app.bot
    start_health_server()

    commands = {
        "start": start,
        "help": help_cmd,
        "call": call_cmd,
        "stop_calling": stop_calling_cmd,
        "calladmins": calladmins_cmd,
        "health": health_cmd,
        "coin_ballance": coin_balance_cmd,
        "quiz": quiz_cmd,
        "rost": roast_cmd,
        "game": game_cmd,
        "rank": rank_cmd,
        "participate": participate_cmd,
        "activity": activity_cmd,
        "fight": fight_cmd,
        "accept": accept_cmd,
        "groupinfo": groupinfo_cmd,
        "userinfo": userinfo_cmd,
        "music": music_menu_cmd,
        "play": play_cmd,
        "pause": pause_cmd,
        "resume": resume_cmd,
        "skip": skip_cmd,
        "stop": stop_cmd,
        "queue": queue_cmd,
        "volume": volume_cmd,
    }
    for name, fn in commands.items():
        app.add_handler(CommandHandler(name, fn))

    # Inline-button quiz answers.
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern=r"^quiz:[0-3]$"))
    app.add_handler(CallbackQueryHandler(game_callback, pattern=r"^game:"))
    app.add_handler(CallbackQueryHandler(music_menu_callback, pattern=r"^music:"))

    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, message_tracker)
    )
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.AUDIO, private_audio))
    app.add_handler(MessageHandler(filters.VOICE, voice_note_reply))
    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND & ~filters.AUDIO & ~filters.VOICE, private_chat)
    )
    app.add_handler(ChatMemberHandler(member_tracker, ChatMemberHandler.CHAT_MEMBER))
    app.add_error_handler(error_handler)

    print("🖤 Fun in Shadows v2 running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
