# Fun in Shadows — all-in-one

## Commands
- Tag: `/call`, `/stop_calling`, `/calladmins`
- Fun: `/quiz`, `/rost`, `/game`, `/fight`, `/accept`
- Coins: `/coin_ballance`, `/rank`
- Group: `/health` (1 coin), `/activity`, `/groupinfo` (1 coin), `/userinfo` (2 coins)
- Music: `/play`, `/pause`, `/resume`, `/skip`, `/stop`, `/queue`, `/volume`
- DM Music Vault: `/music` → Save MP3 button → send MP3/audio
- Giveaway: `/participate` — result around 8 PM IST
- Support: `@shadow_atomic_21`

## Deletion
- `/call` tag messages: 24 hours
- Other bot messages in groups: 10 minutes
- DMs are not auto-deleted

## Music
- `/play` accepts YouTube URLs or song names/lyrics/search lines.
- Saved MP3s can be matched by title/keywords and played in groups.
- Now-playing announcement can include the song thumbnail, title, duration and requester.
- Voice-chat music requires a normal Telegram user account in `MUSIC_SESSION`; a bot token alone cannot join a voice chat.

## Chat / voice replies
- DMs have normal chat replies.
- Voice notes receive a short voice reply when the optional TTS engine is available; otherwise the bot falls back to text.

## Environment variables
Required:
- `BOT_TOKEN`
- `OWNER_ID=6298413188`
- `API_ID`
- `API_HASH`
- `STRING_SESSION`
- `MONGO_URI`
- `MUSIC_SESSION` for music

Render defaults:
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

Keep all secrets in Render Environment Variables. Do not paste tokens or sessions into chat.
