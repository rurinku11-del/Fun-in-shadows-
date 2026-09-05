import os
import sqlite3
import random
import asyncio
from html import escape

from telegram import Update, ChatMember
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ChatMemberHandler,
    ContextTypes, filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
DB_PATH = os.getenv("BOT_DB", "fun_in_shadows.db")

# Number of users mentioned in each /call message.
MIN_PER_CALL = 2
MAX_PER_CALL = 5
CALL_DELAY = 1.2

FUN_REPLIES = [
    "👀 Shadows se koi bach nahi sakta...",
    "🖤 Fun in Shadows mode: ON!",
    "😈 Aaj ka chaos kiski taraf se?",
    "🌑 Shadow roll call complete.",
]

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("""CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY,
    title TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS members (
    chat_id INTEGER,
    user_id INTEGER,
    first_name TEXT,
    username TEXT,
    is_bot INTEGER DEFAULT 0,
    last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(chat_id, user_id)
)""")
conn.commit()


def remember_group(chat):
    conn.execute(
        "INSERT OR REPLACE INTO groups(chat_id,title) VALUES(?,?)",
        (chat.id, chat.title or str(chat.id)),
    )
    conn.commit()


def remember_user(chat_id, user):
    if not user:
        return
    conn.execute(
        """INSERT OR REPLACE INTO members
           (chat_id,user_id,first_name,username,is_bot,last_seen)
           VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)""",
        (chat_id, user.id, user.first_name or "", user.username or "",
         int(user.is_bot)),
    )
    conn.commit()


def get_saved_members(chat_id):
    rows = conn.execute(
        """SELECT user_id, first_name, username
           FROM members WHERE chat_id=? AND is_bot=0
           ORDER BY first_name COLLATE NOCASE""",
        (chat_id,),
    ).fetchall()
    return rows


def mention_html(user_id, first_name):
    # tg://user?id=... lets Telegram mention a user without needing a username.
    return f'<a href="tg://user?id={user_id}">{escape(first_name or "User")}</a>'


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user:
        return False
    member = await context.bot.get_chat_member(
        update.effective_chat.id, update.effective_user.id
    )
    return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat:
        remember_group(update.effective_chat)
    await update.message.reply_text(
        "🖤 <b>Fun in Shadows</b>\n\n"
        "Commands:\n"
        "• /call — members ko 2–5 ke batches mein tag\n"
        "• /calladmins — admins ko tag\n"
        "• /groupinfo — group/member stats\n"
        "• /fun — random fun reply\n"
        "• /help — commands\n\n"
        "Bot ko group mein admin rakhna recommended hai.",
        parse_mode=ParseMode.HTML,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🖤 <b>Fun in Shadows — Help</b>\n\n"
        "/call — saved members ko 2–5 per message tag karta hai\n"
        "/calladmins — current group admins ko tag karta hai\n"
        "/groupinfo — basic stored info\n"
        "/fun — random fun response\n\n"
        "⚠️ /call ko admin-only rakha gaya hai taaki group spam na ho.",
        parse_mode=ParseMode.HTML,
    )


async def call_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("⛔ Sirf group admins /call use kar sakte hain.")
        return

    chat = update.effective_chat
    remember_group(chat)

    members = get_saved_members(chat.id)
    # Don't mention the bot itself.
    members = [m for m in members if m[0] != context.bot.id]

    if not members:
        await update.message.reply_text(
            "👀 Abhi members database mein nahi mile. "
            "Bot ko group mein admin karke members ko interact/join karne do."
        )
        return

    random.shuffle(members)

    await update.message.reply_text(
        f"🌑 <b>Fun in Shadows — Roll Call</b>\n"
        f"👥 {len(members)} saved members",
        parse_mode=ParseMode.HTML,
    )

    i = 0
    while i < len(members):
        batch_size = random.randint(MIN_PER_CALL, MAX_PER_CALL)
        batch = members[i:i + batch_size]
        mentions = " ".join(mention_html(uid, name) for uid, name, username in batch)
        await update.message.reply_text(
            f"🔔 {mentions}",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        i += batch_size
        if i < len(members):
            await asyncio.sleep(CALL_DELAY)


async def call_admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text(
            "⛔ Sirf group admins /calladmins use kar sakte hain."
        )
        return

    chat = update.effective_chat
    admins = await context.bot.get_chat_administrators(chat.id)
    admins = [m.user for m in admins if not m.user.is_bot]

    if not admins:
        await update.message.reply_text("👑 Koi human admin nahi mila.")
        return

    mentions = " ".join(mention_html(u.id, u.first_name) for u in admins)
    await update.message.reply_text(
        f"👑 <b>Calling Admins:</b>\n{mentions}",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def groupinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    chat = update.effective_chat
    remember_group(chat)

    count = conn.execute(
        "SELECT COUNT(*) FROM members WHERE chat_id=? AND is_bot=0",
        (chat.id,),
    ).fetchone()[0]

    admins = await context.bot.get_chat_administrators(chat.id)
    await update.message.reply_text(
        f"🖤 <b>Fun in Shadows — Group Info</b>\n\n"
        f"🏷️ Name: {escape(chat.title or 'Unknown')}\n"
        f"🆔 ID: <code>{chat.id}</code>\n"
        f"👥 Saved members: <b>{count}</b>\n"
        f"👑 Admins: <b>{len(admins)}</b>",
        parse_mode=ParseMode.HTML,
    )


async def fun_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(FUN_REPLIES))


async def message_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_user:
        remember_group(update.effective_chat)
        remember_user(update.effective_chat.id, update.effective_user)


async def member_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    remember_group(chat)

    cm = update.chat_member
    if cm:
        remember_user(chat.id, cm.new_chat_member.user)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("Bot error:", context.error)


def main():
    if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError(
            "BOT_TOKEN set karo. Example Linux/Termux: export BOT_TOKEN='123:ABC...'"
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("call", call_cmd))
    app.add_handler(CommandHandler("calladmins", call_admins_cmd))
    app.add_handler(CommandHandler("groupinfo", groupinfo_cmd))
    app.add_handler(CommandHandler("fun", fun_cmd))

    # Stores users from messages the bot receives.
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, message_tracker)
    )
    # Stores users when Telegram sends join/member-status updates.
    app.add_handler(ChatMemberHandler(member_tracker, ChatMemberHandler.CHAT_MEMBER))

    app.add_error_handler(error_handler)

    print("🖤 Fun in Shadows bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
