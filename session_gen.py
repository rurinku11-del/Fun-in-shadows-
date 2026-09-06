import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(os.environ["API_ID"])
api_hash = os.environ["API_HASH"]
bot_token = os.environ["BOT_TOKEN"]

with TelegramClient(StringSession(), api_id, api_hash) as client:
    client.start(bot_token=bot_token)
    print("\nSTRING_SESSION=\n")
    print(client.session.save())
