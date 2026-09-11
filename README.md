# Fun in Shadows — Render Build

This build intentionally excludes music and AI/chat features.

## Commands
- `/start` — basic introduction
- `/help` — help and feature summary
- `/call [message]` — tag members in random 2–5 batches
- `/stop_calling` — stop an active call
- `/calladmins` — tag group admins
- `/health` — activity health
- `/coin_ballance` — check coin balance
- `/give_coin <amount>` — reply to a user and transfer coins
- `/quiz` — button quiz; winner gets coins
- `/rost` — funny roast
- `/game` — one of three games
- `/rank [daily|weekly|monthly]` — rankings and rank thresholds
- `/participate` — enter the daily giveaway
- `/activity` — last-24h activity
- `/fight` — 2-coin quiz battle
- `/accept` — accept a quiz battle
- `/groupinfo` — group info (1 coin)
- `/userinfo` — user info (2 coins)

## Rank system
Ranks are permanent once archived and rewards are granted once per rank:

| Rank | Coins required | Reward |
|---|---:|---:|
| E | 0 | 0 |
| F | 50 | 10 |
| D | 150 | 25 |
| B | 300 | 50 |
| A | 600 | 100 |
| S | 1,000 | 199 + group admin promotion |

S Rank promotion requires the bot to have Telegram permission to promote members. If Telegram refuses the promotion, the 199-coin reward is still granted and the bot explains what permission is missing.

## Render environment
Required: `BOT_TOKEN`, `OWNER_ID`, `API_ID`, `API_HASH`, `STRING_SESSION`, `MONGO_URI`.

`STRING_SESSION` is a normal Telegram user session used for participant scanning. Keep it private.
