# 𓆩 Fun in Shadows 𓆪 — Render Ready

A Telegram group fun/admin/music bot with MongoDB, MTProto member scanning, music assistant, AI DM chat and voice replies.

## 25 commands

`/start` `/help` `/call` `/stop_calling` `/calladmins` `/health` `/coin_ballance` `/quiz` `/rost` `/game` `/rank` `/participate` `/activity` `/fight` `/accept` `/groupinfo` `/userinfo` `/music` `/play` `/pause` `/resume` `/skip` `/stop` `/queue` `/volume`

## Main features

- `/call` scans members through a normal Telegram user session and tags 2–5 per message.
- `/stop_calling` stops an active call.
- `/calladmins` tags human admins.
- `/health` is free: <=7 days = 5 hearts, <=21 days = 3, <=30 days = 1, older/unknown = 0.
- Rare random coin drops.
- `/quiz` has button answers and gives +2 coins only to the correct winner.
- `/game` has 3 button games; coins are awarded only after a real win.
- `/rank`, `/activity`, `/participate`, `/fight`, `/accept`, `/groupinfo`, `/userinfo`.
- `/userinfo` costs 2 coins; `/groupinfo` costs 1 coin.
- Group bot replies auto-delete after 10 minutes; `/call` tag messages after 24 hours.
- DMs support natural AI conversation.
- Voice notes are transcribed and answered with a voice reply when OpenAI + TTS are configured.
- `/music` in DM opens Music Vault; save MP3/audio and later find it by title/caption/keywords.
- `/play` can search YouTube or use saved songs.
- Music assistant is a normal Telegram user account and is auto-invited through a one-use invite link when `/play` needs it. The assistant does not need admin rights.
- `/pause`, `/resume`, `/skip`, `/stop`, `/queue`, `/volume`.
- Giveaway result is scheduled for 8 PM IST.

## Important MTProto note

`STRING_SESSION` must be a **normal Telegram user session**, not a bot-token session, because `/call` needs MTProto participant scanning. `MUSIC_SESSION` is the normal user session used for voice-chat music.

Keep both sessions private. Never paste them into chat or GitHub.

## Environment variables

Required:

- `BOT_TOKEN`
- `OWNER_ID=6298413188`
- `API_ID`
- `API_HASH`
- `STRING_SESSION`
- `MONGO_URI`

Required for music:

- `MUSIC_SESSION`

Optional AI:

- `OPENAI_API_KEY`
- `AI_MODEL` (default: `gpt-4o-mini`)

Defaults:

- `DELETE_AFTER=600`
- `CALL_DELETE_AFTER=86400`
- `CALL_MIN=2`
- `CALL_MAX=5`
- `CALL_DELAY=1.2`

## Render

Build command:

`apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt`

Start command:

`python bot.py`

The app exposes `/health` on Render's `$PORT` so a free Web Service can be kept awake with an external HTTP monitor.

## Session generation

- `session_gen.py` creates the normal user `STRING_SESSION`.
- `music_session_gen.py` creates the normal user `MUSIC_SESSION`.

Run these locally/Termux and store the resulting values only in Render Environment Variables.
