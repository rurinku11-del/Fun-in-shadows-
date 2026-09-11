import os
import random
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from html import escape

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
MONGO_URI = os.environ["MONGO_URI"]

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

mt = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
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

# Permanent guild ranks. A rank is archived once the balance reaches its threshold.
# The reward is granted only once per rank. S rank is the rarest rank.
RANKS = [
    ("E", 0, 0),
    ("F", 50, 10),
    ("D", 150, 25),
    ("B", 300, 50),
    ("A", 600, 100),
    ("S", 1000, 199),
]
RANK_ORDER = {name: i for i, (name, _, _) in enumerate(RANKS)}

def rank_for_coins(coins):
    current = RANKS[0]
    for rank in RANKS:
        if coins >= rank[1]:
            current = rank
        else:
            break
    return current

async def archive_rank_if_needed(chat_id, user_id, context):
    row = users.find_one({"chat_id": chat_id, "user_id": user_id}) or {}
    coins = int(row.get("coins", 0))
    rank, threshold, reward = rank_for_coins(coins)
    archived = row.get("archived_rank", "E")
    if RANK_ORDER.get(rank, 0) <= RANK_ORDER.get(archived, 0):
        return

    lower_ranks = [name for name, _, _ in RANKS if RANK_ORDER[name] < RANK_ORDER[rank]]
    query = {"chat_id": chat_id, "user_id": user_id, "$or": [
        {"archived_rank": {"$in": lower_ranks}},
        {"archived_rank": {"$exists": False}},
    ]}
    archived_result = users.update_one(
        query,
        {"$set": {"archived_rank": rank, "rank_archived_at": now()}},
        upsert=False,
    )
    if archived_result.modified_count == 0:
        return
    add_coins(chat_id, user_id, reward)
    if reward:
        try:
            db.coin_events.insert_one({"chat_id": chat_id, "user_id": user_id, "amount": reward, "reason": f"{rank}_rank_reward", "at": now()})
        except Exception:
            pass

    if rank == "S":
        admin_ok = False
        admin_error = ""
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
                admin_ok = await context.bot.promote_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    can_manage_chat=True,
                    can_delete_messages=True,
                    can_manage_video_chats=True,
                    can_restrict_members=True,
                    can_pin_messages=True,
                    can_invite_users=True,
                    can_change_info=False,
                    can_promote_members=False,
                )
            else:
                admin_ok = True
        except Exception as e:
            admin_error = str(e)[:180]
        if admin_ok:
            text = (f"🎉 <b>Congratulations!</b> You have archived <b>S Rank</b>.\n\n"
                    f"👑 You have been promoted to group admin.\n"
                    f"🪙 You got <b>{reward}</b> coins.")
        else:
            text = (f"🎉 <b>Congratulations!</b> You have archived <b>S Rank</b>.\n\n"
                    f"🪙 You got <b>{reward}</b> coins.\n"
                    "⚠️ I could not grant admin automatically. Please give the bot permission to promote members and try again.")
    else:
        text = (f"🎉 <b>Congratulations!</b> You have archived <b>{rank} Rank</b>.\n\n"
                f"🪙 You got <b>{reward}</b> coins.")
    try:
        msg = await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        schedule_delete(context, msg)
    except Exception:
        pass


# in-memory state is intentionally small; persistent balances/activity are MongoDB-backed.
active_calls = set()
pending_quizzes = {}
active_games = {}
pending_fights = {}

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
# COMMANDS
# =========================
async def start(update, context):
    save_group(update.effective_chat)
    touch_user(update.effective_chat.id, update.effective_user)
    text = (
        "🖤 <b>FUN IN SHADOWS</b>\n\n"
        "Use /help to see the available features.\n"
        "Music and AI chat are currently disabled.\n\n"
        "Support: @Shadow_atomic_21"
    )
    msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

