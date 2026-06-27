import asyncio
import random
import os
import sqlite3
import time
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from pyrogram import Client, filters
from pyrogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

load_dotenv()

BOT_TOKEN = "8905827145:AAGvHRVEm1GmwBfQZmMxn21oalBv8N5LxNQ"
API_ID = 30474990
API_HASH = "1cceb577c34cb2dead21658545959aad"
GROUP_LINK = "https://t.me/avto_abbu_duel/2"
MESSAGE = os.getenv("MESSAGE", "дуэльку")
MIN_INTERVAL = int(os.getenv("MIN_INTERVAL", 630))
MAX_INTERVAL = int(os.getenv("MAX_INTERVAL", 690))

DB_PATH = "accounts.db"
ACCOUNTS_DIR = "sessions"

os.makedirs(ACCOUNTS_DIR, exist_ok=True)

running_workers = {}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS accounts 
                 (phone TEXT PRIMARY KEY, session_name TEXT, active INTEGER DEFAULT 1)''')
    conn.commit()
    conn.close()

def get_active_sessions():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT phone, session_name FROM accounts WHERE active=1")
    return c.fetchall()

def get_all_accounts():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT phone, session_name, active FROM accounts")
    rows = c.fetchall()
    conn.close()
    return rows

def set_account_active(phone, active: int):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE accounts SET active=? WHERE phone=?", (active, phone))
    conn.commit()
    conn.close()

def get_session_by_phone(phone):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT session_name FROM accounts WHERE phone=?", (phone,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Акаунт илова кардан")],
        [KeyboardButton("📋 Рӯйхати акаунтҳо"), KeyboardButton("📊 Статус")],
        [KeyboardButton("🛑 Стоп")]
    ], resize_keyboard=True)

async def send_duel_and_click(session_name, phone):
    client = TelegramClient(session_name, API_ID, API_HASH)
    try:
        await client.connect()
        entity = await client.get_entity(GROUP_LINK)
        
        sent = await client.send_message(entity, MESSAGE)
        print(f"📤 Дуэль фиристода шуд | {phone}")

        await asyncio.sleep(2.5)

        async for msg in client.iter_messages(entity, limit=5):
            if msg.buttons:
                for row in msg.buttons:
                    for button in row:
                        if button.text and ("Атаковать" in button.text or "атаковать" in button.text.lower()):
                            await msg.click(button)
                            print(f"🎯 Атаковать пахш шуд | {phone}")
                            return
        print(f"⚠️ Тугмаи Атаковать ёфт нашуд | {phone}")

    except FloodWaitError as e:
        print(f"⏳ Flood wait: {e.seconds}с | {phone}")
        await asyncio.sleep(e.seconds + 5)
    except Exception as e:
        print(f"❌ Хато {phone}: {e}")
    finally:
        await client.disconnect()

async def account_worker(session_name, phone):
    print(f"🚀 Worker оғоз: {phone}")
    try:
        while True:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT active FROM accounts WHERE phone=?", (phone,))
            row = c.fetchone()
            conn.close()
            if not row or row[0] != 1:
                print(f"🛑 Worker хомуш карда шуд: {phone}")
                break

            await send_duel_and_click(session_name, phone)
            delay = random.randint(MIN_INTERVAL, MAX_INTERVAL)
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        print(f"🛑 Worker бекор карда шуд: {phone}")
        raise
    finally:
        running_workers.pop(phone, None)

def start_worker(session_name, phone):
    if phone in running_workers and not running_workers[phone].done():
        return
    task = asyncio.create_task(account_worker(session_name, phone))
    running_workers[phone] = task

def stop_worker(phone):
    task = running_workers.get(phone)
    if task and not task.done():
        task.cancel()

app = Client("duel_bot", bot_token=BOT_TOKEN)

@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    await message.reply("**🤖 Auto Duel + Auto Атаковать** тайёр аст!", reply_markup=main_keyboard())

@app.on_message(filters.regex("➕ Акаунт илова кардан") & filters.private)
async def add_start(client, message: Message):
    await message.reply("📱 Phone number бо + фиристед:")

def account_status_emoji(active: int) -> str:
    return "🟢 Фаъол" if active == 1 else "🔴 Хомуш"

def accounts_inline_keyboard():
    accounts = get_all_accounts()
    rows = []
    for phone, session_name, active in accounts:
        label = f"{phone} | {account_status_emoji(active)}"
        rows.append([InlineKeyboardButton(label, callback_data=f"toggle:{phone}")])
    return InlineKeyboardMarkup(rows) if rows else None

@app.on_message(filters.regex("📋 Рӯйхати акаунтҳо") & filters.private)
async def list_accounts(client, message: Message):
    accounts = get_all_accounts()
    if not accounts:
        await message.reply("📋 Ҳоло ягон акаунт илова накардаед.")
        return
    kb = accounts_inline_keyboard()
    await message.reply(
        "📋 **Рӯйхати акаунтҳо**\n\nБарои хомуш/гирён кардани акаунт, тугмаро пахш кунед:",
        reply_markup=kb
    )

@app.on_message(filters.regex("📊 Статус") & filters.private)
async def status_accounts(client, message: Message):
    accounts = get_all_accounts()
    total = len(accounts)
    active_count = sum(1 for _, _, a in accounts if a == 1)
    inactive_count = total - active_count
    running = len([t for t in running_workers.values() if not t.done()])
    await message.reply(
        f"📊 **Статус**\n\n"
        f"Ҳамагӣ акаунтҳо: {total}\n"
        f"🟢 Фаъол: {active_count}\n"
        f"🔴 Хомуш: {inactive_count}\n"
        f"⚙️ Worker-ҳои кор карда истода: {running}"
    )

@app.on_callback_query(filters.regex(r"^toggle:"))
async def toggle_account(client, callback_query: CallbackQuery):
    phone = callback_query.data.split("toggle:", 1)[1]
    session_name = get_session_by_phone(phone)
    if not session_name:
        await callback_query.answer("❌ Акаунт ёфт нашуд", show_alert=True)
        return

    accounts = dict((p, a) for p, s, a in get_all_accounts())
    current_active = accounts.get(phone, 0)
    new_active = 0 if current_active == 1 else 1
    set_account_active(phone, new_active)

    if new_active == 1:
        start_worker(session_name, phone)
        await callback_query.answer(f"🟢 {phone} гирён карда шуд")
    else:
        stop_worker(phone)
        await callback_query.answer(f"🔴 {phone} хомуш карда шуд")

    kb = accounts_inline_keyboard()
    try:
        await callback_query.edit_message_reply_markup(reply_markup=kb)
    except Exception:
        pass

@app.on_message(filters.private & filters.text)
async def handle_messages(client, message: Message):
    text = message.text.strip()
    if text.startswith("+"):
        phone = text

        existing_session = get_session_by_phone(phone)
        if existing_session:
            accounts = dict((p, a) for p, s, a in get_all_accounts())
            if accounts.get(phone) == 1 and phone in running_workers and not running_workers[phone].done():
                await message.reply(
                    f"ℹ️ Акаунти {phone} аллакай илова ва фаъол аст.",
                    reply_markup=main_keyboard()
                )
            else:
                set_account_active(phone, 1)
                start_worker(existing_session, phone)
                await message.reply(
                    f"✅ Акаунти {phone} аллакай вуҷуд дошт — гирён карда шуд.",
                    reply_markup=main_keyboard()
                )
            return

        session_name = f"{ACCOUNTS_DIR}/{phone.replace('+', '').replace(' ', '')}"
        tg = TelegramClient(session_name, API_ID, API_HASH)

        try:
            await tg.connect()
            if not await tg.is_user_authorized():
                await tg.send_code_request(phone)
                await message.reply("🔢 Кодро фиристед:")

                async with client.conversation(message.chat.id) as conv:
                    code_msg = await conv.get_response(timeout=180)
                    code = code_msg.text.strip()

                try:
                    await tg.sign_in(phone, code)
                except SessionPasswordNeededError:
                    await message.reply("🔐 Акаунт бо паролии 2FA ҳифз шудааст. Парол фиристед:")
                    async with client.conversation(message.chat.id) as conv:
                        pwd_msg = await conv.get_response(timeout=180)
                        password = pwd_msg.text.strip()
                    await tg.sign_in(password=password)

                init_db()
                conn = sqlite3.connect(DB_PATH)
                conn.execute("INSERT OR REPLACE INTO accounts VALUES (?, ?, 1)", (phone, session_name))
                conn.commit()
                conn.close()

                await message.reply("✅ Акаунт илова, ворид ва запуск шуд!", reply_markup=main_keyboard())
                start_worker(session_name, phone)
        except Exception as e:
            await message.reply(f"❌ Хато: {e}")
        finally:
            await tg.disconnect()

async def main():
    init_db()
    print("🤖 Auto Duel Bot + Auto Click оғоз шуд...")

    sessions = get_active_sessions()
    for phone, session in sessions:
        start_worker(session, phone)

    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
