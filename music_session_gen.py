from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("API ID: ").strip())
api_hash = input("API HASH: ").strip()
phone = input("Music assistant phone (+countrycode...): ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    client.start(phone=phone)
    print("\nMUSIC_SESSION (normal user account):\n")
    print(client.session.save())
    print("\nKeep this session private. Put it only in Render Environment Variables.\n")
