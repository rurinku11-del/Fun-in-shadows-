import os
import random
import asyncio
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from html import escape

from yt_dlp import YoutubeDL
from pytgcalls import PyTgCalls

from pymongo import MongoClient, UpdateOne
from telethon import TelegramClient
from telethon.sessions import StringSession
from telegram import Update, ChatMember
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler,
    ContextTypes, filters
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

IST = ZoneInfo("Asia/Kolkata")
DELETE_AFTER = int(os.getenv("DELETE_AFTER", "300"))  # 5 minutes
CALL_MIN = int(os.getenv("CALL_MIN", "2"))
CALL_MAX = int(os.getenv("CALL_MAX", "5"))
CALL_DELAY = float(os.getenv("CALL_DELAY", "1.2"))

mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
db = mongo["fun_in_shadows"]
users = db["users"]
groups = db["groups"]
activity = db["activity"]
giveaways = db["giveaways"]

mt = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
music_mt = TelegramClient(StringSession(MUSIC_SESSION), API_ID, API_HASH) if MUSIC_SESSION else None
music_calls = PyTgCalls(music_mt) if music_mt else None

QUIZ = [
    ("What is the capital of India?", ["Delhi", "Mumbai", "Kolkata", "Chennai"], 0),
    ("Which planet is known as the Red Planet?", ["Earth", "Mars", "Jupiter", "Venus"], 1),
    ("2 + 2 × 2 = ?", ["6", "8", "4", "10"], 0),
    ("Which language is used by Telegram bots in this project?", ["Python", "Rust", "PHP", "Ruby"], 0),
]
GAMES = ["🎲 Dice Duel", "🎯 Target Shot", "🪙 Coin Flip"]

# in-memory state is intentionally small; persistent balances/activity are MongoDB-backed.
active_calls = set()
pending_quizzes = {}
pending_fights = {}
music_queues = {}
music_current = {}
music_volume = {}

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
        opts = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": True,
            "noplaylist": True,
            "default_search": "ytsearch1",
        }
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
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
        direct_url, title = await music_direct_url(item["webpage_url"])
        if not direct_url:
            raise RuntimeError("No playable audio URL")
        await music_calls.play(chat_id, direct_url)
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
        msg = await update.message.reply_text("🎵 Usage: /play <song name or YouTube URL>")
        schedule_delete(context, msg)
        return
    query = " ".join(context.args).strip()
    try:
        info = await music_search(query)
        if not info:
            raise RuntimeError("Song not found")
        webpage = info.get("webpage_url") or info.get("url")
        title = info.get("title") or query
        if not webpage:
            raise RuntimeError("No playable result")
        item = {
            "title": title,
            "webpage_url": webpage,
            "requested_by": update.effective_user.id,
        }
        queue = music_queues.setdefault(update.effective_chat.id, [])
        playing = update.effective_chat.id in music_current
        queue.append(item)
        if not playing:
            await music_play_next(update.effective_chat.id)
            text = f"🎵 <b>Now Playing</b>\n{escape(title)}"
        else:
            text = f"🎵 <b>Added to Queue</b>\n{escape(title)}\n📋 Position: <b>{len(queue)}</b>"
    except Exception as e:
        text = f"❌ Music error: <code>{escape(str(e)[:300])}</code>"
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def pause_cmd(update, context):
    if not music_ready():
        return
    try:
        await music_calls.pause(update.effective_chat.id)
        text = "⏸️ Paused."
    except Exception as e:
        text = f"❌ {escape(str(e)[:250])}"
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def resume_cmd(update, context):
    if not music_ready():
        return
    try:
        await music_calls.resume(update.effective_chat.id)
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
        await music_calls.leave_call(chat_id)
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
        await music_calls.leave_call(chat_id)
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

