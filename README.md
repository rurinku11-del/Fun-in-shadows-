# Fun in Shadows v2

## Included
- `/call` participant scan + clickable mentions in batches of 2–5
- `/stop_calling`
- `/calladmins`
- `/health` with 5/3/1/0 heart activity status
- rare random coin drops
- `/coin_ballance`
- `/quiz`
- `/rost`
- `/game` (3 random games, low rewards)
- `/rank`, `/rank daily`, `/rank weekly`, `/rank monthly`
- `/participate` with 8 PM IST daily giveaway result
- `/activity`
- `/fight` with 2-coin entry and quiz battle
- `/groupinfo`
- `/help @shadow_atomic_21`
- automatic deletion of bot group messages after 5 minutes
- normal DM replies
- MongoDB persistent per-group data
- MTProto participant scanning
- Render Background Worker configuration

## Render variables
Required:
BOT_TOKEN
OWNER_ID=6298413188
API_ID
API_HASH
STRING_SESSION
MONGO_URI

Optional:
DELETE_AFTER=300
CALL_MIN=2
CALL_MAX=5
CALL_DELAY=1.2

## Run locally to generate bot StringSession
pip install -r requirements.txt
export API_ID="..."
export API_HASH="..."
export BOT_TOKEN="..."
python session_gen.py

Copy the generated STRING_SESSION to Render. Do not use a personal account session.

## Render
Build:
pip install -r requirements.txt

Start:
python bot.py

The bot must be added to each target group and have appropriate admin permissions.
Telegram can still restrict participant enumeration depending on chat type,
permissions, privacy, or API-side limits.
