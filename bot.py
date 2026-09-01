import os, sqlite3, random, threading, time, html
from datetime import datetime, timedelta, timezone
from flask import Flask
import telebot
from telebot import types
from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError

TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not API_ID or not API_HASH or not SESSION_STRING:
    raise RuntimeError("API_ID, API_HASH and SESSION_STRING are required")

DB = "bot.db"
DELETE_AFTER = 300
AUTO_COIN_INTERVAL = 6 * 60 * 60
IST = timezone(timedelta(hours=5, minutes=30))

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# User account client: used for reading the actual group member list.
# The bot token remains responsible for normal bot commands.
user_client = Client(
    "member_reader",
    api_id=int(API_ID),
    api_hash=API_HASH,
    session_string=SESSION_STRING,
    in_memory=True
)

def db():
    c=sqlite3.connect(DB, check_same_thread=False)
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,name TEXT,username TEXT,is_bot INTEGER,last_seen TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS activity(
        chat_id INTEGER,user_id INTEGER,day TEXT,messages INTEGER,
        PRIMARY KEY(chat_id,user_id,day))""")
    c.execute("""CREATE TABLE IF NOT EXISTS coins(
        chat_id INTEGER,user_id INTEGER,balance INTEGER,
        PRIMARY KEY(chat_id,user_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings(
        chat_id INTEGER PRIMARY KEY,calling INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS giveaway(
        chat_id INTEGER,user_id INTEGER,
        PRIMARY KEY(chat_id,user_id))""")
    c.commit(); return c
db().close()

def now(): return datetime.now(timezone.utc)
def group(m): return m.chat.type in ("group","supergroup")
def remember(u):
    if not u or u.is_bot:return
    c=db(); c.execute("""INSERT INTO users VALUES(?,?,?,?,?)
      ON CONFLICT(user_id) DO UPDATE SET name=excluded.name,
      username=excluded.username,last_seen=excluded.last_seen""",
      (u.id,u.first_name or "User",u.username or "",0,now().isoformat()))
    c.commit(); c.close()
def track(m):
    if not m.from_user or m.from_user.is_bot:return
    remember(m.from_user); d=now().strftime("%Y-%m-%d")
    c=db(); c.execute("""INSERT INTO activity VALUES(?,?,?,1)
      ON CONFLICT(chat_id,user_id,day) DO UPDATE SET messages=messages+1""",
      (m.chat.id,m.from_user.id,d))
    c.execute("UPDATE users SET last_seen=? WHERE user_id=?",
              (now().isoformat(),m.from_user.id)); c.commit(); c.close()
def addcoins(chat,uid,n):
    c=db(); c.execute("""INSERT INTO coins VALUES(?,?,?)
      ON CONFLICT(chat_id,user_id) DO UPDATE SET balance=balance+excluded.balance""",
      (chat,uid,n)); c.commit(); c.close()
def balance(chat,uid):
    c=db(); r=c.execute("SELECT balance FROM coins WHERE chat_id=? AND user_id=?",
                         (chat,uid)).fetchone(); c.close(); return r[0] if r else 0
def mention(uid,name):
    return f'<a href="tg://user?id={uid}">{html.escape(name or "User")}</a>'
def temp(chat,text):
    try:
        m=bot.send_message(chat,text)
        threading.Timer(DELETE_AFTER,lambda:delete(chat,m.message_id)).start()
    except Exception: pass
def delete(chat,mid):
    try: bot.delete_message(chat,mid)
    except Exception: pass
def members(chat):
    c=db(); r=c.execute("""SELECT DISTINCT u.user_id,u.name,u.username
      FROM users u JOIN activity a ON a.user_id=u.user_id
      WHERE a.chat_id=? AND u.is_bot=0""",(chat,)).fetchall(); c.close(); return r

def all_group_members(chat_id):
    """Fetch members through the logged-in Telegram user session.

    Returns (user_id, display_name, username) for members visible to the
    account. This is used by /call so inactive members are not limited to
    the bot's activity database.
    """
    result = []
    try:
        if not user_client.is_connected:
            user_client.start()
        for u in user_client.get_chat_members(chat_id):
            user = u.user
            if not user or user.is_bot:
                continue
            name = " ".join(x for x in [user.first_name, user.last_name] if x).strip() or "User"
            result.append((user.id, name, user.username or ""))
            remember(user)
        return result
    except FloodWait as e:
        time.sleep(e.value)
    except RPCError:
        pass
    except Exception:
        pass
    return result
def isadmin(m):
    try:return bot.get_chat_member(m.chat.id,m.from_user.id).status in ("administrator","creator")
    except:return False

@bot.message_handler(
    func=lambda m: group(m) and bool(m.from_user) and
        not (m.content_type == "text" and (m.text or "").startswith("/")),
    content_types=["text","photo","video","document","audio","voice","sticker","animation"]
)
def tracker(m):
    track(m)

@bot.message_handler(commands=["call"])
def call(m):
    if not group(m):
        return

    # Prefer the real Telegram member list so inactive members are included.
    rows = all_group_members(m.chat.id)

    # Fallback to tracked members if the user session cannot read the group.
    if not rows:
        rows = members(m.chat.id)

    rows = [x for x in rows if x[0] != m.from_user.id]
    if not rows:
        return temp(m.chat.id, "📢 No members found.")

    tags = [mention(x[0], x[1]) for x in rows]
    p = m.text.split(maxsplit=1)
    msg = p[1].strip() if len(p) > 1 else "Kaha ho"

    # Keep each message comfortably below Telegram's message-size limit.
    chunks = []
    current = []
    current_len = 0
    for tag in tags:
        if current and current_len + len(tag) + 1 > 3500:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
        current.append(tag)
        current_len += len(tag) + 1
    if current:
        chunks.append(" ".join(current))

    for i, chunk in enumerate(chunks):
        suffix = f"\n\n<b>{html.escape(msg)}</b> 👀" if i == len(chunks) - 1 else ""
        temp(m.chat.id, chunk + suffix)

@bot.message_handler(commands=["stop_calling"])
def stop_call(m):
    if group(m) and isadmin(m):
        c=db();c.execute("INSERT OR REPLACE INTO settings VALUES(?,0)",(m.chat.id,))
        c.commit();c.close();temp(m.chat.id,"🛑 Automatic calling stopped.")

@bot.message_handler(commands=["coin_ballance","coin_balance"])
def cb(m): temp(m.chat.id,f"🪙 Balance: <b>{balance(m.chat.id,m.from_user.id)}</b>")

@bot.message_handler(commands=["coin"])
def coin(m): temp(m.chat.id,random.choice(["🪙 Heads","🪙 Tails"]))

QUIZ=[
("Which language is this bot written in?",["Python","Java","C++","Ruby"],"python",3),
("2 + 8 × 2 = ?",["20","18","12","16"],"18",3),
("Capital of India?",["Mumbai","Delhi","Kolkata","Chennai"],"delhi",2),
("Python function keyword?",["func","def","function","lambda"],"def",3)]
qs={}
@bot.message_handler(commands=["quiz"])
def quiz(m):
    q,o,a,r=random.choice(QUIZ);qs[m.chat.id]=(a,r,time.time()+120)
    k=types.InlineKeyboardMarkup()
    for x in o:k.add(types.InlineKeyboardButton(x,callback_data="q:"+x.lower()))
    bot.send_message(m.chat.id,f"🧠 <b>{q}</b>",reply_markup=k)
@bot.callback_query_handler(func=lambda c:c.data.startswith("q:"))
def qa(c):
    s=qs.get(c.message.chat.id)
    if not s or time.time()>s[2]:
        bot.answer_callback_query(c.id,"⏰ Expired.");return
    if c.data[2:]==s[0]:
        addcoins(c.message.chat.id,c.from_user.id,s[1]);qs.pop(c.message.chat.id,None)
        bot.answer_callback_query(c.id,"Correct!")
        temp(c.message.chat.id,f"🧠✅ {mention(c.from_user.id,c.from_user.first_name)} +{s[1]} 🪙")
    else:bot.answer_callback_query(c.id,"❌ Wrong!")

@bot.message_handler(commands=["rost","roast"])
def roast(m):
    u=m.reply_to_message.from_user if m.reply_to_message else m.from_user
    temp(m.chat.id,f"😂 {mention(u.id,u.first_name)} — {random.choice(['Logic.exe stopped working 💀','Confidence 100%, accuracy 2% 😂','Even Google needs help with you 😭'])}")

games={}
@bot.message_handler(commands=["game"])
def game(m):
    key=random.choice(["guess","rps","dice"]);games[m.chat.id]=(key,m.from_user.id,time.time()+120)
    prompt={"guess":"🎯 Pick 1, 2 or 3.","rps":"✊ Rock / Paper / Scissors.","dice":"🎲 Type roll."}[key]
    temp(m.chat.id,f"🎮 <b>Random Game</b>\n{prompt}\nWin = +4 coins. Earning is tough.")
@bot.message_handler(func=lambda m:group(m) and m.content_type=="text" and m.chat.id in games and not m.text.startswith("/"))
def gameans(m):
    key,uid,exp=games[m.chat.id]
    if m.from_user.id!=uid or time.time()>exp:return
    t=m.text.lower().strip();ok=False
    if key=="guess":ok=t in ("1","2","3") and t==random.choice(["1","2","3"])
    if key=="rps":ok=t in ("rock","paper","scissors") and random.random()<.45
    if key=="dice":ok=t=="roll" and random.random()<.4
    games.pop(m.chat.id,None)
    if ok:addcoins(m.chat.id,uid,4);temp(m.chat.id,f"🏆 +4 coins for {mention(uid,m.from_user.first_name)}")
    else:temp(m.chat.id,"🎮 ❌ Lost this round.")

@bot.message_handler(commands=["health"])
def health(m):
    u=m.reply_to_message.from_user if m.reply_to_message else m.from_user
    c=db();r=c.execute("SELECT last_seen FROM users WHERE user_id=?",(u.id,)).fetchone();c.close()
    if not r:return temp(m.chat.id,"❤️ No activity data.")
    weeks=(now()-datetime.fromisoformat(r[0])).total_seconds()/604800
    h=5 if weeks<1 else 3 if weeks<3 else 0
    temp(m.chat.id,f"❤️ <b>Health</b>\n👤 {mention(u.id,u.first_name)}\n🆔 <code>{u.id}</code>\n👤 @{html.escape(u.username or 'none')}\n❤️ {'❤️'*h if h else '💀 0 hearts'}")

@bot.message_handler(commands=["rank"])
def rank(m):
    c=db();rows=c.execute("""SELECT u.user_id,u.name,c.balance FROM coins c
      JOIN users u ON u.user_id=c.user_id WHERE c.chat_id=? AND u.is_bot=0
      ORDER BY c.balance DESC LIMIT 10""",(m.chat.id,)).fetchall();c.close()
    temp(m.chat.id,"🏆 <b>Coin Ranking</b>\n"+"\n".join(f"{i}. {mention(u,n)} — 🪙 {b}" for i,(u,n,b) in enumerate(rows,1)))

@bot.message_handler(commands=["activity"])
def activity(m):
    c=db();rows=c.execute("""SELECT u.user_id,u.name,SUM(a.messages) n
      FROM activity a JOIN users u ON u.user_id=a.user_id WHERE a.chat_id=?
      AND u.is_bot=0 GROUP BY u.user_id ORDER BY n DESC LIMIT 10""",(m.chat.id,)).fetchall();c.close()
    temp(m.chat.id,"📊 <b>Activity</b>\n"+"\n".join(f"{i}. {mention(u,n)} — {x}" for i,(u,n,x) in enumerate(rows,1)))

fight={}
@bot.message_handler(commands=["fight"])
def fightcmd(m):
    t=m.reply_to_message.from_user if m.reply_to_message else None
    if not t:return temp(m.chat.id,"⚔️ Reply to a friend's message with /fight.")
    if t.id==m.from_user.id or balance(m.chat.id,m.from_user.id)<2:return temp(m.chat.id,"⚔️ Entry fee is 2 coins.")
    addcoins(m.chat.id,m.from_user.id,-2);fight[m.chat.id]=(m.from_user.id,t.id)
    temp(m.chat.id,f"🧠😂 {mention(m.from_user.id,m.from_user.first_name)} challenged {mention(t.id,t.first_name)}!\nReply <b>accept</b>.")
@bot.message_handler(func=lambda m:group(m) and m.content_type=="text" and m.chat.id in fight and m.text.lower().strip()=="accept")
def fightaccept(m):
    a,b=fight[m.chat.id]
    if m.from_user.id!=b:return
    if balance(m.chat.id,b)<2: fight.pop(m.chat.id,None);return temp(m.chat.id,"❌ Opponent needs 2 coins.")
    addcoins(m.chat.id,b,-2);w=random.choice([a,b]);addcoins(m.chat.id,w,5);fight.pop(m.chat.id,None)
    temp(m.chat.id,f"⚔️ Winner: {mention(w,'Winner')} — 🏆 +5 coins")

@bot.message_handler(commands=["participate"])
def participate(m):
    if group(m):
        c=db();c.execute("INSERT OR IGNORE INTO giveaway VALUES(?,?)",(m.chat.id,m.from_user.id));c.commit();c.close()
        temp(m.chat.id,"🎁 Participation recorded!")

def giveaway_worker():
    while True:
        try:
            t=datetime.now(IST)
            if t.hour==20 and t.minute==0:
                c=db();chats=[x[0] for x in c.execute("SELECT DISTINCT chat_id FROM giveaway")]
                for chat in chats:
                    us=[x[0] for x in c.execute("SELECT user_id FROM giveaway WHERE chat_id=?",(chat,))]
                    if us:
                        w=random.choice(us);temp(chat,f"🎁🏆 Giveaway winner: {mention(w,'Winner')}!")
                    c.execute("DELETE FROM giveaway WHERE chat_id=?",(chat,))
                c.commit();c.close()
        except:pass
        time.sleep(30)

HELP="""🌑 <b>Fun in Shadows</b>
/call [message] — tag members
/stop_calling — stop automatic calling
/health — activity health
/coin_ballance — balance
/quiz — quiz
/rost — roast
/game — random game
/rank — coin ranking
/participate — giveaway
/activity — group activity
/fight — quiz battle (2 coins)
 /help — help"""
@bot.message_handler(commands=["help"])
def helpcmd(m):
    if m.chat.type == "private":
        bot.send_message(m.chat.id, HELP)
    else:
        temp(m.chat.id, HELP)

@bot.message_handler(func=lambda m:m.chat.type=="private" and bool(m.text) and not m.text.startswith("/"))
def dm(m):bot.send_message(m.chat.id,random.choice(["😎 Bolo bro!","🌑 Fun in Shadows online hai.","😂 Kya scene hai?","👀 Main sun raha hoon."]))

def auto_coins():
    while True:
        time.sleep(AUTO_COIN_INTERVAL)
        try:
            c=db();ch=[x[0] for x in c.execute("SELECT DISTINCT chat_id FROM activity")];c.close()
            for chat in ch:
                r=members(chat)
                if r:addcoins(chat,random.choice(r)[0],1)
        except:pass

def set_commands():
    cmds=[("call","Tag group members"),("stop_calling","Stop calling"),("health","User health"),
    ("coin_ballance","Coin balance"),("quiz","Play quiz"),("rost","Funny roast"),("game","Random game"),
    ("rank","Coin ranking"),("participate","Giveaway entry"),("activity","Group activity"),
    ("fight","Quiz battle"),("help","Help")]
    x=[types.BotCommand(a,b) for a,b in cmds];bot.set_my_commands(x)
    try:bot.set_my_commands(x,scope=types.BotCommandScopeAllGroupChats())
    except:pass

@app.get("/")
def home():return "Fun in Shadows is running"

if __name__=="__main__":
    set_commands()
    try:
        user_client.start()
    except Exception as e:
        print("User session could not start:", e)
    threading.Thread(target=lambda:app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000"))),daemon=True).start()
    threading.Thread(target=auto_coins,daemon=True).start()
    threading.Thread(target=giveaway_worker,daemon=True).start()
    while True:
        try:bot.infinity_polling(timeout=30,long_polling_timeout=30,skip_pending=True)
        except:time.sleep(5)