async def volume_cmd(update, context):
    # PyTgCalls' current API does not expose a simple player-volume method;
    # keep the command as a friendly placeholder instead of calling a stale API.
    msg = await update.message.reply_text(
        "🔊 Volume control is reserved for the next music-engine update."
    )
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
        "/groupinfo — group info\n"
        "/play <song> — music in voice chat\n"
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
        "Group: /health, /activity, /groupinfo\n"
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
    schedule_delete(context, status)

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
            batch = rows[i:i + CALL_MAX]
            text = " ".join(mention(r["user_id"], user_label(r)) for r in batch)
            if text:
                out = await context.bot.send_message(
                    chat_id,
                    "🔔 " + text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                schedule_delete(context, out)
            i += CALL_MAX
            await asyncio.sleep(CALL_DELAY)
    except Exception as e:
        out = await context.bot.send_message(
            chat_id, f"❌ Call failed: <code>{escape(str(e))}</code>",
            parse_mode=ParseMode.HTML
        )
        schedule_delete(context, out)
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
    q, options, answer = random.choice(QUIZ)
    pending_quizzes[chat_id] = {"answer": answer, "expires": now() + timedelta(minutes=2)}
    opts = "\n".join(f"{i+1}. {escape(x)}" for i, x in enumerate(options))
    msg = await update.message.reply_text(
        f"🧠 <b>QUIZ</b>\n\n{escape(q)}\n\n{opts}\n\n"
        "Reply with 1–4. Winner gets <b>2 coins</b>.",
        parse_mode=ParseMode.HTML,
    )
    schedule_delete(context, msg)

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
    games = random.sample(GAMES, 3)
    lines = ["🎮 <b>3 Random Games</b>", ""]
    for g in games:
        won = random.random() < 0.22  # deliberately hard
        reward = random.choice([1, 1, 1, 2, 3]) if won else 0
        if won:
            add_coins(update.effective_chat.id, update.effective_user.id, reward)
        lines.append(f"{g} → {'🏆 WIN +' + str(reward) + ' 🪙' if won else '❌ Lose'}")
    lines.append("\n🪙 Coins intentionally hard to earn.")
    msg = await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

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
    balance = get_coins(chat_id, uid)
    if balance < 2:
        msg = await update.message.reply_text("🪙 Fight entry is 2 coins. You don't have enough.")
        schedule_delete(context, msg)
        return
    if not update.message.reply_to_message:
        msg = await update.message.reply_text("🧠😂 Reply to a friend's message and use /fight.")
        schedule_delete(context, msg)
        return
    opponent = update.message.reply_to_message.from_user
    if opponent.is_bot or opponent.id == uid:
        msg = await update.message.reply_text("❌ Choose a real opponent.")
        schedule_delete(context, msg)
        return

    add_coins_logged(chat_id, uid, -2)
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

async def groupinfo_cmd(update, context):
    chat = update.effective_chat
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

        # Quiz answer
        q = pending_quizzes.get(update.effective_chat.id)
        if q and q["expires"] >= now() and update.message.text:
            try:
                choice_num = int(update.message.text.strip()) - 1
                if choice_num == q["answer"]:
                    add_coins_logged(update.effective_chat.id, update.effective_user.id, 2)
                    pending_quizzes.pop(update.effective_chat.id, None)
                    msg = await update.message.reply_text(
                        f"🧠🏆 Correct! {mention(update.effective_user.id, update.effective_user.full_name)} "
                        "wins <b>2 coins</b>.",
                        parse_mode=ParseMode.HTML
                    )
                    schedule_delete(context, msg)
            except ValueError:
                pass

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
    # Normal DM conversation. Commands are handled separately.
    if update.effective_chat.type == "private" and update.message:
        replies = [
            "🖤 Shadows mein welcome. Bolo kya scene hai?",
            "👀 Main sun raha hoon.",
            "😈 Fun in Shadows online hai.",
            "😂 Kya hukam hai?",
        ]
        msg = await update.message.reply_text(random.choice(replies))
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
        music_calls.start()
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
    if music_mt:
        await music_mt.disconnect()
    await mt.disconnect()
    mongo.close()

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

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

    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, message_tracker)
    )
    app.add_handler(
        MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, private_chat)
    )
    app.add_handler(ChatMemberHandler(member_tracker, ChatMemberHandler.CHAT_MEMBER))

    print("🖤 Fun in Shadows v2 running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