async def help_cmd(update, context):
    text = (
        "🖤 <b>Fun in Shadows Help</b>\n\n"
        "Tagging: /call [message], /stop_calling, /calladmins\n"
        "Fun: /quiz, /rost, /game, /fight\n"
        "Coins: /coin_ballance, /give_coin <amount>, /rank\n"
        "Ranks: E → F → D → B → A → S\n"
        "S Rank requires 1,000 coins and grants 199 coins plus admin promotion.\n"
        "Group: /health, /activity, /groupinfo, /userinfo\n"
        "Giveaway: /participate (result at 8 PM IST)\n\n"
        "Support: @Shadow_atomic_21"
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
        msg = await update.message.reply_text("/call is already running. Use /stop_calling.")
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
        custom_message = " ".join(context.args).strip()
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
                call_text = ((escape(custom_message) + "\n\n") if custom_message else "") + text
                out = await context.bot.send_message(
                    chat_id,
                    call_text,
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
        msg = await update.message.reply_text("❤️ Health checks are free.")
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
    add_coins_logged(chat_id, winner.id, 2, context)
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
        f"😂 {escape(target.first_name)}, even your Wi-Fi is more stable than you.",
        f"🔥 {escape(target.first_name)}, confidence 100%, logic still loading...",
        f"🤣 {escape(target.first_name)}, even Google got tired of searching for you.",
        f"💀 {escape(target.first_name)}, you are online, but your system is offline.",
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
            add_coins_logged(chat_id, user_id, 2, context)
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
            add_coins_logged(chat_id, user_id, 3, context)
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
            add_coins_logged(chat_id, user_id, 1, context)
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
        rows = list(users.find({"chat_id": chat_id}, {"user_id":1,"first_name":1,"last_name":1,"coins":1,"archived_rank":1})
                   .sort("coins", -1).limit(10))
    else:
        days = {"daily": 1, "weekly": 7, "monthly": 30}[period]
        since = now() - timedelta(days=days)
        rows = list(db.coin_events.aggregate([
            {"$match": {"chat_id": chat_id, "at": {"$gte": since}}},
            {"$group": {"_id": "$user_id", "coins": {"$sum": "$amount"}}},
            {"$sort": {"coins": -1}}, {"$limit": 10},
        ]))
        for r in rows:
            u = users.find_one({"chat_id": chat_id, "user_id": r["_id"]}) or {}
            r.update({"first_name": u.get("first_name",""), "last_name": u.get("last_name",""), "archived_rank": u.get("archived_rank","E")})

    lines = [f"🏆 <b>{title} Ranking</b>", "", "<b>Ranks</b>"]
    for rank, threshold, reward in RANKS:
        extra = " + admin" if rank == "S" else ""
        lines.append(f"{rank}: {threshold:,} coins → +{reward} reward{extra}")
    lines.append("")
    if not rows:
        lines.append("No coin activity yet.")
    else:
        for i, r in enumerate(rows, 1):
            uid = r.get("user_id", r.get("_id"))
            name = user_label(r)
            coins = r.get("coins", 0)
            archived = r.get("archived_rank", "E")
            lines.append(f"{i}. {mention(uid, name)} — 🪙 {coins} — <b>{escape(archived)} Rank</b>")
    lines.append("\nUse /rank daily, /rank weekly, /rank monthly or /rank.")
    msg = await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
    schedule_delete(context, msg)

def add_coins_logged(chat_id, user_id, amount, context=None):
    add_coins(chat_id, user_id, amount)
    db.coin_events.insert_one({"chat_id": chat_id, "user_id": user_id, "amount": amount, "at": now()})
    if amount > 0 and context is not None:
        context.application.create_task(archive_rank_if_needed(chat_id, user_id, context))

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
        msg = await update.message.reply_text("🧠😂 Reply to a user's message and use /fight.")
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
        msg = await update.message.reply_text("🪙 Both fighters need 2 coins. Fight cancelled.")
        schedule_delete(context, msg)
        return
    if not spend_coins(chat_id, f["a"], 2):
        pending_fights.pop(chat_id, None)
        msg = await update.message.reply_text("🪙 The challenger's balance changed. Fight cancelled.")
        schedule_delete(context, msg)
        return
    if not spend_coins(chat_id, f["b"], 2):
        add_coins(chat_id, f["a"], 2)
        context.application.create_task(archive_rank_if_needed(chat_id, f["a"], context))
        pending_fights.pop(chat_id, None)
        msg = await update.message.reply_text("🪙 The opponent no longer has 2 coins. Fight cancelled; the challenger was refunded.")
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

async def give_coin_cmd(update, context):
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        msg = await update.message.reply_text("🪙 /give_coin can only be used in a group.")
        return
    if not context.args:
        msg = await update.message.reply_text("Usage: reply to a user with /give_coin <amount>.")
        schedule_delete(context, msg)
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        amount = 0
    if amount <= 0:
        msg = await update.message.reply_text("❌ Enter a positive whole number of coins.")
        schedule_delete(context, msg)
        return

    target = None
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
    elif len(context.args) >= 2 and context.args[1].startswith("@"):
        username = context.args[1].lstrip("@")
        row = users.find_one({"chat_id": chat.id, "username": username})
        if row:
            target = type("Obj", (), {
                "id": row["user_id"],
                "first_name": row.get("first_name", "User"),
                "last_name": row.get("last_name", ""),
                "username": row.get("username", username),
                "is_bot": False,
            })()
    if not target:
        msg = await update.message.reply_text("❌ Reply to the user you want to pay, then use /give_coin <amount>.")
        schedule_delete(context, msg)
        return
    if target.is_bot or target.id == update.effective_user.id:
        msg = await update.message.reply_text("❌ You cannot give coins to a bot or to yourself.")
        schedule_delete(context, msg)
        return

    sender_id = update.effective_user.id
    result = users.update_one(
        {"chat_id": chat.id, "user_id": sender_id, "coins": {"$gte": amount}},
        {"$inc": {"coins": -amount}},
        upsert=False,
    )
    if result.modified_count == 0:
        balance = get_coins(chat.id, sender_id)
        if balance <= 0:
            msg = await update.message.reply_text("❌ Your balance is empty. Gain more coins and try again.")
        else:
            msg = await update.message.reply_text(
                f"❌ You only have {balance} coins, so you cannot give {amount}."
            )
        schedule_delete(context, msg)
        return

    touch_user(chat.id, target)
    users.update_one(
        {"chat_id": chat.id, "user_id": target.id},
        {"$inc": {"coins": amount}, "$set": {
            "first_name": target.first_name or "",
            "last_name": target.last_name or "",
            "username": target.username or "",
            "last_seen": now(),
        }},
        upsert=True,
    )
    context.application.create_task(archive_rank_if_needed(chat.id, target.id, context))
    try:
        db.coin_events.insert_one({"chat_id": chat.id, "from_user_id": sender_id,
                                   "to_user_id": target.id, "amount": amount, "at": now()})
    except Exception:
        pass
    new_balance = get_coins(chat.id, sender_id)
    target_name = ((target.first_name or "") + " " + (target.last_name or "")).strip() or "User"
    msg = await update.message.reply_text(
        f"✅ {mention(target.id, target_name)} received <b>{amount}</b> coins.\n"
        f"🪙 Your balance: <b>{new_balance}</b>",
        parse_mode=ParseMode.HTML,
    )
    schedule_delete(context, msg)

async def userinfo_cmd(update, context):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        msg = await update.message.reply_text("👤 User info costs 2 coins in a group.")
        return
    if not spend_coins(chat.id, update.effective_user.id, 2):
        msg = await update.message.reply_text("🪙 You need 2 coins for user info.")
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
        msg = await update.message.reply_text("🪙 You need 1 coin for group info.")
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
            add_coins_logged(update.effective_chat.id, update.effective_user.id, amount, context)
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
                    add_coins_logged(update.effective_chat.id, winner.id, 3, context)
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

# =========================
# STARTUP / SCHEDULER
# =========================
async def post_init(app):
    await mt.connect()
    if not await mt.is_user_authorized():
        raise RuntimeError("STRING_SESSION is not authorized.")

    # Keep the Telegram command menu updated in groups.
    command_list = [
        ("start", "Show bot commands"),
        ("help", "Show all commands"),
        ("call", "Tag members in 2-5 batches"),
        ("stop_calling", "Stop an active call"),
        ("calladmins", "Tag all admins"),
        ("health", "Check activity health"),
        ("coin_ballance", "Check coin balance"),
        ("give_coin", "Give coins to a user"),
        ("quiz", "Play a button quiz"),
        ("rost", "Get a funny roast"),
        ("game", "Play a game"),
        ("rank", "View coin rankings"),
        ("participate", "Enter the giveaway"),
        ("activity", "View group activity"),
        ("fight", "Start a quiz battle"),
        ("accept", "Accept a quiz battle"),
        ("groupinfo", "View group info"),
        ("userinfo", "View user info"),
    ]
    bot_commands = [__import__("telegram").BotCommand(name, desc) for name, desc in command_list]
    await app.bot.set_my_commands(bot_commands)
    try:
        from telegram import BotCommandScopeAllGroupChats
        await app.bot.set_my_commands(bot_commands, scope=BotCommandScopeAllGroupChats())
    except Exception as e:
        print(f"Could not set group command menu: {e!r}")

    # Daily giveaway at 20:00 IST.
    if app.job_queue:
        app.job_queue.run_daily(
            giveaway_job,
            time=time(20, 0, tzinfo=IST),
            name="giveaway_8pm_ist",
        )

async def post_shutdown(app):
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
        "give_coin": give_coin_cmd,
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
    }
    for name, fn in commands.items():
        app.add_handler(CommandHandler(name, fn))

    # Inline-button quiz answers.
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern=r"^quiz:[0-3]$"))
    app.add_handler(CallbackQueryHandler(game_callback, pattern=r"^game:"))
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, message_tracker)
    )
    app.add_handler(ChatMemberHandler(member_tracker, ChatMemberHandler.CHAT_MEMBER))
    app.add_error_handler(error_handler)

    print("🖤 Fun in Shadows v2 running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
