from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("API ID: ").strip())
api_hash = input("API HASH: ").strip()
phone = input("Music assistant Telegram phone (+countrycode...): ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    client.start(phone=phone)
    print("\nMUSIC_SESSION (put this in Render Environment Variables):\n")
    print(client.session.save())
    print("\nNever paste this session publicly.\n")
